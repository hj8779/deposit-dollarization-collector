"""config/targets.json의 adapter 필드를 읽어 README.md의 어댑터 현황 테이블을 갱신한다.

README.md 안의 <!-- ADAPTER_STATUS_TABLE:START --> ~ <!-- ADAPTER_STATUS_TABLE:END --> 사이를
매번 재생성된 테이블로 교체한다 (idempotent).

사용법: python3 scripts/generate_readme_table.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGETS_PATH = ROOT / "config" / "targets.json"
README_PATH = ROOT / "README.md"

START_MARKER = "<!-- ADAPTER_STATUS_TABLE:START -->"
END_MARKER = "<!-- ADAPTER_STATUS_TABLE:END -->"

STATUS_LABEL = {
    "success": "구현됨",
    "failed": "실패(지표 없음)",
    "needs_research": "재조사 필요",
    "todo": "미착수",
    "not_applicable": "대상 아님",
}


def _escape_cell(text: str) -> str:
    # '|'는 표 구분자와 충돌하고, '<'/'>'는 <table> 같은 텍스트가 실제 HTML 태그로
    # 해석되어 이후 표 전체가 깨지는 원인이 되므로 이스케이프한다.
    return text.replace("|", "/").replace("<", "&lt;").replace(">", "&gt;")


def build_table(targets: list[dict]) -> str:
    counts = {"success": 0, "failed": 0, "needs_research": 0, "todo": 0, "not_applicable": 0}
    rows = []
    for t in sorted(targets, key=lambda x: x["country_code"]):
        adapter = t["adapter"]
        status = adapter["status"]
        counts[status] += 1
        if status in ("todo", "not_applicable"):
            continue  # 미착수/대상 아님 국가는 표에서 생략, 요약 카운트에만 반영
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
        f"전체 {total}개국 중 구현됨 {counts['success']}개 / "
        f"실패 {counts['failed']}개 / 재조사 필요 {counts['needs_research']}개 / "
        f"미착수 {counts['todo']}개 / 대상 아님 {counts['not_applicable']}개 "
        f"(미착수·대상 아님 국가는 표에서 생략)"
    )

    header = "| 국가코드 | 국가명 | data_type | strategy_class | adapter 상태 | 비고 |\n"
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
    print(f"README 어댑터 현황 테이블 갱신 완료 ({len(targets)}개국)")


if __name__ == "__main__":
    main()
