# CHIRP Plus

Versione modificata di CHIRP basata sulla build ufficiale `next-20261016`
(commit upstream `832d349e`, ramo `plus`). Ha tutti i driver e le
funzioni dell'originale, più queste modifiche.

## Stile terminale (`chirp/wxui/theme.py`, `console.py`)
- Sfondo nero, font monospace ovunque, etichette come comandi
  (`scarica dalla radio [alt+d]`), intestazioni a prompt
  (`chirp@plus:~$ scarica dalla radio`).
- **Colori con un significato unico in tutta l'app**:

  | Colore | Significato |
  |---|---|
  | verde | riuscito, cavo pronto, verifica OK |
  | giallo | attenzione |
  | rosso | errore |
  | ciano | informazione, frequenze |
  | blu | **legge** dalla radio |
  | arancio | **scrive** nella radio |
  | bianco | file |
  | magenta | toni e codici (CTCSS/DCS) |
  | grigio | secondario, canali vuoti |

- Griglia memorie colorata per funzione (frequenze ciano, nomi bianchi, toni
  magenta, potenza arancio) e numeri di riga per stato (verde programmato,
  grigio vuoto, rosso errore).
- Pagina iniziale come avvio di sistema: righe `[ OK ]`/`[WARN]`/`[INFO]` con
  stato del cavo e delle porte, comandi numerati (clic o tasto 1-5),
  legenda, prompt con cursore.
- Console eventi a colori in basso (Visualizza > Mostra console eventi): cavo
  collegato/scollegato, download, caricamenti, verifiche, file.
- Visualizza > Aspetto > Terminale/Classico, con "Riavvia ora".
- Icone Tabler (MIT) dal pacchetto di Pathfinder in `chirp/share/icons`,
  colorate con gli stessi codici.

## Rilevamento automatico del cavo (`chirp/wxui/portdetect.py`)
- Riconosce i chip dei cavi dall'ID USB (CH340/341/343, PL2303, FTDI,
  CP210x, STM32), li mette in cima e li sceglie da solo; Bluetooth e COM1 in
  fondo. Hot-plug: un cavo collegato con il dialogo aperto viene selezionato.
- Avvisa dei PL2303 contraffatti e non li sceglie.

## Rileva radio (`chirp/radio_detect.py`)
- Radio > Rileva radio e scarica (Alt+R) o pulsante "Rileva": prova le
  strette di mano dei driver con protocollo UV-5R (solo identificazione, nessuna lettura
  o scrittura di memoria) e trova il modello.
- Se il modello già scelto è compatibile, scarica subito nella stessa
  sessione (la radio resta in modalità programmazione solo 2-3 secondi);
  altrimenti chiede il modello e fa un download normale.

## Caricamento sicuro (`chirp/radio_compare.py`, `chirp/wxui/changes.py`)
- "Confronta con la radio prima di caricare": legge la radio e mostra cosa
  cambierà (aggiunto verde, rimosso rosso, modificato giallo) prima di
  scrivere.
- "Rileggi e verifica dopo il caricamento": riscarica e confronta byte per
  byte le zone scritte dal driver.

## Programmazione in serie (`chirp/batch_program.py`, `wxui/batch.py`)
- Radio > Programma più radio: stessa immagine su più radio, una dopo
  l'altra (pulsante o Invio), con verifica, esito per radio e totali.

## Modifica come in Excel (`chirp/grid_fill.py`, `chirp/wxui/cellops.py`, `fillhandle.py`, `seriesdialog.py`)
La griglia delle memorie di qualsiasi radio si usa come un foglio di
calcolo, con la validazione della radio e i colori del tema.
- **Selezione a celle**: clic e trascinamento selezionano un rettangolo,
  Maiusc+frecce lo allarga, Ctrl+clic aggiunge celle. Il clic sul numero di
  riga seleziona la riga intera, come prima; i canali si trascinano solo dal
  numero di riga. Un rettangolo che copre tutte le colonne visibili vale
  come righe intere, quindi i comandi sui canali (elimina, sposta, ordina,
  copia di canali) funzionano come prima.
- **Maniglia di riempimento**: il quadratino nell'angolo in basso a destra
  della selezione (o della sola cella attiva dopo un clic). Trascinato in
  giù incornicia le celle che verranno scritte (in arancio nell'aspetto
  terminale, il colore della scrittura) e al rilascio
  continua la selezione: un valore solo viene copiato, le frequenze
  avanzano con lo stesso passo (`145.500`, `145.525` → `145.550`…), i nomi
  numerati pure, con gli zeri iniziali (`CH01`, `CH02` → `CH03`);
  altrimenti il blocco selezionato si ripete. Esc annulla il trascinamento;
  si ferma all'ultima riga della griglia.
