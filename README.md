# Ren'Py Localization Skill 3.0

面向 Codex 的 Ren'Py 游戏汉化 skill（**PC 优先，Android 兼容**），在 5.7 万条唯一台词的实战项目（Eternum 0.9.0）中打磨成型。

## 3.0 核心能力

- **专有名词一致性强制**：术语表 + 确定性翻译记忆 + 四重自动校验 + 策略化修复，同一英文原文永远渲染同一译文。
- **官方引擎翻译骨架**：调用游戏自带 Ren'Py 引擎生成 `tl/<language>/`，翻译标识符 100% 正确。
- **两遍翻译**：批量直译 + 母语校对润色（长句/带标签/开场剧情走思考模式），断点续跑、批内补漏、残差轮次。
- **自动化流水线**：`scripts/localize.py` 一个入口（extract / translate / polish / validate / repair / apply / names）。
- **全量校验**：标签、插值变量、反斜杠转义、术语四重 multiset 比对；修复器自动收口译名变体、修正标签与换行。
- **中文引导**：`config.language` + 全 UI 中文字体覆盖（init -999 / init 999 时序已验证）。
- **引擎级验证**：`compile` 零错误 + `translate <lang> --count` 零缺失 + 真机/实机冒烟测试。
- **Android 打包**（需要时）：最小 overlay、资源审计、对齐签名、存档兼容、ADB/HDC/模拟器回归。

## 安装

克隆仓库后，将 `renpy-localization` 文件夹复制到个人 Codex skills 目录：

```text
~/.codex/skills/renpy-localization/
```

## 使用（PC 流程）

```powershell
# 0) 环境
$env:RENPY_GAME_DIR = "<游戏根目录>"
$env:DEEPSEEK_API_KEY = "sk-..."

# 1) 引擎生成官方骨架
& $py <game>/Eternum.py $env:RENPY_GAME_DIR translate chinese --no-todo

# 2) 提取 + 术语表（先写 glossary.json，含 entries 与 policies）
python scripts/localize.py extract --lang chinese

# 3) 批量直译 -> 4) 母语润色
python scripts/localize.py translate --lang chinese --workers 4
python scripts/localize.py polish   --lang chinese --workers 4

# 5) 校验 -> 修复（迭代至只剩良性残留）-> 应用
python scripts/localize.py validate --lang chinese
python scripts/localize.py repair   --lang chinese
python scripts/localize.py apply    --lang chinese
python scripts/localize.py names

# 6) 引擎验证 + 冒烟
& $py <game>/Eternum.py $env:RENPY_GAME_DIR compile
& $py <game>/Eternum.py $env:RENPY_GAME_DIR translate chinese --count
```

## 内置脚本

- `localize.py`：统一流水线（extract/translate/polish/validate/repair/apply/names）。
- `glossary.example.json`：术语表结构示例（entries + policies）。
- `extract_characters.py`：从 `Character(...)` 定义提取角色名清单（术语表素材）。
- `audit_apk_assets.py` / `scan_dynamic_strings.py` / `verify_apk_overlay.py`：Android APK 资源审计与 overlay 验证。

## 经验沉淀（详见 references/renpy-field-guide.md）

JSON 解析必须用 `raw_decode`（译文含 `[mc]` 会击穿手写括号计数）；模型可能回显输入结构；max_tokens 截断要靠批内补漏；违规报告截断原文、修复须前缀匹配；`.rpy` 字符串内真实换行必须转义；`translate_clean_stores` 是列表不是布尔；中文路径下 `Start-Process` 传参会被破坏；原版源码常有坏标签需兼容处理。

仓库不包含任何游戏素材、翻译成品、存档、签名密钥或密码。
