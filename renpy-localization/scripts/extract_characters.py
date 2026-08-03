# -*- coding: utf-8 -*-
"""Extract character display names from `define x = Character('Name', ...)`.
Outputs a TSV of counts for glossary building.

Usage: python extract_characters.py <game-dir>
"""
import os, re, sys, io, glob, collections

game = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.environ.get('RENPY_GAME_DIR', ''), 'game')
names = collections.Counter()
for fn in sorted(glob.glob(os.path.join(game, '*.rpy'))):
    with io.open(fn, encoding='utf-8') as f:
        txt = f.read()
    for m in re.finditer(r"(?:Dynamic)?Character\(\s*['\"]([^'\"]+)['\"]", txt):
        names[m.group(1)] += 1
print('unique names:', len(names))
for n, c in names.most_common():
    print('%4d\t%s' % (c, n))
