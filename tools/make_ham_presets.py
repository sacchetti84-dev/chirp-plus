"""Write the Italian amateur, LPD and PMR446 presets in chirp/stock_configs.

Usage:  .venv\\Scripts\\python tools\\make_ham_presets.py

Writes:
  IT Ponti ripetitori 2 m.csv      RV48-RV63 (R0-R7 and "alfa"), -600 kHz
  IT Ponti ripetitori 70 cm.csv    RU0-RU15, -1.6 MHz
  IT Satelliti FM radioamatori.csv FM satellites, three Doppler steps each
  IT Radioamatori tutto in uno.csv the list above plus "IT Chiamata e
                                   simplex radioamatori", for a single import
  IT LPD e PMR446.csv              the 69 LPD and 16 PMR446 channels, at
                                   their legal power (licence free bands)

Sources (checked October 2026): the Italian repeater channel plan of the
ministry circular as reported by ARI sections, and the AMSAT "FM
Satellites" table (https://www.amsat.org/live-fm-satellites/). Satellites
come and go: update SATELLITES when AMSAT changes the table.
"""
import csv
import io
import re
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STOCK = os.path.join(ROOT, 'chirp', 'stock_configs')
CALLING = 'IT Chiamata e simplex radioamatori.csv'

HEADER = ['Location', 'Name', 'Frequency', 'Duplex', 'Offset', 'Tone',
          'rToneFreq', 'cToneFreq', 'DtcsCode', 'DtcsPolarity', 'RxDtcsCode',
          'CrossMode', 'Mode', 'TStep', 'Skip', 'Power', 'Comment',
          'URCALL', 'RPT1CALL', 'RPT2CALL', 'DVCODE']

# Biggest Doppler shift of a low orbit satellite at 435 MHz is about
# +-10 kHz (+-3 kHz at 145 MHz, small enough to ignore on FM)
DOPPLER_KHZ = 10
STEPS = [('A', 'inizio passaggio'), ('C', 'centro passaggio'),
         ('F', 'fine passaggio')]

# name (max 6 chars), uplink MHz, uplink tone, downlink MHz, note
SATELLITES = [
    ('SO50', 145.850, 67.0, 436.795,
     'SaudiSat-1C. Prima va armato il timer di 10 minuti: canale SO50ARM'),
    ('ISS', 145.990, 67.0, 437.800,
     'ripetitore FM della stazione spaziale, non sempre acceso '
     '(stato su ariss.org)'),
    ('AO123', 145.850, 67.0, 435.400, 'ASRTU-1'),
    ('PO101', 437.500, 141.3, 145.900,
     'Diwata-2, acceso solo a orari programmati'),
    ('AO91', 435.250, 67.0, 145.960,
     'Fox-1B, non usarlo quando il satellite è in eclissi (batteria)'),
]


def row(name, freq, comment, duplex='', offset=0.0, tone='', rtone=88.5,
        mode='NFM', step=12.5, power='5.0W'):
    return {'Name': name, 'Frequency': '%.6f' % freq, 'Duplex': duplex,
            'Offset': '%.6f' % offset, 'Tone': tone,
            'rToneFreq': '%.1f' % rtone, 'cToneFreq': '88.5',
            'DtcsCode': '023', 'DtcsPolarity': 'NN', 'RxDtcsCode': '023',
            'CrossMode': 'Tone->Tone', 'Mode': mode, 'TStep': '%.2f' % step,
            'Skip': '', 'Power': power, 'Comment': comment}


