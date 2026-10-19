# Griglia delle memorie "come Excel" — progetto

Data: 19/10/2026 · Stato: approvato a voce, da rivedere per iscritto

## Obiettivo

Andrea vuole lavorare sulle tabelle dei canali di CHIRP Plus come su un
foglio Excel: selezionare rettangoli di celle, copiarli e incollarli
(anche da e verso Excel), riempire in basso, scrivere lo stesso valore in
più celle, creare serie di frequenze e di nomi, anche trascinando una
maniglia col mouse.

**Successo** = queste operazioni funzionano nella griglia delle memorie
di qualsiasi radio, con la validazione della radio, i colori del tema e
un solo passo di annulla per operazione; le operazioni di oggi su righe
intere restano identiche.

### Decisioni prese con Andrea

| Domanda | Scelta |
|---|---|
| Funzioni | tutte e quattro: copia/incolla celle, riempi in basso, modifica multipla (con Canc), serie automatiche |
| Interazione | maniglia trascinabile + tastiera (Ctrl+D, Ctrl+Invio) + menu col tasto destro |
| Approccio | potenziare la griglia CHIRP esistente (non aprire Excel esterno, non sostituire la griglia) |

### Fuori da questa versione

Formule, trova e sostituisci, maniglia orizzontale (trascinare verso destra),
comando "Modifica in Excel", riempimento verso l'alto.

## Stato attuale (da `chirp/wxui/memedit.py`)

- La griglia (`ChirpMemoryGrid`, `wx.grid.Grid`) è in modalità
  `SelectRows`: si selezionano solo righe intere.
- `EnableDragCell()` + `EVT_GRID_CELL_BEGIN_DRAG` trascinano canali interi
  anche partendo da una cella; dal numero di riga c'è già una gestione
  propria (`_row_click`, `_rowheader_mouseover`, `_memory_drag`).
- Copia/incolla (`cb_copy_getdata`, `cb_paste`, `_cb_paste_memories`)
  lavora su memorie intere; gli appunti contengono il formato CHIRP e un
  TSV di righe intere (dal driver `TSVRadio`).
- La modifica di una cella passa da `_memory_edited`
  (`EVT_GRID_CELL_CHANGING`): filtra il nome, applica il valore con
  `col_def.digest_value`, mette i default della banda se cambia la
  frequenza, sceglie il modo tono, **chiede** offset/shift e incrociati
  (`_resolve_duplex`, `_resolve_offset`, `_resolve_cross_mode`,
  `_resolve_tmode_cross`), valida con `radio.validate_memory` e salva in
  un `undo_context`.
- Annulla/ripeti: `undo_context(name)` registra più memorie come un solo
  passo (`MemeditUndoContext`).

## Progetto

### 1. Selezione e interazione

- **Selezione a celle**: la griglia passa a `GridSelectCells`. Clic e
  trascinamento selezionano un rettangolo, Maiusc+frecce lo allarga,
  Ctrl+clic aggiunge celle. Il clic sul numero di riga seleziona la riga
  intera (comportamento attuale di `_row_click`, invariato).
