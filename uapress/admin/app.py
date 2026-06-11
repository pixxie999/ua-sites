"""
uapress 어드민 — Railway 배포
- 행사별 맛집 수집 (카카오 keyword API)
- Claude 큐레이션
- Cloudflare D1 저장
"""

import json
import math
import os
import re
import time
from datetime import datetime, timedelta, timezone
from functools import wraps

import requests
from flask import Flask, flash, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

KST = timezone(timedelta(hours=9))
GITHUB_EVENTS_URL = (
    "https://raw.githubusercontent.com/pixxie999/ua-sites/main"
    "/uapress/data/processed/events.json"
)

# ─────────────────────────────────────────
# 환경변수 접근
# ─────────────────────────────────────────

def _cf_headers():
    return {
        "Authorization": f"Bearer {os.environ['CF_API_TOKEN']}",
        "Content-Type": "application/json",
    }

def _d1_url():
    acct = os.environ["CF_ACCOUNT_ID"]
    db   = os.environ["D1_DATABASE_ID"]
    return f"https://api.cloudflare.com/client/v4/accounts/{acct}/d1/database/{db}/query"

def _kakao_headers():
    return {"Authorization": f"KakaoAK {os.environ['KAKAO_REST_API_KEY']}"}


# ─────────────────────────────────────────
# D1 헬퍼
# ─────────────────────────────────────────

def d1(sql: str, params: list | None = None) -> dict:
    payload = {"sql": sql}
    if params:
        payload["params"] = params
    r = requests.post(_d1_url(), headers=_cf_headers(), json=payload, timeout=15)
    r.raise_for_status()
    result = r.json()
    if not result.get("success"):
        raise RuntimeError(f"D1 오류: {result.get('errors')}")
    return result

def d1_rows(sql: str, params: list | None = None) -> list:
    result = d1(sql, params)
    return result["result"][0].get("results", [])


