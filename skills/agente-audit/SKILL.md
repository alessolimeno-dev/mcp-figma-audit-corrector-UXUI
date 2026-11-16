---
name: agente-audit
description: Esegue l'audit euristico (10 Euristiche di Nielsen) e normativo (W3C WCAG 2.2) in sola lettura (READ-ONLY) su prototipi Figma ed esporta il report Excel strutturato.
---

# Skill: Agente di Audit UI/UX (Fase 1)

Definizione canonica per **Claude Code**. Figma si raggiunge solo tramite il connettore Figma attivo sull'account Claude.

---

## 1. Ambiente di Esecuzione (VENV Locale)

- **Cartella del progetto (`<ROOT>`):** la cartella che contiene `skills/`, `.venv/` e `Audit_modello.xlsx`.
  - Se la sessione è aperta dentro il progetto: `<ROOT>` = `.`
  - Se la sessione è aperta nella cartella superiore (es. `Analisi-skills/`): `<ROOT>` = `mcp-figma-audit-corrector-UXUI`
- **Interprete Python Obbligatorio:** tutte le chiamate agli script devono usare il python locale del progetto:
  - macOS/Linux: `<ROOT>/.venv/bin/python`
  - Windows: `<ROOT>\.venv\Scripts\python.exe`
- Non utilizzare l'interprete Python globale di sistema.

---

## 2. Integrazione con i Moduli Comuni (`skills/common/`)

L'agente delega i calcoli e le definizioni ai moduli condivisi della cartella `skills/common/`:
- **`skills/common/references/wcag.json`:** dizionario unico con 86 criteri W3C WCAG 2.2 e 10 Euristiche di Nielsen.
- **`skills/common/lib/normative.py`:** carica a 0 token il dizionario normativo ed estrae metadati e tecniche ufficiali (es. ARIA14, H37, H42).
- **`skills/common/lib/color_utils.py`:** esegue il calcolo deterministico del rapporto di contrasto (`contrast_ratio`) e la luminanza relativa.
- **`skills/common/lib/excel_utils.py`:** rileva `openpyxl`, **obbligatorio** (nessun fallback: senza `openpyxl` lo script si ferma con un messaggio chiaro).
- **`skills/common/lib/nodi_utils.py`:** normalizza i nodi di una voce (tipo, doppioni, ordine fisso componente → istanze → nodi singoli), scrive/legge l'elenco nella colonna D e definisce la regola "Da correggere" (formula Excel e funzione Python, la stessa per audit e correzione).

> **Le regole di questa skill sono universali.** Valgono per qualsiasi file Figma: non contengono ID, nomi di componenti, pagine o colori di un progetto particolare. Gli esempi qui sotto usano segnaposto (`<id>`, `Bottone primario`). Non aggiungere mai a questa skill, allo script o ai moduli comuni regole o eccezioni legate a un solo file.

---

## 3. Definizione INPUT

1. **Link Prototipo Figma (`link_figma`):**
   - URL Figma fornito dall'utente (es. `https://www.figma.com/design/<file-key>/<titolo>?node-id=...`).
   - L'agente legge i nodi dei frame Desktop e Mobile con i soli strumenti MCP elencati nella sezione 4 ("Strumenti Figma consentiti").
2. **Template Excel (`Audit_modello.xlsx`):**
   - Modello base contenente i fogli `Sessione`, `Voci`, `Nodi`, `Corretto`, `Riepilogo`.
3. **Payload Dati (formato JSON per lo script):**
   - L'agente scrive **una segnalazione per ogni difetto trovato**, elencando i nodi coinvolti in `nodi`. Non deve raggruppare né numerare: lo fa `checker.py` (vedi 4.3). Una segnalazione può avere un solo nodo o più nodi.
     ```json
     {
       "session": {
         "caso": "Nome Progetto / Flusso",
         "link_figma": "https://www.figma.com/design/...",
         "file_figma": "Nome File",
         "versione": "v0 (pre-audit)",
         "pagine": "Desktop e Mobile"
       },
       "voci": [
         {
           "elemento": "Bottone primario",
           "tipo_elemento": "pulsante",
           "riferimento": "WCAG 1.4.3 (AA)",
           "descrizione": "Contrasto testo insufficiente",
           "gravita": "Moderata",
           "misure": { "fg": "#888888", "bg": "#FFFFFF" },
           "nodi": [
             { "id": "<id-componente>", "pagina": "Pagina A", "tipo": "Componente" },
             { "id": "<id-istanza>", "pagina": "Pagina B", "tipo": "Istanza" }
           ]
         },
         {
           "elemento": "Icona chiudi",
           "tipo_elemento": "pulsante-solo-icona",
           "riferimento": "WCAG 2.5.8 (AA)",
           "descrizione": "Target interattivo troppo piccolo",
           "gravita": "Grave",
           "misure": { "w": 18, "h": 18 },
           "nodi": [ { "id": "<id-nodo>", "pagina": "Pagina A", "tipo": "Nodo singolo" } ]
         }
       ],
       "corretto": [
         {
           "pagina": "Desktop / Header",
           "elemento": "Logo brand",
           "riferimento": "WCAG 1.1.1 (A)",
           "descrizione": "Logo vettoriale con testo alternativo presente"
         }
       ]
     }
     ```

