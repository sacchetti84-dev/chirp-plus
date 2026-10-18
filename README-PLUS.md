# CHIRP Plus

Versione modificata di CHIRP basata sulla build ufficiale `next-20261016`
(commit upstream `832d349e`, ramo `baofeng-plus`). Ha tutti i driver e le
funzioni dell'originale, più queste modifiche:

## Rilevamento automatico del cavo (`chirp/wxui/portdetect.py`)
- Riconosce i chip dei cavi di programmazione dall'ID USB: CH340/CH341/CH343,
  PL2303 (tutte le revisioni), FTDI, CP210x, STM32 VCP.
- Mette i cavi in cima alla lista e li sceglie da solo; Bluetooth e porte
  integrate (COM1) finiscono in fondo.
- Ricorda la porta usata per ogni modello, ma non la preferisce a un cavo vero
  se era una porta sbagliata (es. COM1).
- Hot-plug: quando colleghi il cavo con il dialogo aperto lo seleziona subito;
  se lo scolleghi te lo segnala.
- Avvisa dei PL2303 contraffatti/non supportati e non li sceglie.

## Interfaccia
- Barra strumenti: Scarica dalla radio, Carica sulla radio, Apri, Salva (si può
  nascondere da Visualizza > Mostra barra strumenti).
- Stato del cavo sempre visibile nella barra strumenti e in quella di stato.
- Pagina di benvenuto con i pulsanti "Scarica dalla radio" e "Apri un file".
- Dialogo radio: istruzioni, riga di stato del cavo (verde/arancio/rosso),
  pulsante Aggiorna, pulsanti "Scarica"/"Carica" al posto di OK.
- "Cerca...": trova la radio scrivendo parte del nome (es. `uv5r`, `uv9r`).
- Traduzione italiana completa delle nuove voci.

## Aspetto "visore notturno" (`chirp/wxui/theme.py`)
- Nero e verde fosforo, accenti lime; avvisi in ambra, errori in rosso.
- Tema scuro nativo di Windows per menu, barre del titolo, barre di scorrimento
  e finestre di sistema.
- Pagina iniziale a mirino (griglia, reticolo, angoli) con titolo in Stencil e
  stato del cavo al centro del reticolo (PRONTO / IN ATTESA / NESSUN SEGNALE).
- Griglia memorie, impostazioni, schede e dialoghi in font monospace (Cascadia
  Mono, poi Consolas), etichette in maiuscolo, icone ricolorate.
- Si spegne da Visualizza > Aspetto visore notturno (vale dal riavvio).

## Uso
Il programma compilato è in `%LOCALAPPDATA%\Programs\CHIRP-Plus\chirpwx.exe`;
lo ZIP è in `dist\`. Usa le stesse impostazioni del CHIRP ufficiale
(`%APPDATA%\CHIRP`).

## Sviluppo
```
.venv\Scripts\python chirpwx.py                 # avvio dal sorgente
.venv\Scripts\python -m pytest tests\unit -n 8  # test
.venv\Scripts\python tools\build_windows.py     # build + ZIP
```
CHIRP è GPLv3: se distribuisci questa versione devi rendere disponibile anche
il sorgente modificato.
