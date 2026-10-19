# Piano: stile terminale e nuove funzioni

Ogni passo segue lo stesso ciclo: scrivo → test unitari → prova nell'app
(sorgente e, dove serve, eseguibile) → correggo → passo successivo.
Le prove sulla radio vera sono **solo in lettura**, salvo permesso esplicito
per scrivere.

## Legenda colori (unica per tutta l'app)

| Codice | Colore | Quando |
|---|---|---|
| `ok`   | verde `#16C60C`    | riuscito, cavo pronto, verifica superata |
| `warn` | giallo `#F9C74F`   | attenzione: più cavi, fuori banda, potenza alta |
| `bad`  | rosso `#FF5F5F`    | errore, cavo assente, driver da cambiare |
| `info` | ciano `#61D6D6`    | messaggi neutri, porte, frequenze |
| `rx`   | blu `#5F9FFF`      | **legge** dalla radio (Scarica, Rileva) |
| `tx`   | arancio `#FF8F3F`  | **scrive** nella radio (Carica, In serie) |
| `file` | bianco `#F2F2F2`   | file: apri, salva, importa, esporta |
| `code` | magenta `#D670D6`  | toni e codici (CTCSS/DCS) |
| `dim`  | grigio `#767676`   | testo secondario, canali vuoti |

Nella griglia memorie ogni colonna ha il colore della sua funzione:
frequenza/duplex/offset `info`, nome `file`, toni e codici `code`,
potenza `tx`, scansione `rx`, commento `dim`.

## Passi

1. **Stile terminale**: nero, monospace ovunque, pagina iniziale come un
   avvio di sistema con righe `[ OK ]`/`[WARN]`/`[ERR ]`, prompt con
   cursore, comandi rapidi da tastiera, legenda. Console eventi a colori in
   basso. Aspetto classico sempre disponibile.
2. **Rileva radio**: identificazione dal cavo (solo lettura), elenco dei
   modelli compatibili con la risposta.
3. **Confronto e verifica**: prima di caricare mostra le differenze con la
   radio; dopo, riscarica e confronta.
4. **Programmazione in serie**: stessa immagine su più radio, una dopo
   l'altra, con verifica e riepilogo.
5. **Backup**: elenco, confronto, apertura dei backup automatici.
6. **Canali italiani** (PMR446, LPD, chiamata) e **controllo frequenze**.
7. **Scheda tascabile** stampabile, **mappa della memoria** a colori,
   **cambio stile senza riavvio** (dove possibile).
8. **Allineamento con CHIRP ufficiale**: script che integra le novità.
9. Test completi, build, prova finale.
