"""Add the Italian translations for the strings introduced by the automatic
cable detection and the UI improvements. Safe to run more than once."""
import os
import sys

import polib

TRANSLATIONS = {
    'Prolific counterfeit or unsupported chip: the current Windows driver '
    'refuses to work with it. Install an older Prolific driver or use a '
    'CH340/FTDI cable.':
        'Chip Prolific contraffatto o non supportato: il driver di Windows '
        'attuale si rifiuta di usarlo. Installa un driver Prolific più '
        'vecchio oppure usa un cavo CH340/FTDI.',
    'Bluetooth serial port, not a programming cable':
        'Porta seriale Bluetooth, non è un cavo di programmazione',
    'Built-in serial port of the computer':
        'Porta seriale integrata nel computer',
    'Programming cable detected': 'Cavo di programmazione rilevato',
    'USB serial device': 'Dispositivo seriale USB',
    'Serial port': 'Porta seriale',
    'Search radio': 'Cerca radio',
    'Search again for connected cables': 'Cerca di nuovo i cavi collegati',
    'Find your radio by typing part of its name':
        'Trova la tua radio scrivendo parte del nome',
    'Upload': 'Carica',
    'Find your radio': 'Trova la tua radio',
    'Refresh': 'Aggiorna',
    'Search...': 'Cerca...',
    'Connect the programming cable to the radio and to the computer, then '
    'turn the radio on. The cable port is detected automatically.':
        'Collega il cavo di programmazione alla radio e al computer, poi '
        'accendi la radio. La porta del cavo viene rilevata '
        'automaticamente.',
    'No serial port found. Check the cable and its driver, then press '
    'Refresh.':
        'Nessuna porta seriale trovata. Controlla il cavo e il suo driver, '
        'poi premi Aggiorna.',
    'Manually entered port': 'Porta inserita manualmente',
    'Type part of the vendor or model name (for example "UV-5R" or '
    '"Baofeng")':
        'Scrivi parte della marca o del modello (per esempio "UV-5R" o '
        '"Baofeng")',
    'New cable connected on %s': 'Nuovo cavo collegato su %s',
    'The cable on %s was disconnected': 'Il cavo su %s è stato scollegato',
    '%i cables found, %s selected: check that it is the right one':
        'Trovati %i cavi, selezionato %s: verifica che sia quello giusto',
    '%s is probably not your cable, %s looks like a programming cable':
        '%s probabilmente non è il tuo cavo, %s sembra un cavo di '
        'programmazione',
    'No programming cable recognized, %s selected':
        'Nessun cavo di programmazione riconosciuto, selezionato %s',
    'Show toolbar': 'Mostra barra strumenti',
    'Read the memories and settings from the radio':
        'Leggi memorie e impostazioni dalla radio',
    'Write this tab to the radio': 'Scrivi questa scheda nella radio',
    'Connect the cable and read your radio':
        'Collega il cavo e leggi la tua radio',
    'Open a saved radio image or CSV file':
        'Apri un\'immagine radio salvata o un file CSV',
    'Cable: %s': 'Cavo: %s',
    'No programming cable connected': 'Nessun cavo di programmazione '
                                      'collegato',
    'Cable on %s needs a different driver':
        'Il cavo su %s richiede un driver diverso',
    'Serial port %s disconnected': 'Porta seriale %s scollegata',
    'Programming cable connected on %s':
        'Cavo di programmazione collegato su %s',
    'USB': 'USB',
    'Download from the radio or open a file first.':
        'Prima scarica dalla radio o apri un file.',
    'Searching for cables...': 'Ricerca cavi in corso...',
    'PROCEDURE': 'PROCEDURA',
    'Night vision look': 'Aspetto visore notturno',
    'The new look is applied the next time CHIRP starts.':
        'Il nuovo aspetto verrà applicato al prossimo avvio di CHIRP.',
    'RADIO PROGRAMMER': 'PROGRAMMATORE RADIO',
    'Connect the cable to the radio and the PC':
        'Collega il cavo alla radio e al PC',
    'Turn the radio on': 'Accendi la radio',
    'Press DOWNLOAD FROM RADIO': 'Premi SCARICA DALLA RADIO',
    'READY': 'PRONTO',
    'STANDBY': 'IN ATTESA',
    'NO SIGNAL': 'NESSUN SEGNALE',
}


def main(path):
    po = polib.pofile(path)
    missing = [k for k in TRANSLATIONS if po.find(k) is None]
    untranslated = [k for k in TRANSLATIONS
                    if po.find(k) is not None and not po.find(k).msgstr]
    if untranslated:
        # Existing entries need a rewrite of the file
        for msgid in untranslated:
            po.find(msgid).msgstr = TRANSLATIONS[msgid]
        po.save(path)
    # Append new entries without reformatting the rest of the file
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        for msgid in missing:
            entry = polib.POEntry(msgid=msgid, msgstr=TRANSLATIONS[msgid])
            f.write('\n' + entry.__unicode__(wrapwidth=78))
    print('%s: %i added, %i updated' % (
        path, len(missing), len(untranslated)))


if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else
         os.path.join(os.path.dirname(__file__), '..', 'chirp', 'locale',
                      'it.po'))
