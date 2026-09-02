"""Djibouti: Banque Centrale de Djibouti(BCD) 'Dépôts des banques' 페이지
(banque-centrale.dj/depots-des-banques/)에 게시된 PDF들. 각 PDF의 '3 - VENTILATION PAR
DEVISES DES DEPOTS'(통화별 예금 구성) 표에서 'Dollars des Etats-Unis (USD)' +
'Autres devises'(기타 외화) 행의 합 = FCD ('Francs Djibouti (FDJ)'는 자국통화라 제외).

TD(총예금) = 같은 표의 'Total' 행(FDJ + USD + Autres devises 합계). 라벨 경계 계산에
이미 TOTAL top이 포함되어 있어(OTHER 행 값 경계가 TOTAL의 앞쪽 값까지 잘못 삼키지 않도록),
그대로 _values_for("TOTAL")로 값을 뽑아 쓴다.

이 표는 숫자를 천단위 공백으로 묶어 쓰는데(예: '212 382' = 212,382), 같은 줄에 있는
연속된 값들이 전부 공백으로 구분돼 있어 텍스트만으로는 어디까지가 한 숫자이고 어디부터
다음 숫자인지 구분이 안 된다(예: '212 382 213 384 213 584 ...'는 순서대로 212382,
213384, 213584, ... 인데 전부 공백 구분이라 텍스트 파싱만으론 모호함). 게다가 파일마다
표 레이아웃이 미묘하게 다르다: 어떤 파일은 헤더가 두 줄로 쪼개져(최근 분기가 앞줄, 과거
분기가 뒷줄) 데이터도 같은 방식으로 라벨 앞/뒤에 걸쳐 쪼개지고, 어떤 파일은 라벨과 값이
같은 줄에 붙어 있다.

그래서 텍스트 줄 단위가 아니라 pdfplumber의 단어 좌표(extract_words, x0)를 이용해 표를
복원한다: 헤더 행의 기간 토큰(예: 'mars-21', 'Sept. 2017', 'déc-20' 등 표기가 파일마다
다름)들의 x0 좌표를 열(컬럼) 기준점으로 삼고, 각 데이터 숫자 단어를 x0가 가장 가까운
컬럼에 배정한 뒤(같은 컬럼에 배정된 여러 단어는 x0 오름차순으로 이어붙여 '212'+'382' ->
212382 처럼 합친다) 컬럼별로 값을 복원한다. 이 방식은 공백 구분 숫자의 모호성과 줄바꿈
위치가 파일마다 다른 문제를 동시에 해결한다.

분기별 시리즈는 2017-03부터 시작한다. 그 이전(2009~2016)은 연차보고서
(banque-centrale.dj/rapports-annuel-de-la-banque/)의 'Evolution/Composantes de la
masse monétaire' 표(연도별 5개년 롤링 윈도우, 보고서마다 표 레이아웃이 두 가지 변형으로
존재)에서 'Dépôts en devises'(=FCD) 및 'Dépôts à vue' + 'Dépôts sur livrets'(또는 구형
표기 'Autres dépôts à vue FDJ') + 'Dépôts à terme' + 'Dépôts en devises'(=TD) 행을 뽑아
2017년 이전 구간만 보강한다(2017년 이후는 분기 데이터가 이미 더 세밀하므로 중복 삽입하지
않음). 표가 두 가지 레이아웃으로 나뉘는데(연도 헤더 'Composantes'행과 정확히 같은 top인
경우와 'Autres' 라벨로 '기타예금'을 표기하는 구형 Annexe 표), 헤더는 'Composantes' 텍스트가
아니라 같은 top에 연속된 4자리 연도 토큰이 3개 이상 있는 행(페이지에서 제일 위쪽 그룹)으로
찾고, 두 번째 예금 행은 'livrets' 라벨이 없으면 'Autres' 라벨로 대체 탐색해 두 레이아웃을
모두 지원한다.
"""

import re
from datetime import datetime, timezone

import pandas as pd
import requests

from src.collectors.base import INDICATOR, INDICATOR_TD
from src.utils.logger import get_logger

logger = get_logger(__name__)

FILE_URL = "__RENDER__"

LIST_URL = "https://banque-centrale.dj/depots-des-banques/"
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"}

