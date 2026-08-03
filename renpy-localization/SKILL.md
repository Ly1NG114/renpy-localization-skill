---
name: renpy-localization
description: Localize Ren'Py games (PC and Android) into Chinese or other languages with enforced proper-noun consistency, official-engine translation skeletons, two-pass LLM translation with deterministic memory, automated tag/interpolation/glossary validation and repair, CJK font bootstrap, compile verification, and runtime smoke tests - including adult games. Use when Codex must translate a Ren'Py game, generate or compile tl/<language> translations, keep character/place names consistent across 50k+ lines, decompile .rpyc, patch Character display names or CJK fonts, rebuild and sign Android APKs, or diagnose Ren'Py tracebacks.
---

# Ren'Py Localization 3.0

Deliver a natural, terminology-consistent localization for Ren'Py games on **PC and Android**, with quantitative validation and runtime evidence. Translation consistency is a hard requirement, not a hope: the same English source must always render the same Chinese translation, and proper nouns must match a project glossary everywhere.

## Load the relevant guidance

- Read [references/renpy-field-guide.md](references/renpy-field-guide.md) before starting any PC game localization (skeleton generation, extraction, translation, application, fonts, verification) and for the pitfall checklist distilled from a 57k-line production run.
- Read [references/save-compatibility.md](references/save-compatibility.md) before touching ANY save file (fixing stale nicknames/names, save migration, or save surgery) - it covers the real save directory, pickle byte-length semantics, rendered-text baking, verified rewrite/resign, and hook timing.
- Read [references/adult-localization-quality.md](references/adult-localization-quality.md) when the game contains explicit sexual content, fetish terminology, erotic sound effects, route-dependent identities, or character voices that machine translation could flatten.
- Read [references/renpy-android-field-guide.md](references/renpy-android-field-guide.md) when packaging, signing, or runtime-testing an Android APK.
- Read [references/device-runtime-playbook.md](references/device-runtime-playbook.md) when the target uses ADB, HarmonyOS HDC, an emulator, or an Android compatibility container.

## Establish the baseline

1. Inventory the game: Ren'Py version (from `renpy/__init__.py` or log.txt), `.rpy` vs `.rpyc` presence, `archive.rpa` files, existing `tl/` folders, custom fonts, and saves.
2. If only `.rpyc` exists, decompile with UnRen (or unrpyc) and note that decompiled `.rpy` differs byte-wise from the original source. Ren'Py runs `.rpyc` when its embedded md5 matches the `.rpy`; editing the `.rpy` makes Ren'Py recompile automatically on next launch.
3. Record whether the original game itself has broken tags or missing assets. Do not misattribute inherited defects to localization.
4. Keep backups: original `.rpy` files before patching names, and the untouched `tl/` state before `apply`.

## Generate the official translation skeleton (PC)

Use the game's own engine so every translation identifier is exactly right:

```powershell
# game dir contains Eternum.py/renpy.py + lib/py3-windows-x86_64/python.exe
& $py <game>/Eternum.py <game-dir> translate <lang> --no-todo
```

- This writes `game/tl/<lang>/*.rpy` with correct `translate <lang> <label>_<hash>:` dialogue blocks and `translate <lang> strings:` blocks (old/new pairs).
- It needs write access to the Ren'Py tokens dir (`%APPDATA%\RenPy\tokens`) - run unsandboxed.
- Never re-run `translate` on already-filled files (it appends); use `translate <lang> --count` to verify coverage instead.
- For games whose UI is data-driven (chat systems, dynamic menus), the strings block is the only coverage; audit `_()`/`Msg()` calls and dynamic strings separately.

## Extract, then build the glossary first

1. `python scripts/localize.py extract --lang <lang>` - parse the skeleton into `work/records_<lang>.json` (dialogue blocks + string pairs) and `work/unique_<lang>.json` (deduplicated source strings). **Never translate the same source twice**: a 70k-block game usually has ~55-60k unique strings.
2. Build `glossary.json` before any bulk translation: every `define x = Character('Name')` (use `scripts/extract_characters.py` logic or grep), places, organizations, items, currencies, mythology, gameplay meters, and erotic vocabulary. Add `policies` entries mapping model-produced variants to canonical terms.
3. Fix canonical translations for the main cast first; they appear in thousands of lines and every inconsistency is user-visible.

