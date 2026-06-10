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


TOUR_API_BASE = "https://apis.data.go.kr/B551011/KorService1"


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
                                             imageYN="Y", subImageYN="Y",
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

@app.route("/")
@login_required
def index():
    events = get_events()
    # D1에서 맛집 있는 event_id 목록
    try:
        rows = d1_rows("SELECT DISTINCT event_id FROM restaurants WHERE is_excluded = 0")
        has_restaurants = {r["event_id"] for r in rows}
    except Exception:
        has_restaurants = set()

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


if __name__ == "__main__":
    app.run(debug=True, port=5001)
