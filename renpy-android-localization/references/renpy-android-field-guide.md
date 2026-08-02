# Ren'Py Android Localization 2.0 Field Guide

## Contents

1. [Choose a patch strategy](#choose-a-patch-strategy)
2. [Prove the baseline](#prove-the-baseline)
3. [Build and validate translation coverage](#build-and-validate-translation-coverage)
4. [Audit APK asset references](#audit-apk-asset-references)
5. [Patch missing assets narrowly](#patch-missing-assets-narrowly)
6. [Handle fonts and baked media](#handle-fonts-and-baked-media)
7. [Build and sign safely](#build-and-sign-safely)
8. [Protect saves](#protect-saves)
9. [Test risk-bearing states](#test-risk-bearing-states)
10. [Triage recurring failure patterns](#triage-recurring-failure-patterns)

## Choose a patch strategy

Use the original APK as the binary base when its Android wrapper launches. Rebuilding the entire Android project changes manifests, native libraries, compression, resource IDs, and runtime behavior without improving translation.

Prefer an overlay containing compiled translations, one bootstrap/hotfix, fonts/licenses, and intentional media replacements. Rebuild with apktool or Gradle only when manifest or Android resource changes cannot be expressed as a Ren'Py overlay.

Identify the Ren'Py version before decompiling or compiling. Prefer an exact SDK. If only a nearby compatible SDK is available:

1. inspect runtime version and `script_version.txt`;
2. compile the smallest possible patch;
3. reverse-decompile the output and compare non-ASCII literals;
4. prove it on the target runtime before expanding its use.

Do not infer compatibility merely because compilation returned without text. Some Windows Ren'Py launchers are GUI executables and may not set a normal shell exit code; inspect timestamps, output `.rpyc`, `traceback.txt`, and reverse-decompilation.

## Prove the baseline

Record before modifying anything:

- original APK hash and file size;
- package ID and version name/code;
- target/min SDK and ABI set;
- Ren'Py version and compiled script version;
- original certificate fingerprints and signature schemes;
- APK entry list and duplicate entries;
- save location and accessibility;
- known launch/runtime defects in the original.

Separate three diagnoses:

- **localization regression**: the localized overlay changed a working original path;
- **inherited original defect**: both original and localized APK omit or misreference the same resource;
- **target-runtime incompatibility**: the asset exists but fails only under a codec, container, filesystem, or Android version.

Version every candidate. Preserve the first localized build, every installed signing key, and the last known-good APK while iterating.

## Build and validate translation coverage

Generate or reconstruct `tl/<language>/` files from the decompiled game. Reuse another complete language tree as structural evidence, not as semantic source text.

Maintain quantitative gates:

- expected dialogue translation blocks;
- expected `old`/`new` pairs;
- placeholder and Ren'Py text-tag equality;
- dynamic-string candidates and coverage source;
- unchanged Latin-script target allowlist;
- glossary term consistency.

Search beyond generated translation blocks:

- conditional assignments and variables later rendered as `[value]`;
- `renpy.notify`, save notes, captions, tooltips, and gallery labels;
- screen expressions and Python-generated text;
- concatenation, `.format`, percent formatting, and f-strings;
- strings serialized into save metadata;
- character names built dynamically;
- text baked into images or video.

Use `config.replace_text` only as a targeted compatibility hook. Some compiled screens and metadata code bind values before the hook or bypass it entirely. Patch the narrow source/rendering boundary when runtime evidence shows the hook is ineffective.

Use a deterministic translation cache. Bulk translation can be token-efficient yet time-consuming because extraction, batching, local inference, compilation, and validation dominate wall time. Never measure quality or completeness from token count alone.

## Audit APK asset references

The original APK can contain compiled references to files that were never packaged, especially non-ASCII audio names. Audit before building:

```powershell
python scripts/audit_apk_assets.py --source-root <decompiled-game> --apk <original.apk>
```

The default extensions cover common audio. Add visual media deliberately:

```powershell
python scripts/audit_apk_assets.py --source-root <decompiled-game> --apk <original.apk> --extensions png,jpg,jpeg,webp,webm,mp4,ogv
```

The script checks both common layouts:

| Game path | Escaped APK entry |
|---|---|
| `game/zz_patch.rpyc` | `assets/x-game/x-zz_patch.rpyc` |
| `game/tl/schinese/script.rpyc` | `assets/x-game/x-tl/x-schinese/x-script.rpyc` |
| `game/gui/menu.webm` | `assets/x-game/x-gui/x-menu.webm` |

Interpret output:

- `MISSING` is actionable unless the path is demonstrably dead code.
- `CASE` is usually safe because Ren'Py builds a case-normalized loader map; runtime-prove before changing it.
- `DYNAMIC` includes globs and formatted paths. Inspect assignments/control flow; do not invent literal assets.
- `MAPPED` means the missing source has an explicit fallback and the fallback is packaged.

Run the audit against the baseline APK because a localized build may faithfully preserve a broken original. After any missing-asset traceback, rerun the audit across the same media family and related routes rather than fixing one filename per release.

Traceback screenshots can display boxes for Japanese/Chinese filenames because the error screen uses a fallback font. Recover the exact path from decompiled source. Verify it with code-point-aware reading or reverse-decompilation; do not type what the boxes appear to imply.

## Patch missing assets narrowly

Prefer an exact fallback map when the referenced source file cannot be recovered but a semantically suitable packaged asset exists:

```renpy
# -*- coding: utf-8 -*-
init 1100 python:
    _asset_fallbacks = {
        u"gui/missing-non-ascii-name.ogg": "gui/click.ogg",
        u"audio/missing-water.wav": "audio/slurp.ogg",
    }

    if not getattr(renpy.loader.load, "_exact_asset_hotfix", False):
        _original_loader_load = renpy.loader.load

        def _mapped_loader_load(name, *args, **kwargs):
            name = _asset_fallbacks.get(name, name)
            return _original_loader_load(name, *args, **kwargs)

        _mapped_loader_load._exact_asset_hotfix = True
        renpy.loader.load = _mapped_loader_load
```

Requirements:

- map only proven-bad exact names;
- choose a fallback matching the event semantics and channel behavior;
- confirm every target exists in the baseline APK;
- preserve unknown errors so future missing files still produce evidence;
- keep the hook idempotent;
- preserve positional and keyword arguments;
- use a late-enough init priority to wrap the active loader but early enough for menus/gameplay;
- compile and reverse-decompile to prove Unicode literals survived.

The wrapper's filename may appear at the top of a later traceback. That does not mean the wrapper caused the missing asset; read the final `Couldn't find file` path and compare the baseline APK.

Do not globally disable sound, catch all `IOError`, return silence for every missing file, or alias unrelated media by extension. These approaches hide real defects and can alter gameplay timing.

## Handle fonts and baked media

Bundle a font with complete target-language coverage and a license. Configure name, dialogue, interface, button, choice, and system fonts. Test rare glyphs, punctuation, mixed Latin/numerals, long choices, save timestamps, outlines, and tooltips on a phone-sized display.

The Ren'Py exception screen may ignore game GUI fonts. Treat boxes on that screen as a diagnostic-font limitation, not proof that normal dialogue lacks CJK coverage.

Audit raster and video text separately. Main-menu buttons may be PNGs even when all internal screen labels translate correctly. Classify the result accurately:

- internal UI localized, baked media unchanged;
- baked media partially patched;
- full visible localization.

For looping/randomized menu movies:

1. inspect every candidate movie frame by frame;
2. identify semantic phases and transition intervals;
3. composite only required regions;
4. blend morph boundaries;
5. encode with the stock container/codec/pixel format and matching frame rate;
6. test at least two loops on Android.

An H.264 MP4 that works on desktop can show black in Ren'Py Android. Match the original VP8/VP9 WebM or OGV profile when present.

## Build and sign safely

Use this sequence:

1. translation syntax/count/placeholder/tag validation;
2. dynamic-string and asset-reference audit;
3. Ren'Py compilation and reverse-decompilation of new compatibility code;
4. clean staging directory and explicit manifest;
5. original APK plus staged overlay;
6. `zipalign`;
7. `apksigner sign`;
8. `apksigner verify --verbose --print-certs`;
9. overlay integrity verification;
10. final SHA-256 and size.

Retain the signing key, alias, password recovery path, and certificate fingerprint. A new key cannot update an installed build signed by an earlier localization key.

The overlay verifier must require:

- no duplicate entries;
- every untouched original entry byte-identical;
- every staged entry hash-identical to its source;
- no unexplained additions/removals;
- no signature files in the stage.

Common distinctions:

- `INSTALL_FAILED_UPDATE_INCOMPATIBLE`: certificate mismatch;
- parser/install failure: malformed APK, unsupported SDK/ABI, or signing issue;
- launch traceback: Ren'Py script/content failure after installation;
- black media: codec/path/runtime issue rather than signing.

## Protect saves

Before uninstalling or changing certificates:

1. confirm exact package ID and active user/container;
2. stop the game or reach a safe state;
3. locate all save roots;
4. pull slots, `persistent`, `sync/`, security keys, and upgrade markers;
5. hash each relative path;
6. keep the backup until the user confirms normal play.

Attempt a same-certificate replacement install before considering uninstall. If the installed certificate is unknown, determine it or stop before destructive action.

When saves are inside a private compatibility container:

- do not assume `/sdcard/Android/data/<package>` is host-visible;
- do not use root or namespace entry attempts as a workaround;
- inspect load/auto/quick-save pages without opening slots;
- if backup is impossible, never uninstall or clear data;
- limit installation to a proven same-certificate update.

After restore, recompute device-side hashes and confirm slot screenshots/timestamps without advancing the game unnecessarily.

## Test risk-bearing states

Static validation prevents cheap failures but does not prove runtime behavior. Build a state matrix from control flow and past incidents.

Minimum matrix:

| Area | Evidence |
|---|---|
| Launch | cold start, main menu, no traceback |
| UI | settings, load, auto-save, quick-save, help/about where present |
| Text | narration, named dialogue, long lines, choices, dynamic labels |
| Media | patched images/video, two animation loops, audio channel behavior |
| Core loop | first interactive or night loop |
| Risk route | one attack/failure route and one random encounter |
| Mechanics | one QTE/minigame when present |
| Regression | every previously failing path plus adjacent uses of the same asset family |
| Logs | Ren'Py log/logcat/hilog or visible error screen after high-risk states |

Test read-only screens before entering gameplay. Inspect all save categories before starting a new game. If they are empty, advance only enough to validate representative text and explicitly report any auto-save created.

Use evidence labels consistently:

- **static verified**: build/package/signature checks only;
- **smoke tested**: launch and shallow UI/dialogue;
- **route tested**: named gameplay path reproduced;
- **regression tested**: prior failures and related paths pass.

Do not label a smoke test “playable through the whole game.” A defect triggered by a night encounter, loss scene, gallery replay, or QTE can remain hidden after a clean opening.

## Triage recurring failure patterns

### Missing non-ASCII audio or image

Cause: the script retained a Japanese/Chinese filename that the Android build omitted.

Action: recover the exact source literal, audit the media family, map exact missing names to verified targets, rebuild, and route-test every use.

### Translation files are complete but English appears

Cause: dynamic value, save metadata, or baked media was never translated.

Action: trace the value to its rendering boundary. Patch the narrow source or media and add the state to the matrix.

### Corrected video is black on Android

Cause: unsupported codec/profile/pixel format or incorrect escaped path.

Action: match the stock codec and path, then test inside the signed APK.

### Menu body changes but detail overlays stay fixed

Cause: randomized source movies contain form-specific fixed overlays.

Action: compare all movies, composite the correct phase-specific regions, blend transitions, and route random names to a verified result only when variety remains semantically valid.

### Update install fails after a good build

Cause: installed and candidate certificates differ, or the compatibility container applies its own installer rules.

Action: compare fingerprints, preserve saves, use the device-specific playbook, and never convert an update failure into an unapproved uninstall.

### User reports a deep-route traceback after smoke testing

Cause: the acceptance matrix did not exercise the triggering state, or the baseline contains more missing references.

Action: classify the previous evidence honestly, scan the entire related asset family, add the route and adjacent states to regression coverage, and issue a new versioned candidate.
