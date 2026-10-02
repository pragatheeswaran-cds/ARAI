"""Verify the portable specification package; Python 3.10+, standard library only."""
from pathlib import Path
import csv, hashlib, json, re
ROOT = Path(__file__).resolve().parents[1]
def main():
    manifest = json.loads((ROOT / "PACKAGE-MANIFEST.json").read_text(encoding="utf-8"))
    for name, expected in manifest["files_sha256"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT.resolve()):
            raise ValueError("Manifest path escapes package: " + name)
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Missing or changed file: " + name)
    links = 0
    for path in ROOT.rglob("*.md"):
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            linked = (path.parent / target.split("#")[0]).resolve()
            if not linked.is_relative_to(ROOT.resolve()) or not linked.exists():
                raise ValueError("Broken/nonportable link: " + str(path.relative_to(ROOT)) + " -> " + target)
            links += 1
    with (ROOT / "acceptance-register.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    ids = [row["acceptance_id"] for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate acceptance ID")
    for row in rows:
        if row["acceptance_id"] not in (ROOT / row["component"]).read_text(encoding="utf-8"):
            raise ValueError("Acceptance ID not found in owning component")
    html = (ROOT / "wireframe/index.html").read_text(encoding="utf-8")
    if re.search(r'(?:src|href)\s*=\s*["\']https?://', html, flags=re.I):
        raise ValueError("Wireframe depends on external resources")
    print(json.dumps({"files_verified":len(manifest["files_sha256"]), "relative_links":links,
                      "component_specs":len(list((ROOT/"components").glob("*.md"))),
                      "acceptance_criteria":len(ids), "result":"PASS"}, indent=2))
if __name__ == "__main__":
    main()
