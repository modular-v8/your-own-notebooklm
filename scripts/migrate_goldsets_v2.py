"""Throwaway migration: gold-set schema v1 -> v2 for the four Markdown gold sets.

Mechanical only: `doc` + `answer_location` collapse into a one-element
`sources` list (empty for `not-in-document` entries). Tags and everything
else pass through unchanged -- retagging to the controlled vocabulary is a
separate, deliberate authoring pass, not part of this schema migration.

Run once, then delete; a `gold migrate` command would outlive its purpose
by the length of the project (see specs/2-grounded-answering/plan.md).
"""

from __future__ import annotations

from pathlib import Path

import yaml

GOLD_DIR = Path("evals/gold")
TARGETS = ["amg_mct.yaml", "egear.yaml", "smg.yaml", "tiptronic.yaml"]


def migrate_entry(entry: dict) -> dict:
    doc = entry.pop("doc")
    location = entry.pop("answer_location")
    sources = [] if location is None else [{"doc": doc, "answer_location": location}]
    return {
        "id": entry["id"],
        "question": entry["question"],
        "expected_answer": entry["expected_answer"],
        "sources": sources,
        "tags": entry.get("tags", []),
    }


def migrate_file(path: Path) -> None:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        print(f"skip {path}: not version 1")
        return
    raw["version"] = 2
    raw["entries"] = [migrate_entry(e) for e in raw["entries"]]
    path.write_text(yaml.dump(raw, sort_keys=False, allow_unicode=True, width=100), encoding="utf-8")
    print(f"migrated {path}")


def main() -> None:
    for name in TARGETS:
        migrate_file(GOLD_DIR / name)


if __name__ == "__main__":
    main()