- **Righe intere**: `get_selected_rows_safe()` e tutti i comandi di oggi
  (elimina, sposta, ordina, trascina in un'altra scheda, copia di canali)
  usano le righe selezionate dal numero di riga; se la selezione è un
  rettangolo che copre tutte le colonne visibili vale come righe intere.
  Una selezione di sole celle non attiva i comandi che agiscono su canali
  interi (Elimina canali usa la riga del cursore, come oggi senza
  selezione).
- **Trascinamento di canali**: solo dal numero di riga.
  `EnableDragCell()` viene tolto, così il trascinamento sulle celle
  seleziona.
- **Maniglia di riempimento**: quadratino 7×7 px nell'angolo in basso a
  destra della selezione, realizzato come piccola finestra figlia della
  finestra della griglia, riposizionata a ogni cambio di selezione,
  scorrimento, ridimensionamento di colonne o finestra; nascosta se
  l'angolo non è visibile o la scheda è in sola lettura. Trascinata in
  giù: durante il trascinamento la griglia mostra in arancio (tono `tx`
  del tema) le celle che verranno scritte; al rilascio applica le regole
  di serie (sezione 3). Esc annulla il trascinamento.
- **Tastiera**:
  - **Ctrl+D**: per ogni colonna della selezione, copia il valore della
    prima riga selezionata nelle altre.
  - **Ctrl+Invio**: mentre si scrive in una cella, conferma il valore in
    tutte le celle selezionate.
  - **Canc** (con sole celle selezionate): svuota le celle (sezione 4).
  - **Ctrl+C / Ctrl+V / Ctrl+X** su celle: copia, incolla, taglia (= copia
    + Canc).
- **Menu col tasto destro** su una selezione di celle: Copia celle,
  Incolla, Riempi in basso, Serie…, Svuota celle.
- **Dialogo "Serie…"**: valore iniziale (precompilato dalla prima cella),
  passo (frequenze in kHz o MHz, nomi: incremento intero), anteprima delle
  prime tre celle; scrive su tutte le righe selezionate della colonna.

### 2. Motore di applicazione dei valori

- **`_apply_cell_value(mem, col_def, text, interactive)`** (nuovo metodo
  di `ChirpMemEdit`) contiene la logica oggi dentro `_memory_edited`:
  filtro nome, `wants_split`, memoria non più vuota, `digest_value`,
  default della banda se cambia la frequenza, scelta del modo tono,
  gestione duplex/offset/incrociati.
  - `interactive=True` (modifica singola): stesso comportamento di oggi,
    domande comprese. `_memory_edited` diventa un involucro sottile.
  - `interactive=False` (operazioni multiple): nessuna domanda. Duplex
    `+`/`-` senza offset → offset del piano di banda
    (`_set_memory_defaults(mem, 'offset')`); se il piano non ne ha, la
    cella viene saltata. Incrociati che richiederebbero una scelta → cella
    saltata.
  - Restituisce la memoria modificata oppure solleva `CellRejected(motivo)`.
- **`_bulk_edit(nome, celle)`** applica una lista di modifiche
  `(riga, colonna, testo)`:
  1. raggruppa per riga e, per ogni riga, applica **prima la frequenza**
     e poi le altre colonne nell'ordine della griglia (così i default di
     banda vengono poi sovrascritti dai valori espliciti incollati);
  2. valida la memoria risultante con `radio.validate_memory`; errori →
     riga intera saltata e annotata; avvisi → annotati, memoria salvata;
  3. salva tutte le memorie riuscite dentro **un solo**
     `undo_context(nome)` (es. "Riempi 12 celle");
  4. aggiorna le righe, segnala la modifica all'editorset, poi mostra
     **un solo riepilogo** delle celle saltate (stesso stile del
     riepilogo di `_cb_paste_memories`, massimo 19 righe + "…e altre N").
- Le celle saltate non interrompono l'operazione.

### 3. Modulo senza interfaccia: `chirp/grid_fill.py`

Funzioni pure (nessun import di wx), collaudate da test unitari:

