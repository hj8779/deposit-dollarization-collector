#!/usr/bin/env python3
"""Scan a pipeline log file and summarize issues per country.

Usage:
  python scripts/analyze_run_log.py ../log-260813-1219.md
  python scripts/analyze_run_log.py runs/run-....json   # if it's a JSON report, pretty-print as-is
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d+)\s+"
    r"\[(?P<level>DEBUG|INFO|WARNING|ERROR)\]\s+"
    r"(?P<logger>\S+):\s+"
    r"(?:\[(?P<code>[A-Z]{3})\]\s+)?(?P<msg>.*)$"
)


def analyze_log(text: str) -> dict:
    by_code: dict[str, list[dict]] = defaultdict(list)
    levels = Counter()
    timeouts = []
    success_rows = {}
    empty = []
    hard_fail_main = []

    for raw in text.splitlines():
        m = LINE_RE.match(raw.strip())
        if not m:
            continue
        d = m.groupdict()
        levels[d["level"]] += 1
        code = d.get("code")
        msg = d["msg"] or ""
        if code:
            by_code[code].append(
                {"level": d["level"], "logger": d["logger"], "msg": msg[:300]}
            )
        if d["level"] == "ERROR" and code and "TIMEOUT" in msg:
            timeouts.append(code)
        if d["logger"] in ("__main__", "__mp_main__") and code and "Collected" in msg and "rows" in msg:
            mm = re.search(r"Collected (\d+) rows", msg)
            if mm:
                success_rows[code] = int(mm.group(1))
        if "No results collected" in msg and code:
            empty.append(code)
        if d["level"] == "ERROR" and d["logger"] in ("__main__",) and code and "TIMEOUT" not in msg:
            hard_fail_main.append(code)

    # soft issues: WARNING/ERROR from parsers
    soft = {}
    for code, events in by_code.items():
        issues = [
            e
            for e in events
            if e["level"] in ("WARNING", "ERROR")
            or "failed" in e["msg"].lower()
            or "skip" in e["msg"].lower()
        ]
        if issues:
            soft[code] = {
                "n_issues": len(issues),
                "levels": Counter(e["level"] for e in issues),
                "samples": [e["msg"][:160] for e in issues[:5]],
                "final_success_rows": success_rows.get(code),
            }

    # summary line parse
    summary = None
    for raw in text.splitlines():
        if "Collection summary:" in raw:
            summary = raw.strip()

    return {
        "summary_line": summary,
        "level_counts": dict(levels),
        "timeouts": sorted(set(timeouts)),
        "success_with_rows": dict(sorted(success_rows.items())),
        "empty_mentions": sorted(set(empty)),
        "parser_soft_issues": dict(sorted(soft.items(), key=lambda x: -x[1]["n_issues"])),
        "note": (
            "success_with_rows = countries with a final 'Collected N rows' log line. "
            "Still counted as success even with many intermediate download-failure INFO/WARNING "
            "entries, as long as a final row count exists. "
            "empty = empty DF with no exception. fail (summary) = only pipeline ERROR strings returned."
        ),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    path = Path(argv[1])
    if not path.exists():
        print(f"not found: {path}")
        return 1
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".json" and text.lstrip().startswith("{"):
        data = json.loads(text)
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    report = analyze_log(text)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # human hint for TUR-like cases
    soft = report["parser_soft_issues"]
    both = [
        c
        for c, v in soft.items()
        if v.get("final_success_rows") and v["n_issues"] >= 3
    ]
    if both:
        print("\n# Countries with many intermediate issues but eventual success (partial success):")
        for c in both:
            print(f"  {c}: rows={soft[c]['final_success_rows']} issues={soft[c]['n_issues']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
