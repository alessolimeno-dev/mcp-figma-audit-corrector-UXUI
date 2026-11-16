---
name: agente-correzione
description: Applica sul prototipo Figma le correzioni approvate dal progettista nel report Excel (WRITE-BOUNDED) su tutti i nodi di ogni errore (componenti, istanze, nodi singoli, in tutte le pagine) con il principio di minima invasività e compila il foglio Log Correzioni.
---

# Skill: Agente di Correzione UI/UX (Fase 2)

Definizione canonica per **Claude Code**. Figma si raggiunge solo tramite il connettore Figma attivo sull'account Claude.

> **Le regole di questa skill sono universali.** Valgono per qualsiasi file Figma: non contengono ID, nomi di componenti, pagine o colori di un progetto particolare. Gli esempi usano segnaposto (`<id>`). Non aggiungere mai a questa skill, allo script o ai moduli comuni regole legate a un solo file.

---

## 1. Ambiente di Esecuzione (VENV Locale)

- **Cartella del progetto (`<ROOT>`):** la cartella che contiene `skills/`, `.venv/` e `Audit_modello.xlsx`.
  - Se la sessione è aperta dentro il progetto: `<ROOT>` = `.`
  - Se la sessione è aperta nella cartella superiore (es. `Analisi-skills/`): `<ROOT>` = `mcp-figma-audit-corrector-UXUI`
- **Interprete Python Obbligatorio:** tutte le chiamate agli script devono usare il python locale del progetto:
  - macOS/Linux: `<ROOT>/.venv/bin/python`
  - Windows: `<ROOT>\.venv\Scripts\python.exe`
- Non utilizzare l'interprete Python globale di sistema. `openpyxl` è obbligatorio (nessun fallback): senza, lo script si ferma con un messaggio chiaro.

---

## 2. Integrazione con i Moduli Comuni (`skills/common/`)

L'agente sfrutta gli stessi moduli matematici e normativi impiegati nella Fase 1:
- **`skills/common/references/wcag.json`:** dizionario normativo condiviso con l'agente di audit.
- **`skills/common/lib/normative.py`:** mappa ciascun ID anomalia alle prescrizioni e tecniche ufficiali per la generazione del log.
- **`skills/common/lib/color_utils.py`:**
  - `adjust_lightness_for_contrast(fg_hex, bg_hex, target_ratio)`: modula deterministicamente la luminosità (Lightness) in coordinate HLS mantenendo invariata la tonalità (Hue).
  - `calculate_padding_expansion(width, height, min_target)`: calcola l'incremento di padding orizzontale e verticale per raggiungere i target minimi (es. 24px o 44px).
- **`skills/common/lib/wcag_checks.py`:** `measure(riferimento, misure)` unisce le due formule sopra con `check_contrast` / `check_target_size`: dati `{fg,bg}` o `{w,h}` restituisce conformità, soglia, nuovo colore (HLS e RGB 0-1 per Figma) o padding. È usata da `corrector.py` sia per il piano (`--plan`) sia per la verifica post-intervento.
- **`skills/common/lib/nodi_utils.py`:** la regola **"Da correggere"** (`da_correggere`: Decisione `Accolta`/`Modificata` **e** Chi applica `Agente`/`Entrambi`), la lettura dei nodi di una voce e il loro ordine fisso componente → istanze → nodi singoli. È la stessa regola della formula del foglio `Nodi`.

### Cosa fa lo script e cosa fa Claude
| Chi | Cosa |
|---|---|
| `corrector.py --plan` | Legge l'Excel (fogli `Voci` e `Nodi`), elenca le voci da correggere **con tutti i loro nodi in ordine**, calcola i valori da applicare (colore HLS, padding). **Non scrive nulla.** |
| Claude con `use_figma` | **Applica** i valori del piano sui nodi, una chiamata per voce. `corrector.py` non modifica mai Figma. |
| Claude con `get_design_context` / `get_metadata` | Rilegge i valori reali di ogni nodo dopo la modifica (fg, bg, larghezza, altezza), se non li ha già restituiti la chiamata `use_figma`. |
| `corrector.py --apply` | Calcola la **misura** sui valori riletti, nodo per nodo, e scrive il Log (una riga per voce). Senza misura l'esito è `Da verificare`. |
- **`skills/common/lib/excel_utils.py`:** rileva `openpyxl`. Il foglio `Log Correzioni` e la data della decisione li scrive `corrector.py`.