# ─────────────────────────────────────────
# 인증
# ─────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == os.environ.get("ADMIN_PASSWORD", "admin"):
            session["logged_in"] = True
            return redirect(url_for("index"))
        flash("비밀번호가 틀렸습니다.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ─────────────────────────────────────────
# 행사 데이터 (GitHub raw)
# ─────────────────────────────────────────

_events_cache = {"data": None, "at": 0}
_has_restaurants_cache = {"data": None, "at": 0}

def get_events() -> list:
    now = time.time()
    if _events_cache["data"] and now - _events_cache["at"] < 300:
        return _events_cache["data"]
    try:
        r = requests.get(GITHUB_EVENTS_URL, timeout=15)
        r.raise_for_status()
        data = r.json()
        _events_cache["data"] = data
        _events_cache["at"] = now
        return data
    except Exception as e:
        return _events_cache["data"] or []


# ─────────────────────────────────────────
# 카카오 검색
# ─────────────────────────────────────────

KAKAO_CATEGORY_URL = "https://dapi.kakao.com/v2/local/search/category.json"
KAKAO_KEYWORD_URL  = "https://dapi.kakao.com/v2/local/search/keyword.json"

def _parse_kakao_docs(docs, lat=0, lng=0):
    result = []
    for item in docs:
        name = item.get("place_name", "").strip()
        if not name:
            continue
        cat_parts = item.get("category_name", "음식점").split(" > ")
        category = cat_parts[-1] if len(cat_parts) > 1 else cat_parts[0]
        ilat = float(item.get("y", 0))
        ilng = float(item.get("x", 0))
        dist = int(item.get("distance", 0) or 0)
        if dist == 0 and lat and lng and ilat and ilng:
            dy = (ilat - lat) * 111000
            dx = (ilng - lng) * 111000 * math.cos(math.radians(lat))
            dist = int(math.sqrt(dx**2 + dy**2))
        result.append({
            "id": f"kakao_{item.get('id', '')}",
            "source": "kakao",
            "name": name,
            "address": item.get("road_address_name") or item.get("address_name", ""),
            "lat": ilat,
            "lng": ilng,
            "category": category,
            "phone": item.get("phone", ""),
            "distance_meters": dist,
            "kakao_map_url": item.get("place_url", f"https://map.kakao.com/?q={name}"),
        })
    return result


def _extract_area(address, region):
    m = re.search(r'([가-힣]+[시군구])', address)
    return m.group(1) if m else region


def _normalize_name(name: str) -> str:
    return re.sub(r'[^가-힣a-zA-Z0-9]', '', name).lower()


TOUR_API_BASE = "https://apis.data.go.kr/B551011/KorService2"


def _tour_params(**extra) -> dict:
    base = {
        "serviceKey": os.environ.get("TOUR_API_KEY", ""),
        "MobileOS": "ETC", "MobileApp": "uapress", "_type": "json",
    }
    base.update(extra)
    return base


def fetch_tour_images(content_id: str, limit: int = 5) -> list:
    """detailImage2 — 음식점 이미지 목록"""
    if not os.environ.get("TOUR_API_KEY"):
        return []
    try:
        r = requests.get(f"{TOUR_API_BASE}/detailImage2",
                         params=_tour_params(contentId=content_id,
                                             imageYN="Y",
                                             numOfRows=str(limit)),
                         timeout=10)
        items = (r.json().get("response", {}).get("body", {})
                 .get("items", {}).get("item", []))
        if isinstance(items, dict):
            items = [items]
        return [{"origin": it.get("originimgurl", ""),
                 "small": it.get("smallimageurl", "")}
                for it in items if it.get("originimgurl")]
    except Exception:
        return []


def fetch_tour_pet_info(content_id: str) -> dict:
    """detailPetTour2 — 반려동물 동반 여행 정보"""
    if not os.environ.get("TOUR_API_KEY"):
        return {}
    try:
        r = requests.get(f"{TOUR_API_BASE}/detailPetTour2",
                         params=_tour_params(contentId=content_id),
                         timeout=10)
        items = (r.json().get("response", {}).get("body", {})
                 .get("items", {}).get("item", []))
        if isinstance(items, dict):
            items = [items]
        if not items:
            return {}
        it = items[0]
        return {
            "pet_allowed": it.get("acmpyTypeCd", ""),
            "pet_info": it.get("relaAcdntRiskMtr", "") or it.get("acmpyPsblCpam", ""),
            "pet_facility": it.get("relaPosesFclty", ""),
            "pet_extra": it.get("etcAcmpyInfo", ""),
        }
    except Exception:
        return {}


def enrich_tour_restaurants(restaurants: list) -> list:
    """TourAPI 음식점에 이미지 + 반려동물 정보 추가"""
    for r in restaurants:
        if r.get("source") != "tourapi":
            continue
        cid = r["id"].replace("tour_", "")
        if not cid:
            continue
        imgs = fetch_tour_images(cid, limit=3)
        if imgs:
            r["thumbnail"] = imgs[0]["origin"]
            r["images"] = imgs
        pet = fetch_tour_pet_info(cid)
        if pet.get("pet_info") or pet.get("pet_facility"):
            r["pet_info"] = pet
        time.sleep(0.15)
    return restaurants


def search_tour_restaurants(area_code: str, sigungu_code: str,
                            lat: float = 0, lng: float = 0) -> list:
    """TourAPI areaBasedList2 — 시도/시군구 코드 기반 음식점"""
    if not area_code:
        return []
    params = _tour_params(contentTypeId="39", areaCode=area_code,
                          numOfRows="30", pageNo="1", arrange="Q")
    if sigungu_code:
        params["sigunguCode"] = sigungu_code
    if not params["serviceKey"]:
        return []
    try:
        r = requests.get(f"{TOUR_API_BASE}/areaBasedList2",
                         params=params, timeout=15)
        data = r.json()
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
                dy = (ilat - lat) * 111000
                dx = (ilng - lng) * 111000 * math.cos(math.radians(lat))
                dist = int(math.sqrt(dx**2 + dy**2))
            result.append({
                "id": f"tour_{item.get('contentid', '')}",
                "source": "tourapi", "name": name,
                "address": item.get("addr1", ""),
                "lat": ilat, "lng": ilng,
                "category": item.get("cat3", "") or "음식점",
                "phone": item.get("tel", ""), "distance_meters": dist,
                "kakao_map_url": f"https://map.kakao.com/?q={name}",
            })
        return result
    except Exception:
        return []


def search_restaurants(area_code, sigungu_code, lat, lng,
                       address="", region="", radius=3000):
    """TourAPI + 카카오 통합 검색"""
    tour = search_tour_restaurants(area_code, sigungu_code, lat, lng)
    kakao = search_kakao(lat, lng, address=address, region=region, radius=radius)
    # 중복 제거 (이름 기준)
    merged = list(tour)
    tour_names = {_normalize_name(r["name"]) for r in tour}
    merged += [r for r in kakao if _normalize_name(r["name"]) not in tour_names]
    # 부족하면 시도 전체로 재시도
    if len(merged) < 5 and sigungu_code:
        tour2 = search_tour_restaurants(area_code, "", lat, lng)
        existing_names = {_normalize_name(r["name"]) for r in merged}
        merged += [r for r in tour2 if _normalize_name(r["name"]) not in existing_names]
    return sorted(merged, key=lambda x: x["distance_meters"])


def search_kakao(lat, lng, address="", region="", radius=3000):
    headers = _kakao_headers()

    # 1차: 좌표 기반 category
    cat = []
    try:
        r = requests.get(KAKAO_CATEGORY_URL, headers=headers, timeout=10, params={
            "category_group_code": "FD6",
            "x": str(lng), "y": str(lat),
            "radius": radius, "sort": "distance", "size": 15,
        })
        cat = _parse_kakao_docs(r.json().get("documents", []), lat, lng)
    except Exception:
        pass

    # 2차: keyword fallback
    kw = []
    if len(cat) < 5:
        try:
            area = _extract_area(address, region)
            r = requests.get(KAKAO_KEYWORD_URL, headers=headers, timeout=10, params={
                "query": f"{area} 음식점",
                "category_group_code": "FD6",
                "x": str(lng), "y": str(lat),
                "radius": max(radius, 5000),
                "sort": "distance", "size": 15,
            })
            kw = _parse_kakao_docs(r.json().get("documents", []), lat, lng)
        except Exception:
            pass

    merged = list(cat)
    cat_ids = {c["id"] for c in cat}
    merged += [k for k in kw if k["id"] not in cat_ids]
    return merged


# ─────────────────────────────────────────
# Claude 큐레이션
# ─────────────────────────────────────────

CURATION_PROMPT = """\
다음 축제 방문객에게 가장 적합한 맛집 TOP 5를 선정하세요.

축제: {name} ({region} / {period})

후보:
{candidates}

주의: 정확하지 않은 영업시간·가격 언급 금지. 추천 사유는 1~2문장으로 간결하게.

JSON만 출력:
{{
  "selected": [
    {{"id": "후보 id", "recommendation": "추천 이유", "best_time": "축제 전 점심|축제 후 저녁|언제든"}}
  ],
  "curation_note": "한 줄 전체 코멘트"
}}"""


def curate(event, candidates):
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        cand_text = json.dumps(
            [{"id": c["id"], "name": c["name"], "category": c["category"],
              "distance_m": c["distance_meters"], "address": c["address"]}
             for c in candidates[:20]],
            ensure_ascii=False, indent=2
        )
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1500,
            messages=[{"role": "user", "content": CURATION_PROMPT.format(
                name=event["title"],
                region=event.get("region", ""),
                period=f"{event.get('start_date_fmt','')} ~ {event.get('end_date_fmt','')}",
                candidates=cand_text,
            )}]
        )
        raw = resp.content[0].text.strip()
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        return json.loads(m.group() if m else raw)
    except Exception as e:
        app.logger.error(f"Claude 오류: {e}")
        return None


