"""Entry point for the foreign-currency deposit data collection pipeline.

Countries are collected independently, so we run a **continuous worker pool**
(the moment one finishes, the next country starts) while a separate UPSERT
thread batches writes once N countries have accumulated.

Usage examples:
  python main.py --status success --only-with-parser --workers 8 --timeout-sec 120
  python main.py --workers 8 --timeout-sec 120 --upsert-batch-size 5
  python main.py --skip-existing
  python main.py --max-db-rows 30          # only countries with <=30 DB rows (or none)
  python main.py --list-db-stats
  python main.py --db-summary              # summary of loaded data period/indicators
  python main.py --upload-targets          # targets.json -> country_metadata UPSERT
  python main.py --migrate-indicators      # foreign_currency_deposits -> FCD
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

# Load .env (SUPABASE_DB_URL, etc.)
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
    """Filter targets based on the row count already present in Supabase.

    - skip_existing: skip if the country already has at least 1 row in the DB
    - skip_if_rows_gte N: skip if DB row count >= N (avoids partial re-collection)
    - max_db_rows N: only countries with DB row count <= N or **no rows at all**
      (useful for auditing thin/uncollected parsers)
    - min_db_rows N: only countries with DB row count >= N
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
    logger.info("Loaded DB row counts per country: %d countries", len(counts))

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
            "Skipped %d countries via DB filter (e.g. %s%s)",
            len(skipped),
            sample,
            more,
        )
    logger.info("Countries to collect after DB filter: %d", len(kept))
    return kept


def _collect_one(target: dict) -> tuple[str, pd.DataFrame | None, str | None]:
    """Collect a single country. Returns: (country_code, df|None, error|None)."""
    code = target.get("country_code", "?")
    strategy = get_strategy(target.get("data_type"))
    try:
        df = strategy.collect_and_parse(target)
    except Exception as e:
        logger.exception("[%s] Collection failed", code)
        return code, None, f"ERROR: {e}"
    if df is None or df.empty:
        logger.info("[%s] No results collected", code)
        return code, None, None
    logger.info("[%s] Collected %d rows", code, len(df))
    return code, df, None


def _collect_one_worker(target: dict, conn) -> None:
    """Collect in a separate process and send the result over a Pipe (for hard timeouts)."""
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
    """Run a single country in a child process and terminate/kill it if it exceeds the timeout."""
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
            "[%s] TIMEOUT after %.0fs (elapsed %.0fs) — forcibly terminating process and skipping",
            code,
            timeout_sec,
            elapsed,
        )
        proc.terminate()
        proc.join(timeout=10)
        if proc.is_alive():
            logger.error("[%s] terminate failed -> kill()", code)
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
# Upsert worker (runs in its own thread)
# ---------------------------------------------------------------------------