- **Ctrl+D** (Riempi in basso): per ogni colonna copia il valore della
  prima riga selezionata nelle altre.
- **Ctrl+Invio**: mentre si scrive in una cella, conferma il valore in
  tutte le celle selezionate.
- **Canc** svuota le celle selezionate, o la sola cella attiva dopo un
  clic: nome e commento diventano vuoti; modo tono, toni, codici e
  polarità DTCS, modo incrociato, duplex e skip tornano al valore di un
  canale nuovo (duplex vuoto azzera anche l'offset); le celle dei canali
  vuoti vengono ignorate. Frequenza, modo, passo e potenza non hanno un
  valore vuoto e vengono saltati. Con righe intere selezionate Canc fa
  quello che faceva prima.
- **Modifica > Elimina (Ctrl+Backspace)**: con celle selezionate le svuota
  come Canc; altrimenti elimina i canali selezionati, o quello della cella
  attiva, come prima. Anche Elimina nel menu della riga cancella il canale.
- **Copia e incolla celle** (Ctrl+C, Ctrl+V, Ctrl+X): agiscono sulle celle
  selezionate o, dopo un semplice clic, sulla sola cella attiva. La copia
  mette negli appunti il testo delle celle separato da tabulazioni, che
  Excel incolla direttamente; Ctrl+X svuota solo quelle celle. L'incolla
  accetta le tabelle copiate da Excel a partire dalla prima cella
  selezionata (o dalla cella attiva), salta la riga delle intestazioni e
  accetta la virgola decimale (`145,600` = 145.600). Una cella vuota lascia
  il valore che c'era; un valore solo va in tutte le celle selezionate.
  Prima di sovrascrivere celle non vuote chiede conferma una volta. I
  canali interi si copiano e si tagliano selezionando il numero di riga
  (o dal menu della riga): copia e incolla di canali restano quelli di
  prima, e un canale copiato così si incolla intero nella riga della
  cella attiva.
- **Menu col tasto destro** su una selezione: Copia celle, Incolla, Riempi
  in basso, Serie…, Svuota celle.
- **Serie…**: valore iniziale (dalla prima cella), passo (frequenze in MHz,
  per esempio 0.025 per 25 kHz; nomi con incremento intero) e anteprima;
  scrive su tutte le celle selezionate della colonna.
- **Un solo passo di annulla** per ogni operazione (es. "Riempi 12 celle");
  le celle che la radio rifiuta non fermano il resto e compaiono in **un
  solo riepilogo** alla fine. Nelle operazioni multiple non ci sono
  domande: duplex `+`/`-` senza offset prende l'offset del piano di banda;
  un duplex `off` resta `off` (la trasmissione resta spenta) qualunque sia
  l'offset, e un offset zero su simplex resta simplex; i casi che
  richiederebbero una scelta vengono saltati e annotati. Una cella
  rifiutata non lascia modifiche a metà nel canale.
- **Viste filtrate e ordinate**: si scrive solo nelle righe visibili (le
  nascoste non vengono toccate) e nell'ordine a schermo, ogni riga legata
  alla sua memoria. Le schede in sola lettura permettono solo la copia;
  con la radio in diretta, oltre 20 celle compare un avanzamento
  annullabile.
- **Limiti**: niente formule, niente maniglia orizzontale (trascinare verso
  destra), né riempimento verso l'alto.

## Altri strumenti
- **Backup** (File > Backup…): elenco dei backup automatici, apertura,
  confronto con la scheda aperta.
- **Controllo frequenze** (Radio > Controlla frequenze…, regole italiane):
  bande solo ricezione, licenza necessaria, potenza oltre i limiti LPD
  (10 mW) e PMR446 (0,5 W).
- **Preset radioamatori italiani** tra le configurazioni predefinite
  (File > Apri la configurazione predefinita; la lista europea LPD/PMR
  c'era già):
  - "IT Chiamata e simplex radioamatori": chiamata 145.500/433.500,
    simplex 2 m e 70 cm, APRS, voce ISS;
  - "IT Ponti ripetitori 2 m": R0-R7 e canali "alfa" (RV48-RV63), −600 kHz;
  - "IT Ponti ripetitori 70 cm": RU0-RU15 (uscita 431.600-431.975), −1,6 MHz;
  - "IT Satelliti FM radioamatori": SO-50 (con canale per armare il timer),
    ISS, AO-123, PO-101, AO-91, in split con CTCSS e tre passi di Doppler
    (A inizio, C centro, F fine passaggio);
  - "IT Radioamatori tutto in uno": tutte le liste insieme, 72 canali che
    stanno nelle 128 memorie di una UV-9R;
  - "IT LPD e PMR446": i 69 canali LPD e i 16 PMR446 alla potenza di legge
    (10 mW e 0,5 W). Sono bande senza licenza ma solo per apparati
    omologati: la UV-9R non lo è e scende al minimo a 1 W, perciò il
    controllo frequenze li segnala. Non sta nel "tutto in uno" (non ci
    starebbe nelle 128 memorie).

  Le liste generate vengono da `tools/make_ham_presets.py`: per aggiornare i
  satelliti (la tabella AMSAT cambia) si modifica lo script e lo si rilancia.
  Il tono di accesso dei ponti (1750 Hz o CTCSS) dipende dal singolo ponte e
  non è impostato.
- **Scheda canali tascabile** (File > Scheda canali tascabile…): anteprima di
  stampa A4 su due colonne.
- **Mappa della memoria** (Radio > Mappa della memoria…): dump esadecimale
  colorato per funzione, con le zone che il driver non descrive (taratura).
- **Import/export Excel** (`.xlsx` lettura/scrittura, `.xls` lettura).

## Lingue
Tutti i testi nuovi di CHIRP Plus (213 stringhe) sono tradotti nelle 17
lingue di CHIRP più l'inglese di partenza, con la terminologia che ogni
traduzione ufficiale già usa (per esempio "станция" in russo, "無線機" in
giapponese). Le traduzioni stanno in `tools/translations/<lingua>.json`
(`it.json` è l'elenco di riferimento delle chiavi):
```
.venv\Scripts\python tools\add_translations.py --check   # solo verifica
.venv\Scripts\python tools\add_translations.py           # aggiunge ai .po
.venv\Scripts\python tools\compile_locales.py            # .po -> .mo
```
Lo script si ferma se una lingua manca di una stringa o se i segnaposto
(`%s`, `%(nome)s`…) non coincidono con l'originale. Le traduzioni ufficiali
già presenti non vengono toccate. Una stringa nuova va aggiunta in tutti i
file JSON.

## Diritti e licenze
CHIRP Plus è una versione modificata e non ufficiale di CHIRP (vedi
`NOTICE`), sotto la stessa GPLv3. Gli avvisi di copyright e licenza dei
file originali sono invariati; i file nuovi sono "Copyright 2026 CHIRP
Plus contributors". La finestra Informazioni (anche al primo avvio) dice
che è una versione modificata e su cosa si basa.

La build (`chirp-plus.spec` con `tools/third_party.py`) raccoglie le
licenze di tutto ciò che PyInstaller mette nell'exe e le scrive in
`THIRD-PARTY-NOTICES.txt`, dentro il programma e accanto; il sorgente
delle librerie LGPL/MPL (suds, yattag, certifi) va in
`CHIRP-Plus-librerie-sorgente.zip`. Se una libreria nuova finisce nell'exe
senza un testo di licenza, la build si ferma: il testo va aggiunto in
`tools/third_party_licenses/<nome>.txt`.

Verso i servizi del progetto CHIRP: niente statistiche d'uso
(`report.report_model` non invia nulla) e "Segnala un bug" apre le issue
di questa repo; resta il controllo, in sola lettura, di nuove versioni
ufficiali.

## Uso
Il programma compilato è in `%LOCALAPPDATA%\Programs\CHIRP-Plus\chirpwx.exe`;
lo ZIP è in `dist\`. Usa le stesse impostazioni del CHIRP ufficiale
(`%APPDATA%\CHIRP`).

## Sviluppo
```
.venv\Scripts\python chirpwx.py                    # avvio dal sorgente
.venv\Scripts\python -m pytest tests\unit -n 8     # test
.venv\Scripts\python tools\build_windows.py        # build + ZIP
.venv\Scripts\python tools\sync_upstream.py        # novità di CHIRP ufficiale
.venv\Scripts\python tools\sync_upstream.py --merge
```
CHIRP è GPLv3: se distribuisci questa versione devi rendere disponibile anche
il sorgente modificato.