---

## 3. Definizione INPUT

1. **Link Prototipo Figma (`link_figma`):**
   - URL del progetto Figma su cui risiedono i nodi da correggere.
2. **File Excel di Audit con Decisioni Compilate (`file_excel`):**
   - Il report generato nella Fase 1 (fogli `Voci` e `Nodi`) in cui il progettista ha compilato le colonne R-W di `Voci`. Il layout è quello a 23 colonne della versione attuale di `/audit`: un report di una versione precedente va rigenerato.
3. **Regola "Da correggere" (Human-in-the-Loop):**
   - Una voce (e quindi **tutti i suoi nodi**) si corregge **solo se valgono entrambe le condizioni**:
     - Colonna R (`Decisione`): `Accolta` oppure `Modificata`;
     - Colonna V (`Chi applica la correzione`): `Agente` oppure `Entrambi`.
   - `Rifiutata`, decisione vuota, `Progettista` o colonna V **vuota** → la voce non viene toccata. La colonna `Da correggere` del foglio `Nodi` mostra la stessa regola al progettista; lo script la **ricalcola da R e V** e non si fida del valore salvato nella cella.

---

## 4. Elaborazione e Logica Operativa (`WRITE-BOUNDED`)

### Promemoria copia locale (non bloccante)
All'inizio l'agente suggerisce in chat di salvare una copia locale del file Figma (File → **Save local copy…**) prima delle modifiche. È solo un consiglio: l'agente lavora sempre sul file Figma online e procede anche se la copia non viene fatta.

- **Modalità Operativa:** `WRITE-BOUNDED`. Modifica chirurgica limitata esclusivamente ai nodi delle voci da correggere.
- **Ispezione Puntuale su Figma:**
  - L'agente legge e modifica **solo i nodi elencati dal piano** (foglio `Nodi`, che elenca i nodi di ogni voce), **in tutte le pagine in cui compaiono**, non solo nella prima. È vietato richiedere l'intero albero del file.

### Strumenti Figma consentiti (elenco chiuso)
Si usano **solo** questi strumenti del server MCP di Figma. Qualunque altro strumento Figma è vietato (es. `html_to_figma`, `send_code_to_figma`, `create_new_file`, `upload_assets`, `generate_*`).

| Strumento | Quando usarlo |
|---|---|
| `create_session` | Una volta, all'inizio, con il `fileKey` preso dal link. |
| `get_metadata` | Per trovare e verificare i nodi del piano (esistenza, dimensioni prima/dopo la modifica). Leggi un nodo o un frame alla volta, mai una pagina intera. |
| `get_variable_defs` | Per il Livello 1 di minima invasività: scegliere la variabile/stile conforme più vicino. |
| `get_design_context` | Per leggere colori, padding e testi dei soli nodi del piano, prima e dopo la modifica. |
| `get_screenshot` | Facoltativo: controllo visivo del nodo dopo la modifica. |
| `use_figma` | **L'unico strumento che modifica il file.** Solo sui nodi delle voci da correggere, **una chiamata per voce con tutti i nodi dell'elenco**, con i valori del piano (`corrector.py --plan`): colore `suggerito_fg` / `figma_rgb_suggerito`, padding `padding_*_per_lato`, oppure l'annotazione. Non ricalcolare i valori a mano. Mai per creare, spostare o eliminare nodi non coinvolti. |

Questo elenco è applicato anche dall'hook `skills/common/lib/figma_guard.py`, che blocca ogni altro strumento Figma mentre `/correzione` è attivo.

