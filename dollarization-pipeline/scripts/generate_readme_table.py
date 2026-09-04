"""Read the adapter field from config/targets.json and refresh the adapter status table in README.md.

Replaces everything between <!-- ADAPTER_STATUS_TABLE:START --> and
<!-- ADAPTER_STATUS_TABLE:END --> in README.md with a freshly generated table
each time (idempotent).

Usage: python3 scripts/generate_readme_table.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS_PATH = ROOT / "config" / "targets.json"
README_PATH = ROOT / "README.md"

START_MARKER = "<!-- ADAPTER_STATUS_TABLE:START -->"
END_MARKER = "<!-- ADAPTER_STATUS_TABLE:END -->"

STATUS_LABEL = {
    "success": "Implemented",
    "failed": "Failed (no indicator)",
    "needs_research": "Needs re-research",
    "todo": "Not started",
    "not_applicable": "Not applicable",
}


def _escape_cell(text: str) -> str:
    # '|' collides with the table delimiter, and '<'/'>' can be interpreted as
    # real HTML tags (e.g. text like <table>), breaking the rest of the table —
    # so escape them.
    return text.replace("|", "/").replace("<", "&lt;").replace(">", "&gt;")


def build_table(targets: list[dict]) -> str:
    counts = {"success": 0, "failed": 0, "needs_research": 0, "todo": 0, "not_applicable": 0}
    rows = []
    for t in sorted(targets, key=lambda x: x["country_code"]):
        adapter = t["adapter"]
        status = adapter["status"]
        counts[status] += 1
        if status in ("todo", "not_applicable"):
            continue  # not-started/not-applicable countries are omitted from the table, only counted in the summary
        rows.append(
            "| {code} | {name} | {data_type} | {strategy} | {status} | {notes} |".format(
                code=t["country_code"],
                name=t["country_name"],
                data_type=t["data_type"],
                strategy=adapter["strategy_class"] or "-",
                status=STATUS_LABEL[status],
                notes=_escape_cell(adapter["notes"] or ""),
            )
        )

    total = len(targets)
    summary = (
        f"Of {total} countries: {counts['success']} implemented / "
        f"{counts['failed']} failed / {counts['needs_research']} need re-research / "
        f"{counts['todo']} not started / {counts['not_applicable']} not applicable "
        f"(not-started/not-applicable countries are omitted from the table)"
    )

    header = "| Country Code | Country | data_type | strategy_class | Adapter Status | Notes |\n"
    header += "| --- | --- | --- | --- | --- | --- |"

    return "\n".join([summary, "", header, *rows])


def main() -> None:
    targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    table = build_table(targets)

    readme = README_PATH.read_text(encoding="utf-8")
    start = readme.index(START_MARKER) + len(START_MARKER)
    end = readme.index(END_MARKER)
    new_readme = readme[:start] + "\n" + table + "\n" + readme[end:]
    README_PATH.write_text(new_readme, encoding="utf-8")
    print(f"README adapter status table updated ({len(targets)} countries)")


if __name__ == "__main__":
    main()
