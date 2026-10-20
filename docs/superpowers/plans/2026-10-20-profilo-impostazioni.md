# Profili di impostazioni — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** un comando Radio > Applica profilo impostazioni che applica a una radio scaricata il profilo "IT Team Sierra - impostazioni UV-5R" (impostazioni + colonne extra dei canali), mostrando prima le modifiche.

**Architecture:** `chirp/settings_profile.py` (senza wx) carica i profili JSON di `chirp/settings_profiles/`, calcola un `Plan` su copie fresche di impostazioni e memorie, e lo applica; `chirp/wxui/main.py` aggiunge il menu, mostra il piano con `changes.ChangesDialog` e applica (memorie tramite l'editor, in un `undo_context`).

**Tech Stack:** Python 3.14, wxPython 4.3.2, pytest; traduzioni con `tools/add_translations.py`.

**Spec:** `docs/superpowers/specs/2026-10-20-profilo-impostazioni-design.md`

## Global Constraints

- I dati propri della radio non si toccano: il profilo non contiene firmware, messaggi di avvio, limiti di frequenza, codici DTMF, frequenze VFO.
- Una voce non applicabile salta solo quella voce e finisce nei `problems`; il resto si applica.
- Niente modifiche alla radio finché l'utente non conferma; "Annulla" non cambia nulla.
- Valori come li mostra CHIRP: testo dell'opzione per le liste, intero per gli interi, `true`/`false` per i booleani, testo per le stringhe; `"@NOME"` solo per voci intere; chiavi alternative separate da `|`.
- Solo immagini (clone mode): radio in diretta e CSV → messaggio, nessuna azione.
- File nuovi in `chirp/` con `# Copyright 2026 CHIRP Plus contributors` + avviso GPLv3; test senza intestazione (stile tests/unit). flake8 pulito. Nessun nome "Baofeng" nei testi nuovi dell'interfaccia (i nomi di modello nei driver e il campo `radios` del profilo vanno bene).
- Testi nuovi tradotti in tutte le 17 lingue + it.

## Review Focus

1. **JSON del profilo scritto a mano con un errore** (virgola in più, BOM) → `ProfileError` con il nome del file, nessun crash (test in Task 1).
2. **Profilo applicato due volte** → la seconda volta "nessuna modifica", nessun dialogo vuoto (test in Task 2 e Task 3).
3. **Nomi dei canali con spazi finali o minuscole** (la UV-5R riempie i nomi a 7 caratteri) → `@SIERRA1` e `SIERRA*` li trovano lo stesso (test in Task 2).
4. **Scheda CSV o radio in diretta aperta** → messaggio, nessuna eccezione (test in Task 3).
5. **Profilo per un altro modello** → conferma richiesta; con "No" niente cambia (test in Task 3).

---

### Task 1: Caricare i profili

**Files:**
- Create: `chirp/settings_profile.py`, `chirp/settings_profiles/__init__.py` (vuoto, per `importlib.resources`), `chirp/settings_profiles/IT Team Sierra - impostazioni UV-5R.json`
- Modify: `chirp-plus.spec` (`tree('chirp/settings_profiles', 'chirp/settings_profiles')`), `MANIFEST.in` (`include chirp/settings_profiles/*`), `setup.py` se elenca i pacchetti dati
- Test: `tests/unit/test_settings_profile.py`

**Interfaces:**
- Produces: `class ProfileError(Exception)`; `@dataclass Profile: name: str; radios: list[str]; settings: dict[str, object]; memories: list[dict]; path: str`; `load(path: str) -> Profile`; `shipped_profiles() -> list[Profile]` (ordinati per `name`); `fits(profile, radio) -> bool` (`'%s %s' % (radio.VENDOR, radio.MODEL) in profile.radios`).

- [ ] **Step 1: Write the failing tests**

```python
def test_shipped_team_sierra_profile():
    names = [p.name for p in settings_profile.shipped_profiles()]
    assert 'IT Team Sierra - impostazioni UV-5R' in names

def test_load_rejects_broken_json(tmp_path):     # trailing comma -> ProfileError mentioning the file name
def test_load_accepts_utf8_bom(tmp_path):
def test_load_requires_name_and_settings(tmp_path)
def test_fits(uv5r_radio):                       # True for the UV-5R test image, False after changing MODEL on a copy class
```

- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests/unit/test_settings_profile.py -q` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the module and the JSON file. JSON content (spec §4), exactly:
  `settings`: `squelch 3`, `save "1:2"`, `abr 5`, `beep false`, `roger false`, `voice false`, `timeout "60 sec"`, `mdfa "Name"`, `mdfb "Name"`, `wtled "Off"`, `rxled "Off"`, `txled "Off"`, `vox "OFF"`, `tdr true`, `tdrab "A"`, `almod "Site"`, `screv "CO"`, `bcl true`, `autolk true`, `fmradio false`, `ste true`, `rpste "OFF"`, `reset false`, `menu false`, `"limits_old.uhf.enable|limits_new.uhf.enable": false`, `workmode "Channel"`, `"wmchannel.mrcha": "@SIERRA1"`, `"wmchannel.mrchb": "@PMR 01"`, `"vfoa.txpower": "Low"`, `"vfob.txpower": "Low"`, `"vfoa.widenarr": "Narrow"`, `"vfob.widenarr": "Narrow"`, `"ani.aniid": "Off"`, `dtmfst "OFF"`; `memories`: `[{"names": "*", "extra": {"pttid": "Off"}}, {"names": "SIERRA*", "extra": {"bcl": true}}]`; `radios`: `["Baofeng UV-5R"]`. Read files with `encoding='utf-8-sig'`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `settings_profile: Load settings profiles and the Team Sierra one`.

### Task 2: Piano e applicazione

**Files:**
- Modify: `chirp/settings_profile.py`
- Test: `tests/unit/test_settings_profile.py`

**Interfaces:**
- Consumes: Task 1.
- Produces: `@dataclass Plan: settings_tree: RadioSettings; changes: list[radio_compare.Change]; memories: list[Memory]; problems: list[tuple[str, str]]`; `plan(profile, radio) -> Plan`; `apply(plan, radio) -> None` (`radio.set_settings(plan.settings_tree)`, then `radio.set_memory(m)` for each memory).
- `changes` use `radio_compare.Change(kind=radio_compare.CHANGED, what='setting', where=<setting label>, before=<old text>, after=<new text>)` for settings and `what='memory', where=<memory number>` with `before/after` like `'pttid: EOT'` → `'pttid: Off'` for memory extras (one Change per changed memory, listing its changed columns joined with `, `).

- [ ] **Step 1: Write the failing tests** (UV-5R test image; import the "IT Team Sierra" CSV into it from memory 0 with `import_logic.import_mem`, as `tests/unit/test_ham_presets.py` reads presets):

```python
def test_plan_does_not_touch_the_radio(sierra_radio)      # get_settings() values unchanged after plan()
def test_every_profile_setting_applied(sierra_radio)      # after apply(): squelch 3, save '1:2', timeout '60 sec', tdr True, uhf enable False...
def test_at_name_resolves_memory_number(sierra_radio)      # wmchannel.mrcha == number of SIERRA1, mrchb == number of 'PMR 01'
def test_names_match_case_and_trailing_spaces(sierra_radio)
def test_alternative_keys_use_the_first_present(sierra_radio)   # limits_old.uhf.enable on this image
def test_problems_do_not_stop_the_rest(sierra_radio)      # unknown key, 'save': 'never', 'squelch': 42, '@NOPE' -> 4 problems, others applied
def test_memory_rules(sierra_radio)                        # pttid Off on every non-empty memory, bcl True only on SIERRA*
def test_second_plan_is_empty(sierra_radio)                # apply then plan again -> no changes
def test_shipped_profile_is_valid_for_uv5r(uv5r_radio)     # every key (one alternative) exists and every value is accepted: plan().problems only about '@' names when no preset is loaded
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** `plan` on a fresh `radio.get_settings()` tree (find settings by `get_name()` walking groups) and fresh `radio.get_memory(n)` copies; set values through each value object's own setter so its validation rejects bad values (catch `ValueError`/`settings.InvalidValueError` → problem); `'@NAME'` matches `mem.name.strip().upper()`; `names` patterns with `fnmatch.fnmatchcase` on the upper-cased stripped name. Only keep settings/memories whose value actually changes.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `settings_profile: Plan and apply a profile`.

### Task 3: Comando nel menu Radio

**Files:**
- Modify: `chirp/wxui/main.py` (menu near `_memmap_menu_item` ~1144; new handler next to `_menu_memmap` ~2260)
- Test: `tests/unit/test_settings_profile_ui.py` (real wx: reuse the skip-if-mock pattern and the `real_wx` fixture idea from `tests/unit/test_memedit_cells.py`; temp `ChirpConfig` before importing wx modules)

**Interfaces:**
- Consumes: `settings_profile.shipped_profiles`, `load`, `fits`, `plan`, `apply`; `changes.ChangesDialog(parent, changes, title, action_label, action_tone='tx', columns=(before, after))`; `ChirpEditorSet.iter_editors(onlycls)`; `ChirpSettingsEdit.refresh()`; memedit `undo_context(name)`, `set_memory(mem)`.
- Produces: `ChirpMain._menu_settings_profile(profile_or_none)`; submenu `_('Apply settings profile')` with one item per shipped profile, a separator and `_('From file...')`.

- [ ] **Step 1: Write the failing tests**

```python
def test_menu_lists_profiles(main_window)
def test_apply_shows_changes_then_applies(main_window, sierra_tab)     # patch ChangesDialog.ShowModal -> wx.ID_OK; settings changed; one undo item 'Profile ...'; settings tab refreshed
def test_cancel_changes_nothing(main_window, sierra_tab)               # ShowModal -> wx.ID_CANCEL
def test_already_applied_says_so(main_window, sierra_tab)              # second run: info message, no ChangesDialog
def test_csv_tab_is_refused(main_window)                               # open a stock CSV: message, nothing raised
def test_other_model_asks_first(main_window, other_radio_tab)          # 'No' -> nothing changed
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** Refuse with `wx.MessageBox` when no editorset, `isinstance(radio, chirp_common.LiveRadio)` or not `chirp_common.CloneModeRadio`. Model mismatch: `wx.MessageDialog` `_('The profile is for %s. Apply it anyway?')`. No changes: `_('The radio already has these settings.')`. Dialog: title `_('Settings profile')`, action `_('Apply')`, columns `(_('Now'), _('With the profile'))`, plus problems shown after confirm in one `wx.MessageDialog` titled `_('Some settings were not changed')` (same 19-line cap style as the grid summary). On OK: `radio.set_settings(plan.settings_tree)`; memories via the memedit of the editorset inside `undo_context(_('Profile %s') % profile.name)` with `set_memory`; refresh the settings editor(s); post `EditorChanged`; `console.log('file', _('Applied profile %s') % profile.name)`. "From file...": `wx.FileDialog` with wildcard `*.json`; `ProfileError` → `wx.MessageBox` with its text.
- [ ] **Step 4: Run** the file and all of `tests/unit` — Expected: PASS (known flaky: `test_serialtrace::test_timeout_write_read_warning`).
- [ ] **Step 5: Commit** `wxui: Apply settings profile command`.

### Task 4: Lingue, documentazione, prova nell'app

**Files:**
- Modify: `tools/translations/*.json` (17 files), `chirp/locale/*.po` (via script), `README-PLUS.md`, `.github/README.md`

- [ ] **Step 1:** add every new `_()` string of Tasks 1-3 to all translation files; `.venv\Scripts\python tools/add_translations.py --check` → "17 languages, N strings each: placeholders OK"; apply; `tools/compile_locales.py`.
- [ ] **Step 2:** README-PLUS: under the "IT Team Sierra" preset, how to apply the profile (Scarica → importa il preset → Radio > Applica profilo impostazioni → controlla l'elenco → Applica → Carica / Programma più radio), what it changes and what it never touches, that settings are not undoable (backup). Landing page: one sentence in the Italian presets section and the Team Sierra row.
- [ ] **Step 3:** manual check in the real app (scripted like `tools/screenshots.py`): open the UV-5R test image, import Team Sierra, apply the profile, see the list, apply, see the Settings tab updated; no traceback.
- [ ] **Step 4:** `.venv\Scripts\python -m pytest tests/unit -q` and flake8 on touched files — Expected: pass.
- [ ] **Step 5: Commit** `Settings profiles: translations and docs`.