---

## 4. Elaborazione e Logica Operativa (`READ-ONLY`)

- **Modalità Operativa:** `READ-ONLY`. Divieto categorico di modificare il file Figma.

### Strumenti Figma consentiti (elenco chiuso)
Si usano **solo** questi strumenti del server MCP di Figma, nell'ordine indicato. Qualunque altro strumento Figma è vietato, in particolare `use_figma` (esegue codice e può modificare il file) e tutti gli strumenti che creano o caricano contenuti.

| Ordine | Strumento | Quando usarlo |
|---|---|---|
| 1 | `create_session` | Una volta, all'inizio, con il `fileKey` preso dal link. Non modifica il file ma è richiesto prima degli altri strumenti. |
| 2 | `get_metadata` | Per avere la struttura delle pagine e dei frame (ID nodi, nomi, posizione e dimensioni). Costa poco: usalo per orientarti, scegliere i frame Desktop/Mobile e misurare i target (WCAG 2.5.5 / 2.5.8). |
| 3 | `get_variable_defs` | Una volta per file: variabili e stili colore/testo. Serve a verificare la coerenza (Nielsen 4) e a capire se i colori usano i token. |
| 4 | `get_design_context` | Solo sui nodi da approfondire (un frame o una sezione alla volta): colori, testi, font e layout per i calcoli di contrasto e dimensione testo. Non chiamarlo sull'intera pagina. |
| 5 | `get_screenshot` | Per il giudizio visivo (euristiche di Nielsen, gerarchia, leggibilità) e per stabilire se le immagini sono decorative o informative (vedi 4.1). È lo strumento che costa più token: al massimo uno per frame. |

Questo elenco è applicato anche dall'hook `skills/common/lib/figma_guard.py`, che blocca ogni altro strumento Figma mentre `/audit` è attivo.

### 4.1 Copertura e lettura: tutte le pagine, frame per frame
- `get_metadata` **senza** `nodeId` elenca le pagine del file (costa poco). A fine audit dichiara quali frame di pagina sono stati esclusi dalla lettura.
- **Ordine di lettura fisso, in tre passi:** 1) leggi i componenti; 2) cerca le loro istanze nei frame; 3) leggi ogni frame di pagina elemento per elemento, compresi gli elementi che non sono né componenti né istanze (immagini, testi, forme), e segnala i difetti con `tipo: Nodo singolo`.
- **Immagini:** per stabilire se un'immagine è decorativa o informativa fai uno `get_screenshot` del frame che la contiene e giudica dal contesto visivo; poi scegli `immagine-decorativa` o `immagine-informativa` in `tipo_elemento`.
- Non chiamare `get_metadata` su una pagina intera: in un file reale supera il limite di token. Leggi **un frame di pagina o una sezione alla volta**. Ignora i nodi con `hidden="true"`.
- Il metadata di un frame **non espande i figli delle istanze**. Per vedere cosa c'è dentro un'istanza (es. un footer), chiama `get_metadata` sull'ID di quell'istanza: i suoi figli hanno ID `I<istanza>;<nodo-nel-componente>`.
- Ciò che riguarda un componente o un elemento ripetuto va cercato **in tutte le pagine analizzate**, non solo nella prima: la correzione verrà applicata solo ai nodi elencati in `nodi`, quindi un nodo non elencato non sarà mai corretto.

### 4.2 Identificazione dei nodi (solo lettura)
Per ogni nodo con un difetto scrivi in `nodi` `id`, `pagina` e `tipo`. Il tipo si ricava dal **tag** del nodo in `get_metadata` e dal suo ID, mai con `use_figma`:

| `tipo` | Quando |
|---|---|
| `Componente` | Tag `symbol`: la definizione di un componente (anche ogni variante di un componente con varianti). |
| `Istanza` | Tag `instance`, oppure qualunque nodo che sta dentro un'istanza: il suo ID ha la forma `I<istanza>;<nodo-nel-componente>` (inizia con `I` e contiene `;`). |
| `Nodo singolo` | Tutto il resto (`frame`, `text`, `vector`, forme…) che non appartiene a un componente né a un'istanza. |

Le istanze **non indicano il componente d'origine né la variante** (né `get_metadata` né `get_design_context`): l'unico legame è il nome, che di norma coincide con quello del componente.