_SECTION_TITLE_RE = re.compile(r"ventilation\s+par\s+devises", re.I)
# pdfplumber의 extract_words()는 라벨을 'Dollars'/'des'/'Etats-Unis'/'(USD)'처럼 단어 단위로
# 쪼개므로, 한 단어 안에서 전체 구문을 찾는 대신 구분되는 첫 단어만으로 앵커를 잡는다.
_USD_LABEL_RE = re.compile(r"^dollars$", re.I)
_OTHER_LABEL_RE = re.compile(r"^autres$", re.I)
_FDJ_LABEL_RE = re.compile(r"^francs$", re.I)
_TOTAL_RE = re.compile(r"^total$", re.I)

_PERIOD_RE = re.compile(
    r"^(?P<mon>[A-Za-zéû]+)\.?[-\s]?(?P<year>\d{2,4})$"
)
_MONTHS = {
    "jan": 1, "janv": 1, "fev": 2, "fevr": 2, "févr": 2, "feb": 2,
    "mar": 3, "mars": 3, "avr": 4, "avril": 4,
    "mai": 5, "juin": 6, "jun": 6, "juil": 7, "jul": 7,
    "aou": 8, "aoû": 8, "aout": 8, "août": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12, "déc": 12,
}


def parse(content: bytes, country_code: str) -> pd.DataFrame:
    raise NotImplementedError("DJI는 render()를 통해 처리한다 (게시글 목록을 순회해야 함)")


def _collect_pdf_links() -> list[str]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(LIST_URL, timeout=60000)
        page.wait_for_timeout(2000)
        hrefs = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
        browser.close()

    return sorted({h for h in hrefs if "depot" in h.lower() and h.lower().endswith(".pdf")})


def _period_to_yyyymm(token: str) -> str | None:
    m = _PERIOD_RE.match(token.strip().rstrip("."))
    if not m:
        return None
    month = _MONTHS.get(m.group("mon").strip().lower()[:4]) or _MONTHS.get(m.group("mon").strip().lower()[:3])
    if month is None:
        return None
    year = int(m.group("year"))
    if year < 100:
        year += 2000
    return f"{year}-{month:02d}"


_MONTH_ONLY_RE = re.compile(r"^[A-Za-zéû]+\.?$")
_YEAR_ONLY_RE = re.compile(r"^(19|20)\d{2}$")


def _extract_period_columns(header_words: list[dict]) -> list[tuple[float, str]]:
    """헤더 기간 토큰을 (x0, 'YYYY-MM') 목록으로 뽑는다. 'mars-21'처럼 한 단어에 붙어 있는
    경우와 'Mars.' + '2019'처럼 월/연도가 별개 단어(공백)로 떨어져 있는 경우를 모두 처리한다."""
    ordered = sorted(header_words, key=lambda w: w["x0"])
    columns: list[tuple[float, str]] = []
    used_idx: set[int] = set()

    for i, w in enumerate(ordered):
        if i in used_idx:
            continue
        period = _period_to_yyyymm(w["text"])
        if period:
            columns.append((w["x0"], period))
            continue
        if _MONTH_ONLY_RE.match(w["text"]) and i + 1 < len(ordered):
            nxt = ordered[i + 1]
            if _YEAR_ONLY_RE.match(nxt["text"]):
                period = _period_to_yyyymm(f"{w['text']}{nxt['text']}")
                if period:
                    columns.append((w["x0"], period))
                    used_idx.add(i + 1)
    return columns


def _nearest_column(x0: float, columns: list[tuple[float, str]]) -> int:
    best_idx, best_dist = 0, float("inf")
    for i, (col_x0, _) in enumerate(columns):
        dist = abs(col_x0 - x0)
        if dist < best_dist:
            best_idx, best_dist = i, dist
    return best_idx


