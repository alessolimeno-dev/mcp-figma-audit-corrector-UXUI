# CLAUDE.md — Riferimenti Operativi per Claude Code

Le definizioni complete delle skill risiedono nella cartella comune `skills/`.

## Riferimenti alle Skill Comuni
- **Fase 1 (Audit):** `skills/agente-audit/SKILL.md`
- **Fase 2 (Correzione):** `skills/agente-correzione/SKILL.md`
- **Risorse Comuni:** `skills/common/` (`references/wcag.json` e librerie in `lib/`)

## Comandi Slash
- `/audit [link-figma]`: attiva il flusso definito in `skills/agente-audit/SKILL.md`.
- `/audit [link-figma] [file-excel]`: con anche il report Excel esegue la **verifica post-correzione** (sezione 7 di `skills/agente-audit/SKILL.md`): sola lettura, scrive una copia `…-verifica.xlsx` con il foglio `Verifica` e il blocco «A correzione effettuata» nel `Riepilogo`.
- `/correzione [link-figma] [file-excel]`: attiva il flusso definito in `skills/agente-correzione/SKILL.md`.

## Principi Guida Sintetici
1. **Fonte Unica:** consulta direttamente i file `SKILL.md` in `skills/` per ogni dettaglio su logica, vincoli e script.
2. **0 Token AI:** delega calcoli e manipolazione Excel esclusivamente agli script deterministici indicati nelle skill.
3. **Human-in-the-Loop:** nessuna modifica su Figma senza approvazione esplicita nel file Excel.
4. **Interprete Python (.venv):** esegui sempre gli script Python usando l'ambiente virtuale locale (`./.venv/bin/python`).
5. **Cartella di output:** ogni report Excel va in `<nome file Figma>/` (creata da `checker.py`).
6. **Copia locale:** prima della correzione suggerisci di salvare una copia locale del file Figma (consiglio, non bloccante).
7. **Strumenti Figma:** solo gli elenchi chiusi delle skill; l'hook `skills/common/lib/figma_guard.py` blocca gli altri durante `/audit` e `/correzione`.
8. **Regole universali:** nessuna regola, ID, nome o eccezione di un singolo file Figma nelle skill, negli script o nei moduli comuni.
9. **Nodi:** una voce di `Voci` è un errore comune con più nodi (colonna D); il foglio `Nodi` ha una riga per coppia nodo-errore. `Da correggere` = Decisione `Accolta`/`Modificata` **e** Chi applica `Agente`/`Entrambi` (regola in `skills/common/lib/nodi_utils.py`).
10. **Annotazioni:** il suggerimento della colonna P è un testo guida; non si compila mai il codice (i segnaposto `[...]` restano). Scrivi con `labelMarkdown`, mai con `label` (Figma converte `<`, `>` e `"` in entità HTML); verifica rileggendo `labelMarkdown` senza decodificare entità e ignora `label`. Dettagli in `skills/agente-correzione/SKILL.md`.
11. **Verifica post-correzione:** `/audit` con un Excel non rifà l'audit. Si rileggono le voci `Accolta`/`Modificata` (anche se le applica il Progettista), non quelle `Rifiutate`; Claude scrive solo `misure-post.json` (e `nuove.json` per errori nuovi, ID `N-xx`), il resto lo fa `checker.py --verifica` a 0 token. Il report di partenza e il `Log Correzioni` non si modificano.