Regole:
1. **Difetto in un componente:** riporta il componente (`Componente`) **e tutte le sue istanze** nelle pagine analizzate, in una sola segnalazione. Come trovarle:
   - *istanze di primo livello:* nei frame analizzati, i tag `instance` con lo stesso nome del componente. Se un'istanza è stata rinominata può sfuggire: scrivilo nel campo `motivo`;
   - *nodo dentro un'istanza:* se il difetto è nel nodo `N` del componente e `X` è l'ID di un'istanza, il nodo corrispondente è `X;N`, con il prefisso `I` davanti a `X` se non lo ha già (es. istanza `1:100`, nodo `1:55` → `I1:100;1:55`; istanza annidata `I1:100;1:55`, nodo `1:9` → `I1:100;1:55;1:9`). Si costruisce **senza leggere** l'istanza: l'ultimo segmento è sempre l'ID del nodo nel componente.
2. **Istanze con aspetto diverso:** un'istanza può avere dimensioni o stili diversi dal componente (override di colore, testo, misura). Se la differenza è visibile (dimensioni diverse nel metadata) o sospetta, leggila a parte con `get_design_context` e segnalala con **le sue misure**: il raggruppamento la terrà in una voce separata. Per le istanze identiche al componente vale la misura del componente (scrivilo nel campo `motivo`; la correzione le rilegge dopo la modifica).
3. **Più difetti sullo stesso nodo:** una segnalazione per ogni difetto. Lo stesso nodo comparirà in più righe del foglio `Nodi`, una per errore.
4. **Solo i nodi con errore** vanno in `nodi` (e quindi nel foglio `Nodi`). Gli elementi conformi vanno nel foglio `Corretto`.
5. Non inventare ID: usa solo ID letti dagli strumenti o costruiti con la regola 1. In caso di dubbio sul tipo, scrivi `Nodo singolo`.

### 4.3 Raggruppamento degli errori comuni (fatto da `checker.py`, a 0 token)
Non unire le segnalazioni a mano e non numerare le voci: `checker.py` unisce in **una sola voce** (un solo ID in colonna A, elenco dei nodi in colonna D) le segnalazioni con lo stesso errore comune, con queste regole:

| Tipo di difetto | Si uniscono se hanno in comune |
|---|---|
| Contrasto (1.4.3, 1.4.6, 1.4.11) | riferimento e **misure identiche** (stessi `fg`, `bg`, `testo_grande`, `componente_ui`) |
| Dimensione target (2.5.5, 2.5.8) | riferimento e **stesse misure** (`w`, `h`) |
| Tutti gli altri criteri (WCAG con annotazione, euristiche di Nielsen, ecc.) | riferimento, `tipo_elemento` e **descrizione identica** (confronto senza maiuscole e punteggiatura) |

Nel dubbio la voce **si divide**: elementi con colori o dimensioni diverse restano voci separate, anche se hanno la stessa descrizione, perché la correzione dipende dai valori. Una segnalazione di contrasto o target **senza `misure`** non viene mai unita alle altre. Per favorire il raggruppamento: copia i valori `fg`/`bg`/`w`/`h` esattamente come letti da Figma e scrivi la `descrizione` come **frase generica del difetto, sempre uguale per lo stesso difetto** (es. «Manca il testo alternativo»), senza nomi di nodi, pagine o valori: quelli stanno in `elemento`, `nodi` e `misure`. Descrizioni diverse producono voci diverse.

### 4.4 Tipo di elemento (`tipo_elemento`, lista chiusa)
Ogni segnalazione dichiara la categoria funzionale dell'elemento, scelta **solo** tra: `immagine-informativa`, `immagine-decorativa`, `pulsante-solo-icona`, `pulsante`, `link`, `campo-form`, `titolo`, `testo`, `contenitore`, `altro`. Serve a scegliere il suggerimento di annotazione senza indovinare dal testo libero e a non unire elementi di natura diversa. Un valore fuori lista viene trattato come `altro`.

