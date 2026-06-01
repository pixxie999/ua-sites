"""
네이버 카페 후기 수집 — Naver Search API (cafearticle)
행사명으로 검색 후 관련성 필터링으로 정확도 향상
월 25,000건 무료
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
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&quot;', '"').replace('&#39;', "'").replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', text).strip()


def extract_keywords(title: str) -> list[str]:
    """행사 제목에서 핵심 키워드 추출 (2자 이상 한글/영문)"""
    # 괄호 제거
    title = re.sub(r'[(\[（【].*?[)\]）】]', '', title)
    # 한글 2자 이상, 영문 3자 이상
    keywords = re.findall(r'[가-힣]{2,}|[A-Za-z]{3,}', title)
    # 흔한 단어 제외
    stopwords = {'축제', '행사', '페스티벌', '공연', '전시', '체험', '문화', '이번', '이번주'}
    return [k for k in keywords if k not in stopwords][:5]


def is_relevant(item: dict, keywords: list[str], event: dict) -> bool:
    """검색 결과가 해당 행사와 관련 있는지 판단"""
    if not keywords:
        return True  # 키워드 추출 실패 시 통과

    title_text = strip_html(item.get("title", "")).lower()
    desc_text = strip_html(item.get("description", "")).lower()
    combined = title_text + " " + desc_text

    # 키워드 매칭 점수 계산
    matched = sum(1 for kw in keywords if kw.lower() in combined)

    # 연도 필터: 행사 연도가 포함된 글만 (연도 있는 경우)
    event_year = event.get("start_date", "")[:4]
    if event_year and event_year not in combined:
        # 연도 미포함이어도 키워드 3개 이상 매칭이면 통과
        if matched < 3:
            return False

    # 키워드 2개 이상 매칭 or 제목에 1개라도 매칭
    title_matched = sum(1 for kw in keywords if kw.lower() in title_text)
    return matched >= 2 or title_matched >= 1


def search_cafe(query: str, display: int = 10) -> list:
    """네이버 카페 검색 — 최신순"""
    params = {
        "query": query,
        "display": display,
        "sort": "date",
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
        return resp.json().get("items", [])
    except Exception as e:
        print(f"    검색 오류 ({query}): {e}")
        return []


def is_cache_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(days=CACHE_DAYS)


def fetch_reviews_for_event(event: dict) -> list:
    """행사 1개에 대한 카페 후기 수집 + 관련성 필터링"""
    title = event["title"]
    region = event.get("region", "")
    year = event.get("start_date", "")[:4]
    keywords = extract_keywords(title)

    # 쿼리 전략: 구체적인 것부터 시도
    queries = [
        f"{title} {year}",           # "XX축제 2026" — 올해 글 우선
        f"{title} 후기",              # "XX축제 후기"
        f"{title} {region}",          # "XX축제 서울"
    ]

    seen_links = set()
    results = []

    for query in queries:
        # display=10으로 많이 가져와서 필터링
        items = search_cafe(query, display=10)
        for item in items:
            link = item.get("link", "")
            if link in seen_links:
                continue
            seen_links.add(link)

            # 관련성 필터
            if not is_relevant(item, keywords, event):
                continue

            # 행사 시작 6개월 전 이후 글만 (너무 오래된 글 제외)
            post_date = item.get("postdate", "")
            if post_date and len(post_date) == 8:
                cutoff = (datetime.strptime(event["start_date"], "%Y%m%d")
                          - timedelta(days=180)).strftime("%Y%m%d")
                if post_date < cutoff:
                    continue

            results.append({
                "title": strip_html(item.get("title", "")),
                "description": strip_html(item.get("description", ""))[:200],
                "link": link,
                "cafe_name": item.get("cafename", ""),
                "cafe_url": item.get("cafeurl", ""),
                "date": post_date,
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

    active = [e for e in events if e.get("end_date", "") >= today]
    targets = sorted(active, key=lambda x: x["start_date"])[:max_events]

    new_count = 0
    skip_count = 0

    for event in targets:
        cache_path = REVIEWS_DIR / f"{event['id']}.json"

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
        time.sleep(0.15)

    print(f"\n카페 후기 수집 완료: 신규 {new_count}개, 캐시 재사용 {skip_count}개")


if __name__ == "__main__":
    fetch_all()
