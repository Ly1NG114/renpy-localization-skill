---
name: renpy-android-localization
description: Localize, repair, rebuild, sign, and runtime-validate Ren'Py Android APKs, including adult games, while preserving saves, signing compatibility, and original assets. Use when Codex must translate a Ren'Py APK, reconstruct or compile .rpy/.rpyc translations, audit missing or non-ASCII media references, patch CJK fonts or baked menu media, diagnose Ren'Py tracebacks, produce update-installable signed APKs, migrate saves or certificates, or test through ADB, HarmonyOS HDC, an emulator, or an Android compatibility container.
---

# Ren'Py Android Localization 2.0

Deliver a natural localization and a versioned, evidence-backed APK. Treat translation, asset integrity, signing, saves, packaging, and stateful runtime QA as one workflow.

## Load the relevant guidance

- Read [references/renpy-android-field-guide.md](references/renpy-android-field-guide.md) before changing an APK, choosing a patch strategy, compiling a hotfix, migrating signatures, or modifying media.
- Read [references/device-runtime-playbook.md](references/device-runtime-playbook.md) when the target uses ADB, HarmonyOS HDC, an emulator, or an Android compatibility container, or when saves/logs/packages are not visible through the expected tool.
- Read [references/adult-localization-quality.md](references/adult-localization-quality.md) when the game contains explicit sexual content, fetish terminology, erotic sound effects, route-dependent identities, or character voices that machine translation could flatten.

## Establish an immutable baseline

1. Copy the original APK to a read-only baseline; never patch the only copy.
2. Record APK SHA-256, package ID, version name/code, target SDK, ABI, Ren'Py version, entry list, and original signing certificate.
3. Determine whether `.rpy` exists or `.rpyc` decompilation is required. Match the Ren'Py SDK/decompiler to the runtime whenever possible.
4. Preserve a versioned candidate chain (`v1`, `v2`, ...). Never overwrite the last known-good APK.
5. Record whether the original APK itself has broken references. Do not misattribute inherited defects to localization.

## Build translation coverage

1. Reconstruct or generate `tl/<language>/` files and maintain quantitative baselines for dialogue blocks and `old`/`new` pairs.
2. Build a glossary before bulk translation. Fix names, pronouns, honorifics, gameplay terms, erotic vocabulary, sound-effect conventions, and recurring clues.
3. Preserve `[interpolation]`, `{text tags}`, escaped braces, percent tokens, identifiers, labels, persistent keys, and control flow exactly.
4. Translate explicit content as authored unless the user requests sanitization. Preserve consent framing, humor, fear, seduction, pacing, and distinct voices.
5. Use deterministic translation caches keyed by source text and context. Separate bulk generation from contextual repair and syntax validation.
6. Audit dynamic strings that normal Ren'Py translation generation misses:

```powershell
python scripts/scan_dynamic_strings.py --source-root <game-source> --translation-root <tl-language> --direct-map <bootstrap.rpy> --fail-on-uncovered
```

7. Bundle a licensed CJK font and configure dialogue, name, interface, button, choice, and system/error-facing fonts where the engine permits.
8. Identify text baked into PNG/JPG/WebP/video separately. Do not call an APK fully localized while visible baked English remains; either patch it or report it as a visual limitation.

## Audit packaged assets before the first build

Run a static reference audit against the original APK, not only the localized candidate:

```powershell
python scripts/audit_apk_assets.py --source-root <decompiled-game> --apk <original.apk>
```

Use `--extensions png,jpg,jpeg,webp,webm,mp4,ogv` for visual media, and provide a verified exact fallback map when the original APK omits referenced assets:

```powershell
python scripts/audit_apk_assets.py --source-root <decompiled-game> --apk <original.apk> --fallback-map <hotfix.rpy> --map-variable <mapping_variable>
```

Interpret results deliberately:

- `MISSING`: a static reference has no packaged entry; fix or explicitly allowlist it.
- `MAPPED`: the missing path has an exact fallback whose target exists in the APK.
- `CASE`: Ren'Py normally resolves this through its case-normalized loader map; verify the target runtime before patching.
- `DYNAMIC`: a glob or formatted path requires control-flow inspection rather than literal matching.

