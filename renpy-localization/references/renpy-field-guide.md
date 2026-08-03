# Ren'Py PC Localization Field Guide

Field-tested on a 57,619-unique-string production run (Eternum 0.9.0, Ren'Py 8.3.2). Read this before touching any PC Ren'Py game.

## Contents

1. [Engine-generated skeleton](#engine-generated-skeleton)
2. [Extraction model](#extraction-model)
3. [Consistency machinery](#consistency-machinery)
4. [Two-pass translation](#two-pass-translation)
5. [Validation and repair semantics](#validation-and-repair-semantics)
6. [Application format](#application-format)
7. [Language bootstrap and fonts](#language-bootstrap-and-fonts)
8. [Verification ladder](#verification-ladder)
9. [Production numbers and expectations](#production-numbers-and-expectations)

## Engine-generated skeleton

The game's own Ren'Py runtime knows the exact translation identifiers. Generate the skeleton with the game's bundled Python:

```powershell
$py = '<game>/lib/py3-windows-x86_64/python.exe'
& $py '<game>/Eternum.py' '<game-dir>' translate chinese --no-todo
```

Output (per script file, e.g. `game/tl/chinese/script.rpy`):

```renpy
# game/script.rpy:868
translate chinese start_ea0fb88e:

    # a "Hi!" with dissolve
    a "Hi!" with dissolve
```

and for UI strings:

```renpy
translate chinese strings:

    # game/screens.rpy:321
    old "Back"
    new "Back"
```

Notes:

- The `translate` command runs the full script load (10-30s for big games). It writes a token file under `%APPDATA%\RenPy\tokens` - run it outside strict sandboxes.
- `--count` prints missing counts without writing files: `chinese: 0 missing dialogue translations, 0 missing string translations.`
- Do NOT re-run `translate` after filling files - it appends duplicate blocks.
- `.rpyc` files: Ren'Py stores the source md5 at the end of the `.rpyc`; when the `.rpy` changes, the next launch recompiles automatically. Decompiled `.rpy` (UnRen) will therefore trigger recompiles - expected.
- `tl/<lang>/*.rpyc` also carry the md5 of the `.rpy`; editing translations invalidates them and triggers recompile.

## Extraction model

`localize.py extract` parses:

- dialogue blocks: `translate <lang> <id>:` + first non-comment line = a Say statement `[speaker] "text" [with ...]`;
- string blocks: `old "..."` / `new "..."` pairs.

It outputs records (every block, for deterministic re-application) and unique strings (deduplicated by exact source, with speaker/file metadata for prompts). Block count != unique count; the difference can be tens of thousands of repeated lines - deduplication is the main cost saver.

## Consistency machinery

Order of enforcement:

1. **Deterministic memory** (`work/memory_<lang>.json`, keyed by exact source): the same source string maps to exactly one translation everywhere in the game - including repeated lines inside the same file. This is the backbone.
2. **Glossary injection**: every API prompt carries the full glossary (name=term lines). Speakers' display names (resolved from `Character(...)` defines) are attached per item so the model keeps voices distinct.
3. **Validation**: 4 token-multiset checks per record (tags, interpolations, backslash escapes, glossary terms) produce `work/v_*.txt`.
4. **Repair**: policy-driven fixes are applied to memory, then re-validated. Iterate until only benign residuals remain (source bugs, intentional variants).

Glossary `policies` example - when the model produces variants, map them back:

```json
"policies": {
  "Penelope": {"佩妮": "佩内洛普"},
  "Ion": {"伊昂": "艾恩", "爱恩": "艾恩", "离子服务器": "艾恩"}
}
```

## Two-pass translation

Pass 1 (`translate`): temperature 0.4, thinking disabled by default, batches of 100-150, char cap ~14k. Internal behavior:

- every batch is re-requested with only the missing ids until complete (4 attempts);
- whole runs have up to 6 residual rounds, so failed batches are retried with fresh batches;
- identity strings (already CJK, or no latin letters like `...`, `( ... )`) never hit the API.

Pass 2 (`polish`): a native-speaker proofreader prompt (en + current zh -> improved zh). Use thinking mode for: lines >= 81 chars, any line with Ren'Py tags, and early-story files. Everything else runs without thinking. ~22% of lines typically change in this pass; the rest are kept verbatim.

If a batch fails, record its contents (`work/polish_batches/batch_N.txt`) so you can re-run with `--only-en-file`.

## Validation and repair semantics

Token multisets, not string equality:

- tags: `\{[^{}]*\}` - `{i}`, `{/i}`, `{w}`, `{size=31}`, `{image=...}`, `{cps=13}`...
- interpolations: `\[[^\[\]]*\]` - `[mc]`, `[nickname]`, `[npc_name!ti]`
- backslash escapes: `\\[^\\]` - `\"`, `\\`, `\{`, `\n`

Residuals that are usually acceptable (document them):

- source bugs: `{b}...{/i}` mismatched pairs, unclosed `{i}` (mirror or wrap);
- creative pacing: letter-by-letter moans with escalating `{size=N}` tags (character count differs from English);
- context tags dropped from `new`: `old "Yes{#0.1,pregnant}"` / `new "是"` renders correctly;
- `\"` -> Chinese quotes: re-escaped at apply time;
- contextual variants: "King of Eternum" -> 永恒之王 (glossary holds 永恒世界; add a compound entry to silence).

Repair rules (in order): append missing closers; wrap balanced missing pairs; remove extra pairs; drop stray closers without an opener in zh; cap excess self-closing tags; unwrap CJK tags like `{你}`; normalize `[ mc ]`; replace non-canonical interpolation tokens with the source's canonical tokens; escape literal newlines.

CRITICAL: violation reports truncate source strings (en[:120]). Repair must match memory keys by prefix, not exact equality.

## Application format

`apply` rebuilds `tl/<lang>/*.rpy` deterministically:

- dialogue block statement: `speaker "zh" tail` (tail keeps ` with dissolve` etc.);
- strings: `old "..."` / `new "..."`;
- comments preserved;
- escaping: keep existing backslash sequences untouched; bare `"` -> `\"`; literal newline -> `\n`; drop `\r`;
- write UTF-8 **with BOM** (matches engine-generated files).

Report `MISSING translations: 0` before compiling.

## Language bootstrap and fonts

- `config.language` must be set during init (`init -999 python:`). `init_translation()` runs after init code and reads it - verified ordering.
- `config.translate_clean_stores` is a LIST of store names; assigning `False` crashes `change_language` with `TypeError: 'bool' object is not iterable`.
- Latin-only fonts (ade1.ttf, Sketchzone.ttf, poiretone.ttf...) render CJK as tofu. Override at `init 999` (after the game's init-0 style statements) on `style.default` plus dialogue/name/button/input/tooltip/history/menu styles.
- Prefer a CJK font already shipped in `game/` (many repacks include `chinafont.ttf`); otherwise bundle a licensed font.
- `style.default.font` cascades to styles that don't set their own font; explicit per-style overrides cover the rest.

## Save compatibility

- Saves live in `%APPDATA%\RenPy\<config.save_directory>\` - NEVER assume `game/saves` (bundled repack saves can sit there unused). Always resolve via `renpy.config.savedir` inside the runtime.
- Dynamic values like a player nickname are stored BOTH as store variables AND baked into rendered dialogue inside the rollback log. Fixing the menu assignments and an `after_load` callback is not enough for existing saves: byte-level pickle surgery (with BYTE-count length fields), validation via the game's own unpickler, and ECDSA re-signing are required. Full verified procedure: [save-compatibility.md](save-compatibility.md).

## Verification ladder

1. `compile` - zero errors (catches unbalanced quotes, bad escapes, unparseable strings);
2. `translate <lang> --count` - zero missing dialogue/string translations;
3. launch game GUI ~60-75s; inspect `log.txt` for error/traceback/warning;
4. window title / main menu renders in target language (the title often comes from a translated string - strong runtime evidence);
5. screenshot for the record.

## Production numbers and expectations

Eternum 0.9.0 (PC, Ren'Py 8.3.2):

- 71,752 translation blocks (71,736 dialogue + 1,788 UI strings)
- 57,619 unique source strings
- ~952k Chinese characters delivered
- ~9.5M API tokens total (input ~5.4M counted + ~0.2M uncounted killed-process/failed-request overhead; output ~3.6M counted + ~0.1M uncounted), including the full second polish pass
- ~7.5 hours wall time end-to-end

Plan for the long tail: the last few percent of unique strings are long gallery/replay narration and chat strings - they dominate thinking-mode cost.
