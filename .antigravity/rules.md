# Regole Workspace per Antigravity

Le definizioni canoniche delle skill e le loro istruzioni risiedono unicamente in `skills/`:
- **Audit UI/UX:** `skills/agente-audit/SKILL.md` (read-only, script `checker.py`)
- **Correzione UI/UX:** `skills/agente-correzione/SKILL.md` (write-bounded, script `corrector.py`)
- **Risorse condivise:** `skills/common/` (`references/wcag.json`, moduli `lib/`)

Non duplicare istruzioni operative in questa cartella: consulta direttamente i file `SKILL.md` corrispondenti.
