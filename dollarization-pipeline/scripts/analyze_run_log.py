#!/usr/bin/env python3
"""파이프라인 로그 파일을 훑어 국가별 이슈를 요약한다.

사용:
  python scripts/analyze_run_log.py ../log-260813-1219.md
  python scripts/analyze_run_log.py runs/run-....json   # JSON 리포트면 그대로 pretty-print
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
        if d["logger"] in ("__main__", "__mp_main__") and code and "행 수집" in msg:
            mm = re.search(r"(\d+)행 수집", msg)
            if mm:
                success_rows[code] = int(mm.group(1))
        if "수집 결과 없음" in msg and code:
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
            or "실패" in e["msg"]
            or "스킵" in e["msg"]
            or "failed" in e["msg"].lower()
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
        if "수집 요약:" in raw:
            summary = raw.strip()

    return {
        "summary_line": summary,
        "level_counts": dict(levels),
        "timeouts": sorted(set(timeouts)),
        "success_with_rows": dict(sorted(success_rows.items())),
        "empty_mentions": sorted(set(empty)),
        "parser_soft_issues": dict(sorted(soft.items(), key=lambda x: -x[1]["n_issues"])),
        "note": (
            "success_with_rows = 최종 'N행 수집' 로그가 있는 국가. "
            "중간 다운로드 실패 INFO/WARNING이 많아도 최종 행이 있으면 성공 집계됨. "
            "empty = 예외 없이 빈 DF. fail(요약) = 파이프라인 ERROR 문자열 반환만."
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
        print("\n# 중간 이슈가 많았지만 최종 성공(부분 성공) 국가:")
        for c in both:
            print(f"  {c}: rows={soft[c]['final_success_rows']} issues={soft[c]['n_issues']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