def _upsert_worker_loop(
    q: Queue,
    flush_every: int,
    dry_run: bool,
    stop_event: Event,
    stats: dict,
) -> None:
    """Buffer completed DataFrames and UPSERT them every N countries."""
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
                "UPSERT worker dry-run flush (%s): %d countries / %d rows — skipping DB",
                reason,
                n_countries,
                len(df),
            )
        else:
            n = upsert_long_format(df)
            stats["upserted"] = stats.get("upserted", 0) + n
            logger.info(
                "UPSERT worker flush (%s): %d countries / %d rows written (cumulative %d)",
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
# Continuous worker pool (no batch barrier)
# ---------------------------------------------------------------------------


def run_pipeline(
    targets: list[dict],
    dry_run: bool = False,
    workers: int = 1,
    timeout_sec: float = 0,
    upsert_batch_size: int = 5,
    report_path: Path | None = None,
) -> pd.DataFrame:
    """Continuous worker pool for collection plus a separate UPSERT worker.

    - workers: number of collection slots to run concurrently. As soon as one
      finishes, the next country starts immediately.
    - timeout_sec: hard timeout per country (process kill). 0 = unlimited
      (runs directly in a thread).
    - upsert_batch_size: once N countries have been collected successfully,
      the UPSERT worker writes them in a batch.
    - report_path: path for the per-country result JSON report (auto-generated
      under runs/ if None)

    Result classification (important):
      success  — DataFrame has rows (still counted as success even if there
                 were intermediate WARNINGs or partial skips)
      empty    — empty result with no exception (includes cases where the
                 parser swallowed a failure internally)
      fail     — an exception string propagated up to the pipeline (ERROR: ...)
      timeout  — process killed due to hard timeout
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
        "Run mode: continuous workers=%d, timeout_sec=%s (hard=%s), upsert_batch_size=%d",
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
        # fill initial slots
        while idx < len(pending_targets) and len(in_flight) < workers:
            t = pending_targets[idx]
            idx += 1
            fut = ex.submit(_job, t)
            in_flight[fut] = t
            logger.debug(
                "Submitted [%s] (in_flight=%d, queue_left=%d)",
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
                    logger.exception("[%s] Future raised an exception", code)
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

                # submit the next country as soon as a slot frees up
                if idx < len(pending_targets):
                    t = pending_targets[idx]
                    idx += 1
                    nf = ex.submit(_job, t)
                    in_flight[nf] = t
                    logger.debug(
                        "Submitted [%s] (in_flight=%d, queue_left=%d)",
                        t.get("country_code"),
                        len(in_flight),
                        len(pending_targets) - idx,
                    )

    # collection finished -> wrap up the upsert worker
    upsert_q.put(_UPSERT_SENTINEL)
    upsert_q.join()
    stop_event.set()
    upsert_thread.join(timeout=120)

    result = pd.concat(all_frames, ignore_index=True) if all_frames else pd.DataFrame()
    elapsed = time.monotonic() - t_run0

    logger.info(
        "Collection summary: success %d / empty %d / fail %d / timeout %d / rows collected %d / UPSERT %d (%.0fs)",
        ok,
        empty,
        fail,
        timeout_n,
        len(result),
        stats.get("upserted", 0),
        elapsed,
    )
    if success_info:
        # targets.json frequency: annual/semi_annual are excluded from thin-row warnings
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
            "Successful countries (%d): %s",
            len(success_info),
            ", ".join(f"{s['country_code']}({s['rows']})" for s in sorted(success_info, key=lambda x: x["country_code"])),
        )
        if thin:
            logger.warning(
                "Succeeded but thin row count (<=30, annual excluded) (%d) — parser check candidates: %s",
                len(thin),
                ", ".join(f"{s['country_code']}({s['rows']})" for s in thin),
            )
        if thin_expected:
            logger.info(
                "Thin row count but exempted as annual/semi_annual (%d): %s",
                len(thin_expected),
                ", ".join(f"{s['country_code']}({s['rows']})" for s in thin_expected),
            )
    if empty_codes:
        logger.warning(
            "Countries with empty results (%d) — parser returned an empty DF without raising (includes internal soft-fails): %s",
            len(empty_codes),
            ", ".join(sorted(empty_codes)),
        )
    if timeout_codes:
        logger.warning(
            "Countries that timed out (%d): %s",
            len(timeout_codes),
            ", ".join(timeout_codes),
        )
    if fail_codes:
        logger.warning(
            "Failed countries (%d) — exception propagated up to the pipeline: %s",
            len(fail_codes),
            ", ".join(fail_codes),
        )
    if dry_run:
        logger.info("dry-run mode: DB writes are also skipped in the UPSERT worker")

    # save JSON report
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
            "success": "DataFrame has rows. Counted as success even with internal parser WARNINGs/partial skips.",
            "empty": "Empty result without an exception. Includes cases where the parser swallowed a failure and returned empty.",
            "fail": "Only when an ERROR string was returned from the collect path.",
            "timeout": "Process killed due to a hard timeout.",
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
        logger.info("Run report saved: %s", out)
    except Exception:
        logger.exception("Failed to save run report")

    return result


def cmd_init_db() -> None:
    engine = get_engine()
    try:
        ensure_table(engine)
        n = count_rows(engine)
        m = count_metadata_rows(engine)
        logger.info(
            "DB ready. deposit_dollarization=%d rows, country_metadata=%d rows",
            n,
            m,
        )
        sample = fetch_sample(5, engine)
        if len(sample):
            logger.info("Sample:\n%s", sample.to_string(index=False))
    finally:
        engine.dispose()


def cmd_list_db_stats(max_db_rows: int | None = None) -> None:
    """Print DB row count per country. If max_db_rows is given, only show countries at or below it."""
    counts = count_rows_by_country()
    if not counts:
        logger.info("No data in DB (or connection failed)")
        return
    items = sorted(counts.items(), key=lambda x: (x[1], x[0]))
    if max_db_rows is not None:
        items = [(c, n) for c, n in items if n <= max_db_rows]
        logger.info("Countries with DB row count <= %d (%d):", max_db_rows, len(items))
    else:
        logger.info("DB row count per country (%d countries, ascending):", len(items))
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
        logger.info("Has parser but 0 rows in DB (%d): %s", len(missing), ", ".join(missing))


def cmd_db_summary(
    *,
    thin_threshold: int = 30,
    report_path: Path | None = None,
    show_all: bool = True,
    exclude_annual_from_thin: bool = True,
) -> None:
    """Summarize the current state of the deposit_dollarization table (+ optional JSON)."""
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
            "Has parser but 0 deposit rows (%d): %s",
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
        logger.info("DB summary JSON saved: %s", report_path)


def cmd_upload_targets(
    targets_path: Path | None = None,
    *,
    countries: list[str] | None = None,
    status: str | None = None,
) -> int:
    """UPSERT config/targets.json -> country_metadata."""
    path = targets_path or TARGETS_PATH
    targets = load_targets(path)
    targets = filter_targets(
        targets,
        countries=countries,
        status=status,
        only_with_parser=False,
    )
    if not targets:
        logger.error("No targets to upload.")
        return 0
    n = upsert_country_metadata(
        targets,
        parsers_dir=ROOT / "src" / "parsers",
    )
    logger.info("Targets upload complete: %d countries -> country_metadata", n)
    return n


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Dollarization ratio ETL → Supabase")
    p.add_argument("--dry-run", action="store_true", help="Collect only, skip DB write")
    p.add_argument("--countries", type=str, default="", help="Comma-separated ISO3 list")
    p.add_argument("--status", type=str, default="", help="Filter by adapter.status")
    p.add_argument(
        "--only-with-parser",
        action="store_true",
        help="Only countries with src/parsers/{cc}.py",
    )
    p.add_argument(
        "--init-db",
        action="store_true",
        help="Only create/verify tables (deposit_dollarization + country_metadata)",
    )
    p.add_argument(
        "--migrate-indicators",
        action="store_true",
        help="Bulk-migrate legacy indicator foreign_currency_deposits -> FCD",
    )
    p.add_argument(
        "--list-db-stats",
        action="store_true",
        help="Print row count per country in Supabase, then exit",
    )
    p.add_argument(
        "--db-summary",
        action="store_true",
        help="Print DB summary (period/indicators/thin rows), then exit",
    )
    p.add_argument(
        "--upload-targets",
        action="store_true",
        help="UPSERT config/targets.json into the country_metadata table, then exit",
    )
    p.add_argument(
        "--thin-threshold",
        type=int,
        default=30,
        metavar="N",
        help="Thin-row threshold for --db-summary (default 30)",
    )
    p.add_argument(
        "--include-annual-thin",
        action="store_true",
        help="Include annual/semi_annual countries in the thin-row list (default: exempted)",
    )
    p.add_argument(
        "--summary-json",
        type=str,
        default="",
        help="Path to save the --db-summary result as JSON",
    )
    p.add_argument("--targets", type=str, default=str(TARGETS_PATH))
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of concurrent collection workers (default 4). Next country starts as soon as one finishes",
    )
    p.add_argument(
        "--timeout-sec",
        type=float,
        default=0,
        help="Max seconds per country (0=unlimited). Process is force-killed on exceeding it",
    )
    p.add_argument(
        "--upsert-batch-size",
        type=int,
        default=5,
        help="UPSERT worker writes in a batch once N countries have been collected successfully (default 5)",
    )
    # backward-compat aliases
    p.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help=argparse.SUPPRESS,  # deprecated -> upsert-batch-size
    )
    p.add_argument("--upsert-each", action="store_true", help=argparse.SUPPRESS)

    # DB filters
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip countries that already have at least 1 row in the DB",
    )
    p.add_argument(
        "--skip-if-rows-gte",
        type=int,
        default=None,
        metavar="N",
        help="Skip countries with DB row count >= N",
    )
    p.add_argument(
        "--max-db-rows",
        type=int,
        default=None,
        metavar="N",
        help="Only collect countries with DB row count <= N (or not yet collected) — for auditing thin-row parsers",
    )
    p.add_argument(
        "--min-db-rows",
        type=int,
        default=None,
        metavar="N",
        help="Only countries with DB row count >= N",
    )
    p.add_argument(
        "--report",
        type=str,
        default="",
        help="Path for the run report JSON (default: runs/run-YYYYMMDD-HHMMSS.json)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.init_db:
        try:
            cmd_init_db()
            return 0
        except Exception:
            logger.exception("init-db failed")
            return 1

    if args.migrate_indicators:
        try:
            stats = migrate_legacy_indicators()
            logger.info("migrate-indicators result: %s", stats)
            return 0 if stats.get("remaining_legacy", 0) == 0 else 2
        except Exception:
            logger.exception("migrate-indicators failed")
            return 1

    if args.list_db_stats:
        try:
            cmd_list_db_stats(max_db_rows=args.max_db_rows)
            return 0
        except Exception:
            logger.exception("list-db-stats failed")
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
            logger.exception("db-summary failed")
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
            logger.exception("upload-targets failed")
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

    # DB-based skip/thin-row filters
    try:
        targets = apply_db_filters(
            targets,
            skip_existing=args.skip_existing,
            skip_if_rows_gte=args.skip_if_rows_gte,
            max_db_rows=args.max_db_rows,
            min_db_rows=args.min_db_rows,
        )
    except Exception:
        logger.exception("Failed to apply DB filter — drop the option to proceed without filtering")
        return 1

    if not targets:
        logger.error("No target countries remain after filtering.")
        return 1

    upsert_batch = args.upsert_batch_size
    if args.batch_size is not None:
        upsert_batch = args.batch_size
        logger.warning("--batch-size is deprecated -> use --upsert-batch-size")
    if args.upsert_each:
        upsert_batch = 1
        logger.warning("--upsert-each is deprecated -> --upsert-batch-size 1")

    logger.info(
        "Starting collection for %d countries (dry_run=%s, workers=%d, timeout=%s, upsert_batch=%d)",
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
        logger.exception("Pipeline failed")
        return 1

    logger.info("Pipeline finished. Collected %d rows", len(result))
    return 0


if __name__ == "__main__":
    # safe for macOS spawn
    mp.freeze_support()
    sys.exit(main())
