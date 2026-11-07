# CLAUDE.md — Riferimenti Operativi per Claude Code

Le definizioni complete delle skill risiedono nella cartella comune `skills/`.

## Riferimenti alle Skill Comuni
- **Fase 1 (Audit):** `skills/agente-audit/SKILL.md`
- **Fase 2 (Correzione):** `skills/agente-correzione/SKILL.md`
- **Risorse Comuni:** `skills/common/` (`references/wcag.json` e librerie in `lib/`)

## Comandi Slash
- `/audit [link-figma]`: attiva il flusso definito in `skills/agente-audit/SKILL.md`.
- `/correttore [link-figma] [file-excel]`: attiva il flusso definito in `skills/agente-correzione/SKILL.md`.

## Principi Guida Sintetici
1. **Fonte Unica:** consulta direttamente i file `SKILL.md` in `skills/` per ogni dettaglio su logica, vincoli e script.
2. **0 Token AI:** delega calcoli e manipolazione Excel esclusivamente agli script deterministici indicati nelle skill.
3. **Human-in-the-Loop:** nessuna modifica su Figma senza approvazione esplicita nel file Excel.
4. **Interprete Python (.venv):** esegui sempre gli script Python usando l'ambiente virtuale locale (`./.venv/bin/python`).