## Translate in two passes with enforced consistency

Pass 1 - bulk translate:

```powershell
python scripts/localize.py translate --lang chinese --workers 4 --batch 150 --model <model>
```

- Deterministic memory `work/memory_<lang>.json`: exact source -> translation. Same source, same translation, forever. This is the primary consistency mechanism.
- Identity strings (already CJK or no latin letters) are skipped without API cost.
- In-batch gap filling + residual rounds: truncated or malformed model output never silently loses lines.
- Batch sizes: <=150 short strings, <=100 with reasoning enabled; cap total chars ~14k.
- `thinking: disabled` is far cheaper and faster; enable per-pass only for the most complex content.

Pass 2 - native-proofreader polish:

```powershell
python scripts/localize.py polish --lang chinese --workers 4
```

- Long (>80 chars), tag-bearing, and early-story lines get a thinking pass; short lines run fast.
- Keep an audit trail of failed batches (record batch contents before processing) so leftovers can be re-polished with `--only-en-file`.

## Validate, repair, apply

```powershell
python scripts/localize.py validate --lang chinese   # 4-way checks -> work/v_*.txt
python scripts/localize.py repair   --lang chinese   # policy + tag + interp + newline fixes
python scripts/localize.py apply    --lang chinese   # rebuild tl/<lang>/*.rpy from memory
python scripts/localize.py names                      # localize Character(...) display names (backup first)
```

Validation compares token **multisets** (not raw strings) for: Ren'Py tags `{...}`, interpolations `[...]`, backslash escapes, and glossary terms. Repair is policy-driven:

- glossary `policies`: variant -> canonical replacements on flagged rows;
- tag repair: append missing closers, wrap balanced missing pairs, remove extra pairs/lone closers/stray closers, cap excess self-closing tags (`{w}`), unwrap invalid CJK tags like `{你}`;
- interpolation repair: `[ mc ]` -> `[mc]`, replace non-canonical tokens (`[奥赖恩]`) with the source's canonical tokens (`[mc]`);
- literal newlines in zh become `\n` escapes (a raw newline breaks the .rpy string parse).

Apply rebuilds every tl file deterministically; `escape_rpy` keeps existing backslash sequences, escapes bare quotes, and escapes newlines. Report `MISSING translations: 0` before proceeding.

## Bootstrap language + CJK fonts (PC)

Add `game/000_cn_bootstrap.rpy` (name it to load first, e.g. `000_`):

```renpy
init -999 python:
    config.language = "chinese"          # MUST be set before init completes
    # config.translate_clean_stores is a LIST - never assign False to it

init 999 python:
    # Override fonts AFTER all game styles are defined (init 0) so CJK renders
    style.default.font = "chinafont.ttf"
    for _sn in ["say_dialogue", "say_thought", "say_label", "namebox_label",
                "button_text", "textbutton_text", "interface_text",
                "input_prompt", "choice_button_text", "menu_choice_button",
                "quick_button_text", "navigation_button_text", "tooltip_text",
                "history_text", "history_name_text", "game_menu_title",
                "game_menu_subtitle", "nvl_dialogue", "nvl_label"]:
        try:
            setattr(getattr(style, _sn), "font", "chinafont.ttf")
        except Exception:
            pass
```

- Prefer a CJK font already bundled by the game (check `game/*.ttf`/`.otf`); otherwise bundle a licensed one.
- `config.language` set at `init -999` is read by `init_translation()` after init code runs - this ordering works.

## Verify with the engine, then smoke test

```powershell
& $py <game>/Eternum.py <game-dir> compile              # zero errors expected
& $py <game>/Eternum.py <game-dir> translate <lang> --count   # "0 missing dialogue/string translations"
```

