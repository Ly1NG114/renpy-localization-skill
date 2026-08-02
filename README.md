# Ren'Py Android Localization Skill 2.0

面向 Codex 的 Ren'Py Android APK 汉化、修复、签名与真机验证 skill，支持普通视觉小说和成人游戏。

## 2.0 重点能力

- 重建或编译 `.rpy` / `.rpyc` 翻译，保护占位符、文本标签与控制流。
- 审计 APK 中缺失、非 ASCII、大小写差异及动态生成的资源路径。
- 使用精确资源回退映射修复原版 APK 遗留的音频或媒体缺失。
- 保留原始 Android wrapper，以最小 overlay 重建、对齐和签名 APK。
- 保护存档与签名兼容性，禁止在无法备份时贸然卸载或清数据。
- 支持 ADB、HarmonyOS HDC、模拟器和 Android 兼容容器测试。
- 按首夜、袭击/失败路线、随机事件和 QTE 等风险状态做真机回归。
- 保留成人文本的显式程度、人物语气、情境身份和场景节奏。

## 安装

克隆仓库后，将 `renpy-android-localization` 文件夹复制到个人 Codex skills 目录：

```text
~/.codex/skills/renpy-android-localization/
```

## 使用

在 Codex 中调用：

```text
Use $renpy-android-localization to localize, repair, sign, and runtime-validate this Ren'Py Android APK.
```

## 内置脚本

- `audit_apk_assets.py`：对比 Ren'Py 静态资源引用与 APK 实际条目，并验证精确 fallback。
- `scan_dynamic_strings.py`：查找标准翻译块遗漏的动态 UI 与运行时字符串。
- `verify_apk_overlay.py`：验证最终 APK 等于原 APK 加显式 overlay，确保未修改资源字节一致。

仓库不包含任何游戏 APK、游戏素材、翻译成品、存档、签名密钥或密码。
