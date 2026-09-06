from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

OUT = Path(__file__).resolve().parents[1] / "data" / "policy-news.json"
HEADERS = {"User-Agent": "NAEIL-LAB-policy-linker/1.0 (+https://naeillab.ai.kr)"}
KST = timezone(timedelta(hours=9))


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_date(text: str) -> str:
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text or "")
    if not m:
        return ""
    y, mo, d = map(int, m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


def fetch_mpm(limit: int = 8) -> list[dict]:
    feed_url = "https://www.mpm.go.kr/board/rss.do?boardId=bbs_0000000000000127&mode=fed&proc=rss"
    feed = feedparser.parse(feed_url, request_headers=HEADERS)
    items = []
    for entry in feed.entries[:limit]:
        title = clean(entry.get("title", ""))
        link = entry.get("link", "https://www.mpm.go.kr/mpm/comm/policyPR/mpmFocus/")
        date = ""
        if entry.get("published_parsed"):
            t = entry.published_parsed
            date = f"{t.tm_year:04d}-{t.tm_mon:02d}-{t.tm_mday:02d}"
        items.append({
            "agency": "인사혁신처",
            "title": title,
            "date": date,
            "url": link,
            "topic": "인사·채용정책",
        })
    return items


def fetch_moe(limit: int = 8) -> list[dict]:
    # 교육부 홍보이미지 게시판. 게시판 구조 변경 시 파서 보완 필요.
    list_url = "https://www.moe.go.kr/boardCnts/listRenew.do?boardID=340&m=020201&s=moe"
    r = requests.get(list_url, headers=HEADERS, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items = []
    seen = set()
    for a in soup.find_all("a", href=True):
        title = clean(a.get_text(" ", strip=True))
        href = a.get("href", "")
        if "viewRenew.do" not in href or "카드뉴스" not in title:
            continue
        link = urljoin(list_url, href)
        if link in seen:
            continue
        seen.add(link)
        row = a.find_parent("tr") or a.parent
        row_text = clean(row.get_text(" ", strip=True) if row else "")
        items.append({
            "agency": "교육부",
            "title": title,
            "date": parse_date(row_text),
            "url": link,
            "topic": "교육정책",
        })
        if len(items) >= limit:
            break
    return items


def main() -> None:
    collected = []
    errors = []
    for name, fn in (("인사혁신처", fetch_mpm), ("교육부", fetch_moe)):
        try:
            collected.extend(fn())
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    # 기존 데이터는 한 기관의 일시적 수집 실패 때 보존한다.
    existing = {"items": []}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass

    agencies = {x["agency"] for x in collected}
    if agencies != {"인사혁신처", "교육부"}:
        for item in existing.get("items", []):
            if item.get("agency") not in agencies:
                collected.append(item)

    dedup = {}
    for item in collected:
        key = (item.get("agency"), item.get("url"), item.get("title"))
        dedup[key] = item
    items = list(dedup.values())
    items.sort(key=lambda x: x.get("date", ""), reverse=True)
    items = items[:12]

    payload = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "items": items,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
