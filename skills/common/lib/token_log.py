#!/usr/bin/env python3
"""
token_log.py — Registro deterministico dei token reali (0 token AI).

Pensato per essere lanciato da un hook di Claude Code (`Stop` e `SubagentStop`).
Legge il transcript della sessione (.jsonl) e aggiunge a `logs/token_usage.jsonl`
una riga per ogni chiamata API del modello, con i valori letti dal campo `usage`
(mai stimati):

    timestamp, session_id, message_id, model, skill,
    input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens,
    tools, mcp, subagent

Regole:
- una riga = un `message.id` (i messaggi spezzati in più blocchi vengono deduplicati);
- idempotente: gli `message.id` già presenti nel log non vengono riscritti,
  quindi un hook perso o doppio non altera i totali;
- `skill` = ultima skill vista fino a quel messaggio (tag `<command-name>` nel
  messaggio utente oppure tool `Skill`); resta valida finché non ne compare un'altra;
- `mcp` = solo i tool `mcp__<server>__<tool>`; `tools` = tutti i tool chiamati;
- il costo di una singola chiamata MCP NON è un campo diretto: il risultato rientra
  come input del turno successivo. Qui si registra il `usage` esatto del turno.

Uso da hook (JSON su stdin):   token_log.py
Uso manuale / backfill:        token_log.py --transcript <file.jsonl> [--session-id ID]
Percorso log personalizzato:   --log <file.jsonl>   (default: <ROOT>/logs/token_usage.jsonl)

Esce sempre con codice 0: un errore del registro non deve mai bloccare la sessione.
Gli errori vengono scritti in `logs/token_log.err`.
"""

import argparse
import json
import os
import re
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

try:
    import fcntl  # POSIX: lock sul file di log
except ImportError:  # pragma: no cover (Windows)
    fcntl = None

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
DEFAULT_LOG = os.path.join(ROOT, "logs", "token_usage.jsonl")

COMMAND_RE = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")


def _iter_records(transcript_path: str) -> Iterable[Dict[str, Any]]:
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue  # riga parziale in scrittura: verrà letta alla prossima esecuzione


def _user_command(record: Dict[str, Any]) -> Optional[str]:
    """Nome della skill/slash command lanciata dall'utente in questo messaggio (se presente)."""
    content = (record.get("message") or {}).get("content")
    if isinstance(content, list):
        content = " ".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
    if not isinstance(content, str):
        return None
    m = COMMAND_RE.search(content)
    return m.group(1) if m else None


def extract_rows(transcript_path: str, session_id: Optional[str] = None, subagent: Optional[str] = None) -> List[Dict[str, Any]]:
    """Ricostruisce dal transcript una riga per ogni message.id completato."""
    current_skill: Optional[str] = None
    order: List[str] = []
    rows: Dict[str, Dict[str, Any]] = {}

    for rec in _iter_records(transcript_path):
        rtype = rec.get("type")

        if rtype == "user":
            cmd = _user_command(rec)
            if cmd:
                current_skill = cmd
            continue

        if rtype != "assistant":
            continue
        msg = rec.get("message") or {}
        mid = msg.get("id")
        usage = msg.get("usage")
        if not mid or not isinstance(usage, dict) or msg.get("model") in (None, "<synthetic>"):
            continue

        blocks = [b for b in (msg.get("content") or []) if isinstance(b, dict)]
        tools = [b.get("name", "") for b in blocks if b.get("type") == "tool_use"]
        for b in blocks:
            if b.get("type") == "tool_use" and b.get("name") == "Skill":
                skill = (b.get("input") or {}).get("skill")
                if skill:
                    current_skill = str(skill).lstrip("/")

        row = rows.get(mid)
        if row is None:
            row = {
                "timestamp": rec.get("timestamp"),
                "session_id": session_id or rec.get("sessionId"),
                "message_id": mid,
                "model": msg.get("model"),
                "skill": current_skill,
                "input_tokens": 0,
                "output_tokens": 0,
                "cache_creation_input_tokens": 0,
                "cache_read_input_tokens": 0,
                "tools": [],
                "mcp": [],
                "subagent": subagent or (True if rec.get("isSidechain") else None),
                "_final": False,
            }
            rows[mid] = row
            order.append(mid)

        # Lo stesso messaggio compare in più righe (un blocco ciascuna): usage identico o
        # in crescita durante lo streaming -> si tiene il massimo, mai la somma.
        for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"):
            row[key] = max(row[key], int(usage.get(key) or 0))
        for t in tools:
            if t not in row["tools"]:
                row["tools"].append(t)
            if t.startswith("mcp__") and t not in row["mcp"]:
                row["mcp"].append(t)
        if row["skill"] is None and current_skill:
            row["skill"] = current_skill
        if msg.get("stop_reason"):
            row["_final"] = True

    out = []
    for mid in order:
        row = rows[mid]
        if not row.pop("_final"):
            continue  # messaggio ancora in streaming: sarà registrato alla prossima esecuzione
        out.append(row)
    return out


def _known_ids(log_path: str) -> Set[str]:
    ids: Set[str] = set()
    if not os.path.exists(log_path):
        return ids
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                ids.add(json.loads(line).get("message_id"))
            except (json.JSONDecodeError, AttributeError):
                continue
    return ids


def append_new_rows(rows: List[Dict[str, Any]], log_path: str) -> int:
    """Aggiunge al log solo le righe con message_id non ancora presenti. Ritorna quante ne scrive."""
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a+", encoding="utf-8") as f:
        if fcntl:
            fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            known: Set[str] = set()
            for line in f:
                try:
                    known.add(json.loads(line).get("message_id"))
                except (json.JSONDecodeError, AttributeError):
                    continue
            new = [r for r in rows if r["message_id"] not in known]
            if new:
                f.seek(0, os.SEEK_END)
                f.write("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in new))
                f.flush()
            return len(new)
        finally:
            if fcntl:
                fcntl.flock(f, fcntl.LOCK_UN)


def _log_error(log_path: str) -> None:
    try:
        err = os.path.join(os.path.dirname(log_path), "token_log.err")
        os.makedirs(os.path.dirname(err), exist_ok=True)
        with open(err, "a", encoding="utf-8") as f:
            f.write(f"--- {datetime.now().isoformat(timespec='seconds')}\n{traceback.format_exc()}\n")
    except Exception:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Registra nel log i token reali letti dal transcript di Claude Code")
    parser.add_argument("--transcript", help="Transcript .jsonl (se omesso, legge il JSON dell'hook da stdin)")
    parser.add_argument("--session-id", help="ID sessione (default: quello scritto nel transcript)")
    parser.add_argument("--log", default=DEFAULT_LOG, help="File di log JSONL (default: logs/token_usage.jsonl)")
    args = parser.parse_args()

    try:
        jobs = []  # (transcript_path, session_id, subagent)
        if args.transcript:
            jobs.append((args.transcript, args.session_id, None))
        else:
            payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
            sid = payload.get("session_id")
            if payload.get("transcript_path"):
                jobs.append((payload["transcript_path"], sid, None))
            if payload.get("agent_transcript_path"):
                jobs.append((payload["agent_transcript_path"], sid, payload.get("agent_id") or payload.get("agent_type") or "subagent"))

        total = 0
        for path, sid, sub in jobs:
            if path and os.path.exists(path):
                total += append_new_rows(extract_rows(path, sid, sub), args.log)
        if args.transcript:
            print(f"Righe aggiunte a {args.log}: {total}")
    except Exception:
        _log_error(args.log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
