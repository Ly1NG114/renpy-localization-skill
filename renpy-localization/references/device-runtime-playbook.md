# Ren'Py Android Device Runtime Playbook

## Contents

1. [Identify the actual transport](#identify-the-actual-transport)
2. [Use the ADB path](#use-the-adb-path)
3. [Use the HarmonyOS HDC path](#use-the-harmonyos-hdc-path)
4. [Handle Android compatibility containers](#handle-android-compatibility-containers)
5. [Transfer and install safely](#transfer-and-install-safely)
6. [Capture UI and logs](#capture-ui-and-logs)
7. [Protect saves when visibility is limited](#protect-saves-when-visibility-is-limited)
8. [Run a device QA sequence](#run-a-device-qa-sequence)

## Identify the actual transport

Do not equate “USB debugging enabled” with “ADB available.” Inspect the exposed interface and run both discovery commands when relevant:

```powershell
adb devices -l
hdc list targets -v
```

Classify the target:

- **Native Android/ADB**: the game package, process, logcat, and external saves are visible through Android tooling.
- **HarmonyOS/HDC**: the phone exposes an HDC interface and native Harmony packages through `bm`/`aa`.
- **Android compatibility container**: an Android app runs inside a host Harmony bundle or container; HDC sees the host but not necessarily Android package manager, private files, or logcat.
- **Emulator**: determine whether its Android runtime is reachable through ADB even when the host UI uses another tool.

Record device model, OS/build, API/SDK, CPU ABI, serial/target ID, transport tool/version, package visibility, and save visibility.

## Use the ADB path

Prefer read-only orientation first:

```powershell
adb shell getprop ro.product.model
adb shell getprop ro.build.version.release
adb shell getprop ro.product.cpu.abi
adb shell pm path <package>
adb shell dumpsys package <package>
adb shell pidof <package>
```

Back up accessible saves before installation. Then use a replacement install:

```powershell
adb install -r <candidate.apk>
```

Treat `INSTALL_FAILED_UPDATE_INCOMPATIBLE` as certificate evidence. Do not follow it with uninstall unless a complete verified backup exists and the user has authorized reinstall/migration.

Capture runtime evidence with screenshots, screen recording, and filtered logcat. Preserve the full traceback and several seconds of context around it.

## Use the HarmonyOS HDC path

Use an HDC binary appropriate for the device generation. Verify its signature/source when it was obtained outside an existing SDK installation.

Common read-only commands:

```powershell
hdc list targets -v
hdc shell "param get const.product.model"
hdc shell "bm dump -a"
hdc shell "ps -ef"
hdc shell "hilog -x"
```

HDC application installation commonly targets HAP/HSP rather than an APK inside an Android compatibility container. Read `hdc help` for the installed version before assuming `hdc install` can update the game.

Use HDC file transfer and UI automation when the compatibility app is visible on screen but its Android package manager is not exposed:

```powershell
hdc shell "uitest uiInput keyEvent Home"
hdc shell "uitest uiInput click <x> <y>"
hdc shell "uitest dumpLayout -p /data/local/tmp/layout.json"
hdc shell "snapshot_display -f /data/local/tmp/screen.jpeg"
hdc file recv /data/local/tmp/screen.jpeg <local-path>
```

Some `snapshot_display` versions accept only JPEG. Query help or honor the error message rather than repeatedly changing unrelated flags.

## Handle Android compatibility containers

Recognize container evidence:

- the visible game has an Android activity name but native `bm` lists only a host bundle;
- a host process starts LXC/isulad or another Android runtime;
- the package name appears in UI hierarchy while host package tools cannot query it;
- HDC shell cannot access Android save/database paths;
- Harmony `hilog` lacks Ren'Py/Python tracebacks shown on screen.

Treat the host and Android guest as separate security and data boundaries.

Do not attempt root mode, `nsenter`, private mount traversal, or permission bypass simply to obtain saves/logs. Lack of access is a constraint to report, not permission to weaken the device.

Do not use host bundle uninstall/clear-data to repair the guest game. It may destroy the entire compatibility container and every Android app within it.

## Transfer and install safely

When a manual compatibility-container installer is required:

1. verify the candidate locally (alignment, signature, overlay, SHA-256);
2. compare its certificate with the previous localized APK;
3. discover a user-visible shared directory;
4. transfer a tiny probe file first;
5. verify the probe and remove only files created by the test if cleanup is needed;
6. transfer the APK;
7. compute the device-side SHA-256 when permitted;
8. ask the user or use approved UI interaction to choose **update/replace**, never uninstall;
9. cancel if the installer requires uninstall or reports a signature mismatch.

A common Harmony shared download path is:

```text
/storage/media/<user-id>/local/files/Docs/Download/
```

Do not hard-code the user ID. Confirm the active user/path, and expect shell listing permissions to differ from HDC file-transfer permissions.

Keep the APK in the shared directory until runtime verification completes. Tell the user it can be deleted afterward to reclaim space.

## Capture UI and logs

Use the strongest evidence available in this order:

1. Ren'Py `log.txt`, `traceback.txt`, or `errors.txt` from the game save/log root;
2. Android logcat for the package/process;
3. container-specific Android logs;
4. Harmony hilog for host/container events;
5. full-resolution screenshot or photo of the Ren'Py error screen.

If only a screenshot is available:

- read the final exception and missing path;
- note the first game or translation script frame;
- do not blame a loader wrapper merely because it appears in the stack;
- recover boxed/non-ASCII text from decompiled source;
- locate every use of the same asset family.

Capture screenshots at native device resolution. Image viewers may resize them; convert visible coordinates back to original pixels before UI automation. Verify every click by capturing the resulting screen rather than trusting a “No Error” response.

UI hierarchy dumps may expose only one Android surface view. In that case, visual coordinates are the correct testing method; semantic text selection will not be available.

## Protect saves when visibility is limited

Use this decision table:

| Save access | Certificate match | Allowed installation action |
|---|---|---|
| Full verified backup | Match | Replacement update; preserve backup |
| Full verified backup | Mismatch | Reinstall/migrate only with user authorization |
| No backup, slots visible | Proven match | Replacement update only |
| No backup | Unknown/mismatch | Stop; do not uninstall or clear data |

Inspect manual, auto-save, and quick-save pages before starting a new game. Empty page 1 does not prove auto/quick pages are empty.

Avoid loading a slot just to prove it exists. Loading can advance state, trigger autosaves, or migrate persistent data.

If testing begins from an entirely empty save set, advance only to representative text/mechanics and record whether the game created an autosave.

## Run a device QA sequence

Use this order to minimize state changes and transfer loops:

1. confirm device/transport/package/container identity;
2. assess save backup and certificate compatibility;
3. cold-launch the installed build;
4. capture main menu and wait for delayed media/audio failures;
5. open settings, manual load, auto-save, and quick-save pages;
6. verify CJK font coverage and long UI labels;
7. enter representative dialogue only after save inspection;
8. exercise the first core interactive/night loop;
9. exercise prior traceback routes and adjacent uses of the same asset family;
10. capture logs/screens after each high-risk state;
11. leave the device in a safe, understandable state;
12. retain save backup and prior APK until the user confirms continued play.

When the device disconnects, continue static diagnosis/build work but label the candidate “static verified, awaiting runtime retest.” Do not convert absence of a device into a runtime pass.