def repeaters_2m():
    rows = []
    for i in range(16):
        out = 145.600 + i * 0.0125
        name = 'R%i' % (i // 2) + (' ALFA' if i % 2 else '')
        rows.append(row(
            name, out,
            '[2m] Ponte RV%i (%s): ascolto %.4f, trasmetti %.4f. Accesso con '
            'nota 1750 Hz o CTCSS, secondo il ponte - serve licenza' % (
                48 + i, name, out, out - 0.6),
            duplex='-', offset=0.6))
    return rows


def repeaters_70cm():
    rows = []
    for i in range(16):
        out = 431.600 + i * 0.025
        rows.append(row(
            'RU%i' % i, out,
            '[70cm] Ponte RU%i: ascolto %.3f, trasmetti %.3f. Molti ponti '
            'vogliono un CTCSS (spesso 88.5 Hz) - serve licenza' % (
                i, out, out - 1.6),
            duplex='-', offset=1.6))
    return rows


def satellites():
    rows = []
    for name, up, tone, down, note in SATELLITES:
        if name == 'SO50':
            rows.append(row(
                'SO50ARM', down,
                'Satellite SO-50: arma il timer con 2 secondi di portante '
                '(CTCSS 74.4 Hz), poi passa ai canali SO50',
                duplex='split', offset=up, tone='Tone', rtone=74.4,
                mode='FM', step=5.0))
        for k, (letter, when) in enumerate(STEPS):
            # Approaching satellite: what it sends arrives higher, what we
            # send must leave lower. Only the UHF leg is corrected.
            shift = (1 - k) * DOPPLER_KHZ / 1000.0
            rx = down + shift if down > 400 else down
            tx = up - shift if up > 400 else up
            rows.append(row(
                '%s %s' % (name, letter), rx,
                'Satellite %s, %s (Doppler): ricevi %.3f, trasmetti %.3f con '
                'CTCSS %.1f Hz. %s - serve licenza' % (
                    re.sub(r'(\D)(\d)', r'\1-\2', name, count=1), when,
                    rx, tx, tone, note[0].upper() + note[1:]),
                duplex='split', offset=tx, tone='Tone', rtone=tone,
                mode='FM', step=5.0))
    return rows


def lpd_pmr():
    # LPD: 433.075-434.775 MHz every 25 kHz, 10 mW. PMR446: 446.00625-
    # 446.19375 MHz every 12.5 kHz, 0.5 W. A Baofeng cannot go that low
    # and is not an approved radio for either band: the comment says so.
    rows = []
    for i in range(69):
        freq = 433.075 + i * 0.025
        rows.append(row(
            'LPD %02i' % (i + 1), freq,
            '[LPD] Canale %i, %.3f MHz: senza licenza ma solo con apparati '
            'LPD omologati, max 10 mW (la Baofeng scende a 1 W)' % (
                i + 1, freq),
            mode='FM', step=25.0, power='0.01W'))
    for i in range(16):
        freq = 446.00625 + i * 0.0125
        rows.append(row(
            'PMR %02i' % (i + 1), freq,
            '[PMR446] Canale %i, %.5f MHz: senza licenza ma solo con '
            'apparati PMR446 omologati con antenna fissa, max 0,5 W' % (
                i + 1, freq),
            step=6.25, power='0.5W'))
    return rows


def read_calling():
    with open(os.path.join(STOCK, CALLING), encoding='utf-8',
              newline='') as f:
        return list(csv.DictReader(f))


def render(rows):
    out = io.StringIO()
    writer = csv.DictWriter(out, HEADER, lineterminator='\n')
    writer.writeheader()
    for location, data in enumerate(rows, 1):
        data = dict(data, Location=str(location))
        writer.writerow({k: data.get(k, '') for k in HEADER})
    return out.getvalue()


def presets():
    """{file name: CSV text} of every generated preset"""
    files = {
        'IT Ponti ripetitori 2 m.csv': repeaters_2m(),
        'IT Ponti ripetitori 70 cm.csv': repeaters_70cm(),
        'IT Satelliti FM radioamatori.csv': satellites(),
    }
    everything = read_calling()
    for rows in files.values():
        everything.extend(rows)
    files['IT Radioamatori tutto in uno.csv'] = everything
    # Not in the all-in-one list: 85 more channels would not fit 128
    files['IT LPD e PMR446.csv'] = lpd_pmr()
    return {name: render(rows) for name, rows in files.items()}


def main():
    for filename, text in presets().items():
        with open(os.path.join(STOCK, filename), 'w', encoding='utf-8',
                  newline='') as f:
            f.write(text)
        print('%-36s %3i channels' % (filename, text.count('\n') - 1))


if __name__ == '__main__':
    main()
