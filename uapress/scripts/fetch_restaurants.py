"""
축제별 인근 맛집 수집 + Claude AI 큐레이션
- TourAPI (primary): contentTypeId=39 (음식점)
- 카카오 로컬 API (secondary): FD6 카테고리
- Claude Haiku: TOP 5 큐레이션
- 결과: data/restaurants/{event_id}.json
실행: python fetch_restaurants.py [--limit 30]
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

TOUR_API_BASE = "https://apis.data.go.kr/B551011/KorService1"
KAKAO_CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"
KAKAO_KEYWORD_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"
RESTAURANTS_DIR = PROJECT_ROOT / "data" / "restaurants"
EVENTS_PATH = PROJECT_ROOT / "data" / "processed" / "events.json"

CACHE_DAYS = 30
MAX_PER_RUN = 30
KST = timezone(timedelta(hours=9))


def _get_tour_key():
    return os.environ["TOUR_API_KEY"]

def _get_kakao_key():
    return os.environ["KAKAO_REST_API_KEY"]

def _get_anthropic_client():
    import anthropic
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


# ─────────────────────────────────────────
# TourAPI 음식점 수집
# ─────────────────────────────────────────

def fetch_tour_restaurants(area_code: str, sigungu_code: str,
                           lat: float = 0, lng: float = 0) -> list:
    """시도코드 + 시군구코드 기반 음식점 조회 (areaBasedList2)"""
    if not area_code:
        return []
    params = {
        "serviceKey": _get_tour_key(),
        "MobileOS": "ETC",
        "MobileApp": "uapress",
        "_type": "json",
        "contentTypeId": "39",
        "areaCode": area_code,
        "numOfRows": "30",
        "pageNo": "1",
        "arrange": "Q",
    }
    if sigungu_code:
        params["sigunguCode"] = sigungu_code
    try:
        resp = requests.get(f"{TOUR_API_BASE}/areaBasedList2", params=params, timeout=15)
        data = resp.json()
        raw = data.get("response", {}).get("body", {}).get("items", {})
        if not raw or not isinstance(raw, dict):
            return []
        items = raw.get("item", [])
        if isinstance(items, dict):
            items = [items]
        result = []
        for item in items:
            name = item.get("title", "").strip()
            if not name:
                continue
            ilat = float(item.get("mapy", 0) or 0)
            ilng = float(item.get("mapx", 0) or 0)
            dist = 0
            if lat and lng and ilat and ilng:
                import math
                dy = (ilat - lat) * 111000
                dx = (ilng - lng) * 111000 * math.cos(math.radians(lat))
                dist = int(math.sqrt(dx**2 + dy**2))
            result.append({
                "id": f"tour_{item.get('contentid', '')}",
                "source": "tourapi",
                "name": name,
                "address": item.get("addr1", ""),
                "lat": ilat,
                "lng": ilng,
                "category": item.get("cat3", "") or item.get("cat2", "") or "음식점",
                "phone": item.get("tel", ""),
                "image_url": item.get("firstimage", "") or item.get("firstimage2", ""),
                "distance_meters": dist,
                "kakao_map_url": f"https://map.kakao.com/?q={name}",
            })
        return result
    except Exception as e:
        print(f"    TourAPI 오류: {e}")
        return []


# ─────────────────────────────────────────
# 카카오 로컬 API 음식점 수집
# ─────────────────────────────────────────

def _parse_kakao_items(documents: list, lat: float = 0, lng: float = 0) -> list:
    """카카오 API 응답 documents → 표준 dict 변환"""
    import math
    result = []
    for item in documents:
        name = item.get("place_name", "").strip()
        if not name:
            continue
        cat_parts = item.get("category_name", "음식점").split(" > ")
        category = cat_parts[-1] if len(cat_parts) > 1 else cat_parts[0]
        item_lat = float(item.get("y", 0))
        item_lng = float(item.get("x", 0))
        # 카카오 keyword API는 distance 필드가 없는 경우가 있으므로 직접 계산
        dist = int(item.get("distance", 0) or 0)
        if dist == 0 and lat and lng and item_lat and item_lng:
            # 간이 거리 계산 (m)
            dy = (item_lat - lat) * 111000
            dx = (item_lng - lng) * 111000 * math.cos(math.radians(lat))
            dist = int(math.sqrt(dx**2 + dy**2))
        result.append({
            "id": f"kakao_{item.get('id', '')}",
            "source": "kakao",
            "name": name,
            "address": item.get("road_address_name") or item.get("address_name", ""),
            "lat": item_lat,
            "lng": item_lng,
            "category": category,
            "phone": item.get("phone", ""),
            "image_url": "",
            "distance_meters": dist,
            "kakao_map_url": item.get("place_url", f"https://map.kakao.com/?q={name}"),
        })
    return result


def _extract_area_keyword(address: str, region: str) -> str:
    """주소에서 시/군/구 단위 추출 — 카카오 키워드 검색용"""
    import re
    # "경상남도 함안군 가야읍 ..." → "함안군"
    m = re.search(r'([가-힣]+[시군구])', address)
    if m:
        return m.group(1)
    return region  # 없으면 지역명(도 단위) 사용


def fetch_kakao_restaurants(lat: float, lng: float, radius: int = 3000,
                            address: str = "", region: str = "") -> list:
    headers = {"Authorization": f"KakaoAK {_get_kakao_key()}"}

    # 1차: 좌표 기반 category 검색
    cat_result = []
    try:
        params = {
            "category_group_code": "FD6",
            "x": str(lng), "y": str(lat),
            "radius": radius, "sort": "distance", "size": 15,
        }
        resp = requests.get(KAKAO_CATEGORY_URL, headers=headers, params=params, timeout=15)
        cat_result = _parse_kakao_items(resp.json().get("documents", []), lat, lng)
    except Exception as e:
        print(f"    카카오 category 오류: {e}")

    # 2차: 주소 기반 keyword 검색 (1차 결과 부족 시 보완)
    kw_result = []
    if len(cat_result) < 5:
        try:
            area = _extract_area_keyword(address, region)
            kw_params = {
                "query": f"{area} 음식점",
                "category_group_code": "FD6",
                "x": str(lng), "y": str(lat),
                "radius": max(radius, 5000),
                "sort": "distance", "size": 15,
            }
            resp2 = requests.get(KAKAO_KEYWORD_URL, headers=headers, params=kw_params, timeout=15)
            kw_result = _parse_kakao_items(resp2.json().get("documents", []), lat, lng)
            if kw_result:
                print(f"    카카오 keyword 보완: {len(kw_result)}개 ({area} 음식점)")
        except Exception as e:
            print(f"    카카오 keyword 오류: {e}")

    # 중복 제거 후 합산
    merged = list(cat_result)
    cat_ids = {r["id"] for r in cat_result}
    merged += [r for r in kw_result if r["id"] not in cat_ids]
    return merged


# ─────────────────────────────────────────
# 중복 제거
# ─────────────────────────────────────────

def _normalize_name(name: str) -> str:
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', name).lower()

def deduplicate(tour: list, kakao: list) -> list:
    """TourAPI 우선, 카카오에서 새로운 것만 보완"""
    merged = list(tour)
    tour_names = {_normalize_name(r["name"]) for r in tour}
    for item in kakao:
        normalized = _normalize_name(item["name"])
        if normalized not in tour_names:
            merged.append(item)
            tour_names.add(normalized)
    return merged


# ─────────────────────────────────────────
# Claude 큐레이션
# ─────────────────────────────────────────

CURATION_PROMPT = """당신은 축제 방문객을 위한 맛집 큐레이션 전문가입니다.

