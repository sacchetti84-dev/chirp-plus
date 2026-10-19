# CHIRP Plus

Versione modificata di CHIRP basata sulla build ufficiale `next-20261016`
(commit upstream `832d349e`, ramo `baofeng-plus`). Ha tutti i driver e le
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
  strette di mano dei driver Baofeng (solo identificazione, nessuna lettura
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

## Altri strumenti
- **Backup** (File > Backup…): elenco dei backup automatici, apertura,
  confronto con la scheda aperta.
- **Controllo frequenze** (Radio > Controlla frequenze…, regole italiane):
  bande solo ricezione, licenza necessaria, potenza oltre i limiti LPD
  (10 mW) e PMR446 (0,5 W).
- **Lista italiana** "IT Chiamata e simplex radioamatori" tra le
  configurazioni predefinite (la lista europea LPD/PMR c'era già).
- **Scheda canali tascabile** (File > Scheda canali tascabile…): anteprima di
  stampa A4 su due colonne.
- **Mappa della memoria** (Radio > Mappa della memoria…): dump esadecimale
  colorato per funzione, con le zone che il driver non descrive (taratura).
- **Import/export Excel** (`.xlsx` lettura/scrittura, `.xls` lettura).

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