# ─────────────────────────────────────────
# 라우트
# ─────────────────────────────────────────

def get_has_restaurants() -> set:
    """맛집 있는 event_id 세트 — 5분 캐시"""
    now = time.time()
    if _has_restaurants_cache["data"] is not None and now - _has_restaurants_cache["at"] < 300:
        return _has_restaurants_cache["data"]
    try:
        rows = d1_rows("SELECT DISTINCT event_id FROM restaurants WHERE is_excluded = 0")
        result = {r["event_id"] for r in rows}
        _has_restaurants_cache["data"] = result
        _has_restaurants_cache["at"] = now
        return result
    except Exception:
        return _has_restaurants_cache["data"] or set()


@app.route("/")
@login_required
def index():
    events = get_events()
    has_restaurants = get_has_restaurants()

    # 좌표 있는 행사만
    items = []
    for e in events:
        lat = float(e.get("lat", 0) or 0)
        lng = float(e.get("lng", 0) or 0)
        items.append({
            **e,
            "has_coord": lat != 0 and lng != 0,
            "has_restaurants": e["id"] in has_restaurants,
        })

    q = request.args.get("q", "").strip()
    if q:
        items = [i for i in items if q in i["title"] or q in i.get("region", "")]

    filter_no_rest = request.args.get("no_rest") == "1"
    if filter_no_rest:
        items = [i for i in items if i["has_coord"] and not i["has_restaurants"]]

    return render_template("index.html", events=items, q=q,
                           filter_no_rest=filter_no_rest,
                           total=len(events), has_coord=sum(1 for i in items if i["has_coord"]),
                           has_rest=len(has_restaurants))


