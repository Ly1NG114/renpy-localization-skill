#!/usr/bin/env python3
"""Find likely runtime-generated Ren'Py strings missing from translation coverage."""

from __future__ import annotations

import argparse
import ast
import re
import sys
import warnings
from dataclasses import dataclass
from pathlib import Path


QUOTED_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
OLD_RE = re.compile(r'(?m)^\s*old\s+("(?:\\.|[^"\\])*")\s*$')
ASSIGN_RE = re.compile(r"^\s*\$?\s*([A-Za-z_]\w*)\s*=\s*(.+)$")
SCREEN_RE = re.compile(r"^\s*(text|textbutton)\s+(.+)$")
CALL_RE = re.compile(
    r"\b(renpy\.notify|save_checkpoint|save_manual|renpy\.save|Text)\s*\((.*)$"
)
INTERESTING_NAME_RE = re.compile(
    r"prompt|label|note|message|title|caption|tooltip|description|save_name|button_text",
    re.I,
)
LATIN_WORD_RE = re.compile(r"[A-Za-z]{2,}")
CJK_RE = re.compile(r"[\u3400-\u9fff]")

warnings.filterwarnings("ignore", category=SyntaxWarning)


@dataclass(frozen=True)
class Candidate:
    text: str
    path: Path
    line: int
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--translation-root", required=True, type=Path)
    parser.add_argument("--direct-map", type=Path)
    parser.add_argument("--map-variable", default="_cn_direct_text_map")
    parser.add_argument("--fail-on-uncovered", action="store_true")
    return parser.parse_args()


def decode_literal(token: str, context: str) -> str:
    try:
        value = ast.literal_eval(token)
    except (SyntaxError, ValueError) as error:
        raise SystemExit(f"invalid string literal in {context}: {token}: {error}") from error
    return value if isinstance(value, str) else ""


def extract_dict_assignment(source: str, variable: str) -> dict[str, str]:
    match = re.search(rf"\b{re.escape(variable)}\s*=\s*", source)
    if match is None:
        return {}
    start = source.find("{", match.end())
    if start < 0:
        return {}

    depth = 0
    quote = ""
    escaped = False
    for index in range(start, len(source)):
        char = source[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in "\"'":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                value = ast.literal_eval(source[start : index + 1])
                if not isinstance(value, dict):
                    return {}
                return {str(key): str(target) for key, target in value.items()}
    return {}


def translated_sources(root: Path) -> set[str]:
    covered: set[str] = set()
    for path in root.rglob("*.rpy"):
        source = path.read_text(encoding="utf-8-sig")
        for token in OLD_RE.findall(source):
            covered.add(decode_literal(token, str(path)))
    return covered


def candidate_literals(expression: str) -> list[str]:
    values: list[str] = []
    for token in QUOTED_RE.findall(expression):
        value = decode_literal(token, expression)
        if LATIN_WORD_RE.search(value):
            values.append(value)
    return values


def first_screen_literal(expression: str) -> str | None:
    expression = expression.lstrip()
    if not expression.startswith(("\"", "'")):
        return None
    match = QUOTED_RE.match(expression)
    if match is None:
        return None
    value = decode_literal(match.group(0), expression)
    if not LATIN_WORD_RE.search(value):
        return None
    if re.fullmatch(r"\s*\[[^]]+\]\s*", value):
        return None
    return value


def scan_sources(root: Path) -> list[Candidate]:
    candidates: list[Candidate] = []
    for path in root.rglob("*.rpy"):
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            assignment = ASSIGN_RE.match(line)
            if assignment and INTERESTING_NAME_RE.search(assignment.group(1)):
                for value in candidate_literals(assignment.group(2)):
                    candidates.append(Candidate(value, path, number, "assignment"))
                continue

            call = CALL_RE.search(line)
            if call:
                for value in candidate_literals(call.group(2)):
                    candidates.append(Candidate(value, path, number, call.group(1)))
                continue

            screen = SCREEN_RE.match(line)
            if screen:
                value = first_screen_literal(screen.group(2))
                if value is not None:
                    candidates.append(Candidate(value, path, number, screen.group(1)))
    return candidates


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()
    translation_root = args.translation_root.resolve()
    if not source_root.is_dir():
        raise SystemExit(f"source root not found: {source_root}")
    if not translation_root.is_dir():
        raise SystemExit(f"translation root not found: {translation_root}")

    covered_by_tl = translated_sources(translation_root)
    direct_map: dict[str, str] = {}
    if args.direct_map:
        direct_path = args.direct_map.resolve()
        direct_map = extract_dict_assignment(
            direct_path.read_text(encoding="utf-8-sig"), args.map_variable
        )
        if not direct_map:
            raise SystemExit(
                f"could not parse {args.map_variable!r} from direct map: {direct_path}"
            )

    unique: dict[str, Candidate] = {}
    for candidate in scan_sources(source_root):
        unique.setdefault(candidate.text, candidate)

    uncovered: list[Candidate] = []
    bad_targets: list[Candidate] = []
    direct_count = 0
    tl_count = 0
    for text, candidate in sorted(unique.items()):
        if text in direct_map:
            direct_count += 1
            if text == direct_map[text] or not CJK_RE.search(direct_map[text]):
                bad_targets.append(candidate)
        elif text in covered_by_tl:
            tl_count += 1
        else:
            uncovered.append(candidate)

    print(f"candidates={len(unique)}")
    print(f"covered_by_translation={tl_count}")
    print(f"covered_by_direct_map={direct_count}")
    print(f"bad_direct_targets={len(bad_targets)}")
    print(f"uncovered={len(uncovered)}")

    for candidate in bad_targets:
        print(
            f"BAD_TARGET\t{candidate.path}:{candidate.line}\t{candidate.reason}\t{candidate.text}"
        )
    for candidate in uncovered:
        print(
            f"UNCOVERED\t{candidate.path}:{candidate.line}\t{candidate.reason}\t{candidate.text}"
        )

    if bad_targets or (args.fail_on_uncovered and uncovered):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