- **`continue_series(values, count)`** → `count` nuovi testi che
  continuano `values` (i valori selezionati di una colonna, dall'alto):
  - un valore solo → ripetuto;
  - tutti numerici (virgola decimale accettata) con differenza costante
    (tolleranza 1e-6) → progressione aritmetica, con lo stesso numero di
    decimali del valore più preciso;
  - tutti `prefisso + numero + suffisso` con prefisso e suffisso uguali e
    passo intero costante → nomi numerati, mantenendo gli zeri iniziali
    (`CH01, CH02 → CH03`);
  - altrimenti → il blocco selezionato ripetuto ciclicamente (come Excel).
- **`make_series(start, step, count, kind)`** per il dialogo Serie.
- **`parse_table(text)`** → matrice di stringhe da testo TSV (appunti di
  Excel o di CHIRP): righe separate da `\r\n`/`\n`, ultima riga vuota
  scartata, celle separate da tab, virgolette di Excel rimosse.
- **`is_header_row(row, labels)`** → vero se la prima riga incollata
  coincide con le intestazioni delle colonne (es. da un export Excel di
  CHIRP Plus): in quel caso viene saltata.
- **`target_cells(start_row, start_col, matrix, visible_rows, ncols)`**
  → celle bersaglio di un incolla: solo righe visibili, a partire dalla
  cella attiva; righe oltre l'ultima memoria e colonne oltre l'ultima
  scartate e contate per il riepilogo. Se la matrice è un solo valore e
  la selezione ha più celle, il valore va in tutte le celle selezionate.

### 4. Copia, incolla, svuota

- **Copia celle**: negli appunti un TSV dei testi mostrati nelle celle
  (uno per riga, tab tra colonne), che Excel incolla direttamente. Con
  righe intere selezionate resta la copia di oggi (formato CHIRP + TSV).
- **Incolla**:
  - formato CHIRP (canali interi) → comportamento di oggi, alla riga del
    cursore;
  - testo con struttura di tabella → `parse_table`, `target_cells`,
    `_bulk_edit`. Il controllo di oggi "più di 10 tab = righe di canali
    complete" (`common.mems_from_clipboard`) resta per le righe intere
    selezionate dal numero di riga o quando la prima riga incollata è
    un'intestazione CHIRP completa (con colonna `Location`).
  - Una cella vuota nella tabella incollata lascia il valore che c'era.
  - Nelle colonne numeriche (frequenza, offset, toni, potenza in watt) la
    virgola decimale di Excel in italiano è accettata (`145,6` = 145.6).
  - Prima di sovrascrivere celle non vuote in canali esistenti chiede
    conferma una volta sola, come l'incolla di oggi.
- **Svuota (Canc)**: per ogni cella selezionata
  - nome, commento → testo vuoto;
  - modo tono, duplex, skip, polarità DTCS, modo incrociato, toni, codici
    DTCS → valore di una `chirp_common.Memory()` nuova (duplex vuoto
    azzera anche l'offset);
  - frequenza, modo, passo, potenza → cella saltata, motivo "non ha un
    valore vuoto" (per cancellare un canale resta Elimina sulla riga);
  - celle di canali vuoti → ignorate.

### 5. Casi particolari

- **Vista filtrata**: si scrive solo nelle righe visibili; le righe
  nascoste vengono saltate senza sovrascriverle.
- **Vista ordinata**: le operazioni seguono l'ordine a schermo; ogni riga
  resta legata alla sua memoria (`row2mem`).
- **Celle non modificabili**: memorie speciali, campi in
  `mem.immutable`, colonne extra senza editor, schede in sola lettura
  (`editable` falso, es. risultati di RepeaterBook) → saltate e annotate;
  nelle schede in sola lettura i comandi di modifica sono disattivati, la
  copia funziona.
- **Radio in diretta** (`ChirpLiveMemEdit`): ogni memoria viene scritta
  subito nella radio; oltre 20 celle compare un `wx.ProgressDialog`
  annullabile; ciò che è stato scritto prima dell'annullamento resta e
  fa parte del passo di annulla.
- **Potenza**: valori accettati come nome del livello della radio
  ("High", "Low") o in watt (livello più vicino, come l'import da CSV);
  nelle schede CSV restano i watt esatti (anche 0.01W).
- **Maniglia oltre la fine**: il trascinamento si ferma all'ultima riga
  della griglia.

### 6. Lingue, stile, documentazione

- Nuove stringhe (comandi, dialogo Serie, riepilogo) in
  `tools/translations/*.json` per tutte le 17 lingue + italiano, applicate
  con `tools/add_translations.py`.
- Maniglia e celle in anteprima con i toni del tema terminale (`info`
  per la selezione, `tx` per l'anteprima di scrittura); nell'aspetto
  classico colori di sistema.
- README-PLUS (sezione "Modifica come in Excel") e landing page (riga
  nella tabella delle novità, una cattura nuova da `tools/screenshots.py`).

## Collaudo

- **`tests/unit/test_grid_fill.py`**: serie numeriche (frequenze a 12,5 e
  25 kHz, virgola decimale), nomi numerati con e senza zeri, valore
  singolo, blocco ciclico, `parse_table` (CRLF, riga finale vuota,
  virgolette), intestazioni, `target_cells` con righe nascoste e bordi.
- **`tests/unit/test_bulk_edit.py`** (radio finta e immagine UV-9R di
  test, wx simulato come negli altri test della UI):
  - Ctrl+D di CTCSS e potenza su 5 righe;
  - serie di frequenze su righe vuote → canali creati con i default di
    banda;
  - incolla di una tabella con frequenza + duplex + offset → valori
    espliciti che vincono sui default;
  - un valore rifiutato → nel riepilogo, gli altri applicati;
  - un solo passo di annulla che ripristina tutte le memorie;
  - svuota: nome vuoto, frequenza saltata.
- **Prova nell'app** con lo strumento delle catture: selezione a
  rettangolo, maniglia (serie e copia), Ctrl+D, Ctrl+Invio, incolla di un
  TSV come quello di Excel, Canc, annulla; nessun errore nel log.
- Tutti i test unitari esistenti continuano a passare.

## Criteri di accettazione

1. Un rettangolo di celle si copia e si incolla in Excel e viceversa.
2. Ctrl+D, Ctrl+Invio, Canc e la maniglia funzionano come descritto.
3. Serie di frequenze e di nomi si creano con la maniglia e col dialogo.
4. Ogni operazione multipla è un solo passo di annulla.
5. Le celle rifiutate compaiono in un solo riepilogo; il resto è
   applicato.
6. Le operazioni su righe intere di oggi funzionano come prima.
7. Testi nuovi tradotti in 18 lingue; test unitari tutti verdi.
