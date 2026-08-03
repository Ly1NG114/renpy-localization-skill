# Ren'Py Save-Compatibility Surgery

Field lesson from a production incident (Eternum 0.9.0): a nickname displayed as
English in existing saves led to byte-level save patching that initially corrupted
every save with a `UnicodeDecodeError: 'utf-8' codec can't decode bytes in position
3-4: unexpected end of data` at load time. This guide is the corrected, verified
procedure.

## 1. Find the REAL save directory first

Ren'Py games save to `config.save_directory`, NOT to `game/saves`:

```renpy
# options.rpy
define config.save_directory = "Eternum-1610153667"
```

Resolved location: `%APPDATA%\RenPy\<save_directory>\` (Windows),
`~/.renpy/<save_directory>/` (Linux), `~/Library/RenPy/<save_directory>/` (macOS).

- `game/saves` may contain **bundled, unused saves** from the repack - analyzing
  them instead of the real saves produces completely wrong conclusions.
- Inside the runtime, the authoritative path is `renpy.config.savedir`.
- Sandboxes often cannot read `%APPDATA%` - verify with escalated access.

## 2. Why a save shows stale text

Two independent mechanisms:

1. **Store values**: the save's pickle contains `store.nickname` etc. Fix the
   VALUE and the runtime display (via `[nickname]`) updates after load.
2. **Rendered dialogue in the rollback log**: Ren'Py's rollback log stores the
   DISPLAYED say text - i.e. translations with `[nickname]` ALREADY substituted.
   The sentence "他将宝石交给Heracles" is baked into the log as one string.
   Fixing the store value alone does NOT clean these baked strings.

To make old saves fully clean you must rewrite both.

## 3. Pickle string length fields count BYTES

When byte-patching pickles (protocol 2+):

- `X` (0x58) BINUNICODE: 4-byte little-endian length + UTF-8 data. Length = BYTES.
- `\x8c` SHORT_BINUNICODE: 1-byte length = BYTES.
- `\x8d` BINUNICODE8: 8-byte length = BYTES.

「赫拉克勒斯」is 5 CHARACTERS but 15 BYTES. Writing `X\x05...` for it makes the
unpickler read only 5 bytes (`\xe8\xb5\xab\xe6\x8b`) and die with
`UnicodeDecodeError ... unexpected end of data` at position 3-4.

Rule: when replacing a string, new length = len(new_bytes) in BYTES.

## 4. Never trust partial pickle tests

`pickle.loads(log)` fails early at the first renpy class reference
(`ModuleNotFoundError: No module named 'renpy'`) - **every string after that point
was never validated**. Use a full opcode-stream walker to validate every string:

- Correct opcode table (protocol 0-4): line ops `S I L P g p`, two-line ops
  `c i` and `\x93`, fixed args (`J`4 `K`1 `M`2 `G`8 `q h`1 `r j`4 `\x80`1
  `\x95`8 `\x94`8 `\x82`1 `\x83`2 `\x84`4, `\x8a`1+len, `\x8b`4+len,
  `U \x8f`1+len, `T \x90`4+len, `\x8e`8+len, `\x96`8+len), unicode ops
  `X \x8c \x8d V`, plus all single-byte ops.
- Any opcode table bug causes silent desync: output shrinks (opcodes dropped) or
  strings skipped. ALWAYS check output length deltas: for N replacements of
  "Heracles"(8B) -> "赫拉克勒斯"(15B) the output must grow by exactly N*7.

## 5. The verified rewrite + resign procedure

In-game bootstrap (runs with the real runtime so `savetoken` works):

```python
# config.after_load_callbacks - called with NO arguments after a load
# (defined in renpy/common/00start.rpy - not a config.py entry!)
config.after_load_callbacks.append(_cn_fix_saved_names)

# renpy.game.post_init - runs right after init, BEFORE the main menu
renpy.game.post_init.append(_cn_patch_save_nicknames)
```

Per save file:

1. Read `log` from the save ZIP.
2. Walk the opcode stream; for every `X`/`\x8c`/`\x8d` string, replace embedded
   names with **ASCII word boundaries**:
   `(?<![A-Za-z])Heracles(?![A-Za-z])` - Python `\b` treats CJK ideographs as
   word characters, so `\bHeracles\b` FAILS before/after Chinese text
   ("Heracles的" has no boundary at `s|的`).
3. Fix length fields to byte counts.
4. Validate with the game's own unpickler: `renpy.compat.pickle.loads(new_log)` -
   the exact call that crashed. If it raises, do NOT write.
5. Re-sign: `sig = renpy.savetoken.sign_data(new_log)` returns a STR;
   verify with `renpy.savetoken.check_load(new_log, sig)` - passing BYTES to
   check_load silently fails verification (decode_line compares str).
6. Only then rewrite the ZIP (`log` + `signatures` entries), write to `.tmp`,
   `os.replace`.
7. Log every decision (`renpy.display.log.write`) - silent `except: pass`
   makes incidents undebuggable.

Keep the patcher idempotent: it skips saves whose rewritten log equals the
original, so it is safe to leave installed.

## 6. Hook timing (Ren'Py 8.3.x)

- `config.after_load_callbacks`: exists, defined in `00start.rpy`, called with no
  args in the `_after_load` label after store restoration. Use for store-value
  normalization on load.
- `renpy.game.post_init`: callbacks run once after init, before the interface.
  Perfect for one-shot file repairs.
- `config.start_callbacks`: fires ONLY when a game starts (after the main menu),
  not at launch - wrong hook for menu-time repairs.
- `config.overlay_screens` + a screen with `timer N action Function(...)`:
  runs at the main menu - a valid alternative trigger.

## 7. Incident checklist

- [ ] Confirmed `config.save_directory` and patched the REAL saves (`renpy.config.savedir`).
- [ ] Fixed store VALUES (menu assignments + after_load normalization).
- [ ] Rewrote BAKED dialogue strings in the rollback log (byte-level, byte lengths).
- [ ] Validated every file with `renpy.compat.pickle.loads` before writing.
- [ ] Re-signed with `savetoken.sign_data` and verified `check_load` (str!).
- [ ] Backed up the broken state before touching anything.
- [ ] Re-verified: no English nickname tokens, structure walker passes, length deltas match.
- [ ] Bootstrapped an idempotent self-healing patcher for future saves.
