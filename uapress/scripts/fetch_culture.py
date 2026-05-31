"""
한국문화정보원 문화예술공연 통합 API (CNV_060)
https://api.kcisa.kr/openapi/CNV_060/request
연극·뮤지컬·오페라·음악·콘서트·국악·무용·전시 등
"""

import requests
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import os

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

API_URL = "https://api.kcisa.kr/openapi/CNV_060/request"

REALM_TO_CATEGORY = {
    "연극": "공연", "뮤지컬": "공연", "오페라": "공연",
    "음악": "공연", "콘서트": "공연", "국악": "공연", "무용": "공연",
    "전시": "전시", "미술": "전시", "사진": "전시", "조각": "전시",
    "축제": "축제", "체험": "체험", "교육": "체험",
}


def _get_api_key():
    return os.environ["CULTURE_API_KEY"]


def detect_category(realm: str) -> str:
    for keyword, category in REALM_TO_CATEGORY.items():
        if keyword in realm:
            return category
    return "문화행사"


def parse_date(d: str) -> str:
    """다양한 날짜 포맷 → YYYYMMDD"""
    if not d:
        return ""
    d = d.strip().replace("-", "").replace(".", "").replace("/", "")
    return d[:8] if len(d) >= 8 else ""


def make_slug(seq: str, title: str) -> str:
    en = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip()
    en = re.sub(r'\s+', '-', en).lower()[:35]
    return f"k{seq}-{en}" if en else f"k{seq}"


def fetch_page(start_date: str, end_date: str, page: int) -> dict:
    params = {
        "serviceKey": _get_api_key(),
        "numOfRows": 100,
        "pageNo": page,
        "from": start_date,
        "to": end_date,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  HTTP {resp.status_code}: {resp.text[:200]!r}")
            return {}
        return resp.json()
    except Exception as e:
        print(f"  페이지 {page} 오류: {e}")
        return {}


def fetch_all_events(start_date: str, end_date: str) -> list:
    all_events = []
    today = datetime.now().strftime("%Y%m%d")
    page = 1

    while True:
        data = fetch_page(start_date, end_date, page)
        if not data:
            break

        # 응답 구조 파악 (API마다 다를 수 있음)
        body = (data.get("response") or data.get("msgBody") or data)
        if isinstance(body, dict):
            items = (
                body.get("items") or
                body.get("perforList") or
                body.get("item") or
                []
            )
            total_count = int(body.get("totalCount", 0) or body.get("numOfRows", 0))
        else:
            items = body if isinstance(body, list) else []
            total_count = len(items)

        if isinstance(items, dict):
            items = list(items.values())[0] if items else []
            if isinstance(items, dict):
                items = [items]

        if not items:
            if page == 1:
                print(f"  응답 구조: {str(data)[:300]}")
            break

        count = 0
        for item in items:
            if not isinstance(item, dict):
                continue

            # 날짜 필드 (API마다 키 이름 다름)
            start = parse_date(
                item.get("startDate") or item.get("beginDt") or
                item.get("eventstartdate") or item.get("from") or ""
            )
            end = parse_date(
                item.get("endDate") or item.get("endDt") or
                item.get("eventenddate") or item.get("to") or ""
            )

            if not start or not end:
                continue
            if end < today:
                continue

            # 제목
            title = (
                item.get("title") or item.get("nm") or
                item.get("prfnm") or ""
            ).strip()
            if not title:
                continue

            # 지역
            region = (
                item.get("area") or item.get("sido") or
                item.get("signguNm") or "기타"
            ).strip()
            if not region or region == "기타":
                addr = item.get("place") or item.get("fcltynm") or ""
                for r in ["서울", "부산", "대구", "인천", "광주", "대전", "울산",
                          "세종", "경기", "강원", "충북", "충남", "전북", "전남",
                          "경북", "경남", "제주"]:
                    if r in addr:
                        region = r
                        break
                else:
                    region = "기타"

            # 카테고리
            realm = (
                item.get("realmName") or item.get("genrenm") or
                item.get("realm") or ""
            )
            category = detect_category(realm)

            # 관람료
            price = (
                item.get("price") or item.get("pcseguidance") or
                item.get("fee") or ""
            )
            is_free = "무료" in price or price.strip() in ("", "0", "0원")

            # 기타 필드
            seq = str(item.get("seq") or item.get("mt20id") or item.get("contentid") or "")
            slug = make_slug(seq, title)

            def fmt(d):
                return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d

            all_events.append({
                "id": slug,
                "content_id": f"k{seq}",
                "source": "culture",
                "title": title,
                "category": category,
                "region": region,
                "area_code": "",
                "address": item.get("place") or item.get("fcltynm") or "",
                "lat": float(item.get("gpsY") or item.get("la") or 0),
                "lng": float(item.get("gpsX") or item.get("lo") or 0),
                "start_date": start,
                "end_date": end,
                "start_date_fmt": fmt(start),
                "end_date_fmt": fmt(end),
                "place": item.get("place") or item.get("fcltynm") or "",
                "fee": price,
                "is_free": is_free,
                "organizer": item.get("organization") or item.get("entrpsnm") or "",
                "overview": (item.get("contents1") or item.get("styurls") or "")[:500],
                "thumbnail": item.get("thumbnail") or item.get("poster") or "",
                "homepage": item.get("homepage") or item.get("relates") or "",
                "tel": item.get("phone") or item.get("telno") or "",
                "summary": "",
                "highlight": "",
                "target_audience": "",
                "tips": [],
                "seo_title": "",
                "meta_description": "",
                "tags": [],
            })
            count += 1

        print(f"  페이지 {page}: {count}개 (누적 {len(all_events)})")

        if total_count and len(all_events) >= total_count:
            break
        if len(items) < 100:
            break
        page += 1
        time.sleep(0.3)

    print(f"\n문화부 총 {len(all_events)}개 수집 완료")
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