### 4.5 Suggerimenti di annotazione: testo guida, mai codice compilato
La colonna P ("Suggerimento (Annotazioni in Figma)") è generata da `checker.py` da `wcag.json` in base a riferimento e `tipo_elemento`. Contiene i **tag e gli attributi da annotare** con segnaposto tra parentesi quadre (es. `<img alt="[descrizione funzione/contenuto]">`). Non riscriverla e non sostituire i segnaposto con testi inventati: la descrizione reale (alt, aria-label, ecc.) la decidono progettista e sviluppatori. La correzione riporterà il suggerimento così com'è.
- **Calcoli Deterministici a 0 Token (eseguiti da `checker.py`, non dal modello):**
  - Contrasto cromatico testo (WCAG 1.4.3: $\ge 4.5:1$ per testo normale, $\ge 3.0:1$ per testo grande $\ge 18$pt o $\ge 14$pt bold).
  - Contrasto componenti grafici e stati interattivi (WCAG 1.4.11: $\ge 3.0:1$).
  - Dimensioni target touch/click (WCAG 2.5.8: $\ge 24\times 24$ px, WCAG 2.5.5: $\ge 44\times 44$ px).
  - **Come si attivano:** per ogni voce (e per ogni elemento di `corretto`) su 1.4.3, 1.4.6, 1.4.11, 2.5.5, 2.5.8 il payload deve contenere `misure`, con i valori **letti da Figma**: `{"fg","bg"}` (hex; opzionali `"testo_grande": true`, `"componente_ui": true`) oppure `{"w","h"}` in px. Lo script calcola rapporto e conformità (`check_contrast`, `check_target_size` in `skills/common/lib/wcag_checks.py`), scrive la misura nella Descrizione, propone il colore corretto a tonalità costante o il padding e, se la correzione è vuota, la compila.
  - **Non scrivere il rapporto di contrasto nella `descrizione`**: se presente viene sostituito dal valore misurato. Una voce senza `misure` su questi criteri produce un avviso: il valore non è verificato dallo script. Una voce segnalata ma misurata conforme passa ad Affidabilità `Da controllare`.
- **Auto-popolamento Tecniche W3C (Colonna P):**
  - Lo script associa in automatico le tecniche W3C (es. `ARIA14` per icone interattive, `H37` per immagini) per prescrivere annotazioni per gli sviluppatori.

---

## 5. Comando di Esecuzione dello Script

### Cartella di output
Il report viene **sempre** salvato in una cartella con il nome del file Figma analizzato (`session.file_figma`):
`<cartella corrente>/<nome file Figma>/<nome file Figma>-<data>-audit.xlsx`.
Lo script crea la cartella da solo; `--out-root` cambia la cartella base. Salva anche il `payload.json` dentro la stessa cartella.

```bash
# Esecuzione con file JSON:
<ROOT>/.venv/bin/python <ROOT>/skills/agente-audit/scripts/checker.py \
  --template <ROOT>/Audit_modello.xlsx \
  --input-json "<nome file Figma>/payload.json"

# In alternativa via standard input:
cat payload.json | <ROOT>/.venv/bin/python <ROOT>/skills/agente-audit/scripts/checker.py \
  --template <ROOT>/Audit_modello.xlsx \
  --stdin

# Verifica preliminare dataset e formule:
<ROOT>/.venv/bin/python <ROOT>/skills/agente-audit/scripts/checker.py --demo
```

---

## 6. Definizione OUTPUT

- **File Excel di Audit Generato (`<nome file Figma>/<nome file Figma>-<data>-audit.xlsx`):**
  1. **Foglio `Sessione`:** metadati completi dell'audit.
  2. **Foglio `Voci` (23 Colonne):** una riga per **errore comune** (ID assegnato dallo script: V-01, V-02, …).
     - *Colonne A-Q compilate dall'agente:* `ID`, `Pagina` (le pagine dei nodi), `Elemento`, `ID Nodi Figma` (colonna D: **un ID per riga della cella**, in ordine componente → istanze → nodi singoli), `Ambito`, `Riferimento`, `Descrizione`, `Gravità`, `Stato`, `Affidabilità`, `Motivo`, `Conflitto`, `Motivo conflitto`, `Correzione proposta`, `Dove si corregge`, `Suggerimento (Annotazioni in Figma)` (colonna P), `Fonte`.
     - *Colonne R-W vuote (riservate al Progettista):* `Decisione`, `Motivo`, `Tipo motivo`, `Gravità confermata`, `Chi applica la correzione`, `Data decisione`.
  3. **Foglio `Nodi`:** una riga per ogni coppia nodo-errore, solo per i nodi con un errore. Colonne: `ID nodo Figma`, `Pagina`, `Tipo` (Componente / Istanza / Nodo singolo), `Elemento`, `ID errore riferimento` (l'ID della voce), `Da correggere`. L'ultima colonna è una **formula**: vale `Sì` solo se, nella voce collegata, `Decisione` (R) è `Accolta` o `Modificata` **e** `Chi applica la correzione` (V) è `Agente` o `Entrambi`; altrimenti `No`. Il progettista non la compila: si aggiorna quando sceglie dai menù di Voci.
  4. **Foglio `Corretto`:** elementi esaminati e conformi.
  5. **Foglio `Riepilogo`:** matrice d'impatto incrociata (Gravità $\times$ Ambito).
- **Passaggio di Consegna:** l'agente comunica all'utente in chat:
  1. il percorso del file generato;
  2. il promemoria: *"Prima della Fase 2 (correzione), salva una copia locale del file Figma: File → Save local copy… (.fig)"*.
  Poi attende che il progettista compili le decisioni (Human-in-the-Loop).
