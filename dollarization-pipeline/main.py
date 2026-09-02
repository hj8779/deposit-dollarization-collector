"""외화예금 데이터 자동 수집 파이프라인 실행 엔트리포인트.

국가 수집은 서로 독립이므로 **연속 워커 풀**(끝난 즉시 다음 국가)로 돌리고,
UPSERT는 별도 스레드가 N국 모이면 일괄 처리한다.

사용 예:
  python main.py --status success --only-with-parser --workers 8 --timeout-sec 120
  python main.py --workers 8 --timeout-sec 120 --upsert-batch-size 5
  python main.py --skip-existing
  python main.py --max-db-rows 30          # DB에 30행 이하(또는 없음)인 국가만
  python main.py --list-db-stats
  python main.py --db-summary              # 적재 데이터 기간/지표 요약
  python main.py --upload-targets          # targets.json → country_metadata UPSERT
  python main.py --migrate-indicators      # foreign_currency_deposits → FCD
  python main.py --init-db
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
import traceback
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path
from queue import Empty, Queue
from threading import Event, Thread

import pandas as pd
from dotenv import load_dotenv

from src.collectors.registry import get_strategy
from src.storage.supabase_store import (
    count_metadata_rows,
    count_rows,
    count_rows_by_country,
    ensure_table,
    fetch_sample,
    format_deposit_summary,
    get_engine,
    is_expected_thin,
    list_countries_with_rows,
    migrate_legacy_indicators,
    normalize_frequency_bucket,
    summarize_deposit_data,
    upsert_country_metadata,
    upsert_long_format,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

ROOT = Path(__file__).resolve().parent
TARGETS_PATH = ROOT / "config" / "targets.json"
_UPSERT_SENTINEL = object()

# .env 로드 (SUPABASE_DB_URL 등)
load_dotenv(ROOT / ".env")
load_dotenv()  # cwd fallback


def load_targets(path: Path = TARGETS_PATH) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def filter_targets(
    targets: list[dict],
    countries: list[str] | None = None,
    status: str | None = None,
    only_with_parser: bool = False,
) -> list[dict]:
    out = targets
    if countries:
        want = {c.strip().upper() for c in countries if c.strip()}
        out = [t for t in out if t.get("country_code", "").upper() in want]
    if status:
        out = [
            t
            for t in out
            if (t.get("adapter") or {}).get("status") == status
        ]
    if only_with_parser:
        filtered = []
        for t in out:
            cc = t.get("country_code", "").lower()
            path = ROOT / "src" / "parsers" / f"{cc}.py"
            if path.exists():
                filtered.append(t)
        out = filtered
    return out


def apply_db_filters(
    targets: list[dict],
    *,
    skip_existing: bool = False,
    skip_if_rows_gte: int | None = None,
    max_db_rows: int | None = None,
    min_db_rows: int | None = None,
) -> list[dict]:
    """Supabase에 이미 있는 행 수 기준으로 대상 필터.

    - skip_existing: DB에 1행이라도 있으면 스킵
    - skip_if_rows_gte N: DB 행 수 >= N 이면 스킵 (부분 재수집 방지)
    - max_db_rows N: DB 행 수 <= N 이거나 **아예 없는** 국가만 (저행수/미수집 파서 점검용)
    - min_db_rows N: DB 행 수 >= N 인 국가만
    """
    if not any(
        [
            skip_existing,
            skip_if_rows_gte is not None,
            max_db_rows is not None,
            min_db_rows is not None,
        ]
    ):
        return targets

    counts = count_rows_by_country()
    logger.info("DB 국가별 행 수 로드: %d개국", len(counts))

    kept = []
    skipped = []
    for t in targets:
        code = t.get("country_code", "").upper()
        n = counts.get(code, 0)

        if skip_existing and n > 0:
            skipped.append((code, n, "skip-existing"))
            continue
        if skip_if_rows_gte is not None and n >= skip_if_rows_gte:
            skipped.append((code, n, f"skip-if-rows-gte({skip_if_rows_gte})"))
            continue
        if max_db_rows is not None and n > max_db_rows:
            skipped.append((code, n, f"max-db-rows({max_db_rows})"))
            continue
        if min_db_rows is not None and n < min_db_rows:
            skipped.append((code, n, f"min-db-rows({min_db_rows})"))
            continue
        kept.append(t)

    if skipped:
        sample = ", ".join(f"{c}({n})" for c, n, _ in skipped[:15])
        more = "…" if len(skipped) > 15 else ""
        logger.info(
            "DB 필터로 %d개국 스킵 (예: %s%s)",
            len(skipped),
            sample,
            more,
        )
    logger.info("DB 필터 후 수집 대상: %d개국", len(kept))
    return kept


def _collect_one(target: dict) -> tuple[str, pd.DataFrame | None, str | None]:
    """단일 국가 수집. 반환: (country_code, df|None, error|None)."""
    code = target.get("country_code", "?")
    strategy = get_strategy(target.get("data_type"))
    try:
        df = strategy.collect_and_parse(target)
    except Exception as e:
        logger.exception("[%s] 수집 실패", code)
        return code, None, f"ERROR: {e}"
    if df is None or df.empty:
        logger.info("[%s] 수집 결과 없음", code)
        return code, None, None
    logger.info("[%s] %d행 수집", code, len(df))
    return code, df, None


def _collect_one_worker(target: dict, conn) -> None:
    """별도 프로세스에서 수집 후 Pipe로 결과 전송 (하드 타임아웃용)."""
    load_dotenv(ROOT / ".env")
    load_dotenv()
    code = target.get("country_code", "?")
    try:
        result = _collect_one(target)
        conn.send(("ok", result))
    except Exception as e:
        conn.send(
            (
                "ok",
                (
                    code,
                    None,
                    f"ERROR: {e}\n{traceback.format_exc(limit=5)}",
                ),
            )
        )
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _collect_one_hard_timeout(
    target: dict,
    timeout_sec: float,
) -> tuple[str, pd.DataFrame | None, str | None]:
    """국가 1개를 자식 프로세스에서 돌리고, 초과 시 terminate/kill."""
    code = target.get("country_code", "?")
    if timeout_sec <= 0:
        return _collect_one(target)

    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_collect_one_worker,
        args=(target, child_conn),
        name=f"collect-{code}",
        daemon=True,
    )
    t0 = time.monotonic()
    proc.start()
    child_conn.close()

    proc.join(timeout_sec)
    elapsed = time.monotonic() - t0

    if proc.is_alive():
        logger.error(
            "[%s] TIMEOUT after %.0fs (elapsed %.0fs) — 프로세스 강제 종료 후 스킵",
            code,
            timeout_sec,
            elapsed,
        )
        proc.terminate()
        proc.join(timeout=10)
        if proc.is_alive():
            logger.error("[%s] terminate 실패 → kill()", code)
            proc.kill()
            proc.join(timeout=5)
        parent_conn.close()
        return code, None, f"TIMEOUT after {timeout_sec:.0f}s (elapsed {elapsed:.0f}s)"

    try:
        if parent_conn.poll(1):
            status, payload = parent_conn.recv()
            parent_conn.close()
            if status == "ok":
                return payload
            return code, None, f"ERROR: unexpected status {status}"
        parent_conn.close()
        return code, None, f"ERROR: no result from child (exitcode={proc.exitcode})"
    except Exception as e:
        parent_conn.close()
        return code, None, f"ERROR: {e}"


# ---------------------------------------------------------------------------
# Upsert worker (별도 스레드)
# ---------------------------------------------------------------------------


def _upsert_worker_loop(
    q: Queue,
    flush_every: int,
    dry_run: bool,
    stop_event: Event,
    stats: dict,
) -> None:
    """수집 완료 DataFrame을 모아 N국마다 UPSERT."""
    buffer: list[pd.DataFrame] = []
    codes: list[str] = []

    def _flush(reason: str) -> None:
        nonlocal buffer, codes
        if not buffer:
            return
        df = pd.concat(buffer, ignore_index=True)
        n_countries = len(codes)
        if dry_run:
            logger.info(
                "UPSERT 워커 dry-run flush (%s): %d국 / %d행 — DB 스킵",
                reason,
                n_countries,
                len(df),
            )
        else:
            n = upsert_long_format(df)
            stats["upserted"] = stats.get("upserted", 0) + n
            logger.info(
                "UPSERT 워커 flush (%s): %d국 / %d행 적재 (누적 %d)",
                reason,
                n_countries,
                n,
                stats["upserted"],
            )
        buffer = []
        codes = []

    while not stop_event.is_set() or not q.empty():
        try:
            item = q.get(timeout=0.5)
        except Empty:
            continue
        if item is _UPSERT_SENTINEL:
            _flush("final")
            q.task_done()
            break
        code, df = item
        buffer.append(df)
        codes.append(code)
        q.task_done()
        if flush_every > 0 and len(buffer) >= flush_every:
            _flush(f"batch-{flush_every}")
    # safety
    _flush("shutdown")


# ---------------------------------------------------------------------------
# Continuous worker pool (배치 장벽 없음)
# ---------------------------------------------------------------------------


def run_pipeline(
    targets: list[dict],
    dry_run: bool = False,
    workers: int = 1,
    timeout_sec: float = 0,
    upsert_batch_size: int = 5,
    report_path: Path | None = None,
) -> pd.DataFrame:
    """연속 워커 풀로 수집 + 별도 UPSERT 워커.

    - workers: 동시에 돌릴 수집 슬롯 수. 하나가 끝나면 즉시 다음 국가 시작.
    - timeout_sec: 국가당 하드 타임아웃(프로세스 kill). 0=무제한(스레드 직접 실행).
    - upsert_batch_size: 성공 수집 N국 모이면 UPSERT 워커가 일괄 적재.
    - report_path: 국가별 결과 JSON 리포트 경로 (None이면 runs/ 아래 자동 생성)

    결과 분류 (중요):
      success  — DataFrame 행 있음 (중간 WARNING/부분 스킵이 있어도 성공으로 잡힘)
      empty    — 예외 없이 빈 결과 (파서가 내부에서 실패를 삼킨 경우 포함)
      fail     — 파이프라인까지 예외 문자열이 올라온 경우 (ERROR: ...)
      timeout  — 하드 타임아웃으로 프로세스 kill
    """
    workers = max(1, int(workers))
    upsert_batch_size = max(1, int(upsert_batch_size))

    all_frames: list[pd.DataFrame] = []
    ok = empty = fail = timeout_n = 0
    timeout_codes: list[str] = []
    fail_codes: list[str] = []
    empty_codes: list[str] = []
    success_info: list[dict] = []  # {code, rows}
    outcomes: list[dict] = []  # full per-country record
    stats: dict = {"upserted": 0}
    t_run0 = time.monotonic()

    upsert_q: Queue = Queue()
    stop_event = Event()
    upsert_thread = Thread(
        target=_upsert_worker_loop,
        args=(upsert_q, upsert_batch_size, dry_run, stop_event, stats),
        name="upsert-worker",
        daemon=True,
    )
    upsert_thread.start()

    logger.info(
        "실행 모드: continuous workers=%d, timeout_sec=%s (hard=%s), upsert_batch_size=%d",
        workers,
        timeout_sec or "none",
        timeout_sec > 0,
        upsert_batch_size,
    )

    def _job(t: dict):
        if timeout_sec > 0:
            return _collect_one_hard_timeout(t, timeout_sec)
        return _collect_one(t)

    pending_targets = list(targets)
    idx = 0
    in_flight: dict = {}

    with ThreadPoolExecutor(max_workers=workers) as ex:
        # 초기 슬롯 채우기
        while idx < len(pending_targets) and len(in_flight) < workers:
            t = pending_targets[idx]
            idx += 1
            fut = ex.submit(_job, t)
            in_flight[fut] = t
            logger.debug(
                "제출 [%s] (in_flight=%d, queue_left=%d)",
                t.get("country_code"),
                len(in_flight),
                len(pending_targets) - idx,
            )

        while in_flight:
            done, _ = wait(in_flight.keys(), return_when=FIRST_COMPLETED, timeout=1.0)
            for fut in done:
                target = in_flight.pop(fut)
                code = target.get("country_code", "?")
                try:
                    code, df, err = fut.result()
                except Exception as e:
                    logger.exception("[%s] future 예외", code)
                    code, df, err = code, None, f"ERROR: {e}"

                if err is not None:
                    if str(err).startswith("TIMEOUT"):
                        timeout_n += 1
                        timeout_codes.append(code)
                        outcomes.append(
                            {
                                "country_code": code,
                                "status": "timeout",
                                "rows": 0,
                                "detail": str(err),
                            }
                        )
                    else:
                        fail += 1
                        fail_codes.append(code)
                        outcomes.append(
                            {
                                "country_code": code,
                                "status": "fail",
                                "rows": 0,
                                "detail": str(err)[:500],
                            }
                        )
                elif df is None:
                    empty += 1
                    empty_codes.append(code)
                    outcomes.append(
                        {
                            "country_code": code,
                            "status": "empty",
                            "rows": 0,
                            "detail": "parser returned empty (soft-fail / no data)",
                        }
                    )
                else:
                    ok += 1
                    nrows = len(df)
                    success_info.append({"country_code": code, "rows": nrows})
                    outcomes.append(
                        {
                            "country_code": code,
                            "status": "success",
                            "rows": nrows,
                            "detail": None,
                        }
                    )
                    all_frames.append(df)
                    upsert_q.put((code, df))

                # 슬롯 비는 즉시 다음 국가 제출
                if idx < len(pending_targets):
                    t = pending_targets[idx]
                    idx += 1
                    nf = ex.submit(_job, t)
                    in_flight[nf] = t
                    logger.debug(
                        "제출 [%s] (in_flight=%d, queue_left=%d)",
                        t.get("country_code"),
                        len(in_flight),
                        len(pending_targets) - idx,
                    )

    # 수집 종료 → upsert 워커 마무리
    upsert_q.put(_UPSERT_SENTINEL)
    upsert_q.join()
    stop_event.set()
    upsert_thread.join(timeout=120)

    result = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
    elapsed = time.monotonic() - t_run0

    logger.info(
        "수집 요약: 성공 %d / 빈결과 %d / 실패 %d / 타임아웃 %d / 수집행 %d / UPSERT %d (%.0fs)",
        ok,
        empty,
        fail,
        timeout_n,
        len(result),
        stats.get("upserted", 0),
        elapsed,
    )
    if success_info:
        # targets.json 주기: annual/semi_annual 은 저행수 경고에서 제외
        freq_by_code = {
            str(t.get("country_code", "")).upper(): normalize_frequency_bucket(
                t.get("update_frequency")
            )
            for t in targets
        }
        thin_all = [s for s in success_info if s["rows"] <= 30]
        thin = [
            s
            for s in thin_all
            if not is_expected_thin(
                frequency_bucket=freq_by_code.get(s["country_code"], "unknown")
            )
        ]
        thin_expected = [
            s
            for s in thin_all
            if is_expected_thin(
                frequency_bucket=freq_by_code.get(s["country_code"], "unknown")
            )
        ]
        logger.info(
            "성공 국가 (%d): %s",
            len(success_info),
            ", ".join(f"{s['country_code']}({s['rows']})" for s in sorted(success_info, key=lambda x: x["country_code"])),
        )
        if thin:
            logger.warning(
                "성공이지만 저행수(≤30, annual 제외) (%d) — 파서 점검 후보: %s",
                len(thin),
                ", ".join(f"{s['country_code']}({s['rows']})" for s in thin),
            )
        if thin_expected:
            logger.info(
                "저행수이지만 annual/semi_annual 예외 (%d): %s",
                len(thin_expected),
                ", ".join(f"{s['country_code']}({s['rows']})" for s in thin_expected),
            )
    if empty_codes:
        logger.warning(
            "빈결과 국가 (%d) — 파서가 예외 없이 빈 DF 반환(내부 soft-fail 포함): %s",
            len(empty_codes),
            ", ".join(sorted(empty_codes)),
        )
    if timeout_codes:
        logger.warning(
            "타임아웃 국가 (%d): %s",
            len(timeout_codes),
            ", ".join(timeout_codes),
        )
    if fail_codes:
        logger.warning(
            "실패 국가 (%d) — 파이프라인까지 예외 전파: %s",
            len(fail_codes),
            ", ".join(fail_codes),
        )
    if dry_run:
        logger.info("dry-run 모드: DB 저장은 UPSERT 워커에서도 스킵됨")

    # JSON 리포트 저장
    report = {
        "finished_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "elapsed_sec": round(elapsed, 1),
        "dry_run": dry_run,
        "workers": workers,
        "timeout_sec": timeout_sec,
        "upsert_batch_size": upsert_batch_size,
        "summary": {
            "success": ok,
            "empty": empty,
            "fail": fail,
            "timeout": timeout_n,
            "rows_collected": len(result),
            "rows_upserted": stats.get("upserted", 0),
        },
        "success": sorted(success_info, key=lambda x: x["country_code"]),
        "empty": sorted(empty_codes),
        "fail": sorted(fail_codes),
        "timeout": sorted(timeout_codes),
        "outcomes": sorted(outcomes, key=lambda x: x["country_code"]),
        "notes": {
            "success": "DataFrame 행 있음. 파서 내부 WARNING/부분 스킵이 있어도 성공으로 집계.",
            "empty": "예외 없이 빈 결과. 파서가 실패를 삼키고 empty를 반환한 경우 포함.",
            "fail": "collect 경로에서 ERROR 문자열이 반환된 경우만.",
            "timeout": "하드 타임아웃으로 프로세스 kill.",
        },
    }
    try:
        out = report_path
        if out is None:
            runs_dir = ROOT / "runs"
            runs_dir.mkdir(exist_ok=True)
            out = runs_dir / f"run-{time.strftime('%Y%m%d-%H%M%S')}.json"
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info("실행 리포트 저장: %s", out)
    except Exception:
        logger.exception("실행 리포트 저장 실패")

    return result


def cmd_init_db() -> None:
    engine = get_engine()
    try:
        ensure_table(engine)
        n = count_rows(engine)
        m = count_metadata_rows(engine)
        logger.info(
            "DB 준비 완료. deposit_dollarization=%d행, country_metadata=%d행",
            n,
            m,
        )
        sample = fetch_sample(5, engine)
        if len(sample):
            logger.info("샘플:\n%s", sample.to_string(index=False))
    finally:
        engine.dispose()


def cmd_list_db_stats(max_db_rows: int | None = None) -> None:
    """국가별 DB 행 수 출력. max_db_rows 주면 그 이하만."""
    counts = count_rows_by_country()
    if not counts:
        logger.info("DB에 데이터 없음 (또는 연결 실패)")
        return
    items = sorted(counts.items(), key=lambda x: (x[1], x[0]))
    if max_db_rows is not None:
        items = [(c, n) for c, n in items if n <= max_db_rows]
        logger.info("DB 행 수 ≤ %d 인 국가 (%d개):", max_db_rows, len(items))
    else:
        logger.info("DB 국가별 행 수 (%d개국, 오름차순):", len(items))
    for code, n in items:
        print(f"  {code:4}  {n:6d}")
    # also list targets with parser but missing from DB
    targets = load_targets()
    with_parser = {
        t["country_code"].upper()
        for t in targets
        if (ROOT / "src" / "parsers" / f"{t['country_code'].lower()}.py").exists()
    }
    missing = sorted(with_parser - set(counts))
    if missing:
        logger.info("파서 있으나 DB 0행 (%d): %s", len(missing), ", ".join(missing))


def cmd_db_summary(
    *,
    thin_threshold: int = 30,
    report_path: Path | None = None,
    show_all: bool = True,
    exclude_annual_from_thin: bool = True,
) -> None:
    """deposit_dollarization 적재 현황 요약 (+ optional JSON)."""
    summary = summarize_deposit_data(
        thin_threshold=thin_threshold,
        exclude_annual_from_thin=exclude_annual_from_thin,
    )
    text = format_deposit_summary(summary, show_all_countries=show_all)
    print(text)

    targets = load_targets()
    with_parser = {
        t["country_code"].upper()
        for t in targets
        if (ROOT / "src" / "parsers" / f"{t['country_code'].lower()}.py").exists()
    }
    in_db = {c["country_code"] for c in summary.get("countries") or []}
    missing = sorted(with_parser - in_db)
    summary["parser_but_no_data"] = missing
    if missing:
        logger.info(
            "파서 있으나 deposit 0행 (%d): %s",
            len(missing),
            ", ".join(missing[:40]) + ("…" if len(missing) > 40 else ""),
        )

    if report_path is not None:
        report_path = Path(report_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("DB 요약 JSON 저장: %s", report_path)


def cmd_upload_targets(
    targets_path: Path | None = None,
    *,
    countries: list[str] | None = None,
    status: str | None = None,
) -> int:
    """config/targets.json → country_metadata UPSERT."""
    path = targets_path or TARGETS_PATH
    targets = load_targets(path)
    targets = filter_targets(
        targets,
        countries=countries,
        status=status,
        only_with_parser=False,
    )
    if not targets:
        logger.error("업로드할 targets가 없습니다.")
        return 0
    n = upsert_country_metadata(
        targets,
        parsers_dir=ROOT / "src" / "parsers",
    )
    logger.info("targets 업로드 완료: %d개국 → country_metadata", n)
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dollarization ratio ETL → Supabase")
    p.add_argument("--dry-run", action="store_true", help="수집만, DB 저장 생략")
    p.add_argument("--countries", type=str, default="", help="ISO3 콤마 목록")
    p.add_argument("--status", type=str, default="", help="adapter.status 필터")
    p.add_argument(
        "--only-with-parser",
        action="store_true",
        help="src/parsers/{cc}.py 있는 국가만",
    )
    p.add_argument(
        "--init-db",
        action="store_true",
        help="테이블 생성/확인만 (deposit_dollarization + country_metadata)",
    )
    p.add_argument(
        "--migrate-indicators",
        action="store_true",
        help="레거시 indicator foreign_currency_deposits → FCD 일괄 이전",
    )
    p.add_argument(
        "--list-db-stats",
        action="store_true",
        help="Supabase 국가별 행 수 출력 후 종료",
    )
    p.add_argument(
        "--db-summary",
        action="store_true",
        help="DB 적재 데이터 요약(기간/지표/저행수) 출력 후 종료",
    )
    p.add_argument(
        "--upload-targets",
        action="store_true",
        help="config/targets.json을 country_metadata 테이블에 UPSERT 후 종료",
    )
    p.add_argument(
        "--thin-threshold",
        type=int,
        default=30,
        metavar="N",
        help="--db-summary 저행수 기준 (기본 30)",
    )
    p.add_argument(
        "--include-annual-thin",
        action="store_true",
        help="저행수 목록에 annual/semi_annual 국가도 포함 (기본: 예외 처리)",
    )
    p.add_argument(
        "--summary-json",
        type=str,
        default="",
        help="--db-summary 결과를 JSON으로 저장할 경로",
    )
    p.add_argument("--targets", type=str, default=str(TARGETS_PATH))
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        help="동시 수집 워커 수 (기본 4). 끝난 즉시 다음 국가 시작",
    )
    p.add_argument(
        "--timeout-sec",
        type=float,
        default=0,
        help="국가당 최대 초 (0=무제한). 초과 시 프로세스 강제 종료",
    )
    p.add_argument(
        "--upsert-batch-size",
        type=int,
        default=5,
        help="성공 수집 N국 모이면 UPSERT 워커가 일괄 적재 (기본 5)",
    )
    # backward-compat aliases
    p.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=argparse.SUPPRESS,  # deprecated → upsert-batch-size
    )
    p.add_argument("--upsert-each", action="store_true", help=argparse.SUPPRESS)

    # DB filters
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="DB에 이미 1행 이상 있는 국가 스킵",
    )
    p.add_argument(
        "--skip-if-rows-gte",
        type=int,
        default=None,
        metavar="N",
        help="DB 행 수 ≥ N 인 국가 스킵",
    )
    p.add_argument(
        "--max-db-rows",
        type=int,
        default=None,
        metavar="N",
        help="DB 행 수 ≤ N (또는 미수집) 국가만 수집 — 저행수 파서 점검용",
    )
    p.add_argument(
        "--min-db-rows",
        type=int,
        default=None,
        metavar="N",
        help="DB 행 수 ≥ N 인 국가만",
    )
    p.add_argument(
        "--report",
        type=str,
        default="",
        help="실행 리포트 JSON 경로 (기본: runs/run-YYYYMMDD-HHMMSS.json)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.init_db:
        try:
            cmd_init_db()
            return 0
        except Exception:
            logger.exception("init-db 실패")
            return 1

    if args.migrate_indicators:
        try:
            stats = migrate_legacy_indicators()
            logger.info("migrate-indicators 결과: %s", stats)
            return 0 if stats.get("remaining_legacy", 0) == 0 else 2
        except Exception:
            logger.exception("migrate-indicators 실패")
            return 1

    if args.list_db_stats:
        try:
            cmd_list_db_stats(max_db_rows=args.max_db_rows)
            return 0
        except Exception:
            logger.exception("list-db-stats 실패")
            return 1

    if args.db_summary:
        try:
            cmd_db_summary(
                thin_threshold=args.thin_threshold,
                report_path=Path(args.summary_json)
                if args.summary_json.strip()
                else None,
                exclude_annual_from_thin=not args.include_annual_thin,
            )
            return 0
        except Exception:
            logger.exception("db-summary 실패")
            return 1

    if args.upload_targets:
        try:
            countries = [c for c in args.countries.split(",") if c.strip()] or None
            status = args.status.strip() or None
            n = cmd_upload_targets(
                Path(args.targets),
                countries=countries,
                status=status,
            )
            return 0 if n >= 0 else 1
        except Exception:
            logger.exception("upload-targets 실패")
            return 1

    targets = load_targets(Path(args.targets))
    countries = [c for c in args.countries.split(",") if c.strip()] or None
    status = args.status.strip() or None
    targets = filter_targets(
        targets,
        countries=countries,
        status=status,
        only_with_parser=args.only_with_parser,
    )

    # DB 기반 스킵/저행수 필터
    try:
        targets = apply_db_filters(
            targets,
            skip_existing=args.skip_existing,
            skip_if_rows_gte=args.skip_if_rows_gte,
            max_db_rows=args.max_db_rows,
            min_db_rows=args.min_db_rows,
        )
    except Exception:
        logger.exception("DB 필터 적용 실패 — 필터 없이 진행하려면 옵션을 빼세요")
        return 1

    if not targets:
        logger.error("필터 후 대상 국가가 없습니다.")
        return 1

    upsert_batch = args.upsert_batch_size
    if args.batch_size is not None:
        upsert_batch = args.batch_size
        logger.warning("--batch-size 는 deprecated → --upsert-batch-size 로 사용됨")
    if args.upsert_each:
        upsert_batch = 1
        logger.warning("--upsert-each 는 deprecated → --upsert-batch-size 1")

    logger.info(
        "총 %d개 국가 수집 시작 (dry_run=%s, workers=%d, timeout=%s, upsert_batch=%d)",
        len(targets),
        args.dry_run,
        args.workers,
        args.timeout_sec or "none",
        upsert_batch,
    )

    try:
        result = run_pipeline(
            targets,
            dry_run=args.dry_run,
            workers=args.workers,
            timeout_sec=args.timeout_sec,
            upsert_batch_size=upsert_batch,
            report_path=Path(args.report) if args.report.strip() else None,
        )
    except Exception:
        logger.exception("파이프라인 실패")
        return 1

    logger.info("파이프라인 종료. 수집 %d행", len(result))
    return 0


if __name__ == "__main__":
    # macOS spawn 안전
    mp.freeze_support()
    sys.exit(main())
