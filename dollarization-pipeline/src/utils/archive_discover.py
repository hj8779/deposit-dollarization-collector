"""Helpers to expand short time series via multi-year PDF/Excel URL archives.

Used by country parsers that currently only scrape the "latest window" page.
"""

from __future__ import annotations

from typing import Iterable
from urllib.parse import urljoin

import re
import requests


def dedupe_urls(urls: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for u in urls:
        if not u or u in seen:
            continue
        seen.add(u)
        out.append(u)
    return out


def hrefs_matching(
    html: str,
    pattern: str,
    *,
    base: str | None = None,
    flags: int = re.I,
) -> list[str]:
    """Extract hrefs matching regex; optionally absolutize with base."""
    out: list[str] = []
    for m in re.finditer(r'href=["\']([^"\']+)["\']', html, flags):
        h = m.group(1).replace("&amp;", "&")
        if re.search(pattern, h, flags):
            out.append(urljoin(base, h) if base else h)
    return dedupe_urls(out)


def head_ok_pdf(url: str, headers: dict | None = None, timeout: int = 20) -> bool:
    try:
        r = requests.head(
            url,
            headers=headers or {},
            timeout=timeout,
            allow_redirects=True,
            verify=False,
        )
        if r.status_code != 200:
            return False
        ct = (r.headers.get("content-type") or "").lower()
        return "pdf" in ct or "octet" in ct
    except Exception:
        return False
