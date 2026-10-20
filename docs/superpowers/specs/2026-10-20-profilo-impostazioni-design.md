# Profili di impostazioni — progetto

Data: 20/10/2026 · Stato: approvato a voce, da rivedere per iscritto

## Obiettivo

Il preset "IT Team Sierra" porta solo canali (è un CSV). Andrea vuole che
con lo stesso preset arrivino anche le impostazioni consigliate della
UV-5R, così che ogni radio della squadra abbia canali **e** impostazioni
uguali senza rifarle a mano.

**Successo** = dopo aver scaricato una UV-5R e importato "IT Team
Sierra", un comando applica tutte le impostazioni consigliate e le colonne
extra dei canali, mostrando prima cosa cambia; poi si carica (anche con
Programma più radio). I dati propri di ogni radio (firmware, messaggi di
avvio, limiti di banda, codici DTMF, frequenze VFO) non vengono toccati.

### Decisioni prese con Andrea

| Domanda | Scelta |
|---|---|
| Come portare le impostazioni | profilo di impostazioni applicato alla radio scaricata (non un'immagine .img pronta, non solo istruzioni) |
| Contenuto | le impostazioni consigliate in chat, più `pttid = Off` su tutti i canali e `bcl = On` sui SIERRA |

### Fuori da questa versione

Creare un profilo dalle impostazioni di una radio, profili per altri
modelli, applicazione a radio in diretta (live).

## Stato attuale

- Le impostazioni di un driver sono un albero di `RadioSettingGroup` /
  `RadioSetting` (`chirp/settings.py`), letto con `radio.get_settings()` e
  scritto con `radio.set_settings(tree)`. Ogni voce ha un nome interno
  stabile (`get_name()`, es. `squelch`, `limits_old.uhf.enable`) e un
  valore con i suoi vincoli (`RadioSettingValueList` con opzioni,
  `Integer` con minimo/massimo, `Boolean`, `String`).
- La UV-5R (`chirp/drivers/uv5r.py`) chiama i limiti di banda
  `limits_old` o `limits_new` secondo il firmware (riga ~2042).
- Le colonne extra dei canali della UV-5R sono `bcl` (Boolean), `pttid`
  (List: Off/BOT/EOT/Both) e `scode`.
- La scheda Impostazioni è `chirp/wxui/settingsedit.py`; il confronto
  prima del caricamento usa `chirp/wxui/changes.py` (`ChangesDialog`).
- I preset stanno in `chirp/stock_configs` e compaiono tutti nel menu
  "Apri la configurazione predefinita"; la build li include con `tree()`
  in `chirp-plus.spec`.

## Progetto

### 1. Il file profilo

- Cartella nuova `chirp/settings_profiles/` (pacchetto dati, inclusa in
  exe, build a cartelle, sorgente e `MANIFEST.in`). Non in
  `stock_configs`, altrimenti finirebbe nel menu dei preset.
- Formato JSON, UTF-8:

```json
{
  "name": "IT Team Sierra - impostazioni UV-5R",
  "radios": ["Baofeng UV-5R"],
  "settings": {
    "squelch": 3,
    "save": "1:2",
    "limits_old.uhf.enable|limits_new.uhf.enable": false,
    "wmchannel.mrcha": "@SIERRA1"
  },
  "memories": [
    {"names": "*", "extra": {"pttid": "Off"}},
    {"names": "SIERRA*", "extra": {"bcl": true}}
  ]
}
```

- `radios`: modelli "VENDOR MODEL" a cui è destinato.
- `settings`: chiave = nome interno della voce; più nomi alternativi
  separati da `|` (vale il primo che la radio ha). Valore = come lo
  mostra CHIRP: testo di un'opzione per le liste, numero per gli interi,
  `true`/`false` per i booleani, testo per le stringhe.
- Valore `"@NOME"` (solo per voci intere) = numero della memoria che si
  chiama NOME (confronto senza maiuscole/minuscole e spazi finali); se non
  esiste la voce è saltata.
- `memories`: regole applicate in ordine; `names` è un modello con `*`
  (fnmatch, senza maiuscole/minuscole); `extra` = colonna extra → valore,
  con le stesse regole dei valori delle impostazioni. Solo memorie non
  vuote.

### 2. Motore senza interfaccia: `chirp/settings_profile.py`

- `load(path) -> Profile` (dataclass `name, radios, settings, memories,
  path`); errore leggibile (`ProfileError`) se il JSON non è valido o
  manca `name`/`settings`.
- `shipped_profiles() -> list[Profile]` dai file di
  `chirp/settings_profiles/*.json`, ordinati per nome.
- `fits(profile, radio) -> bool` (VENDOR MODEL tra `radios`).
- `plan(profile, radio) -> Plan` calcola **senza modificare la radio**:
  - `settings_tree`: copia dell'albero di `get_settings()` con i valori
    nuovi già impostati;
  - `setting_changes: list[(etichetta, ora, nuovo)]` solo per le voci che
    cambiano davvero;
  - `memories: list[Memory]` copie dei canali modificati, e
    `memory_changes: list[(canale, colonna, ora, nuovo)]`;
  - `problems: list[(voce, motivo)]`: voce assente, valore non ammesso
    (fuori lista, fuori intervallo, tipo sbagliato), `@NOME` non trovato,
    colonna extra assente. Un problema salta solo quella voce.
- `apply(plan, radio)`: `radio.set_settings(plan.settings_tree)` e
  `radio.set_memory(m)` per ogni memoria del piano. Il controllore UI
  usa i propri percorsi (vedi sotto) per le memorie, così ottiene undo.

### 3. Interfaccia

- Menu **Radio > Applica profilo impostazioni** con un sottomenu: i
  profili inclusi, separatore, "Da file…" (apre un JSON).
- Funziona sulla scheda aperta se è un'immagine (clone mode); su radio in
  diretta o file CSV mostra un messaggio e non fa nulla.
- Se `fits()` è falso: domanda "Il profilo è per %s; applicarlo
  comunque?".
- Mostra le modifiche in un `ChangesDialog` (colonne: Cosa / Ora / Con il
  profilo), con l'elenco dei problemi sotto o in un riepilogo; "Applica" /
  "Annulla". Se non cambia nulla: messaggio "La radio ha già queste
  impostazioni".
- Su "Applica": impostazioni con `set_settings`, canali con l'editor
  delle memorie in un solo `undo_context` ("Profilo %s"); la scheda
  Impostazioni si ricarica; evento "modificato"; riga in console
  (`[FILE]` / tono `file`).
- Le impostazioni non hanno annulla (come oggi in CHIRP): il dialogo lo
  dice in una riga ("Per tornare indietro riapri il backup del download").

### 4. Il profilo "IT Team Sierra - impostazioni UV-5R"

`squelch 3`, `save 1:2`, `abr 5`, `beep false`, `roger false`,
`voice false`, `timeout 60 sec`, `mdfa Name`, `mdfb Name`,
`wtled/rxled/txled Off`, `vox OFF`, `tdr true`, `tdrab A`,
`almod Site`, `screv CO`, `bcl true`, `autolk true`, `fmradio false`,
`ste true`, `rpste OFF`, `reset false`, `menu false`,
`limits_old.uhf.enable|limits_new.uhf.enable false`,
`workmode Channel`, `wmchannel.mrcha @SIERRA1`,
`wmchannel.mrchb @PMR 01`, `vfoa.txpower Low`, `vfob.txpower Low`,
`vfoa.widenarr Narrow`, `vfob.widenarr Narrow`, `ani.aniid Off`,
`dtmfst OFF`. Canali: `*` → `pttid Off`; `SIERRA*` → `bcl true`.

### 5. Lingue, documentazione, build

- Testi nuovi in `tools/translations/*.json` per tutte le 17 lingue +
  italiano.
- README-PLUS (sezione preset: come applicare il profilo) e landing page
  (riga accanto al preset Team Sierra).
- `chirp-plus.spec`: `tree('chirp/settings_profiles', ...)`;
  `MANIFEST.in` e pacchetto Python (`chirp/settings_profiles/__init__.py`
  vuoto se serve a `importlib.resources`).

## Collaudo

- `tests/unit/test_settings_profile.py` (immagine
  `tests/images/Baofeng_UV-5R.img`, senza wx):
  - ogni voce del profilo applicata con il valore giusto nell'albero
    della copia; la radio originale invariata finché non si chiama
    `apply`;
  - `@SIERRA1` risolto dopo l'import di "IT Team Sierra";
  - voce assente, valore fuori lista/intervallo, `@NOME` mancante →
    `problems`, il resto applicato;
  - alternative `a|b`: usata la prima presente;
  - `fits()` vero per UV-5R, falso per un altro modello;
  - regole `memories`: `pttid` su tutti i canali non vuoti, `bcl` solo
    sui SIERRA;
  - dopo `apply`, `get_settings()` della radio riporta i valori nuovi.
- Validità del file incluso: ogni chiave del profilo Team Sierra esiste
  nella UV-5R di test (almeno una delle alternative) e ogni valore è
  ammesso.
- Test nella finestra vera (`tests/unit/test_memedit_cells.py` o un file
  nuovo con la stessa fixture `real_wx`): menu presente, dialogo con le
  modifiche (pacchettizzato), applicazione, una sola voce di annulla per i
  canali, scheda Impostazioni ricaricata.
- Prova nell'app: apri l'immagine di test, importa Team Sierra, applica il
  profilo, confronto prima del caricamento simulato.

## Criteri di accettazione

1. Il menu mostra il profilo incluso e "Da file…".
2. Il dialogo elenca prima ogni modifica; "Annulla" non cambia nulla.
3. Dopo "Applica" le impostazioni e le colonne dei canali sono quelle del
   profilo; i dati propri della radio sono invariati.
4. Le voci non applicabili sono elencate e non fermano il resto.
5. Testi nuovi in 18 lingue; test unitari tutti verdi.