@app.route("/fetch/<event_id>", methods=["GET", "POST"])
@login_required
def fetch_restaurants(event_id):
    events = get_events()
    event = next((e for e in events if e["id"] == event_id), None)
    if not event:
        flash("행사를 찾을 수 없습니다.")
        return redirect(url_for("index"))

    # events_meta에서 좌표/주소 override 확인
    meta_rows = d1_rows("SELECT * FROM events_meta WHERE event_id = ?", [event_id])
    meta = meta_rows[0] if meta_rows else {}
    lat = float(meta.get("lat_override") or event.get("lat", 0) or 0)
    lng = float(meta.get("lng_override") or event.get("lng", 0) or 0)
    search_address = meta.get("address_override") or event.get("address", "")

    if request.method == "POST":
        action = request.form.get("action")

        # 좌표/주소 저장
        if action == "save_meta":
            new_lat = float(request.form.get("lat") or lat or 0)
            new_lng = float(request.form.get("lng") or lng or 0)
            new_addr = request.form.get("address_override", "").strip()
            note = request.form.get("curation_note", "")
            now = datetime.now(KST).isoformat()
            d1("""INSERT INTO events_meta
                    (event_id, lat_override, lng_override, address_override, curation_note, updated_at)
                  VALUES (?, ?, ?, ?, ?, ?)
                  ON CONFLICT(event_id) DO UPDATE SET
                    lat_override=excluded.lat_override,
                    lng_override=excluded.lng_override,
                    address_override=excluded.address_override,
                    curation_note=excluded.curation_note,
                    updated_at=excluded.updated_at""",
               [event_id, new_lat or None, new_lng or None, new_addr or None, note, now])
            flash("저장 완료")
            lat, lng = new_lat, new_lng
            search_address = new_addr or event.get("address", "")

        # 맛집 검색
        elif action == "search":
            if not lat or not lng:
                flash("좌표를 먼저 입력하세요.")
            else:
                area_code = event.get("area_code", "")
                sigungu_code = event.get("sigungu_code", "")
                candidates = search_restaurants(
                    area_code, sigungu_code, lat, lng,
                    address=search_address, region=event.get("region", ""))
                candidates = enrich_tour_restaurants(candidates)
                curation = curate(event, candidates) if candidates else None
                curation_note = curation.get("curation_note", "") if curation else ""
                c_map = {c["id"]: c for c in candidates}

                restaurants = []
                if curation and curation.get("selected"):
                    for sel in curation["selected"][:5]:
                        c = c_map.get(sel.get("id", ""))
                        if not c:
                            continue
                        restaurants.append({**c,
                            "recommendation": sel.get("recommendation", ""),
                            "best_time": sel.get("best_time", "언제든"),
                        })
                if not restaurants:
                    restaurants = sorted(candidates, key=lambda x: x["distance_meters"])[:5]

                return render_template("fetch.html", event=event, lat=lat, lng=lng,
                                       search_address=search_address,
                                       restaurants=restaurants, candidates=candidates,
                                       curation_note=curation_note, meta=meta)

        # 맛집 저장 (선택 항목)
        elif action == "save_restaurants":
            selected_ids = request.form.getlist("selected_ids")
            candidates_json = request.form.get("candidates_json", "[]")
            curation_note = request.form.get("curation_note", "")
            recommendations = json.loads(request.form.get("recommendations_json", "{}"))
            best_times = json.loads(request.form.get("best_times_json", "{}"))
            candidates = json.loads(candidates_json)
            c_map = {c["id"]: c for c in candidates}
            now = datetime.now(KST).isoformat()

            # 기존 맛집 삭제 후 재저장
            d1("DELETE FROM restaurants WHERE event_id = ?", [event_id])
            for cid in selected_ids:
                c = c_map.get(cid)
                if not c:
                    continue
                row_id = f"{event_id}_{cid}"
                thumb = c.get("thumbnail", "")
                imgs_json = json.dumps(c.get("images", []), ensure_ascii=False) if c.get("images") else ""
                pet_json = json.dumps(c.get("pet_info", {}), ensure_ascii=False) if c.get("pet_info") else ""
                d1("""INSERT INTO restaurants
                       (id, event_id, name, category, address, lat, lng, phone,
                        distance_meters, recommendation, best_time, kakao_map_url,
                        source, thumbnail, images, pet_info, is_excluded, created_at)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                      ON CONFLICT(id) DO UPDATE SET
                        recommendation=excluded.recommendation,
                        best_time=excluded.best_time,
                        thumbnail=excluded.thumbnail,
                        images=excluded.images,
                        pet_info=excluded.pet_info,
                        is_excluded=0""",
                   [row_id, event_id, c["name"], c["category"], c["address"],
                    c["lat"], c["lng"], c.get("phone", ""),
                    c["distance_meters"],
                    recommendations.get(cid, c.get("recommendation", "")),
                    best_times.get(cid, c.get("best_time", "언제든")),
                    c.get("kakao_map_url", ""), c["source"],
                    thumb, imgs_json, pet_json, now])

            # curation_note 저장
            if curation_note:
                d1("""INSERT INTO events_meta (event_id, curation_note, updated_at)
                      VALUES (?, ?, ?)
                      ON CONFLICT(event_id) DO UPDATE SET
                        curation_note=excluded.curation_note,
                        updated_at=excluded.updated_at""",
                   [event_id, curation_note, now])

            flash(f"맛집 {len(selected_ids)}개 저장 완료")
            return redirect(url_for("restaurants_view", event_id=event_id))

    return render_template("fetch.html", event=event, lat=lat, lng=lng,
                           search_address=search_address,
                           restaurants=None, candidates=None, meta=meta)


