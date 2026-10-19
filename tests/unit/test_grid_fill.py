from chirp import grid_fill as gf


def test_single_value_repeats():
    assert gf.continue_series(['88.5'], 3) == ['88.5', '88.5', '88.5']


def test_frequency_step_12_5_khz():
    assert gf.continue_series(['145.600000', '145.612500'], 3) == [
        '145.625000', '145.637500', '145.650000']


def test_decimal_comma():
    assert gf.continue_series(['431,600', '431,625'], 2) == [
        '431.650', '431.675']


def test_numbered_names_keep_zero_padding():
    assert gf.continue_series(['CH08', 'CH09'], 2) == ['CH10', 'CH11']
    assert gf.continue_series(['RU0', 'RU1'], 2) == ['RU2', 'RU3']


def test_uneven_values_repeat_cyclically():
    assert gf.continue_series(['FM', 'NFM'], 3) == ['FM', 'NFM', 'FM']


def test_make_series():
    assert gf.make_series('431.600', '0.025', 3) == [
        '431.600', '431.625', '431.650']
    assert gf.make_series('RU0', '1', 3) == ['RU0', 'RU1', 'RU2']


def test_to_number():
    assert gf.to_number('145,6') == 145.6
    assert gf.to_number('High') is None


def test_parse_table_from_excel():
    assert gf.parse_table('a\tb\r\nc\t"d"\r\n') == [['a', 'b'], ['c', 'd']]


def test_header_row():
    assert gf.is_header_row(['Frequency', 'Name'],
                            ['Frequency', 'Name', 'Tone'])
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
    assert gf.spread('88.5', [(0, 3), (2, 3)]) == [
        (0, 3, '88.5'), (2, 3, '88.5')]
