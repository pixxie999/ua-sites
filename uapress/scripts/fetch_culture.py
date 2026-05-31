"""
문화체육관광부 문화포털 공연·전시 정보 API
http://www.culture.go.kr/openapi/rest/publicperformancedisplays
자동승인 / 일 1,000건 무료
"""

import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import os

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

API_BASE = "http://www.culture.go.kr/openapi/rest/publicperformancedisplays"

# 지역명 → area 파라미터
SIDO_LIST = [
    "서울", "인천", "대전", "대구", "광주", "부산", "울산", "세종",
    "경기", "강원", "충북", "충남", "경북", "경남", "전북", "전남", "제주"
]

# 카테고리 코드
REALM_CODES = {
    "A000": "문학",
    "B000": "미술",
    "C000": "공예",
    "D000": "디자인",
    "E000": "사진",
    "F000": "서예",
    "G000": "음악",
    "H000": "무용",
    "I000": "연극",
    "J000": "영화",
    "K000": "만화",
    "L000": "게임",
    "M000": "축제",
    "N000": "전통",
    "O000": "기타",
}


def _get_api_key():
    return os.environ["CULTURE_API_KEY"]


def fetch_by_area(start_date: str, end_date: str, sido: str, page: int = 1) -> dict:
    params = {
        "serviceKey": _get_api_key(),
        "cPage": page,
        "rows": 100,
        "from": start_date,
        "to": end_date,
        "sido": sido,
        "place": "",
        "keyword": "",
        "openRun": "",
    }
    try:
        resp = requests.get(
            f"{API_BASE}/area",
            params=params,
            timeout=30
        )
        return resp.json()
    except Exception as e:
        print(f"  [{sido}] 오류: {e}")
        return {}


def parse_item(item: dict, region: str) -> dict:
    """API 응답 아이템 → 표준 포맷 변환"""
    seq = str(item.get("seq", ""))
    title = item.get("title", "").strip()

    # 날짜 변환 (YYYYMMDD → YYYYMMDD 유지)
    start_date = item.get("startDate", "").replace("-", "").replace(".", "")[:8]
    end_date = item.get("endDate", "").replace("-", "").replace(".", "")[:8]

    def fmt(d):
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d

    # 카테고리 매핑
    realm = item.get("realmName", "")
    if any(k in realm for k in ["음악", "클래식", "국악", "재즈"]):
        category = "공연"
    elif any(k in realm for k in ["연극", "뮤지컬", "무용", "오페라"]):
        category = "공연"
    elif any(k in realm for k in ["미술", "전시", "사진", "조각"]):
        category = "전시"
    elif any(k in realm for k in ["축제"]):
        category = "축제"
    elif any(k in realm for k in ["공예", "체험", "교육"]):
        category = "체험"
    else:
        category = "문화행사"

    # 무료 여부
    price = item.get("price", "")
    is_free = "무료" in price or price.strip() in ("", "0", "0원")

    # 슬러그 (culture 소스 prefix로 중복 방지)
    import re
    en = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip()
    en = re.sub(r'\s+', '-', en).lower()[:35]
    slug = f"c{seq}-{en}" if en else f"c{seq}"

    return {
        "id": slug,
        "content_id": f"c{seq}",
        "source": "culture",
        "title": title,
        "category": category,
        "region": region,
        "area_code": "",
        "address": item.get("place", ""),
        "lat": float(item.get("gpsY", 0) or 0),
        "lng": float(item.get("gpsX", 0) or 0),
        "start_date": start_date,
        "end_date": end_date,
        "start_date_fmt": fmt(start_date),
        "end_date_fmt": fmt(end_date),
        "place": item.get("place", ""),
        "fee": price,
        "is_free": is_free,
        "organizer": item.get("organization", ""),
        "overview": item.get("contents1", "")[:500] if item.get("contents1") else "",
        "thumbnail": item.get("thumbnail", ""),
        "homepage": item.get("homepage", ""),
        "tel": item.get("phone", ""),
        "summary": "",
        "highlight": "",
        "target_audience": "",
        "tips": [],
        "seo_title": "",
        "meta_description": "",
        "tags": [],
    }


def fetch_all_events(start_date: str, end_date: str) -> list:
    all_events = []
    today = datetime.now().strftime("%Y%m%d")

    for sido in SIDO_LIST:
        page = 1
        while True:
            data = fetch_by_area(start_date, end_date, sido, page)
            msg_body = data.get("msgBody", {})

            if not msg_body:
                break

            total_count = int(msg_body.get("totalCount", 0))
            perf_list = msg_body.get("perforList", [])

            if not perf_list:
                break

            if isinstance(perf_list, dict):
                perf_list = [perf_list]

            count = 0
            for item in perf_list:
                # 종료된 행사 제외
                end = item.get("endDate", "").replace("-", "")[:8]
                if end and end < today:
                    continue
                parsed = parse_item(item, sido)
                if parsed["title"]:
                    all_events.append(parsed)
                    count += 1

            print(f"  [{sido}] 페이지 {page}: {count}개 (누적 {len(all_events)})")

            if len(all_events) >= total_count or len(perf_list) < 100:
                break
            page += 1
            time.sleep(0.2)

    print(f"\n문화부 총 {len(all_events)}개 행사 수집 완료")
    return all_events


if __name__ == "__main__":
    today = datetime.now()
    end = today + timedelta(days=90)

    start_str = today.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    print(f"수집 기간: {start_str} ~ {end_str}")
    events = fetch_all_events(start_str, end_str)

    (PROJECT_ROOT / "data/raw").mkdir(parents=True, exist_ok=True)
    out = PROJECT_ROOT / f"data/raw/culture_{start_str}.json"
    out.write_text(json.dumps(events, ensure_ascii=False, indent=2))
    print(f"저장 완료: {out} ({len(events)}개)")
