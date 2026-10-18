"""Compile chirp/locale/*.po into <lang>/LC_MESSAGES/CHIRP.mo.

Equivalent to `make -C chirp/locale` but needs only Python + polib, so it
works on Windows without gettext installed."""
import glob
import os

import polib

LOCALE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      '..', 'chirp', 'locale')


def main():
    for po_path in sorted(glob.glob(os.path.join(LOCALE, '*.po'))):
        lang = os.path.splitext(os.path.basename(po_path))[0]
        out_dir = os.path.join(LOCALE, lang, 'LC_MESSAGES')
        os.makedirs(out_dir, exist_ok=True)
        po = polib.pofile(po_path)
        po.save_as_mofile(os.path.join(out_dir, 'CHIRP.mo'))
        print('%-8s %3i%% translated' % (lang, po.percent_translated()))


if __name__ == '__main__':
    main()