def _parse_pdf(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()
    rows_out = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            if not _SECTION_TITLE_RE.search(text):
                continue

            all_words = page.extract_words()
            # 0. 같은 페이지에 표 1/2/3(예금 종류별/예금주체별/통화별)이 함께 있고 1·2번 표도
            #    동일한 기간 헤더(예: 'Juin-25')를 반복 사용해 혼동될 수 있어, '3 - VENTILATION
            #    PAR DEVISES' 제목이 나오는 지점 아래쪽 단어만 이 표의 것으로 취급한다.
            devises_title_words = [w for w in all_words if w["text"].upper().startswith("DEVISES")]
            if not devises_title_words:
                continue
            section_top = min(w["top"] for w in devises_title_words)
            words = [w for w in all_words if w["top"] >= section_top]

            # 1. 헤더 기간 토큰(중복 없이, top이 낮은(=위쪽) 것부터, 같은 top이면 x0 순)으로 컬럼 정의.
            #    'Selon les devises' 텍스트가 나오는 top 이후 ~ 첫 통화 라벨 전까지가 헤더 영역이다.
            # 'Total' 행도 다른 통화 행과 똑같이 앞/뒤로 값이 쪼개질 수 있어(예: 최근 분기
            # 합계가 'Total' 라벨보다 먼저 나옴), OTHER 행의 값 수집 범위가 Total의 앞쪽
            # 값까지 잘못 삼키지 않도록 TOTAL도 라벨 중 하나로 취급해 경계 계산에 포함한다.
            label_tops_by_kind = {
                "FDJ": [w["top"] for w in words if _FDJ_LABEL_RE.search(w["text"])],
                "USD": [w["top"] for w in words if _USD_LABEL_RE.search(w["text"])],
                "OTHER": [w["top"] for w in words if _OTHER_LABEL_RE.search(w["text"])],
                "TOTAL": [w["top"] for w in words if _TOTAL_RE.match(w["text"])],
            }
            if not label_tops_by_kind["USD"] or not label_tops_by_kind["OTHER"]:
                logger.warning("[%s] USD/Autres devises 라벨을 찾지 못함", country_code)
                continue
            first_label_top = min(min(v) for v in label_tops_by_kind.values() if v)

            header_candidates = [w for w in words if w["top"] < first_label_top]
            columns = _extract_period_columns(header_candidates)
            if not columns:
                continue
            columns.sort(key=lambda c: c[0])  # x0 오름차순 = 시간순(왼쪽=과거, 오른쪽=최근)
            n_periods = len(columns)

            # 2. 라벨들을 top 순으로 나열하고, 인접 라벨 top의 중간지점을 경계로 삼아 값
            #    영역을 나눈다. 파일에 따라 한 행의 값이 라벨 줄 앞(구형: 최근 분기가 먼저
            #    나옴)과 뒤(과거 분기)에 걸쳐 나뉘어 있는 경우가 있는데, 중간지점 경계 방식은
            #    앞뒤 어느 쪽에 값이 있든 '가장 가까운 라벨'에 자동으로 배정되어 두 레이아웃을
            #    모두 처리한다.
            all_label_tops = sorted(
                (top, kind) for kind, tops in label_tops_by_kind.items() for top in tops
            )
            section_end = max(w["top"] for w in words) + 1

            boundaries = [min(w["top"] for w in header_candidates)]
            for i in range(len(all_label_tops) - 1):
                boundaries.append((all_label_tops[i][0] + all_label_tops[i + 1][0]) / 2)
            boundaries.append(section_end)

            def _values_for(kind: str) -> list[float] | None:
                idx = next((i for i, (_, k) in enumerate(all_label_tops) if k == kind), None)
                if idx is None:
                    return None
                lo, hi = boundaries[idx], boundaries[idx + 1]
                value_words = [
                    w for w in words
                    if lo <= w["top"] < hi and re.fullmatch(r"-?[\d]+", w["text"])
                ]
                if not value_words:
                    return None

                buckets: dict[int, list[tuple[float, str]]] = {}
                for w in value_words:
                    col_idx = _nearest_column(w["x0"], columns)
                    buckets.setdefault(col_idx, []).append((w["x0"], w["text"]))

                values = [None] * n_periods
                for col_idx, items in buckets.items():
                    items.sort(key=lambda t: t[0])
                    combined = "".join(t[1] for t in items)
                    try:
                        values[col_idx] = float(combined)
                    except ValueError:
                        pass
                return values

            usd_vals = _values_for("USD")
            other_vals = _values_for("OTHER")
            total_vals = _values_for("TOTAL")
            if usd_vals is None or other_vals is None:
                logger.warning("[%s] USD/Autres devises 값을 찾지 못함", country_code)
                continue

            for i, period in enumerate(p for _, p in columns):
                usd = usd_vals[i] if i < len(usd_vals) else None
                other = other_vals[i] if i < len(other_vals) else None
                if usd is None or other is None:
                    continue
                rows_out.append({
                    "country_code": country_code,
                    "year": int(period[:4]),
                    "period": period,
                    "indicator": INDICATOR,
                    "value": round(usd + other, 2),
                    "updated_at": now,
                })

                total = total_vals[i] if total_vals is not None and i < len(total_vals) else None
                if total is not None:
                    rows_out.append({
                        "country_code": country_code,
                        "year": int(period[:4]),
                        "period": period,
                        "indicator": INDICATOR_TD,
                        "value": round(total, 2),
                        "updated_at": now,
                    })

    return pd.DataFrame(rows_out)


# --- 연차보고서(2009~2016 보강용) ---------------------------------------------

ANNUAL_REPORTS_URL = "https://banque-centrale.dj/rapports-annuel-de-la-banque/"
# 분기 시리즈가 시작하는 첫 해. 이 해 이후는 분기 데이터가 이미 더 세밀하므로
# 연차보고서 값을 중복 삽입하지 않는다.
_QUARTERLY_SERIES_START_YEAR = 2017

_YEAR_TOKEN_RE = re.compile(r"^(19|20)\d{2}$")
_VUE_LABEL_RE = re.compile(r"^vue$")
_LIVRETS_LABEL_RE = re.compile(r"^livrets$")
_AUTRES_LABEL_RE = re.compile(r"^Autres$")
_TERME_LABEL_RE = re.compile(r"^terme$")
_DEVISES_LABEL_RE = re.compile(r"^devises$")
_NUM_TOKEN_RE = re.compile(r"\d{1,3}(\.\d{3})*|\d+")


def _collect_annual_report_links() -> list[str]:
    response = requests.get(ANNUAL_REPORTS_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()
    candidates = set(re.findall(
        r"https://banque-centrale\.dj/wp-content/uploads/[^\"'\s]+\.pdf", response.text,
    ))
    return sorted(
        url for url in candidates
        if "rapport" in url.lower() and "annuel" in url.lower()
    )


def _extract_masse_monetaire_table(page) -> dict | None:
    """'Evolution/Composantes de la masse monétaire' 5개년 표를 한 페이지에서 찾아
    {연도(str): {'vue','second'(livrets/autres),'terme','devises'} 정수값} 형태로 반환한다.
    표를 못 찾거나 값이 불완전하면 None."""
    words = page.extract_words()

    year_tokens = [w for w in words if _YEAR_TOKEN_RE.match(w["text"])]
    if not year_tokens:
        return None
    year_tokens.sort(key=lambda w: w["top"])
    groups: list[list[dict]] = []
    for w in year_tokens:
        for g in groups:
            if abs(g[0]["top"] - w["top"]) < 3:
                g.append(w)
                break
        else:
            groups.append([w])
    groups = [g for g in groups if len(g) >= 3]
    if not groups:
        return None
    header_group = min(groups, key=lambda g: g[0]["top"])
    header_top = header_group[0]["top"]
    columns = sorted((w["x0"], w["text"]) for w in header_group)
    n = len(columns)

    def first_after(pattern: re.Pattern, after_top: float, before_top: float | None = None) -> float | None:
        cands = [
            w for w in words
            if pattern.match(w["text"]) and w["top"] > after_top and (before_top is None or w["top"] < before_top)
        ]
        return min(cands, key=lambda w: w["top"])["top"] if cands else None

    vue_top = first_after(_VUE_LABEL_RE, header_top)
    devises_top = first_after(_DEVISES_LABEL_RE, header_top)
    terme_top = first_after(_TERME_LABEL_RE, header_top, devises_top)
    if vue_top is None or terme_top is None or devises_top is None:
        return None
    second_top = first_after(_LIVRETS_LABEL_RE, vue_top, terme_top)
    if second_top is None:
        second_top = first_after(_AUTRES_LABEL_RE, vue_top, terme_top)
    if second_top is None:
        return None

    def nearest_col(x0: float) -> int:
        return min(range(n), key=lambda i: abs(columns[i][0] - x0))

    def values_for(label_top: float) -> list[int | None]:
        toks = [
            w for w in words
            if abs(w["top"] - label_top) <= 6 and _NUM_TOKEN_RE.fullmatch(w["text"])
        ]
        buckets: dict[int, list[dict]] = {}
        for w in toks:
            buckets.setdefault(nearest_col(w["x0"]), []).append(w)
        vals: list[int | None] = [None] * n
        for c, items in buckets.items():
            items.sort(key=lambda w: w["x0"])
            try:
                vals[c] = int("".join(w["text"].replace(".", "") for w in items))
            except ValueError:
                pass
        return vals

    vue_vals = values_for(vue_top)
    second_vals = values_for(second_top)
    terme_vals = values_for(terme_top)
    devises_vals = values_for(devises_top)
    if any(v is None for v in vue_vals + second_vals + terme_vals + devises_vals):
        return None

    return {
        year: {"vue": vue_vals[i], "second": second_vals[i], "terme": terme_vals[i], "devises": devises_vals[i]}
        for i, (_, year) in enumerate(columns)
    }


def _parse_annual_report(content: bytes, country_code: str) -> pd.DataFrame:
    import pdfplumber
    from io import BytesIO

    now = datetime.now(timezone.utc).isoformat()
    rows_out = []

    with pdfplumber.open(BytesIO(content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            tl = text.lower()
            if "devises" not in tl or "terme" not in tl or "vue" not in tl:
                continue
            table = _extract_masse_monetaire_table(page)
            if not table:
                continue
            for year_str, vals in table.items():
                year = int(year_str)
                if year >= _QUARTERLY_SERIES_START_YEAR:
                    continue
                period = f"{year}-Annual"
                fcd = vals["devises"]
                td = vals["vue"] + vals["second"] + vals["terme"] + vals["devises"]
                rows_out.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": INDICATOR, "value": float(fcd), "updated_at": now,
                })
                rows_out.append({
                    "country_code": country_code, "year": year, "period": period,
                    "indicator": INDICATOR_TD, "value": float(td), "updated_at": now,
                })
            break  # 페이지당 표는 하나만 취급(같은 페이지의 구조표/% 표는 건너뜀)

    return pd.DataFrame(rows_out)


def render(target: dict) -> pd.DataFrame:
    country_code = target["country_code"]

    links = _collect_pdf_links()
    logger.info("[%s] Depots des banques PDF %d개 발견", country_code, len(links))

    frames = []
    for url in links:
        try:
            response = requests.get(url, headers=_HEADERS, timeout=60)
            response.raise_for_status()
        except Exception:
            logger.warning("[%s] 다운로드 실패, 스킵: %s", country_code, url)
            continue

        df = _parse_pdf(response.content, country_code)
        if not df.empty:
            frames.append(df)
        logger.info("[%s] %s -> %d개 기간", country_code, url.rsplit("/", 1)[-1], len(df))

    try:
        annual_links = _collect_annual_report_links()
        logger.info("[%s] 연차보고서 %d개 발견 (2017년 이전 보강용)", country_code, len(annual_links))
        for url in annual_links:
            try:
                response = requests.get(url, headers=_HEADERS, timeout=60)
                response.raise_for_status()
            except Exception:
                logger.warning("[%s] 연차보고서 다운로드 실패, 스킵: %s", country_code, url)
                continue
            df = _parse_annual_report(response.content, country_code)
            if not df.empty:
                frames.append(df)
            logger.info("[%s] %s -> %d행 (연차)", country_code, url.rsplit("/", 1)[-1], len(df))
    except Exception:
        logger.warning("[%s] 연차보고서 수집 단계 실패, 분기 데이터만 사용", country_code, exc_info=True)

    if not frames:
        return pd.DataFrame(columns=["country_code", "year", "period", "indicator", "value", "updated_at"])

    merged = pd.concat(frames, ignore_index=True)
    merged = merged.drop_duplicates(subset=["period", "indicator"], keep="last")
    return merged.sort_values("period").reset_index(drop=True)
