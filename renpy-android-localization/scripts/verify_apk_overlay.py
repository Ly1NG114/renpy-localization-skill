#!/usr/bin/env python3
"""Verify that a localized APK equals an original APK plus an explicit overlay."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from pathlib import Path


SIGNATURE_RE = re.compile(r"^META-INF/[^/]+\.(?:MF|SF|RSA|DSA|EC)$", re.I)
CHUNK = 1024 * 1024


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original", required=True, type=Path)
    parser.add_argument("--final", required=True, type=Path)
    parser.add_argument("--stage", required=True, type=Path)
    return parser.parse_args()


def is_signature(name: str) -> bool:
    return bool(SIGNATURE_RE.fullmatch(name))


def duplicate_names(zf: zipfile.ZipFile) -> list[str]:
    seen: set[str] = set()
    duplicates: list[str] = []
    for info in zf.infolist():
        if info.filename in seen:
            duplicates.append(info.filename)
        seen.add(info.filename)
    return duplicates


def file_map(zf: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    return {info.filename: info for info in zf.infolist() if not info.is_dir()}


def stream_equal_and_hash(
    left: zipfile.ZipFile,
    left_info: zipfile.ZipInfo,
    right: zipfile.ZipFile,
    right_info: zipfile.ZipInfo,
    aggregate: hashlib._Hash,
) -> bool:
    with left.open(left_info) as left_stream, right.open(right_info) as right_stream:
        while True:
            left_chunk = left_stream.read(CHUNK)
            right_chunk = right_stream.read(CHUNK)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True
            aggregate.update(left_chunk)


def main() -> int:
    args = parse_args()
    original = args.original.resolve()
    final = args.final.resolve()
    stage = args.stage.resolve()

    for label, path in (("original", original), ("final", final)):
        if not path.is_file():
            raise SystemExit(f"{label} APK not found: {path}")
    if not stage.is_dir():
        raise SystemExit(f"stage directory not found: {stage}")

    stage_files = sorted(path for path in stage.rglob("*") if path.is_file())
    patch_names = {path.relative_to(stage).as_posix() for path in stage_files}
    if any(is_signature(name) for name in patch_names):
        raise SystemExit("stage must not contain APK signature entries")

    errors: list[str] = []
    aggregate = hashlib.sha256()

    with zipfile.ZipFile(original) as original_zip, zipfile.ZipFile(final) as final_zip:
        original_map = file_map(original_zip)
        final_map = file_map(final_zip)

        for label, archive in (("original", original_zip), ("final", final_zip)):
            duplicates = duplicate_names(archive)
            if duplicates:
                errors.append(f"{label} APK has duplicate entries: {duplicates[:20]}")

        preserved_names = sorted(
            name for name in original_map if not is_signature(name) and name not in patch_names
        )
        for name in preserved_names:
            old_info = original_map[name]
            new_info = final_map.get(name)
            if new_info is None:
                errors.append(f"missing original entry: {name}")
                continue
            if (old_info.file_size, old_info.CRC) != (new_info.file_size, new_info.CRC):
                errors.append(f"size/CRC changed for untouched entry: {name}")
                continue

            aggregate.update(name.encode("utf-8"))
            aggregate.update(b"\0")
            aggregate.update(old_info.file_size.to_bytes(8, "little"))
            if not stream_equal_and_hash(original_zip, old_info, final_zip, new_info, aggregate):
                errors.append(f"content changed for untouched entry: {name}")

        for stage_file in stage_files:
            name = stage_file.relative_to(stage).as_posix()
            info = final_map.get(name)
            if info is None:
                errors.append(f"missing staged entry: {name}")
                continue
            expected = hashlib.sha256(stage_file.read_bytes()).digest()
            with final_zip.open(info) as stream:
                actual = hashlib.file_digest(stream, "sha256").digest()
            if expected != actual:
                errors.append(f"staged entry hash mismatch: {name}")

        original_non_signatures = {name for name in original_map if not is_signature(name)}
        final_signatures = {name for name in final_map if is_signature(name)}
        expected_names = original_non_signatures | patch_names | final_signatures
        unexpected = sorted(set(final_map) - expected_names)
        missing = sorted(expected_names - set(final_map))
        if unexpected:
            errors.append(f"unexpected final entries: {unexpected[:30]}")
        if missing:
            errors.append(f"missing expected entries: {missing[:30]}")

        print(f"original_files={len(original_map)}")
        print(f"final_files={len(final_map)}")
        print(f"untouched_files={len(preserved_names)}")
        print(f"staged_files={len(stage_files)}")
        print(f"signature_files={sorted(final_signatures)}")
        print(f"untouched_content_sha256={aggregate.hexdigest()}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("errors=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
