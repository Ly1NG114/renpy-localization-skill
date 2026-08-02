#!/usr/bin/env python3
"""Audit static Ren'Py asset references against files packaged in an APK."""

from __future__ import annotations

import argparse
import ast
import re
import zipfile
from collections import defaultdict
from pathlib import Path, PurePosixPath


DEFAULT_EXTENSIONS = "aac,flac,m4a,mp3,ogg,opus,wav"
QUOTED_RE = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
DYNAMIC_RE = re.compile(r"[*?\[\]{}%]")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--apk", required=True, type=Path)
    parser.add_argument(
        "--extensions",
        default=DEFAULT_EXTENSIONS,
        help="Comma-separated extensions without dots; defaults to common audio files.",
    )
    parser.add_argument(
        "--layout",
        choices=("auto", "escaped", "plain"),
        default="auto",
        help="Android asset layout. Auto checks escaped and plain Ren'Py layouts.",
    )
    parser.add_argument("--fallback-map", type=Path)
    parser.add_argument("--map-variable", default="_nt_audio_fallbacks")
    parser.add_argument("--allowlist", type=Path)
    parser.add_argument("--include-translations", action="store_true")
    parser.add_argument("--fail-on-dynamic", action="store_true")
    parser.add_argument("--fail-on-case-mismatch", action="store_true")
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


def normalize_reference(reference: str) -> str:
    reference = reference.replace("\\", "/").lstrip("./")
    if reference.startswith("game/"):
        reference = reference[5:]
    return PurePosixPath(reference).as_posix()


def apk_candidates(reference: str, layout: str) -> list[str]:
    reference = normalize_reference(reference)
    parts = PurePosixPath(reference).parts
    escaped = "assets/x-game/" + "/".join("x-" + part for part in parts)
    plain = "assets/game/" + reference
    if layout == "escaped":
        return [escaped]
    if layout == "plain":
        return [plain]
    return [escaped, plain]


def locate_entry(
    reference: str,
    layout: str,
    entries: set[str],
    casefolded: dict[str, str],
) -> tuple[str, str | None]:
    candidates = apk_candidates(reference, layout)
    for candidate in candidates:
        if candidate in entries:
            return "present", candidate
    for candidate in candidates:
        actual = casefolded.get(candidate.casefold())
        if actual is not None:
            return "case", actual
    return "missing", None


def read_allowlist(path: Path | None) -> set[str]:
    if path is None:
        return set()
    return {
        normalize_reference(line.strip())
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def scan_sources(
    root: Path, extensions: set[str], include_translations: bool
) -> dict[str, list[str]]:
    references: dict[str, list[str]] = defaultdict(list)
    for source in sorted(root.rglob("*.rpy")):
        relative = source.relative_to(root)
        if not include_translations and "tl" in relative.parts:
            continue
        if source.name.startswith("unren-"):
            continue
        for number, line in enumerate(
            source.read_text(encoding="utf-8-sig").splitlines(), 1
        ):
            if line.lstrip().startswith("#"):
                continue
            for token in QUOTED_RE.findall(line):
                value = decode_literal(token, f"{source}:{number}")
                suffix = PurePosixPath(value.lower()).suffix.lstrip(".")
                if suffix in extensions:
                    references[normalize_reference(value)].append(
                        f"{relative.as_posix()}:{number}"
                    )
    return references


def main() -> int:
    args = parse_args()
    source_root = args.source_root.resolve()
    apk = args.apk.resolve()
    if not source_root.is_dir():
        raise SystemExit(f"source root not found: {source_root}")
    if not apk.is_file():
        raise SystemExit(f"APK not found: {apk}")

    extensions = {
        value.strip().lower().lstrip(".")
        for value in args.extensions.split(",")
        if value.strip()
    }
    if not extensions:
        raise SystemExit("at least one extension is required")

    allowlist = read_allowlist(args.allowlist)
    fallback_map: dict[str, str] = {}
    if args.fallback_map:
        map_path = args.fallback_map.resolve()
        fallback_map = extract_dict_assignment(
            map_path.read_text(encoding="utf-8-sig"), args.map_variable
        )
        fallback_map = {
            normalize_reference(key): normalize_reference(value)
            for key, value in fallback_map.items()
        }
        if not fallback_map:
            raise SystemExit(
                f"could not parse {args.map_variable!r} from fallback map: {map_path}"
            )

    references = scan_sources(source_root, extensions, args.include_translations)
    with zipfile.ZipFile(apk) as archive:
        entries = {info.filename for info in archive.infolist() if not info.is_dir()}
    casefolded = {entry.casefold(): entry for entry in entries}

    present: list[str] = []
    case_mismatches: list[tuple[str, str]] = []
    dynamic: list[str] = []
    allowlisted: list[str] = []
    mapped: list[tuple[str, str]] = []
    missing: list[str] = []
    invalid_targets: list[tuple[str, str]] = []

    for reference in sorted(references):
        if reference in allowlist:
            allowlisted.append(reference)
            continue
        if DYNAMIC_RE.search(reference):
            dynamic.append(reference)
            continue
        status, actual = locate_entry(
            reference, args.layout, entries, casefolded
        )
        if status == "present":
            present.append(reference)
            continue
        if status == "case":
            case_mismatches.append((reference, actual or ""))
            continue

        fallback = fallback_map.get(reference)
        if fallback is None:
            missing.append(reference)
            continue
        fallback_status, _ = locate_entry(
            fallback, args.layout, entries, casefolded
        )
        if fallback_status == "missing":
            invalid_targets.append((reference, fallback))
        else:
            mapped.append((reference, fallback))

    print(f"references={len(references)}")
    print(f"present={len(present)}")
    print(f"casefold_present={len(case_mismatches)}")
    print(f"dynamic={len(dynamic)}")
    print(f"allowlisted={len(allowlisted)}")
    print(f"mapped_missing={len(mapped)}")
    print(f"unmapped_missing={len(missing)}")
    print(f"invalid_fallback_targets={len(invalid_targets)}")

    for reference, fallback in mapped:
        print(f"MAPPED\t{reference}\t{fallback}")
    for reference in missing:
        print(f"MISSING\t{reference}\t{', '.join(references[reference])}")
    for reference, fallback in invalid_targets:
        print(f"BAD_FALLBACK\t{reference}\t{fallback}")
    for reference, actual in case_mismatches:
        print(f"CASE\t{reference}\t{actual}")
    for reference in dynamic:
        print(f"DYNAMIC\t{reference}\t{', '.join(references[reference])}")

    failed = bool(missing or invalid_targets)
    failed = failed or bool(args.fail_on_dynamic and dynamic)
    failed = failed or bool(args.fail_on_case_mismatch and case_mismatches)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