다음 축제 정보와 인근 맛집 후보를 보고, 축제 방문객에게 가장 적합한 맛집 TOP 5를 선정하세요.

## 축제 정보
- 이름: {festival_name}
- 카테고리: {category}
- 기간: {period}
- 위치: {location}

## 후보 맛집 목록
{candidates}

## 선정 기준
1. 축제 방문객 동선에 적합 (가까운 곳 우선)
2. 다양한 음식 카테고리 분산 (한식/카페/분식 등 균형)
3. 축제 성격에 어울리는 분위기

## 주의사항
- 정확한 영업시간이나 메뉴 가격은 절대 단정하지 마세요
- 폐업 가능성을 고려해 확실한 정보만 추천 사유에 포함하세요
- 추천 사유는 1~2문장, 간결하게 작성하세요

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
{{
  "selected": [
    {{
      "source_id": "후보 맛집의 id 값",
      "recommendation": "방문객에게 추천하는 1~2문장 이유",
      "best_time": "축제 전 점심" 또는 "축제 후 저녁" 또는 "언제든"
    }}
  ],
  "curation_note": "이 축제 방문객에게 전하는 맛집 전반에 대한 한 줄 코멘트"
}}"""


def curate_with_claude(event: dict, candidates: list) -> dict | None:
    if not candidates:
        return None

    client = _get_anthropic_client()

    candidates_text = json.dumps(
        [{"id": c["id"], "name": c["name"], "category": c["category"],
          "distance_m": c["distance_meters"], "address": c["address"]}
         for c in candidates[:20]],
        ensure_ascii=False, indent=2
    )

    prompt = CURATION_PROMPT.format(
        festival_name=event["title"],
        category=event.get("category", ""),
        period=f"{event.get('start_date_fmt', '')} ~ {event.get('end_date_fmt', '')}",
        location=f"{event.get('region', '')} {event.get('place', '')}".strip(),
        candidates=candidates_text,
    )

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )
        raw = resp.content[0].text.strip()
        # 마크다운 펜스 제거
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return json.loads(raw)
    except Exception as e:
        print(f"    Claude 오류: {e}")
        return None


# ─────────────────────────────────────────
# 메인 파이프라인
# ─────────────────────────────────────────

def needs_refresh(event_id: str) -> bool:
    path = RESTAURANTS_DIR / f"{event_id}.json"
    if not path.exists():
        return True
    age = datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)
    return age > timedelta(days=CACHE_DAYS)


def process_event(event: dict) -> bool:
    lat = event.get("lat", 0)
    lng = event.get("lng", 0)
    if not lat or not lng:
        return False

    print(f"  [{event['region']}] {event['title']}")

    address = event.get("address", "")
    region = event.get("region", "")
    area_code = event.get("area_code", "")
    sigungu_code = event.get("sigungu_code", "")

    # 음식점 수집: 시도/시군구 코드 기반 TourAPI + 카카오
    tour = fetch_tour_restaurants(area_code, sigungu_code, lat, lng)
    kakao = fetch_kakao_restaurants(lat, lng, address=address, region=region)
    candidates = deduplicate(tour, kakao)

    # 부족하면 시군구 코드 없이 시도 전체 + 카카오 반경 5km
    if len(candidates) < 3:
        tour2 = fetch_tour_restaurants(area_code, "", lat, lng)
        kakao2 = fetch_kakao_restaurants(lat, lng, radius=5000, address=address, region=region)
        candidates = deduplicate(tour2, kakao2)

    if len(candidates) < 3:
        print(f"    후보 부족 ({len(candidates)}개) — 스킵")
        return False

    print(f"    후보 {len(candidates)}개 (TourAPI:{len(tour)}, 카카오:{len(kakao)})")

    # Claude 큐레이션
    curation = curate_with_claude(event, candidates)
    candidate_map = {c["id"]: c for c in candidates}

    restaurants = []
    curation_note = ""

    if curation and curation.get("selected"):
        for sel in curation["selected"][:5]:
            c = candidate_map.get(sel.get("source_id", ""))
            if not c:
                continue
            restaurants.append({
                "name": c["name"],
                "category": c["category"],
                "address": c["address"],
                "lat": c["lat"],
                "lng": c["lng"],
                "phone": c.get("phone", ""),
                "image_url": c.get("image_url", ""),
                "distance_meters": c["distance_meters"],
                "distance_minutes": max(1, round(c["distance_meters"] / 80)),
                "recommendation": sel.get("recommendation", ""),
                "best_time": sel.get("best_time", "언제든"),
                "kakao_map_url": c.get("kakao_map_url", ""),
                "source": c["source"],
            })
        curation_note = curation.get("curation_note", "")

    # Claude 실패 시 거리순 fallback
    if not restaurants:
        for c in sorted(candidates, key=lambda x: x["distance_meters"])[:5]:
            restaurants.append({
                "name": c["name"],
                "category": c["category"],
                "address": c["address"],
                "lat": c["lat"],
                "lng": c["lng"],
                "phone": c.get("phone", ""),
                "image_url": c.get("image_url", ""),
                "distance_meters": c["distance_meters"],
                "distance_minutes": max(1, round(c["distance_meters"] / 80)),
                "recommendation": "",
                "best_time": "언제든",
                "kakao_map_url": c.get("kakao_map_url", ""),
                "source": c["source"],
            })

    if not restaurants:
        return False

    # 저장
    RESTAURANTS_DIR.mkdir(parents=True, exist_ok=True)
    out = {
        "festival_id": event["id"],
        "festival_name": event["title"],
        "generated_at": datetime.now(KST).isoformat(),
        "next_refresh_at": (datetime.now(KST) + timedelta(days=CACHE_DAYS)).isoformat(),
        "curation_note": curation_note,
        "restaurants": restaurants,
        "sources": {
            "primary": "한국관광공사 TourAPI",
            "secondary": "카카오 로컬 API (© Kakao)"
        }
    }
    (RESTAURANTS_DIR / f"{event['id']}.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2)
    )
    print(f"    ✓ 저장 완료: {len(restaurants)}개 맛집")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=MAX_PER_RUN,
                        help="한 번에 처리할 최대 축제 수")
    args = parser.parse_args()

    if not EVENTS_PATH.exists():
        print("events.json 없음 — 종료")
        sys.exit(1)

    events = json.loads(EVENTS_PATH.read_text())

    # 좌표 있고 갱신 필요한 행사만 처리
    to_process = [
        e for e in events
        if e.get("lat") and e.get("lng")
        and float(e.get("lat", 0)) != 0
        and float(e.get("lng", 0)) != 0
        and needs_refresh(e["id"])
    ]
    to_process = to_process[:args.limit]

    total = len([e for e in events if e.get("lat") and float(e.get("lat", 0)) != 0])
    print(f"처리 대상: {len(to_process)}개 (좌표 있는 행사 {total}개 중)")

    if not to_process:
        print("갱신 필요 없음")
        return

    success = 0
    for event in to_process:
        ok = process_event(event)
        if ok:
            success += 1
        time.sleep(0.5)

    print(f"\n완료: {success}/{len(to_process)}개 성공")
    print(f"저장 위치: {RESTAURANTS_DIR}")


if __name__ == "__main__":
    main()
