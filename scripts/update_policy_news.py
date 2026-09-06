from __future__ import annotations

import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

OUT = Path(__file__).resolve().parents[1] / "data" / "policy-news.json"
KST = timezone(timedelta(hours=9))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; NAEILLAB-PolicyLinker/3.0; +https://naeillab2026-lang.github.io/my-first-website/)"
}

KEYWORDS = (
    "채용", "공채", "인사", "인재", "시험", "면접", "평가", "직무", "교육", "훈련", "진로",
    "취업", "역량", "청년", "창업", "중소기업", "벤처", "소상공인", "AI", "인공지능", "일자리",
    "공공기관", "노동", "고용", "지역인재", "직업", "학교", "대학", "지원", "정책", "경제"
)


def session() -> requests.Session:
    s = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=1.2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET"]),
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.headers.update(HEADERS)
    return s


HTTP = session()


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def clean_title(text: str) -> str:
    text = clean(text)
    for marker in (" 담당부서 ", " 작성일 ", " 등록일 ", " 조회 "):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    return text


def parse_date(text: str) -> str:
    m = re.search(r"(20\d{2})[.\-/](\d{1,2})[.\-/](\d{1,2})", text or "")
    if not m:
        return ""
    y, mo, d = map(int, m.groups())
    return f"{y:04d}-{mo:02d}-{d:02d}"


def relevant(title: str) -> bool:
    low = title.lower()
    return any(k.lower() in low for k in KEYWORDS)


def get(url: str) -> BeautifulSoup:
    r = HTTP.get(url, timeout=(12, 35))
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def add_item(items: list[dict], seen: set[str], *, agency: str, title: str, date: str, url: str, topic: str, content_type: str = "카드뉴스") -> None:
    title = clean_title(title)
    if not title or url in seen:
        return
    seen.add(url)
    items.append({
        "agency": agency,
        "title": title,
        "date": date,
        "url": url,
        "topic": topic,
        "type": content_type,
    })


def fetch_mofe(limit: int = 8) -> list[dict]:
    list_url = "https://www.mofe.go.kr/nw/mosfnw/mosfnw.do?menuNo=4040600"
    soup = get(list_url)
    items: list[dict] = []
    seen: set[str] = set()
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "detailCardNewsView.do" not in href:
            continue
        title = clean_title(a.get_text(" ", strip=True))
        if not title:
            img = a.find("img")
            title = clean_title(img.get("alt", "") if img else "")
        if not title:
            continue
        block = a.find_parent(["li", "tr", "article", "div"]) or a.parent
        date = parse_date(clean(block.get_text(" ", strip=True) if block else ""))
        link = urljoin(list_url, href)
        candidates.append((title, date, link))
    preferred = [x for x in candidates if relevant(x[0])] or candidates
    for title, date, link in preferred:
        add_item(items, seen, agency="재정경제부", title=title, date=date, url=link, topic="경제·정책")
        if len(items) >= limit:
            break
    return items


def fetch_mpm(limit: int = 8) -> list[dict]:
    list_url = "https://www.mpm.go.kr/mpm/comm/policyPR/mpmFocus/"
    soup = get(list_url)
    items: list[dict] = []
    seen: set[str] = set()
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if "mode=view" not in href:
            continue
        title = clean_title(a.get_text(" ", strip=True))
        if not title:
            continue
        block = a.find_parent(["li", "tr", "article", "div"]) or a.parent
        date = parse_date(clean(block.get_text(" ", strip=True) if block else ""))
        candidates.append((title, date, urljoin(list_url, href)))
    preferred = [x for x in candidates if relevant(x[0])] or candidates
    for title, date, link in preferred:
        add_item(items, seen, agency="인사혁신처", title=title, date=date, url=link, topic="인사·채용정책")
        if len(items) >= limit:
            break
    return items


def fetch_moe(limit: int = 8) -> list[dict]:
    list_url = "https://www.moe.go.kr/boardCnts/listRenew.do?boardID=340&m=020201&s=moe"
    soup = get(list_url)
    items: list[dict] = []
    seen: set[str] = set()
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        title = clean_title(a.get_text(" ", strip=True))
        if "viewRenew.do" not in href or not title:
            continue
        if "카드뉴스" not in title and "홍보" not in title:
            continue
        row = a.find_parent("tr") or a.find_parent("li") or a.find_parent("div") or a.parent
        date = parse_date(clean(row.get_text(" ", strip=True) if row else ""))
        candidates.append((title, date, urljoin(list_url, href)))
    preferred = [x for x in candidates if relevant(x[0])] or candidates
    for title, date, link in preferred:
        add_item(items, seen, agency="교육부", title=title, date=date, url=link, topic="교육·인재정책")
        if len(items) >= limit:
            break
    return items


def fetch_mss(limit: int = 8) -> list[dict]:
    list_url = "https://www.mss.go.kr/site/smba/ex/bbs/List.do?cbIdx=288"
    soup = get(list_url)
    items: list[dict] = []
    seen: set[str] = set()
    candidates = []
    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        title = clean_title(a.get_text(" ", strip=True))
        if not title:
            continue
        if "View.do" not in href and "view.do" not in href:
            continue
        block = a.find_parent("tr") or a.find_parent("li") or a.find_parent("div") or a.parent
        date = parse_date(clean(block.get_text(" ", strip=True) if block else ""))
        candidates.append((title, date, urljoin(list_url, href)))
    preferred = [x for x in candidates if relevant(x[0])] or candidates
    for title, date, link in preferred:
        add_item(items, seen, agency="중소벤처기업부", title=title, date=date, url=link, topic="기업·창업정책")
        if len(items) >= limit:
            break
    return items


def main() -> None:
    collectors = (
        ("재정경제부", fetch_mofe),
        ("인사혁신처", fetch_mpm),
        ("교육부", fetch_moe),
        ("중소벤처기업부", fetch_mss),
    )
    collected: list[dict] = []
    errors: list[str] = []

    for name, fn in collectors:
        try:
            rows = fn()
            if not rows:
                raise RuntimeError("목록에서 새 게시물을 찾지 못했습니다")
            collected.extend(rows)
        except Exception as exc:
            errors.append(f"{name}: {type(exc).__name__}: {exc}")

    existing = {"items": []}
    if OUT.exists():
        try:
            existing = json.loads(OUT.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 기관별 수집 실패 시 직전 정상 데이터를 유지합니다.
    successful_agencies = {x.get("agency") for x in collected}
    for item in existing.get("items", []):
        if item.get("agency") not in successful_agencies:
            collected.append(item)

    dedup: dict[tuple, dict] = {}
    for item in collected:
        key = (item.get("agency"), item.get("url"), item.get("title"))
        dedup[key] = item

    items = list(dedup.values())
    items.sort(key=lambda x: (x.get("date", ""), x.get("agency", "")), reverse=True)
    items = items[:32]

    payload = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "대한민국 정부기관 공식 누리집",
        "agencies": [name for name, _ in collectors],
        "items": items,
        "errors": errors,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
