# Cartella skills

Questa cartella è la **singola fonte di verità** per le skill del repository, usate da **Claude Code**.

---

## Struttura

- **`agente-audit/`**
  - `SKILL.md`: regole e vincoli per l'analisi euristica e normativa (`READ-ONLY`), con l'elenco chiuso degli strumenti Figma.
  - `scripts/checker.py`: motore deterministico Python per contrasto, target size, raggruppamento degli errori comuni (una voce con più nodi) e generazione del report Excel (fogli `Voci` e `Nodi`).
- **`agente-correzione/`**
  - `SKILL.md`: regole e vincoli per la correzione mirata su Figma (`WRITE-BOUNDED`), con l'elenco chiuso degli strumenti Figma.
  - `scripts/corrector.py`: motore deterministico Python per estrazione delle voci da correggere con tutti i loro nodi, calcolo HLS/padding e Log Correzioni (una riga per ID errore).
- **`common/`**
  - `references/wcag.json`: dataset W3C WCAG 2.2 + 10 Euristiche di Nielsen.
  - `lib/`: moduli Python condivisi (`color_utils.py`, `wcag_checks.py`, `normative.py`, `excel_utils.py`, `nodi_utils.py` con nodi di una voce e regola "Da correggere") e script degli hook (`figma_guard.py`, `token_log.py`).

---

## Collegamento con Claude Code

- `.claude/commands/audit.md` e `.claude/commands/correzione.md` puntano rispettivamente a `agente-audit/SKILL.md` e `agente-correzione/SKILL.md`.
- `.claude/settings.json` registra gli hook:
  - `figma_guard.py` (PreToolUse): blocca gli strumenti Figma non consentiti dalla skill attiva;
  - `token_log.py` (Stop / SubagentStop): registra i token reali di ogni chiamata in `logs/token_usage.jsonl`.
- Figma è raggiungibile solo tramite il connettore Figma attivo sull'account Claude (vedi il README principale).
