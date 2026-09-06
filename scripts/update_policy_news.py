from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

OUT = Path(__file__).resolve().parents[1] / "data" / "policy-news.json"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; NAEILLAB-PolicyLinker/2.0; +https://naeillab.ai.kr)"}
KST = timezone(timedelta(hours=9))
KEYWORDS = ("채용", "공채", "인사", "인재", "시험", "면접", "평가", "직무", "교육", "훈련", "진로", "취업", "역량", "학교", "AI", "인공지능")


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def parse_date(text: str) -> str:
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text or "")
    if not m:
        return ""
    y, mo, d = map(int, m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


def relevant(title: str) -> bool:
    return any(k.lower() in title.lower() for k in KEYWORDS)


def fetch_mpm(limit: int = 8) -> list[dict]:
    list_url = "https://www.mpm.go.kr/mpm/comm/policyPR/mpmFocus/"
    r = requests.get(list_url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        title = clean(a.get_text(" ", strip=True))
        if "mode=view" not in href or not title or not relevant(title):
            continue
        link = urljoin(list_url, href)
        if link in seen:
            continue
        seen.add(link)
        block = a.find_parent(["li", "tr", "div"]) or a.parent
        date = parse_date(clean(block.get_text(" ", strip=True) if block else ""))
        items.append({"agency":"인사혁신처","title":title,"date":date,"url":link,"topic":"인사·채용정책"})
        if len(items) >= limit:
            break
    return items


def fetch_moe(limit: int = 8) -> list[dict]:
    list_url = "https://www.moe.go.kr/boardCnts/listRenew.do?boardID=340&m=020201&s=moe"
    r = requests.get(list_url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    items, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        title = clean(a.get_text(" ", strip=True))
        if "viewRenew.do" not in href or not title.startswith("[카드뉴스]") or not relevant(title):
            continue
        link = urljoin(list_url, href)
        if link in seen:
            continue
        seen.add(link)
        row = a.find_parent("tr") or a.find_parent("li") or a.parent
        date = parse_date(clean(row.get_text(" ", strip=True) if row else ""))
        items.append({"agency":"교육부","title":title,"date":date,"url":link,"topic":"교육정책"})
        if len(items) >= limit:
            break
    return items


def main() -> None:
    collected, errors = [], []
    for name, fn in (("인사혁신처", fetch_mpm), ("교육부", fetch_moe)):
        try:
            collected.extend(fn())
        except Exception as exc:
            errors.append(f"{name}: {exc}")

    existing = {"items": []}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass

    agencies = {x.get("agency") for x in collected}
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

    payload = {"updated_at": datetime.now(KST).isoformat(timespec="seconds"), "items": items, "errors": errors}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
