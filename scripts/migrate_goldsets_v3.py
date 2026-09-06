"""One-shot, throwaway migration: v2 gold sets -> v3 (turns + collection).

Mechanical only: `question: X` -> `turns: [{question: X}]`, plus a
`collection` key inserted from DOC_COLLECTIONS below. Everything else
(expected_answer, sources, tags, ids, corpus_hashes) passes through
unchanged. None of the four files this script targets carry comments, so a
plain load -> transform -> dump round-trip is safe -- fb_rules.yaml and
scoping.yaml were migrated by hand instead, since they needed judgment
calls (occurrence fixes, new follow-up entries) a script can't make.

Usage: uv run python scripts/migrate_goldsets_v3.py
"""

from __future__ import annotations

from pathlib import Path

import yaml

GOLD_DIR = Path("evals/gold")

# Every document a target file's entries reference belongs to this
# collection (config.toml's [collections] table).
FILE_COLLECTIONS = {
    "amg_mct.yaml": "transmissions",
    "egear.yaml": "transmissions",
    "smg.yaml": "transmissions",
    "tiptronic.yaml": "transmissions",
}


def migrate_entry(entry: dict) -> dict:
    if "turns" in entry:
        return entry  # already v3
    question = entry.pop("question")
    migrated = {"id": entry["id"], "turns": [{"question": question}]}
    for key in ("expected_answer", "sources", "tags"):
        migrated[key] = entry[key]
    return migrated


def migrate_file(path: Path, collection: str) -> None:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("version") != 2:
        print(f"  skip {path.name}: not v2 (version={raw.get('version')})")
        return

    migrated = {
        "version": 3,
        "collection": collection,
        "corpus_hashes": raw["corpus_hashes"],
        "entries": [migrate_entry(dict(e)) for e in raw["entries"]],
    }
    path.write_text(yaml.safe_dump(migrated, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"  wrote {path.name}: {len(migrated['entries'])} entries, collection={collection}")


def main() -> None:
    for filename, collection in FILE_COLLECTIONS.items():
        migrate_file(GOLD_DIR / filename, collection)


if __name__ == "__main__":
    main()