TOUR_API_ENDPOINTS = {
    "searchFestival2": {
        "label": "축제 목록 조회",
        "params": lambda cid, e: {"eventStartDate": e.get("start_date",""), "eventEndDate": e.get("end_date","")},
    },
    "detailCommon2": {
        "label": "공통 상세 정보",
        "params": lambda cid, e: {"contentId": cid, "contentTypeId": "15",
                                   "defaultYN": "Y", "overviewYN": "Y", "addrinfoYN": "Y"},
    },
    "detailIntro2": {
        "label": "소개 정보 (관람료·공연시간)",
        "params": lambda cid, e: {"contentId": cid, "contentTypeId": "15"},
    },
    "detailImage2": {
        "label": "이미지 목록",
        "params": lambda cid, e: {"contentId": cid, "imageYN": "Y", "numOfRows": "10"},
    },
    "detailPetTour2": {
        "label": "반려동물 동반 정보",
        "params": lambda cid, e: {"contentId": cid},
    },
    "areaBasedList2": {
        "label": "지역 기반 목록 (음식점)",
        "params": lambda cid, e: {"areaCode": e.get("area_code",""), "sigunguCode": e.get("sigungu_code",""),
                                   "contentTypeId": "39", "numOfRows": "20", "arrange": "Q"},
    },
}


@app.route("/event/<event_id>")
@login_required
def event_detail(event_id):
    events = get_events()
    event = next((e for e in events if e["id"] == event_id), None)
    if not event:
        flash("행사를 찾을 수 없습니다.")
        return redirect(url_for("index"))

    # 선택된 엔드포인트 호출
    endpoint = request.args.get("endpoint", "")
    api_result = None
    api_error = None
    api_url = None

    if endpoint and endpoint in TOUR_API_ENDPOINTS:
        ep = TOUR_API_ENDPOINTS[endpoint]
        cid = event.get("content_id", "")
        base_params = {
            "serviceKey": os.environ.get("TOUR_API_KEY", ""),
            "MobileOS": "ETC", "MobileApp": "uapress", "_type": "json",
            "numOfRows": "100", "pageNo": "1",
        }
        base_params.update(ep["params"](cid, event))
        api_url = f"https://apis.data.go.kr/B551011/KorService2/{endpoint}"
        try:
            r = requests.get(api_url, params=base_params, timeout=15)
            api_result = json.dumps(r.json(), ensure_ascii=False, indent=2)
        except Exception as e:
            api_error = str(e)

    endpoints_list = [
        {"key": k, "label": v["label"]} for k, v in TOUR_API_ENDPOINTS.items()
    ]

    return render_template("event_detail.html",
                           event=event,
                           endpoints=endpoints_list,
                           selected_endpoint=endpoint,
                           api_url=api_url,
                           api_result=api_result,
                           api_error=api_error)