### Ordine di applicazione sui nodi di una voce
I nodi di ogni voce arrivano dal piano già ordinati: **prima il componente, poi le istanze, poi i nodi singoli**. Non seguire l'ordine in cui li incontri su Figma. Nel codice della chiamata `use_figma` di una voce:
1. **Componente:** applica il valore del piano.
2. **Istanze:** per ognuna rileggi il valore attuale.
   - Se ha **ereditato** la correzione (valore ora conforme) **non scrivere nulla**: azione `ereditato`.
   - Se ha un **override** e l'errore c'è ancora, correggila direttamente con lo stesso valore del piano: azione `override`.
   - Se il componente principale sta in una **libreria esterna** (non modificabile), correggi solo l'istanza come override: azione `libreria`.
3. **Nodi singoli:** applica il valore del piano (azione `applicato`).
4. Un nodo che non esiste più o non è modificabile: azione `non_trovato` (l'esito della voce sarà `Non risolto`).
5. Fai restituire alla stessa chiamata, per ogni nodo, i valori riletti (`fg`/`bg` oppure `w`/`h`) e l'azione eseguita. Se il formato di ritorno non lo permette, rileggi i nodi con `get_design_context` / `get_metadata`. I valori servono per `--misure-post`.

### Gerarchia di Minima Invasività per Correzioni Grafiche
1. *Livello 1 - Token di Progetto:* Se il progetto ha variabili colore o stili, applica il token conforme più vicino.
2. *Livello 2 - Spaziature/Padding:* Per bottoni o icone sotto target, espande il padding secondo la formula deterministica di `color_utils.py`.
3. *Livello 3 - Modulazione HLS a Tonalità Costante:* Per problemi di colore/contrasto, applica il valore esadecimale calcolato da `adjust_lightness_for_contrast`.

### Annotazioni Tecniche Figma (testo guida, mai codice compilato)
- Per difetti non correggibili visivamente su Figma (es. attributi ARIA, focus ring da tastiera, semantica HTML), inserisci un'**annotazione per gli sviluppatori su ogni nodo dell'elenco della voce** (componente, istanze e nodi singoli), non su uno solo.
- Il testo dell'annotazione è **esattamente il suggerimento della colonna P** di quella voce, con i segnaposto tra parentesi quadre **lasciati così come sono**. Esempio, per un'immagine senza testo alternativo: *«per immagine informativa `<img alt="[descrizione funzione/contenuto]">`; se puramente decorativa `alt=""`»*. **Non inventare** né compilare il contenuto (alt, aria-label, ecc.): lo decidono progettista e sviluppatori. `corrector.py` ignora ogni override dell'annotazione nel Log.

---

## 5. Flusso e comandi dello script

Il file Excel resta nella sua cartella (quella con il nome del file Figma): lo script aggiorna lo stesso file.

**Flusso obbligatorio, nell'ordine:**

1. **Piano (dry-run reale, non scrive nulla):** legge l'Excel, elenca le voci da correggere con i nodi in ordine e calcola i valori da applicare. Mostra il piano all'utente.
2. **Misure mancanti:** per le voci con stato `misure_mancanti` leggi fg/bg o larghezza/altezza da Figma (`get_design_context` / `get_metadata`), salvale in un JSON e rilancia il piano con `--misure-prima`.
3. **Modifica su Figma:** con `use_figma`, **una chiamata per voce**, applica il piano a tutti i nodi della voce nell'ordine della sezione 4.
4. **Rilettura:** salva in `misure-post.json` i valori dei nodi dopo la modifica e l'azione eseguita su ciascuno.
5. **Log:** `--apply` con `--misure-post` calcola la verifica sulle misure e scrive il Log Correzioni.

```bash
# Passo 1: piano di correzione (nessun file modificato; --plan-out salva i valori in JSON)
<ROOT>/.venv/bin/python <ROOT>/skills/agente-correzione/scripts/corrector.py \
  --excel [percorso-report-audit.xlsx] \
  --plan [--plan-out piano.json] [--misure-prima misure-prima.json]

# Passo 5: scrittura Log Correzioni con verifica misurata
<ROOT>/.venv/bin/python <ROOT>/skills/agente-correzione/scripts/corrector.py \
  --excel [percorso-report-audit.xlsx] \
  --apply --misure-post misure-post.json [--misure-prima misure-prima.json] [--log-json override.json]

# Solo test delle formule e della regola Da correggere (NON legge l'Excel, non è un dry-run):
<ROOT>/.venv/bin/python <ROOT>/skills/agente-correzione/scripts/corrector.py --demo
```

**Formato dei file di misura** (chiave = ID voce; contrasto `fg`/`bg` in hex, target `w`/`h` in px).

`--misure-prima`: una misura per voce (i nodi di una voce hanno le stesse misure per costruzione del raggruppamento):

```json
{ "V-01": {"fg": "#767676", "bg": "#FFFFFF"}, "V-02": {"w": 24, "h": 24} }
```

`--misure-post`: una misura per voce **oppure** una per nodo, con l'azione eseguita (`applicato` predefinita, `ereditato`, `override`, `libreria`, `non_trovato`) e una nota facoltativa:

```json
{
  "V-01": {
    "<id-componente>": {"fg": "#767676", "bg": "#FFFFFF"},
    "<id-istanza-1>":  {"fg": "#767676", "bg": "#FFFFFF", "azione": "ereditato"},
    "<id-istanza-2>":  {"fg": "#767676", "bg": "#FFFFFF", "azione": "override", "nota": "override locale"}
  },
  "V-02": {"w": 24, "h": 24}
}
```

`--log-json` accetta solo `azione` (testo libero) per voce, e `esito`/`verifica` per i soli criteri non misurabili. Per contrasto (1.4.3, 1.4.6, 1.4.11) e target (2.5.5, 2.5.8) `esito` e `verifica` sono sempre calcolati dalla misura: un override viene ignorato con un avviso. L'`annotazione` è sempre il suggerimento della colonna P: un override viene ignorato con un avviso.

---

## 6. Definizione OUTPUT

1. **Prototipo Figma Aggiornato:**
   - Tutti i nodi delle voci da correggere risultano modificati chirurgicamente (colori aggiornati, padding adattati, annotazioni inserite su ogni nodo), in tutte le pagine; le istanze che hanno ereditato la correzione non vengono riscritte.
2. **File Excel di Audit AGGIORNATO (stesso file in input):**
   - **Foglio `Log Correzioni` (9 Colonne, UNA RIGA PER ID ERRORE della colonna A di `Voci`):** così il progettista confronta la correzione proposta con quella applicata.
     - `1: ID Voce`
     - `2: ID Nodi Figma` (tutti i nodi della voce, uno per riga della cella)
     - `3: Ambito` (Usabilità / Accessibilità)
     - `4: Riferimento` (WCAG / Nielsen)
     - `5: Elemento`
     - `6: Azione Eseguita` (correzione applicata + riepilogo dei nodi, es. «componente corretto x1; istanza ereditata dal componente x3; istanza con override corretta direttamente x1»)
     - `7: Annotazione / Codice Applicato` (il suggerimento della colonna P, testo guida con i segnaposto non compilati)
     - `8: Esito` della voce = il **caso peggiore tra i nodi**: `Non risolto` (almeno un nodo misurato non conforme o non trovato) > `Da verificare` (almeno un nodo senza misura o non misurabile da script) > `Annotato` (solo annotazione per sviluppatori) > `Risolto` (tutti i nodi misurati conformi)
     - `9: Verifica Post-Intervento`: **una riga per nodo** con la misura calcolata da `wcag_checks.measure()` sui valori riletti da Figma (es. `<id> (Istanza): Misurato dopo l'intervento: #767676 su #FFFFFF = 4.54:1 (soglia 4.5:1) -> conforme`). Mai un testo scritto dal modello
   - **Foglio `Voci`:** Colonna W (`Data della decisione`) popolata automaticamente con la data odierna per le voci corrette, se lasciata vuota.
- **Notifica Finale:** riepilogo per l'utente dei nodi modificati su Figma, per voce e per pagina, e conferma dell'aggiornamento del file Excel. Elenca a parte le voci `Non risolto` e `Da verificare`: non vanno presentate come risolte.
