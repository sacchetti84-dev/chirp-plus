"""Add the translations of the CHIRP Plus strings to chirp/locale/*.po.

Usage:  .venv\\Scripts\\python tools\\add_translations.py [--check]

Translations live in tools/translations/<lang>.json as {msgid: msgstr},
one file per .po. New entries are appended at the end of the .po file
(the rest of the file is left untouched); entries that already exist
with a translation are kept, so official CHIRP translations win.

Every msgstr must use exactly the same placeholders as its msgid
(%s, %i, %(name)s...): a mismatch would crash the program at run time,
so it stops the script. --check only validates, writing nothing.
"""
import argparse
import collections
import glob
import json
import os
import re
import sys

import polib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'tools', 'translations')
LOCALE = os.path.join(ROOT, 'chirp', 'locale')
PLACEHOLDER = re.compile(r'%(?:\([a-z_]+\))?[-+ #0]*\d*(?:\.\d+)?[sdif%]')


def placeholders(text):
    return collections.Counter(p for p in PLACEHOLDER.findall(text)
                               if p != '%%')


def check(lang, table):
    problems = []
    for msgid, msgstr in table.items():
        if not msgstr.strip():
            problems.append('%s: empty translation for %r' % (lang, msgid))
        elif placeholders(msgid) != placeholders(msgstr):
            problems.append('%s: placeholders differ in %r -> %r' % (
                lang, msgid, msgstr))
    return problems


def drop_obsolete(path, entries):
    """Remove the given obsolete (#~) entries from the file, as text."""
    with open(path, encoding='utf-8', newline='') as f:
        lines = f.readlines()
    drop = set()
    for entry in entries:
        first = last = entry.linenum - 1
        while first > 0 and lines[first - 1].startswith('#'):
            first -= 1
        while last + 1 < len(lines) and lines[last + 1].startswith('#~'):
            last += 1
        if last + 1 < len(lines) and not lines[last + 1].strip():
            last += 1
        drop.update(range(first, last + 1))
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.writelines(l for i, l in enumerate(lines) if i not in drop)


def apply(lang, table):
    path = os.path.join(LOCALE, '%s.po' % lang)
    po = polib.pofile(path)
    missing = [k for k in table if po.find(k) is None]
    # A string that upstream dropped stays in the file as "#~": it would
    # come back twice, so the obsolete copy goes away
    obsolete = [e for e in po.obsolete_entries() if e.msgid in missing]
    if obsolete:
        drop_obsolete(path, obsolete)
        po = polib.pofile(path)
    empty = [k for k in table
             if po.find(k) is not None and not po.find(k).msgstr]
    if empty:
        # Existing but untranslated entries: the file has to be rewritten
        for msgid in empty:
            po.find(msgid).msgstr = table[msgid]
        po.save(path)
    with open(path, 'a', encoding='utf-8', newline='\n') as f:
        for msgid in missing:
            entry = polib.POEntry(msgid=msgid, msgstr=table[msgid])
            f.write('\n' + entry.__unicode__(wrapwidth=78))
    return len(missing), len(empty)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    reference = json.load(open(os.path.join(DATA, 'it.json'),
                               encoding='utf-8'))
    problems = []
    tables = {}
    for path in sorted(glob.glob(os.path.join(DATA, '*.json'))):
        lang = os.path.splitext(os.path.basename(path))[0]
        table = json.load(open(path, encoding='utf-8'))
        absent = [k for k in reference if k not in table]
        extra = [k for k in table if k not in reference]
        if absent:
            problems.append('%s: %i strings missing, e.g. %r' % (
                lang, len(absent), absent[0]))
        if extra:
            problems.append('%s: unknown strings, e.g. %r' % (lang, extra[0]))
        problems.extend(check(lang, table))
        tables[lang] = table
    if problems:
        print('\n'.join(problems))
        return 1
    print('%i languages, %i strings each: placeholders OK' % (
        len(tables), len(reference)))
    if args.check:
        return 0
    for lang, table in tables.items():
        added, filled = apply(lang, table)
        print('%-6s %3i added, %3i filled' % (lang, added, filled))
    return 0


if __name__ == '__main__':
    sys.exit(main())
