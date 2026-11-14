#!/usr/bin/env python3
"""
figma_guard.py — Hook PreToolUse di Claude Code che limita gli strumenti Figma per skill (0 token AI).

Le skill indicano quali strumenti usare, ma sono solo istruzioni: questo hook le fa rispettare.
Legge dalla conversazione quale comando è attivo (l'ultimo `/audit` o `/correzione`
lanciato dall'utente, oppure il tool `Skill`) e decide se la chiamata MCP a Figma può partire.

- `/audit` (READ-ONLY): consentiti solo gli strumenti di lettura in AUDIT_ALLOWED.
- `/correzione` (WRITE-BOUNDED): gli stessi più `use_figma`.
- Nessuno dei due comandi attivo: nessun limite.

Uno strumento è considerato "di Figma" se il nome del server contiene "figma" oppure se il nome
dello strumento è tra quelli noti del server MCP ufficiale di Figma (il connettore di claude.ai
ha come nome server un identificativo, non "figma").

Esce sempre con codice 0. Per bloccare risponde con `permissionDecision: deny`.
Se qualcosa va storto non blocca e scrive l'errore in `logs/figma_guard.err`.
"""

import json
import os
import re
import sys
import traceback
from datetime import datetime
from typing import Any, Dict, Optional

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
ERR_LOG = os.path.join(ROOT, "logs", "figma_guard.err")

# Strumenti di sola lettura consentiti durante l'audit (elenco chiuso, vedi agente-audit/SKILL.md)
AUDIT_ALLOWED = {
    "create_session",
    "get_metadata",
    "get_design_context",
    "get_variable_defs",
    "get_screenshot",
}
# Durante la correzione si aggiunge solo use_figma (vedi agente-correzione/SKILL.md)
CORRECTION_ALLOWED = AUDIT_ALLOWED | {"use_figma"}

POLICIES = {
    "audit": ("/audit (sola lettura)", AUDIT_ALLOWED),
    "correzione": ("/correzione", CORRECTION_ALLOWED),
    "agente-audit": ("/audit (sola lettura)", AUDIT_ALLOWED),
    "agente-correzione": ("/correzione", CORRECTION_ALLOWED),
}

# Strumenti noti del server MCP ufficiale di Figma (per riconoscerlo anche se il server non si chiama "figma")
KNOWN_FIGMA_TOOLS = CORRECTION_ALLOWED | {
    "add_code_connect_map", "create_generative_plugin", "create_new_file", "create_shader",
    "download_assets", "export_video", "generate_diagram", "generate_figma_design", "generate_image",
    "generate_vector_illustration", "get_code_connect_map", "get_code_connect_suggestions", "get_comments",
    "get_context_for_code_connect", "get_figjam", "get_figma_skill", "get_generative_plugin",
    "get_libraries", "get_motion_context", "get_shader", "html_to_figma", "list_file_shaders",
    "list_generative_plugins", "list_shaders", "search_design_system", "send_code_connect_mappings",
    "send_code_to_figma", "update_generative_plugin", "update_shader", "upload_assets", "whoami",
    "weave_cancel_tool_run", "weave_find_model", "weave_get_model_run_output", "weave_get_tool_inputs",
    "weave_get_tool_run_output", "weave_list_tools", "weave_run_model", "weave_run_tool", "weave_upload_asset",
}

COMMAND_RE = re.compile(r"<command-name>\s*/?([^<\s]+)\s*</command-name>")


def split_mcp_name(tool_name: str):
    """'mcp__<server>__<tool>' -> (server, tool). Altrimenti (None, None)."""
    if not tool_name.startswith("mcp__"):
        return None, None
    rest = tool_name[len("mcp__"):]
    if "__" not in rest:
        return None, None
    server, tool = rest.split("__", 1)
    return server, tool


def is_figma_tool(server: str, tool: str) -> bool:
    return "figma" in server.lower() or tool in KNOWN_FIGMA_TOOLS


def _normalize(name: str) -> str:
    name = name.strip().lstrip("/")
    return name.split(":")[-1]  # eventuale prefisso plugin/cartella (es. 'x:audit')


def active_command(transcript_path: str) -> Optional[str]:
    """Ultimo comando o skill del flusso Figma lanciato nella conversazione."""
    last = None
    with open(transcript_path, "r", encoding="utf-8") as f:
        for line in f:
            # filtro veloce: si analizzano solo le righe che possono contenere un comando o una skill
            if "command-name" not in line and '"Skill"' not in line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = rec.get("message") or {}
            content = msg.get("content")
            if rec.get("type") == "user":
                if isinstance(content, list):
                    content = " ".join(
                        b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"
                    )
                if isinstance(content, str):
                    for m in COMMAND_RE.finditer(content):
                        last = _normalize(m.group(1))
            elif rec.get("type") == "assistant" and isinstance(content, list):
                for b in content:
                    if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Skill":
                        skill = (b.get("input") or {}).get("skill")
                        if skill:
                            last = _normalize(str(skill))
    return last


def decide(payload: Dict[str, Any]) -> Optional[str]:
    """Ritorna il motivo del blocco, oppure None se la chiamata è consentita."""
    server, tool = split_mcp_name(str(payload.get("tool_name", "")))
    if not server or not is_figma_tool(server, tool):
        return None
    transcript = payload.get("transcript_path")
    if not transcript or not os.path.exists(transcript):
        return None
    cmd = active_command(transcript)
    if cmd not in POLICIES:
        return None
    label, allowed = POLICIES[cmd]
    if tool in allowed:
        return None
    return (
        f"Bloccato da figma_guard: durante {label} lo strumento Figma '{tool}' non è consentito. "
        f"Strumenti consentiti: {', '.join(sorted(allowed))}. "
        "Usa uno di questi oppure chiedi all'utente di cambiare l'elenco in skills/common/lib/figma_guard.py."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin) if not sys.stdin.isatty() else {}
        reason = decide(payload)
        if reason:
            print(json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }, ensure_ascii=False))
    except Exception:
        try:
            os.makedirs(os.path.dirname(ERR_LOG), exist_ok=True)
            with open(ERR_LOG, "a", encoding="utf-8") as f:
                f.write(f"--- {datetime.now().isoformat(timespec='seconds')}\n{traceback.format_exc()}\n")
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
