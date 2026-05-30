"""
한국관광공사 Tour API - 축제·공연·행사 수집
contentTypeId=15: 축제공연행사 (핵심)
"""

import requests
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import os

load_dotenv()

TOUR_API_BASE = "https://apis.data.go.kr/B551011/KorService1"

def _get_api_key():
    return os.environ["TOUR_API_KEY"]

AREA_CODES = {
    "1": "서울", "2": "인천", "3": "대전", "4": "대구",
    "5": "광주", "6": "부산", "7": "울산", "8": "세종",
    "31": "경기", "32": "강원", "33": "충북", "34": "충남",
    "35": "경북", "36": "경남", "37": "전북", "38": "전남",
    "39": "제주"
}


def fetch_events(start_date: str, end_date: str) -> list:
    all_events = []
    api_key = _get_api_key()

    for area_code, area_name in AREA_CODES.items():
        page = 1
        while True:
            params = {
                "serviceKey": api_key,
                "numOfRows": 100,
                "pageNo": page,
                "MobileOS": "ETC",
                "MobileApp": "uapress",
                "_type": "json",
                "listYN": "Y",
                "arrange": "A",
                "contentTypeId": "15",
                "areaCode": area_code,
                "eventStartDate": start_date,
                "eventEndDate": end_date,
            }

            try:
                resp = requests.get(
                    f"{TOUR_API_BASE}/searchFestival1",
                    params=params,
                    timeout=30
                )
                data = resp.json()
                items = (
                    data.get("response", {})
                        .get("body", {})
                        .get("items", {})
                        .get("item", [])
                )

                if isinstance(items, dict):
                    items = [items]
                if not items:
                    break

                for item in items:
                    all_events.append({
                        "content_id": str(item.get("contentid", "")),
                        "title": item.get("title", "").strip(),
                        "region": area_name,
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
                    })

                print(f"  [{area_name}] 페이지 {page}: {len(items)}개")

                if len(items) < 100:
                    break
                page += 1
                time.sleep(0.3)

            except Exception as e:
                print(f"  [{area_name}] 오류: {e}")
                break

    print(f"\n총 {len(all_events)}개 행사 수집 완료")
    return all_events


def fetch_event_detail(content_id: str) -> dict:
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
        resp = requests.get(
            f"{TOUR_API_BASE}/detailCommon1",
            params=params,
            timeout=15
        )
        data = resp.json()
        item = (
            data.get("response", {})
                .get("body", {})
                .get("items", {})
                .get("item", [{}])
        )
        return item[0] if isinstance(item, list) else item
    except Exception:
        return {}


def fetch_event_intro(content_id: str) -> dict:
    params = {
        "serviceKey": _get_api_key(),
        "contentId": content_id,
        "contentTypeId": "15",
        "MobileOS": "ETC",
        "MobileApp": "uapress",
        "_type": "json",
    }
    try:
        resp = requests.get(
            f"{TOUR_API_BASE}/detailIntro1",
            params=params,
            timeout=15
        )
        data = resp.json()
        item = (
            data.get("response", {})
                .get("body", {})
                .get("items", {})
                .get("item", [{}])
        )
        return item[0] if isinstance(item, list) else item
    except Exception:
        return {}


if __name__ == "__main__":
    today = datetime.now()
    end = today + timedelta(days=90)

    start_str = today.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    print(f"수집 기간: {start_str} ~ {end_str}")
    events = fetch_events(start_str, end_str)

    print("\n상세 정보 수집 중...")
    for i, event in enumerate(events[:500]):
        detail = fetch_event_detail(event["content_id"])
        intro = fetch_event_intro(event["content_id"])

        event["overview"] = detail.get("overview", "")
        event["homepage"] = detail.get("homepage", event.get("homepage", ""))
        event["fee"] = intro.get("usetimefestival", "")
        event["organizer"] = intro.get("sponsor1", "")
        event["playtime"] = intro.get("playtime", "")

        if i % 50 == 0:
            print(f"  {i}/{min(500, len(events))}개 처리")
        time.sleep(0.2)

    Path("data/raw").mkdir(parents=True, exist_ok=True)
    out = Path(f"data/raw/events_{start_str}.json")
    out.write_text(json.dumps(events, ensure_ascii=False, indent=2))
    print(f"\n저장 완료: {out} ({len(events)}개)")