When an error screen replaces non-ASCII filenames with squares, recover the exact string from the decompiled source and verify Unicode code points. Never guess a filename from the screenshot alone.

After one missing-resource traceback, audit all related references across the game. Avoid whack-a-mole builds.

## Patch the smallest safe surface

Prefer an overlay containing only:

- compiled `tl/<language>/*.rpyc` files;
- one late-init bootstrap for language, fonts, dynamic strings, and narrowly scoped compatibility fixes;
- intentional font/media assets and licenses.

Map only proven-bad asset names to semantically suitable shipped assets. Keep the original exception behavior for unknown missing files; never catch every `IOError` or disable an entire audio/media subsystem.

Make runtime hooks idempotent, preserve `*args`/`**kwargs`, and compile them with a compatible Ren'Py SDK. Decompile the resulting `.rpyc` into a temporary directory and compare all non-ASCII strings to the source before packaging.

Derive Android asset escaping from the APK. A game path may become `assets/x-game/x-...`; a correct file at the wrong entry path is still missing.

## Build, align, sign, and verify

Use this order:

1. Run translation, placeholder, tag, dynamic-string, and asset-reference validators.
2. Compile Ren'Py sources and inspect compiler tracebacks.
3. Recreate a clean staging directory from explicit inputs.
4. Copy the original APK to a new unsigned candidate and apply the overlay.
5. Run `zipalign` before signing.
6. Sign with the retained localization key.
7. Run `apksigner verify --verbose --print-certs` and record certificate fingerprints.
8. Verify the final APK against the original and stage:

```powershell
python scripts/verify_apk_overlay.py --original <original.apk> --final <localized.apk> --stage <overlay-directory>
```

9. Compute final size and SHA-256.

Never claim update compatibility until the installed build and candidate certificates match.

## Protect saves and installed state

1. Locate and hash the full save set before uninstalling, clearing data, or replacing a differently signed build. Include slots, `persistent`, sync data, security keys, and upgrade markers.
2. Stop the game or reach a safe point before copying saves.
3. Attempt a same-certificate replacement install first.
4. Treat a certificate mismatch as an install-state problem, not an APK-content problem.
5. If saves are inside a private compatibility container and cannot be backed up, do not uninstall or clear data. Limit work to a proven same-certificate update or stop for user direction.
6. Confirm save visibility from the load, auto-save, and quick-save pages without loading or overwriting slots unnecessarily.

## Route device work correctly

Detect the actual transport before assuming ADB:

- Use ADB when `adb devices` exposes the Android runtime.
- Use HDC when the device exposes a HarmonyOS HDC interface.
- Treat Android compatibility containers as a separate package/save/log boundary. HDC may see only the host bundle, and `hdc install` may accept HAP/HSP but not the APK inside the container.
- Use UI automation and screenshots when semantic Android tooling cannot enter the container. Transfer a tiny probe before a multi-hundred-megabyte APK.

Never use root, `nsenter`, uninstall, or data clearing merely to make testing convenient.

## Test states, not only screens

Create a risk-based runtime matrix. At minimum verify:

- cold launch and main menu;
- settings, language/font rendering, load, auto-save, and quick-save pages;
- representative narration, character names, long dialogue, choices, and quick menu;
- baked menu images/video and at least two loops for patched animation;
- the first interactive/night loop;
- one failure/attack route, one random encounter, and one QTE/minigame when present;
- every route named in a prior traceback or user report;
- logs or visible error screens after each high-risk state.

Do not overwrite existing progress solely for QA. If no saves exist, enter only as far as needed and report any auto-save created by testing.

Classify evidence precisely:

- `static verified`: compilation/signature/hash/overlay checks only;
- `smoke tested`: launch and shallow UI/dialogue only;
- `route tested`: the named gameplay path was reproduced on target runtime;
- `regression tested`: earlier failing paths and adjacent risky paths all pass.

Never promote static verification to runtime proof. Say “未发现新增严重问题” rather than claiming no bug can exist.

## Deliver the result

Return:

- clickable APK path, size, SHA-256, package/version, and certificate compatibility;
- fixes and inherited original defects addressed;
- exact static and runtime states tested;
- save backup/restoration status;
- remaining baked English, untested routes, inaccessible logs, or container limitations;
- safe update instructions, including “cancel if uninstall is required” when appropriate.
