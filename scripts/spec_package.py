"""Rebuild the derived files of final-spec after an edit, then verify the package.

final-spec is hash-locked: every edit must refresh the acceptance register, the document index and
PACKAGE-MANIFEST.json. Files in the package are ASCII with CRLF line endings; this script enforces both.

    uv run python scripts/spec_package.py            # rebuild and verify
    uv run python scripts/spec_package.py --zip 1.2  # also write ARAI-final-spec-v1.2.zip
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "final-spec"
REGISTER_COLUMNS = ["acceptance_id", "component", "criterion", "status", "evidence_path", "executed_at", "reviewer"]
TEXT_SUFFIXES = {".md", ".yaml", ".json", ".csv", ".html", ".py"}


def _criteria():
    """(component file, title, [(id, text), ...]) for every component, read from its acceptance table."""
    for path in sorted((SPEC / "components").glob("*.md")):
        text = path.read_bytes().decode("ascii").replace("\r\n", "\n")
        yield path.name, text.split("\n")[0][2:], re.findall(r"^\| ([A-Z]+-AC-\d\d) \| (.*) \|$", text, re.M)


def rebuild_register() -> int:
    """Regenerate the register from the component tables, keeping any recorded status and evidence."""
    path = SPEC / "acceptance-register.csv"
    with path.open(encoding="ascii", newline="") as handle:
        recorded = {row["acceptance_id"]: row for row in csv.DictReader(handle)}
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(REGISTER_COLUMNS)
    index, count = [], 0
    for name, title, rows in _criteria():
        index.append([name, title, rows[0][0].split("-")[0], [text for _, text in rows]])
        for criterion_id, text in rows:
            old = recorded.get(criterion_id, {})
            writer.writerow([criterion_id, f"components/{name}", text, old.get("status") or "NOT_RUN",
                             old.get("evidence_path", ""), old.get("executed_at", ""), old.get("reviewer", "")])
            count += 1
    path.write_bytes(out.getvalue().encode("ascii"))
    (SPEC / "verification" / "doc-index.json").write_bytes(json.dumps(index, indent=2).replace("\n", "\r\n").encode("ascii"))
    return count


def check_text_files() -> None:
    for path in sorted(SPEC.rglob("*")):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            data = path.read_bytes()
            data.decode("ascii")
            if b"\n" in data.replace(b"\r\n", b""):
                raise SystemExit(f"{path.relative_to(ROOT)} has bare LF line endings; the package uses CRLF")


def rebuild_manifest(version: str | None, amended: str | None) -> list:
    path = SPEC / "PACKAGE-MANIFEST.json"
    manifest = json.loads(path.read_bytes())
    listed = set(manifest["files_sha256"]) | {"PACKAGE-MANIFEST.json"}
    on_disk = {p.relative_to(SPEC).as_posix() for p in SPEC.rglob("*") if p.is_file()}
    if on_disk != listed:
        raise SystemExit(f"package file list changed: unlisted {sorted(on_disk - listed)}, missing {sorted(listed - on_disk)}")
    changed = []
    for name, old in manifest["files_sha256"].items():
        new = hashlib.sha256((SPEC / name).read_bytes()).hexdigest()
        if new != old:
            changed.append(name)
        manifest["files_sha256"][name] = new
    if version:
        manifest["version"] = version
    if amended:
        manifest["amended"] = amended
    path.write_bytes((json.dumps(manifest, indent=2).replace("\n", "\r\n") + "\r\n").encode("ascii"))
    return changed


def write_zip(version: str) -> Path:
    target = ROOT / f"ARAI-final-spec-v{version}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(p for p in SPEC.rglob("*") if p.is_file()):
            archive.write(path, path.relative_to(ROOT).as_posix())
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--version", help="set the package version in the manifest")
    parser.add_argument("--amended", help="set the amendment date in the manifest (YYYY-MM-DD)")
    parser.add_argument("--zip", metavar="VERSION", help="also write ARAI-final-spec-v<VERSION>.zip")
    args = parser.parse_args()
    count = rebuild_register()
    check_text_files()
    changed = rebuild_manifest(args.version, args.amended)
    print(f"{count} acceptance criteria; {len(changed)} file hashes updated")
    result = subprocess.run([sys.executable, str(SPEC / "tools" / "verify_package.py")])
    if result.returncode == 0 and args.zip:
        print("wrote", write_zip(args.zip).name)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
