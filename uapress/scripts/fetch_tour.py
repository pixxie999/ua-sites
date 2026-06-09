"""
한국관광공사 Tour API (KorService2) - 축제·공연·행사 수집
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

TOUR_API_BASE = "https://apis.data.go.kr/B551011/KorService2"

# 지역코드 → 지역명 매핑 (areacode 필드 기반)
AREA_MAP = {
    "1": "서울", "2": "인천", "3": "대전", "4": "대구",
    "5": "광주", "6": "부산", "7": "울산", "8": "세종",
    "31": "경기", "32": "강원", "33": "충북", "34": "충남",
    "35": "경북", "36": "경남", "37": "전북", "38": "전남",
    "39": "제주"
}

# 주소 기반 지역 감지 — 긴 키워드(광역시/특별자치도)를 먼저 검사해야
# "경기도 광주시"를 "광주광역시"로 오인하지 않음
ADDRESS_REGION_RULES = [
    ("서울특별시", "서울"), ("서울", "서울"),
    ("부산광역시", "부산"), ("부산", "부산"),
    ("대구광역시", "대구"), ("대구", "대구"),
    ("인천광역시", "인천"), ("인천", "인천"),
    ("광주광역시", "광주"),                       # '경기 광주' 보다 먼저
    ("대전광역시", "대전"), ("대전", "대전"),
    ("울산광역시", "울산"), ("울산", "울산"),
    ("세종특별자치시", "세종"), ("세종", "세종"),
    ("경기도", "경기"), ("경기", "경기"),
    ("강원특별자치도", "강원"), ("강원도", "강원"), ("강원", "강원"),
    ("충청북도", "충북"), ("충북", "충북"),
    ("충청남도", "충남"), ("충남", "충남"),
    ("전북특별자치도", "전북"), ("전라북도", "전북"), ("전북", "전북"),
    ("전라남도", "전남"), ("전남", "전남"),
    ("경상북도", "경북"), ("경북", "경북"),
    ("경상남도", "경남"), ("경남", "경남"),
    ("제주특별자치도", "제주"), ("제주도", "제주"), ("제주", "제주"),
    ("광주", "광주"),  # '경기 광주' 처리 — 경기는 이미 위에서 매핑됨
]


def _get_api_key():
    return os.environ["TOUR_API_KEY"]


def detect_region_from_address(addr: str) -> str:
    """주소 문자열에서 지역명 추출"""
    if not addr:
        return "기타"
    for keyword, region in ADDRESS_REGION_RULES:
        if keyword in addr:
            return region
    return "기타"


def resolve_region(item: dict) -> tuple[str, str]:
    """지역명과 area_code 반환.
    우선순위: areacode(Tour API 코드) → 주소(addr1) 기반 감지
    lDongRegnCd는 Tour API와 코드 체계가 불일치하여 사용하지 않음.
    """
    area_code = str(item.get("areacode", "")).strip()
    if area_code and area_code in AREA_MAP:
        return AREA_MAP[area_code], area_code

    # areacode 없거나 매핑 실패 → 주소로 감지
    addr = item.get("addr1", "") or ""
    region = detect_region_from_address(addr)
    return region, area_code or "0"


def fetch_events(start_date: str, end_date: str) -> list:
    """전국 행사 한꺼번에 페이지네이션으로 수집"""
    all_events = []
    api_key = _get_api_key()
    page = 1

    while True:
        params = {
            "serviceKey": api_key,
            "numOfRows": 100,
            "pageNo": page,
            "MobileOS": "ETC",
            "MobileApp": "uapress",
            "_type": "json",
            "arrange": "A",
            "eventStartDate": start_date,
            "eventEndDate": end_date,
        }

        try:
            resp = requests.get(
                f"{TOUR_API_BASE}/searchFestival2",
                params=params,
                timeout=30
            )
            data = resp.json()

            body = data.get("response", {}).get("body", {})
            total_count = body.get("totalCount", 0)
            items = body.get("items", {})

            if not items or items == "":
                break

            item_list = items.get("item", [])
            if isinstance(item_list, dict):
                item_list = [item_list]
            if not item_list:
                break

            for item in item_list:
                region, area_code = resolve_region(item)
                all_events.append({
                    "content_id": str(item.get("contentid", "")),
                    "title": item.get("title", "").strip(),
                    "region": region,
                    "area_code": area_code,
                    "address": item.get("addr1", ""),
                    "lat": float(item.get("mapy", 0) or 0),
                    "lng": float(item.get("mapx", 0) or 0),
                    "start_date": item.get("eventstartdate", ""),
                    "end_date": item.get("eventenddate", ""),
                    "place": item.get("eventplace", ""),
                    "thumbnail": item.get("firstimage", ""),
                    "thumbnail_small": item.get("firstimage2", ""),
                    "tel": item.get("tel", ""),
                    "homepage": item.get("homepage", ""),
                    "overview": "",
                    "fee": "",
                    "organizer": "",
                })

            print(f"  페이지 {page}: {len(item_list)}개 (누적 {len(all_events)}/{total_count})")

            if len(all_events) >= total_count or len(item_list) < 100:
                break
            page += 1
            time.sleep(0.3)

        except Exception as e:
            print(f"  페이지 {page} 오류: {e}")
            if 'resp' in locals():
                print(f"  HTTP {resp.status_code}: {resp.text[:200]!r}")
            break

    print(f"\n총 {len(all_events)}개 행사 수집 완료")
    return all_events


def fetch_event_detail(content_id: str) -> dict:
    """행사 상세 정보 (개요·관람료 등)"""
    params = {
        "serviceKey": _get_api_key(),
        "contentId": content_id,
        "contentTypeId": "15",
        "MobileOS": "ETC",
        "MobileApp": "uapress",
        "_type": "json",
        "defaultYN": "Y",
        "overviewYN": "Y",
        "addrinfoYN": "Y",
    }
    try:
        resp = requests.get(f"{TOUR_API_BASE}/detailCommon2", params=params, timeout=15)
        data = resp.json()
        item = (data.get("response", {}).get("body", {})
                    .get("items", {}).get("item", [{}]))
        return item[0] if isinstance(item, list) else item
    except Exception:
        return {}


def fetch_event_intro(content_id: str) -> dict:
    """행사 소개 (관람료·주최 등)"""
    params = {
        "serviceKey": _get_api_key(),
        "contentId": content_id,
        "contentTypeId": "15",
        "MobileOS": "ETC",
        "MobileApp": "uapress",
        "_type": "json",
    }
    try:
        resp = requests.get(f"{TOUR_API_BASE}/detailIntro2", params=params, timeout=15)
        data = resp.json()
        item = (data.get("response", {}).get("body", {})
                    .get("items", {}).get("item", [{}]))
        return item[0] if isinstance(item, list) else item
    except Exception:
        return {}


def fetch_nearby_attractions(area_code: str, region_name: str, limit: int = 6) -> list:
    """지역별 관광지 수집 (contentTypeId=12: 관광지)"""
    params = {
        "serviceKey": _get_api_key(),
        "numOfRows": 20,
        "pageNo": 1,
        "MobileOS": "ETC",
        "MobileApp": "uapress",
        "_type": "json",
        "listYN": "Y",
        "arrange": "A",        # 제목순 (Q=조회순은 로그인 필요)
        "contentTypeId": "12", # 관광지
        "areaCode": area_code,
    }
    try:
        # KorService1/areaBasedList1 사용 (KorService2/areaBasedList2는 totalCount=0 반환)
        resp = requests.get(
            "https://apis.data.go.kr/B551011/KorService1/areaBasedList1",
            params=params, timeout=15
        )
        data = resp.json()
        # 첫 번째 지역만 응답 구조 디버그 출력
        if area_code == "1":
            body = data.get("response", {}).get("body", {})
            total = body.get("totalCount", 0)
            print(f"  [디버그 서울] totalCount={total}, HTTP={resp.status_code}")
        raw_items = (data.get("response", {}).get("body", {}).get("items", {}))
        # 결과 없을 때 items가 "" (빈 문자열)로 오는 경우 방어
        if not raw_items or not isinstance(raw_items, dict):
            return []
        items = raw_items.get("item", [])
        if isinstance(items, dict):
            items = [items]
        result = []
        for item in items[:limit]:
            result.append({
                "title": item.get("title", "").strip(),
                "address": item.get("addr1", ""),
                "thumbnail": item.get("firstimage", "") or item.get("firstimage2", ""),
                "content_id": str(item.get("contentid", "")),
                "region": region_name,
            })
        return result
    except Exception as e:
        print(f"  관광지 수집 오류 ({region_name}): {e}")
        return []


def fetch_all_attractions():
    """17개 지역 관광지 수집 후 저장"""
    out_dir = PROJECT_ROOT / "data/raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_attractions = {}
    for area_code, region_name in AREA_MAP.items():
        spots = fetch_nearby_attractions(area_code, region_name)
        all_attractions[region_name] = spots
        print(f"  {region_name}: {len(spots)}개")
        time.sleep(0.3)
    out = out_dir / "attractions.json"
    out.write_text(json.dumps(all_attractions, ensure_ascii=False, indent=2))
    print(f"관광지 저장 완료: {out}")
    return all_attractions


if __name__ == "__main__":
    today = datetime.now()
    end = today + timedelta(days=90)

    start_str = today.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    print(f"수집 기간: {start_str} ~ {end_str}")
    events = fetch_events(start_str, end_str)

    # 상세 정보 추가 (전체 — 124개 수준이므로 제한 불필요)
    if events:
        print("\n상세 정보 수집 중...")
        for i, event in enumerate(events):
            detail = fetch_event_detail(event["content_id"])
            intro = fetch_event_intro(event["content_id"])

            event["overview"] = detail.get("overview", "")
            event["homepage"] = detail.get("homepage", event.get("homepage", ""))
            event["fee"] = intro.get("usetimefestival", "")
            event["organizer"] = intro.get("sponsor1", "")
            event["playtime"] = intro.get("playtime", "")

            if i % 50 == 0:
                print(f"  {i}/{len(events)}개 처리")
            time.sleep(0.2)

    (PROJECT_ROOT / "data/raw").mkdir(parents=True, exist_ok=True)
    out = PROJECT_ROOT / f"data/raw/events_{start_str}.json"
    out.write_text(json.dumps(events, ensure_ascii=False, indent=2))
    print(f"\n저장 완료: {out} ({len(events)}개)")
