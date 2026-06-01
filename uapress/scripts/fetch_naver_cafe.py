"""
네이버 카페 후기 수집 — Naver Search API (cafearticle)
행사명으로 검색해 실제 방문 후기·정보 글 수집
월 25,000건 무료 (행사당 최대 5건 × 약 200개 = 1,000건/회)
"""

import requests
import json
import time
import re
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

NAVER_SEARCH_URL = "https://openapi.naver.com/v1/search/cafearticle.json"
REVIEWS_DIR = PROJECT_ROOT / "data/content/cafe_reviews"
CACHE_DAYS = 7  # 7일 이상 된 캐시만 갱신


def _get_headers():
    return {
        "X-Naver-Client-Id": os.environ["NAVER_CLIENT_ID"],
        "X-Naver-Client-Secret": os.environ["NAVER_CLIENT_SECRET"],
    }


def strip_html(text: str) -> str:
    """HTML 태그 제거"""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def search_cafe(query: str, display: int = 5) -> list:
    """네이버 카페 검색 — 최신순"""
    params = {
        "query": query,
        "display": display,
        "sort": "date",  # 최신순
    }
    try:
        resp = requests.get(
            NAVER_SEARCH_URL,
            headers=_get_headers(),
            params=params,
            timeout=10
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
        return data.get("items", [])
    except Exception as e:
        print(f"    검색 오류 ({query}): {e}")
        return []


def is_cache_fresh(path: Path) -> bool:
    """캐시가 CACHE_DAYS 이내이면 True"""
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(days=CACHE_DAYS)


def fetch_reviews_for_event(event: dict) -> list:
    """행사 1개에 대한 카페 후기 수집"""
    title = event["title"]
    region = event.get("region", "")

    # 검색 쿼리: "행사명 후기" 우선, 없으면 "행사명 지역"
    queries = [
        f"{title} 후기",
        f"{title} {region}" if region else title,
    ]

    seen_links = set()
    results = []

    for query in queries:
        items = search_cafe(query, display=5)
        for item in items:
            link = item.get("link", "")
            if link in seen_links:
                continue
            seen_links.add(link)

            results.append({
                "title": strip_html(item.get("title", "")),
                "description": strip_html(item.get("description", ""))[:200],
                "link": link,
                "cafe_name": item.get("cafename", ""),
                "cafe_url": item.get("cafeurl", ""),
                "date": item.get("postdate", ""),  # YYYYMMDD
            })

        if len(results) >= 5:
            break
        time.sleep(0.1)

    return results[:5]


def fetch_all(max_events: int = 300):
    """처리된 행사 전체에 대해 카페 후기 수집 (캐시 활용)"""
    REVIEWS_DIR.mkdir(parents=True, exist_ok=True)

    events_path = PROJECT_ROOT / "data/processed/events.json"
    if not events_path.exists():
        print("events.json 없음 — process_events.py 먼저 실행하세요.")
        return

    events = json.loads(events_path.read_text())
    today = datetime.now().strftime("%Y%m%d")

    # 진행 중인 행사만, Tour API 우선 (썸네일 있는 것)
    active = [e for e in events if e.get("end_date", "") >= today]
    tour_events = [e for e in active if e.get("source") != "culture"]
    targets = (tour_events + [e for e in active if e.get("source") == "culture"])[:max_events]

    new_count = 0
    skip_count = 0

    for i, event in enumerate(targets):
        cache_path = REVIEWS_DIR / f"{event['id']}.json"

        # 캐시 신선하면 스킵
        if is_cache_fresh(cache_path):
            skip_count += 1
            continue

        reviews = fetch_reviews_for_event(event)

        cache_path.write_text(json.dumps({
            "event_id": event["id"],
            "event_title": event["title"],
            "fetched_at": datetime.now().isoformat(),
            "reviews": reviews,
        }, ensure_ascii=False, indent=2))

        new_count += 1
        if new_count % 20 == 0:
            print(f"  {new_count}개 수집 완료 (스킵: {skip_count}개)")
        time.sleep(0.15)  # 속도 제한

    print(f"\n카페 후기 수집 완료: 신규 {new_count}개, 캐시 재사용 {skip_count}개")


if __name__ == "__main__":
    fetch_all()