@app.route("/restaurants/<event_id>")
@login_required
def restaurants_view(event_id):
    events = get_events()
    event = next((e for e in events if e["id"] == event_id), None)
    rows = d1_rows(
        "SELECT * FROM restaurants WHERE event_id = ? ORDER BY distance_meters",
        [event_id]
    )
    meta_rows = d1_rows("SELECT * FROM events_meta WHERE event_id = ?", [event_id])
    meta = meta_rows[0] if meta_rows else {}
    return render_template("restaurants.html", event=event, restaurants=rows, meta=meta)


@app.route("/restaurants/<event_id>/toggle/<row_id>", methods=["POST"])
@login_required
def toggle_restaurant(event_id, row_id):
    rows = d1_rows("SELECT is_excluded FROM restaurants WHERE id = ?", [row_id])
    if rows:
        new_val = 0 if rows[0]["is_excluded"] else 1
        d1("UPDATE restaurants SET is_excluded = ? WHERE id = ?", [new_val, row_id])
    return redirect(url_for("restaurants_view", event_id=event_id))


@app.route("/restaurants/<event_id>/delete", methods=["POST"])
@login_required
def delete_restaurants(event_id):
    d1("DELETE FROM restaurants WHERE event_id = ?", [event_id])
    flash("맛집 데이터 삭제 완료")
    return redirect(url_for("fetch_restaurants", event_id=event_id))


# ─────────────────────────────────────────
# 큐레이션
# ─────────────────────────────────────────

def _make_curation_id() -> str:
    import uuid
    return uuid.uuid4().hex[:12]


def _slugify(text: str) -> str:
    """제목에서 URL 슬러그 생성"""
    slug = re.sub(r'[^a-zA-Z0-9가-힣\s-]', '', text).strip()
    slug = re.sub(r'\s+', '-', slug)
    return slug[:60] or "curation"


def _get_font(size: int = 36):
    """한국어 폰트 로드 (없으면 기본 폰트)"""
    from PIL import ImageFont
    font_path = Path("/tmp/NotoSansKR-Bold.ttf")
    if not font_path.exists():
        try:
            url = ("https://github.com/googlefonts/noto-fonts/raw/main/"
                   "hinted/ttf/NotoSansKR/NotoSansKR-Bold.ttf")
            r = requests.get(url, timeout=20)
            font_path.write_bytes(r.content)
        except Exception:
            return ImageFont.load_default()
    try:
        return ImageFont.truetype(str(font_path), size)
    except Exception:
        return ImageFont.load_default()


