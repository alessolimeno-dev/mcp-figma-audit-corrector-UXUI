# Directory Skills (Definizioni Canoniche Condivise)

Questa cartella è la **singola fonte di verità** per le skill del repository, condivisa sia da **Claude Code** che da **Antigravity**.

---

## Struttura

- **`agente-audit/`**:
  - `SKILL.md`: definizione completa e vincoli per l'analisi euristica e normativa (`READ-ONLY`).
  - `scripts/checker.py`: motore deterministico Python a 0 token AI per calcoli di contrasto, target size e generazione report Excel.
- **`agente-correzione/`**:
  - `SKILL.md`: definizione completa e vincoli per la correzione mirata su Figma (`WRITE-BOUNDED`).
  - `scripts/corrector.py`: motore deterministico Python a 0 token AI per estrazione decisioni approvate, calcolo HLS/padding e compilazione log.
- **`common/`**:
  - `references/wcag.json`: dataset unico W3C WCAG 2.2 + 10 Euristiche di Nielsen.
  - `lib/`: moduli Python condivisi (`color_utils.py`, `normative.py`, `excel_utils.py`).

---

## Modalità di Riferimento nei Client AI

I file di configurazione specifici di ciascun assistente contengono esclusivamente puntatori sintetici a questi file:
- **Claude Code**: `.claude/commands/audit.md` e `.claude/commands/correttore.md` puntano rispettivamente a `skills/agente-audit/SKILL.md` e `skills/agente-correzione/SKILL.md`.
- **Antigravity**: `.agents/skills.json` registra il percorso della cartella comune `skills/` e `.agents/rules/audit-corrector.md` instrada le richieste referenziando gli stessi file.