Then launch the game (GUI) briefly: check `log.txt` for error/traceback/warning, confirm the window title renders in the target language, and capture a screenshot as evidence. Check the main menu, settings, a save/load screen, dialogue, choices, and history. Never claim runtime proof from static checks alone.

## Android packaging (when required)

Follow `references/renpy-android-field-guide.md`: immutable APK baseline, minimal overlay (compiled `tl/<lang>/*.rpyc` + bootstrap + fonts), asset audits, `zipalign`, sign with the retained key, `apksigner verify`, save/signature compatibility, and the route-based runtime matrix via ADB/HDC/emulator/container.

## Pitfall checklist (learned the hard way)

1. **Never hand-roll JSON bracket counting** for model output - translations contain `[mc]`, `[...]` inside string values which break depth tracking. Use `json.JSONDecoder().raw_decode`.
2. **Models sometimes echo the input shape** (`{"id","text"}`) instead of `{"id","zh"}` - accept both keys and forbid extra keys in the prompt.
3. **max_tokens truncation drops the tail of the array** - always gap-fill and run residual rounds.
4. **Violation reports truncate source strings** - repair must match by prefix, not exact key.
5. **Literal newlines in translations break .rpy parsing** - escape at apply time.
6. **`\"` -> Chinese quotes is benign** - re-escape bare quotes at apply; don't fight it in validation.
7. **Original sources often contain broken tags** (`{b}...{/i}`, unclosed `{i}`) - mirror the source or handle explicitly; do not over-"fix".
8. **Windows + Chinese paths**: PowerShell `Start-Process -ArgumentList` mangles non-ASCII paths - use relative paths with `-WorkingDirectory`.
9. **CRLF vs LF**: PowerShell `Set-Content` writes CRLF and a BOM; normalize when patching scripts.
10. **`translate_clean_stores` is a list, not a bool** - `config.translate_clean_stores = False` crashes `change_language`.
11. **The engine's own `translate` command appends** - never run it on filled files; use `--count`.
12. **Keep the API key out of logs**; unverified SSL context may be required behind MITM proxies (CN networks).
13. **Time/cost expectations**: ~57k unique strings took ~9.5M tokens (in ~5.5M / out ~3.6M counted) and ~7.5h wall time in production, including a full second polish pass.
14. **Saves live in `%APPDATA%\RenPy\<config.save_directory>\`, not `game/saves`** - the latter may hold bundled, unused saves; patch the real ones.
15. **Pickle string length fields count BYTES** (BINUNICODE `X`/`\x8c`/`\x8d`): writing character counts corrupts saves with `UnicodeDecodeError ... unexpected end of data`.
16. **Rollback logs store RENDERED dialogue** - `[nickname]` is already substituted; fixing the store value alone leaves baked English in history/rollback text. Rewrite strings at the byte level.
17. **`pickle.loads` tests stop at the first renpy class reference** - strings after it are never validated. Use a full opcode-stream walker and check length deltas (each "Heracles"->"赫拉克勒斯" replacement must grow output by exactly 7 bytes).
18. **Python `\b` treats CJK as word chars** - use `(?<![A-Za-z])Name(?![A-Za-z])` when replacing ASCII names embedded in Chinese text.
19. **`renpy.savetoken.check_load(log, sig)` expects a str signature**; passing bytes silently fails verification.
20. **Hook timing**: `config.after_load_callbacks` (no args) normalizes store values on load; `renpy.game.post_init` runs once before the main menu (one-shot repairs); `config.start_callbacks` only fires when a game starts - wrong for menu-time fixes.

## Deliver the result

Return: the translated game path, translation block counts, `0 missing` verification output, glossary size and consistency mechanisms, validation summary (tag/interp/backslash/glossary counts), font/bootstrap files added, compile + smoke-test evidence, remaining baked-image/video English, exact instructions to launch, and - when saves were touched - the save-compatibility report (real save dir, what was rewritten, validation + resign evidence, backups).