def generate_card_image(title: str, events: list, intro: str = "") -> bytes:
    """카드뉴스 이미지 생성 (1080×1080)"""
    from PIL import Image, ImageDraw

    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), "#1e3a5f")
    draw = ImageDraw.Draw(img)

    # 그라디언트 효과 (세로줄)
    for y in range(H):
        ratio = y / H
        r = int(30 + ratio * 20)
        g = int(58 + ratio * 10)
        b = int(95 + ratio * 40)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # 브랜딩 영역 상단
    draw.rectangle([0, 0, W, 90], fill="#0f2340")
    font_brand = _get_font(32)
    draw.text((40, 28), "🎪 이번주 행사 | uapress.kr", font=font_brand, fill="#93c5fd")

    # 제목
    font_title = _get_font(56)
    # 긴 제목 줄바꿈 처리
    words = list(title)
    lines, cur = [], ""
    for ch in title:
        if len(cur) >= 16:
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    title_lines = lines[:3]

    y_title = 130
    for line in title_lines:
        draw.text((60, y_title), line, font=font_title, fill="white")
        y_title += 70

    # 구분선
    draw.rectangle([60, y_title + 10, W - 60, y_title + 13], fill="#3b82f6")
    y_cur = y_title + 40

    # 행사 목록
    font_ev = _get_font(38)
    font_small = _get_font(28)
    markers = ["① ", "② ", "③ ", "④ ", "⑤ "]
    for i, ev in enumerate(events[:5]):
        marker = markers[i] if i < len(markers) else f"{i+1}. "
        region = f"[{ev.get('region', '')}] " if ev.get('region') else ""
        ev_title = ev.get('title', '')
        # 제목이 너무 길면 자름
        display = region + ev_title
        if len(display) > 20:
            display = display[:19] + "…"
        draw.text((60, y_cur), marker + display, font=font_ev, fill="#e2e8f0")
        # 날짜
        dates = f"{ev.get('start_date_fmt','')[:10]}"
        draw.text((80, y_cur + 46), dates, font=font_small, fill="#94a3b8")
        y_cur += 105

    # 하단 바
    draw.rectangle([0, H - 80, W, H], fill="#0f2340")
    font_url = _get_font(30)
    draw.text((40, H - 56), "👉 uapress.kr 에서 자세히 보기", font=font_url, fill="#60a5fa")

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def send_telegram(title: str, intro: str, events: list, url: str, image_bytes: bytes | None = None) -> bool:
    """텔레그램 채널/그룹 발행"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat_id:
        app.logger.warning("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID 미설정")
        return False

    lines = [f"🎪 *{title}*\n"]
    if intro:
        lines.append(f"{intro[:200]}\n")
    for i, ev in enumerate(events[:5], 1):
        region = f"[{ev.get('region','')}] " if ev.get('region') else ""
        ev_title = ev.get('title', '')
        date_str = f" ({ev.get('start_date_fmt','')[:10]}~{ev.get('end_date_fmt','')[5:10]})"
        lines.append(f"{i}\\. {region}{ev_title}{date_str}")
    lines.append(f"\n👉 {url}")
    text = "\n".join(lines)

    try:
        if image_bytes:
            import io
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendPhoto",
                data={"chat_id": chat_id, "caption": text, "parse_mode": "MarkdownV2"},
                files={"photo": ("card.png", io.BytesIO(image_bytes), "image/png")},
                timeout=20,
            )
        else:
            resp = requests.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"},
                timeout=10,
            )
        resp.raise_for_status()
        return True
    except Exception as e:
        app.logger.error(f"텔레그램 발송 실패: {e}")
        return False


def trigger_github_deploy() -> bool:
    """GitHub Actions deploy_uapress.yml 워크플로우 트리거"""
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return False
    try:
        resp = requests.post(
            "https://api.github.com/repos/pixxie999/ua-sites/actions/workflows/deploy_uapress.yml/dispatches",
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
            json={"ref": "main", "inputs": {"mode": "build_only"}},
            timeout=10,
        )
        return resp.status_code == 204
    except Exception as e:
        app.logger.error(f"GitHub 트리거 실패: {e}")
        return False


@app.route("/curations/")
@login_required
def curation_list():
    curations = d1_rows("SELECT * FROM curations ORDER BY created_at DESC")
    return render_template("curations.html", curations=curations)


@app.route("/curations/new", methods=["GET", "POST"])
@login_required
def curation_new():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        if not title:
            flash("제목을 입력하세요.")
            return redirect(url_for("curation_new"))
        cid = _make_curation_id()
        slug = _slugify(title) + "-" + cid[:6]
        now = datetime.now(KST).isoformat()
        d1("""INSERT INTO curations (id, slug, title, intro, status, created_at)
               VALUES (?, ?, ?, '', 'draft', ?)""",
           [cid, slug, title, now])
        return redirect(url_for("curation_edit", curation_id=cid))
    return render_template("curation_edit.html", curation=None, events=[], all_events=[])


@app.route("/curations/<curation_id>/edit", methods=["GET", "POST"])
@login_required
def curation_edit(curation_id):
    rows = d1_rows("SELECT * FROM curations WHERE id = ?", [curation_id])
    if not rows:
        flash("큐레이션을 찾을 수 없습니다.")
        return redirect(url_for("curation_list"))
    curation = rows[0]

    if request.method == "POST":
        action = request.form.get("action")

        if action == "save_meta":
            title = request.form.get("title", "").strip()
            intro = request.form.get("intro", "").strip()
            now = datetime.now(KST).isoformat()
            d1("UPDATE curations SET title=?, intro=?, updated_at=? WHERE id=?",
               [title, intro, now, curation_id])
            flash("저장 완료")
            return redirect(url_for("curation_edit", curation_id=curation_id))

        elif action == "add_event":
            event_id = request.form.get("event_id", "")
            note = request.form.get("note", "")
            existing = d1_rows("SELECT COUNT(*) as cnt FROM curation_events WHERE curation_id=? AND event_id=?",
                               [curation_id, event_id])
            if existing and existing[0]["cnt"] == 0:
                order_num = len(d1_rows("SELECT id FROM curation_events WHERE curation_id=?", [curation_id]))
                d1("INSERT INTO curation_events (curation_id, event_id, order_num, note) VALUES (?,?,?,?)",
                   [curation_id, event_id, order_num, note])
            return redirect(url_for("curation_edit", curation_id=curation_id))

        elif action == "remove_event":
            event_id = request.form.get("event_id", "")
            d1("DELETE FROM curation_events WHERE curation_id=? AND event_id=?",
               [curation_id, event_id])
            return redirect(url_for("curation_edit", curation_id=curation_id))

        elif action == "reorder":
            order_json = request.form.get("order_json", "[]")
            try:
                ordered_ids = json.loads(order_json)
                for i, eid in enumerate(ordered_ids):
                    d1("UPDATE curation_events SET order_num=? WHERE curation_id=? AND event_id=?",
                       [i, curation_id, eid])
            except Exception:
                pass
            return redirect(url_for("curation_edit", curation_id=curation_id))

    # 큐레이션에 포함된 행사
    ce_rows = d1_rows(
        "SELECT * FROM curation_events WHERE curation_id=? ORDER BY order_num",
        [curation_id]
    )
    all_events_raw = get_events()
    event_map = {e["id"]: e for e in all_events_raw}
    selected_ids = {r["event_id"] for r in ce_rows}
    selected_events = []
    for r in ce_rows:
        ev = event_map.get(r["event_id"])
        if ev:
            selected_events.append({**ev, "note": r.get("note", ""), "ce_id": r.get("id")})

    # 검색 필터
    q = request.args.get("q", "").strip()
    filtered = [e for e in all_events_raw if e["id"] not in selected_ids]
    if q:
        filtered = [e for e in filtered if q in e["title"] or q in e.get("region", "")]
    else:
        filtered = filtered[:30]

    return render_template("curation_edit.html",
                           curation=curation,
                           selected_events=selected_events,
                           all_events=filtered,
                           q=q)


@app.route("/curations/<curation_id>/publish", methods=["POST"])
@login_required
def curation_publish(curation_id):
    rows = d1_rows("SELECT * FROM curations WHERE id = ?", [curation_id])
    if not rows:
        flash("큐레이션을 찾을 수 없습니다.")
        return redirect(url_for("curation_list"))
    curation = rows[0]

    ce_rows = d1_rows(
        "SELECT * FROM curation_events WHERE curation_id=? ORDER BY order_num",
        [curation_id]
    )
    all_events_raw = get_events()
    event_map = {e["id"]: e for e in all_events_raw}
    events = [event_map[r["event_id"]] for r in ce_rows if r["event_id"] in event_map]

    if not events:
        flash("행사를 먼저 추가하세요.")
        return redirect(url_for("curation_edit", curation_id=curation_id))

    # 카드뉴스 이미지 생성
    image_bytes = None
    try:
        image_bytes = generate_card_image(curation["title"], events, curation.get("intro", ""))
    except Exception as e:
        app.logger.error(f"카드뉴스 생성 실패: {e}")

    # 텔레그램 발행
    url = f"https://uapress.kr/curation/{curation['slug']}/"
    tg_ok = send_telegram(curation["title"], curation.get("intro", ""), events, url, image_bytes)

    # D1 status 업데이트
    now = datetime.now(KST).isoformat()
    d1("UPDATE curations SET status='published', published_at=? WHERE id=?",
       [now, curation_id])

    # GitHub Actions 배포 트리거
    deploy_ok = trigger_github_deploy()

    msg_parts = ["발행 완료"]
    if tg_ok:
        msg_parts.append("텔레그램 전송 ✓")
    else:
        msg_parts.append("텔레그램 전송 실패 (환경변수 확인)")
    if deploy_ok:
        msg_parts.append("배포 트리거 ✓")
    flash(" · ".join(msg_parts))
    return redirect(url_for("curation_list"))


@app.route("/curations/<curation_id>/unpublish", methods=["POST"])
@login_required
def curation_unpublish(curation_id):
    d1("UPDATE curations SET status='draft', published_at=NULL WHERE id=?", [curation_id])
    flash("발행 취소 (초안으로 변경)")
    return redirect(url_for("curation_list"))


@app.route("/curations/<curation_id>/delete", methods=["POST"])
@login_required
def curation_delete(curation_id):
    d1("DELETE FROM curation_events WHERE curation_id=?", [curation_id])
    d1("DELETE FROM curations WHERE id=?", [curation_id])
    flash("삭제 완료")
    return redirect(url_for("curation_list"))


if __name__ == "__main__":
    app.run(debug=True, port=5001)
