# Griglia delle memorie "come Excel" — piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** selezione a celle, copia/incolla di celle da e verso Excel, Ctrl+D, Ctrl+Invio, Canc, serie (maniglia e dialogo) nella griglia delle memorie di CHIRP Plus, con validazione della radio, un solo passo di annulla e un solo riepilogo degli errori.

**Architecture:** tre strati. `chirp/grid_fill.py` (puro: serie, tabelle incollate, celle bersaglio); `chirp/wxui/cellops.py` (senza wx: applica liste di modifiche alle memorie tramite un piccolo protocollo verso l'editor); `chirp/wxui/memedit.py` (selezione, tastiera, menu, appunti, annulla, dialoghi) più due file di interfaccia nuovi, `fillhandle.py` (maniglia) e `seriesdialog.py`.

**Tech Stack:** Python 3.14, wxPython 4.3.2 (`wx.grid.Grid`), pytest; traduzioni con `tools/add_translations.py`.

**Spec:** `docs/superpowers/specs/2026-10-19-griglia-excel-design.md`

## Global Constraints

- Le operazioni di oggi su righe intere (copia/incolla canali, elimina, sposta, ordina, trascina dal numero di riga) restano identiche.
- Ogni operazione multipla = **un solo** `undo_context` (nome visibile nel menu Modifica: "Riempi %i celle", "Incolla %i celle", "Svuota %i celle", "Serie in %i celle").
- Le celle rifiutate non fermano l'operazione: **un solo** riepilogo alla fine (massimo 19 righe + "...and %i more", come `_cb_paste_memories`).
- Le operazioni multiple non aprono mai domande su offset/duplex/incrociati (`interactive=False`).
- Si scrive solo nelle righe visibili (filtro); in vista ordinata ogni riga resta legata alla sua memoria (`row2mem`).
- Per ogni riga si applica prima la frequenza, poi le altre colonne nell'ordine della griglia.
- Celle vuote in una tabella incollata = valore lasciato com'era. Virgola decimale accettata nelle colonne `freq`, `offset`, `rtone`, `ctone`, `power`.
- Canc: `name`, `comment` → `''`; `tmode`, `duplex` (+ `offset` = 0), `skip`, `dtcs_polarity`, `cross_mode`, `rtone`, `ctone`, `dtcs`, `rx_dtcs` → valori di `chirp_common.Memory()`; `freq`, `mode`, `tuning_step`, `power` → rifiutate con "has no empty value".
- Radio in diretta: oltre 20 celle `wx.ProgressDialog` annullabile.
- Nessun nome "Baofeng" nei testi nuovi. Testi nuovi in inglese nel codice, tradotti in tutte le 17 lingue + it.
- File nuovi con intestazione `# Copyright 2026 CHIRP Plus contributors` + avviso GPLv3 come gli altri file di CHIRP Plus.
- flake8 pulito sui file toccati (tranne l'E722 già presente in `generic_csv.py`).

## Review Focus

1. **Selezione che attraversa righe nascoste dal filtro** → quelle righe non vengono toccate (test in Task 2 e Task 5).
2. **Incolla da Excel italiano con `145,600` e `88,5`** → accettati come 145.6 MHz e 88.5 Hz (test in Task 3).
3. **Incolla più lungo delle righe rimaste** → applicato fino all'ultima memoria, il resto contato nel riepilogo, nessuna eccezione (test in Task 2 e Task 6).
4. **Vista ordinata per nome, poi Ctrl+D** → i valori finiscono nelle memorie che si vedono in quelle righe, non nei numeri di riga originali (test in Task 5).
5. **Annulla dopo un'operazione con celle rifiutate** → ripristina esattamente le memorie modificate, quelle rifiutate restano come prima (test in Task 5).

---

### Task 1: Serie in `chirp/grid_fill.py`

**Files:**
- Create: `chirp/grid_fill.py`
- Test: `tests/unit/test_grid_fill.py`

**Interfaces:**
- Produces: `continue_series(values: list[str], count: int) -> list[str]`; `make_series(start: str, step: str, count: int) -> list[str]` (step numerico, es. `'0.025'`, o intero per i nomi); `to_number(text: str) -> float | None` (accetta la virgola decimale, `None` se non numerico).

- [ ] **Step 1: Write the failing tests**

```python
from chirp import grid_fill as gf

def test_single_value_repeats():
    assert gf.continue_series(['88.5'], 3) == ['88.5', '88.5', '88.5']

def test_frequency_step_12_5_khz():
    assert gf.continue_series(['145.600000', '145.612500'], 3) == [
        '145.625000', '145.637500', '145.650000']

def test_decimal_comma():
    assert gf.continue_series(['431,600', '431,625'], 2) == ['431.650', '431.675']

def test_numbered_names_keep_zero_padding():
    assert gf.continue_series(['CH08', 'CH09'], 2) == ['CH10', 'CH11']
    assert gf.continue_series(['RU0', 'RU1'], 2) == ['RU2', 'RU3']

def test_uneven_values_repeat_cyclically():
    assert gf.continue_series(['FM', 'NFM'], 3) == ['FM', 'NFM', 'FM']

def test_make_series():
    assert gf.make_series('431.600', '0.025', 3) == ['431.600', '431.625', '431.650']
    assert gf.make_series('RU0', '1', 3) == ['RU0', 'RU1', 'RU2']

def test_to_number():
    assert gf.to_number('145,6') == 145.6
    assert gf.to_number('High') is None
```

- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests/unit/test_grid_fill.py -q` — Expected: FAIL (module missing).
- [ ] **Step 3: Implement** the three functions. Numeric series: constant difference within 1e-6, decimals = max decimals among the inputs (comma counts as decimal point, output uses `.`). Names: regex `^(.*?)(\d+)(\D*)$`, same prefix/suffix, constant integer step, width = longest digit string when any input has a leading zero. Otherwise cycle the inputs. `make_series` uses the same two rules with an explicit step; the first item is `start` itself.
- [ ] **Step 4: Run** the tests — Expected: PASS.
- [ ] **Step 5: Commit** `grid_fill: Series for the spreadsheet-like grid`.

### Task 2: Tabelle incollate e celle bersaglio in `chirp/grid_fill.py`

**Files:**
- Modify: `chirp/grid_fill.py`
- Test: `tests/unit/test_grid_fill.py`

**Interfaces:**
- Produces: `parse_table(text: str) -> list[list[str]]`; `is_header_row(row: list[str], labels: list[str]) -> bool`; `target_cells(anchor_row: int, anchor_col: int, matrix: list[list[str]], visible_rows: list[int], ncols: int) -> tuple[list[tuple[int, int, str]], int]` (celle `(riga, colonna, testo)` e numero di valori scartati); `spread(value: str, cells: list[tuple[int, int]]) -> list[tuple[int, int, str]]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_parse_table_from_excel():
    assert gf.parse_table('a\tb\r\nc\t"d"\r\n') == [['a', 'b'], ['c', 'd']]

def test_header_row():
    assert gf.is_header_row(['Frequency', 'Name'], ['Frequency', 'Name', 'Tone'])
    assert not gf.is_header_row(['145.5', 'CHIA'], ['Frequency', 'Name'])

def test_target_cells_skip_hidden_rows_and_count_overflow():
    cells, dropped = gf.target_cells(
        anchor_row=1, anchor_col=0, matrix=[['1'], ['2'], ['3']],
        visible_rows=[0, 1, 3], ncols=5)
    assert cells == [(1, 0, '1'), (3, 0, '2')]
    assert dropped == 1

def test_target_cells_drop_extra_columns():
    cells, dropped = gf.target_cells(0, 4, [['a', 'b']], [0], ncols=5)
    assert cells == [(0, 4, 'a')] and dropped == 1

def test_empty_pasted_cell_is_kept_out():
    cells, _ = gf.target_cells(0, 0, [['', 'x']], [0], ncols=2)
    assert cells == [(0, 1, 'x')]

def test_spread_one_value():
    assert gf.spread('88.5', [(0, 3), (2, 3)]) == [(0, 3, '88.5'), (2, 3, '88.5')]
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** `target_cells` walks `visible_rows` from the first one `>= anchor_row`; each matrix row takes the next visible row; values past the last visible row or past `ncols - 1` are counted in `dropped`; empty strings produce no cell and are not counted.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `grid_fill: Pasted tables and target cells`.

### Task 3: Motore `chirp/wxui/cellops.py`

**Files:**
- Create: `chirp/wxui/cellops.py`
- Test: `tests/unit/test_cellops.py`

**Interfaces:**
- Consumes: `grid_fill.to_number`.
- Produces:
  - `class CellRejected(Exception)` (messaggio = motivo, già tradotto con `_()`).
  - `@dataclass CellEdit: row: int; col: int; text: str | None` (`None` = svuota).
  - `@dataclass BulkResult: changed: list[Memory]; problems: list[tuple[str, str]]` (`(etichetta memoria o cella, motivo)`).
  - Protocollo editor (duck typing): `memory_for_row(row) -> Memory` (copia; `KeyError` se assente), `column(col) -> col_def` (con `.name`), `apply_cell_value(mem, col_def, text, interactive=False) -> Memory` (solleva `CellRejected`), `validate(mem) -> tuple[list[str], list[str]]` (avvisi, errori).
  - `NUMERIC_COLUMNS = {'freq', 'offset', 'rtone', 'ctone', 'power'}`; `NO_EMPTY = {'freq', 'mode', 'tuning_step', 'power'}`.
  - `clear_cell(mem: Memory, name: str) -> None` (solleva `CellRejected` per `NO_EMPTY`).
  - `apply_edits(editor, edits: list[CellEdit]) -> BulkResult`.

- [ ] **Step 1: Write the failing tests** with a `FakeEditor` (memories by row, columns = objects with `.name`, `apply_cell_value` that sets `setattr(mem, name, text)` and rejects `'BAD'`, `validate` that errors when `mem.freq == 0` and warns when `name == 'WARN'`):

```python
def test_frequency_applied_before_other_columns():   # order of calls on one row
def test_rejected_cell_is_reported_others_applied():
def test_validation_error_skips_the_row():
def test_validation_warning_keeps_the_memory():
def test_empty_memory_name_only_is_rejected():       # freq 0 -> validate error
def test_decimal_comma_in_numeric_columns():         # '88,5' reaches apply as '88.5'
def test_clear_cell_semantics():
    mem = chirp_common.Memory(); mem.name = 'X'; mem.duplex = '-'; mem.offset = 600000
    cellops.clear_cell(mem, 'name'); cellops.clear_cell(mem, 'duplex')
    assert (mem.name, mem.duplex, mem.offset) == ('', '', 0)
    with pytest.raises(cellops.CellRejected):
        cellops.clear_cell(mem, 'freq')
def test_immutable_field_is_rejected():              # name in mem.immutable
```

- [ ] **Step 2: Run** `.venv\Scripts\python -m pytest tests/unit/test_cellops.py -q` — Expected: FAIL.
- [ ] **Step 3: Implement.** Group edits by row (rows in first-seen order); per row take `editor.memory_for_row` (missing → one problem per cell, "Unable to edit memory before radio is loaded"), sort the row's edits with `freq` first then by `col`; immutable field → `CellRejected(_('%s cannot be changed on this memory'))`; `text is None` → `clear_cell`; numeric columns → replace `,` with `.` when `to_number` accepts the text; after the row, `validate`: errors → drop the row and record each error, warnings → record and keep. Problem label: `'%s %s' % (mem.extd_number or mem.number, col_def.name)`.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `cellops: Apply cell edits to memories without asking`.

### Task 4: `_apply_cell_value` estratto da `_memory_edited`

**Files:**
- Modify: `chirp/wxui/memedit.py:1979-2094` (`_memory_edited`)
- Create: `tests/unit/test_memedit_cells.py` (harness condiviso dalle Task 4-7)

**Interfaces:**
- Consumes: `cellops.CellRejected`.
- Produces: `ChirpMemEdit.apply_cell_value(mem, col_def, text, interactive=True) -> Memory`; `ChirpMemEdit.memory_for_row(row)`, `column(col)`, `validate(mem)` (protocollo di Task 3). Harness: fixture `memedit` = `wx.App` + `wx.Frame` nascosto + `ChirpMemEdit(radio, frame)` su `tests/images/Baofeng_UV-5R.img`, con `config._CONFIG = config.ChirpConfig(tmpdir)` impostato **prima** di importare `memedit`; `pytest.skip` se `wx.App()` non si può creare.

- [ ] **Step 1: Write the failing tests**

```python
def test_single_edit_unchanged(memedit):      # edit name of row 1 via apply + store: same result as today
def test_noninteractive_duplex_uses_band_offset(memedit):
    mem = memedit.memory_for_row(1); mem.freq = 145600000
    out = memedit.apply_cell_value(mem, memedit._col_def_by_name('duplex'), '-', interactive=False)
    assert out.duplex == '-' and out.offset == 600000
def test_noninteractive_never_opens_dialogs(memedit, monkeypatch):  # patch _resolve_* to raise
def test_power_in_watts_picks_closest_level(memedit):
    mem = memedit.memory_for_row(1)
    out = memedit.apply_cell_value(mem, memedit._col_def_by_name('power'), '4.5W', interactive=False)
    assert str(out.power) == 'High'          # UV-5R: High 4 W, Low 1 W
```

- [ ] **Step 2: Run** — Expected: FAIL (`apply_cell_value` missing).
- [ ] **Step 3: Implement.** Move the body of `_memory_edited` between the name filter and the cross/duplex/offset resolution into `apply_cell_value`; with `interactive=True` call the existing `_resolve_*` methods (a `False` return becomes `CellRejected('')` that `_memory_edited` turns into `event.Veto()`); with `interactive=False` use `_set_memory_defaults(mem, 'offset')` for `+`/`-` without offset and raise `CellRejected(_('Needs a choice the bulk edit cannot make'))` for cross modes. `_memory_edited` keeps validation, message boxes and its own `undo_context` exactly as today. Power column with a fixed list of levels: a text that is not a level label but parses with `chirp_common.parse_power` (`'4.5W'`, `'4,5'`) becomes `import_logic.find_closest_power(watts, features.valid_power_levels)`; an unknown text raises `CellRejected`.
- [ ] **Step 4: Run** the new tests and `tests/unit` — Expected: PASS, nothing else changes.
- [ ] **Step 5: Commit** `memedit: One cell-value engine for single and bulk edits`.

### Task 5: Selezione a celle, `_bulk_edit`, Ctrl+D

**Files:**
- Modify: `chirp/wxui/memedit.py` (`__init__` ~992-996, `get_selected_rows_safe` ~2726, new methods)
- Test: `tests/unit/test_memedit_cells.py`

**Interfaces:**
- Consumes: `cellops.apply_edits`, `CellEdit`.
- Produces: `selected_cells() -> list[tuple[int, int]]` (righe visibili, ordinate per riga poi colonna); `visible_rows() -> list[int]`; `bulk_edit(name: str, edits: list[CellEdit]) -> BulkResult` (undo, store, refresh, `EditorChanged`, riepilogo, progresso per radio in diretta); `fill_down() -> None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_fill_down_ctcss(memedit):      # select rows 1-5 col rtone, value on row 1 -> rows 2-5 get it, tmode Tone
def test_fill_down_is_one_undo(memedit):    # _undo() once restores rows 2-5
def test_fill_down_skips_filtered_rows(memedit):   # HideRow(3) -> row 3 unchanged
def test_fill_down_in_sorted_view(memedit):        # sort by name, fill, check memories by number
def test_undo_after_rejection_restores_only_changed(memedit)
def test_whole_row_selection_still_works(memedit): # SelectRow(2) -> get_selected_rows_safe() == [2]
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** `SetTable(..., selmode=wx.grid.Grid.GridSelectCells)`; remove `EnableDragCell()` and the `EVT_GRID_CELL_BEGIN_DRAG` binding (row-header drag stays). `get_selected_rows_safe`: full rows from `GetSelectedRows()` plus blocks from `GetSelectedBlocks()` that span every column; else the cursor row (today's fallback). `bulk_edit` runs `cellops.apply_edits(self, edits)` inside `undo_context(name)` storing each changed memory with `set_memory(mem)`; for `ChirpLiveMemEdit` with more than 20 edits wrap in `wx.ProgressDialog(style=wx.PD_CAN_ABORT)`; after it, if `result.problems`, one `wx.MessageDialog` titled `_('Some cells were not changed')` with the problem lines. `fill_down`: per selected column, top selected visible row's rendered text → `CellEdit` for the other selected rows; undo name `_('Fill %i cells')`.
- [ ] **Step 4: Run** the file and `tests/unit` — Expected: PASS.
- [ ] **Step 5: Commit** `memedit: Cell selection, bulk edits and fill down`.

### Task 6: Copia, incolla, taglia e svuota celle

**Files:**
- Modify: `chirp/wxui/memedit.py` (`cb_copy_getdata` ~2480, `cb_paste` ~2687, `cb_delete` ~2722)
- Test: `tests/unit/test_memedit_cells.py`

**Interfaces:**
- Consumes: `grid_fill.parse_table`, `is_header_row`, `target_cells`, `spread`; `bulk_edit`.
- Produces: `copy_cells_text() -> str`; `paste_table(text: str) -> BulkResult | None`; `clear_cells() -> BulkResult`.

- [ ] **Step 1: Write the failing tests**

```python
def test_copy_cells_is_tsv_of_shown_text(memedit)   # 2x2 block -> 'a\tb\nc\td\n'
def test_paste_table_from_excel(memedit)            # 'freq\tname' rows into empty rows -> channels created
def test_paste_explicit_offset_wins_over_band(memedit)   # freq+duplex+offset row
def test_paste_header_row_skipped(memedit)
def test_paste_overflow_reported(memedit)           # anchor near last row -> problem counted, no exception
def test_paste_one_value_into_selection(memedit)
def test_clear_cells(memedit)                       # name '' ; freq rejected in problems
def test_row_copy_paste_unchanged(memedit)          # full-row selection -> CHIRP format as today
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** Cell copy when the selection is not whole rows: text only (`wx.TextDataObject(copy_cells_text())`), no CHIRP payload. `cb_paste`: CHIRP payload → today's path; text → if whole rows are selected or the first line has a `Location` column use today's `mems_from_clipboard` path, else `paste_table` (anchor = grid cursor; one value and several selected cells → `spread`; one overwrite confirmation if any target cell of a non-empty memory is non-empty; undo name `_('Paste %i cells')`; `dropped` added to the problems as `_('%i values did not fit')`). `cb_delete` with cells selected → `clear_cells` (undo `_('Clear %i cells')`), with rows → today. Cut on cells = copy + clear.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `memedit: Copy, paste, cut and clear cells`.

### Task 7: Tastiera, menu, Ctrl+Invio, dialogo Serie

**Files:**
- Create: `chirp/wxui/seriesdialog.py`
- Modify: `chirp/wxui/memedit.py` (`_keyboard_overrides` ~1173, `_memory_rclick` ~2220)
- Test: `tests/unit/test_memedit_cells.py`

**Interfaces:**
- Consumes: `grid_fill.make_series`, `fill_down`, `paste_table`, `clear_cells`, `copy_cells_text`, `bulk_edit`.
- Produces: `SeriesDialog(parent, start: str, count: int)` with `.values -> list[str]` after `ShowModal() == wx.ID_OK` (fields: Start, Step, preview of the first three values); `ChirpMemEdit.enter_in_selection()` (Ctrl+Invio).

- [ ] **Step 1: Write the failing tests**

```python
def test_ctrl_d_calls_fill_down(memedit)          # simulate wx.KeyEvent Ctrl+D on the grid window
def test_ctrl_enter_writes_all_selected(memedit)  # open editor, set value, Ctrl+Enter -> all cells, one undo
def test_series_dialog_values()                   # start '431.600', step '0.025', count 3
def test_cell_menu_items(memedit)                 # menu for a cell selection lists the five commands
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement.** Ctrl+D → `fill_down`. Ctrl+Invio while `IsCellEditControlShown()`: read the editor value (`GetCellEditor(r, c).GetValue()`), `Reset()` it, `DisableCellEditControl()`, then `bulk_edit` of that text into every selected cell (undo `_('Fill %i cells')`). Delete key with cells selected → `clear_cells`. Context menu for a cell selection: `_('Copy cells')`, `_('Paste')`, `_('Fill down')`, `_('Series...')`, `_('Clear cells')`; row selections keep today's menu. Series dialog over the selected cells of the cursor column (undo `_('Series in %i cells')`). Every command disabled when `not self.editable`, except copy.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `memedit: Keyboard, menu and series for cells`.

### Task 8: Maniglia di riempimento

**Files:**
- Create: `chirp/wxui/fillhandle.py`
- Modify: `chirp/wxui/memedit.py` (create the handle in `__init__`, bind selection/scroll/size events)
- Test: `tests/unit/test_memedit_cells.py`

**Interfaces:**
- Consumes: `grid_fill.continue_series`, `bulk_edit`, `selected_cells`.
- Produces: `class FillHandle(wx.Window)`: `__init__(grid, on_fill: Callable[[int], None])` where the argument is the last target row; `update()` repositions it (7×7 px at the bottom-right corner of the selection, hidden when not visible or read-only); drag with mouse capture, preview rows painted with `theme.tone('tx')`, Esc cancels. `ChirpMemEdit.fill_to(last_row: int)` applies `continue_series` per selected column over the visible rows from the end of the selection to `last_row` (undo `_('Fill %i cells')`).

- [ ] **Step 1: Write the failing tests**

```python
def test_fill_to_continues_frequency_series(memedit)   # two freqs selected, fill_to(row+3)
def test_fill_to_copies_single_value(memedit)
def test_handle_follows_selection(memedit)             # after SelectBlock, handle rect at block corner
def test_handle_hidden_when_read_only(memedit)
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** `FillHandle` and `fill_to`; call `update()` on `EVT_GRID_RANGE_SELECTED`, `EVT_GRID_SELECT_CELL`, `EVT_SCROLLWIN`, `EVT_GRID_COL_SIZE`, `EVT_SIZE`; drag stops at the last grid row.
- [ ] **Step 4: Run** — Expected: PASS.
- [ ] **Step 5: Commit** `memedit: Fill handle`.

### Task 9: Traduzioni, documentazione, prova nell'app

**Files:**
- Modify: `tools/translations/*.json` (17 file + it), `chirp/locale/*.po` (via script), `README-PLUS.md`, `.github/README.md`, `tools/screenshots.py`
- Create: `.github/screenshots/spreadsheet.png`

- [ ] **Step 1:** add every new `_()` string of Tasks 3-8 to all translation JSON files; run `.venv\Scripts\python tools/add_translations.py --check` — Expected: "17 languages, N strings each: placeholders OK"; then apply and `tools/compile_locales.py`.
- [ ] **Step 2:** README-PLUS section "Modifica come in Excel" (commands and limits from the spec); landing page: one row in the "What's new" table and a screenshot paragraph.
- [ ] **Step 3:** `tools/screenshots.py`: a `spreadsheet` shot with a selected block, the handle and a filled series; run it and look at the image.
- [ ] **Step 4:** manual check in the app (scripted like `tools/screenshots.py`): rectangle selection, handle series and copy, Ctrl+D, Ctrl+Invio, paste of a TSV with `145,600`, Delete, undo; no traceback in the log.
- [ ] **Step 5:** `.venv\Scripts\python -m pytest tests/unit -q` and flake8 on the touched files — Expected: all pass.
- [ ] **Step 6: Commit** `Spreadsheet-like grid: translations, docs, screenshot`.
