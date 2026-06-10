"""
원본 행사 데이터 정제·분류·슬러그 생성
"""

import json
import re
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent


def make_slug(content_id: str, title: str) -> str:
    en = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip()
    en = re.sub(r'\s+', '-', en).lower()[:40]
    return f"{content_id}-{en}" if en else content_id


def detect_category(title: str, overview: str) -> str:
    text = title + " " + overview

    rules = {
        "축제": ["축제", "페스티벌", "festival", "잔치", "한마당"],
        "공연": ["공연", "콘서트", "뮤지컬", "연극", "오페라", "국악", "클래식"],
        "전시": ["전시", "박람회", "엑스포", "아트페어", "갤러리"],
        "체험": ["체험", "만들기", "클래스", "워크숍", "교육"],
        "스포츠": ["마라톤", "달리기", "자전거", "스포츠", "경기", "대회"],
        "문화행사": [],
    }

    for category, keywords in rules.items():
        if any(kw in text for kw in keywords):
            return category
    return "문화행사"


def is_free(fee: str, title: str) -> bool:
    if not fee:
        return False
    # "무료"와 "유료"가 함께 있으면 부분유료 → 유료로 처리
    has_free = "무료" in fee or "free" in fee.lower() or fee.strip() in ("0", "0원", "없음")
    has_paid = "유료" in fee or ("원" in fee and any(c.isdigit() for c in fee) and fee.strip() != "0원") or "₩" in fee
    if has_free and has_paid:
        return False   # "무료(일부 유료)", "유료(장애인 무료)" 등
    if has_free:
        return True
    if has_paid:
        return False
    return False


def process_events(raw_path: str) -> list:
    raw = json.loads(Path(raw_path).read_text())
    today = datetime.now().strftime("%Y%m%d")

    # 기존 AI 데이터 로드 (seo_title 등 보존용)
    existing_path = PROJECT_ROOT / "data/processed/events.json"
    existing_map = {}
    if existing_path.exists():
        try:
            existing = json.loads(existing_path.read_text())
            existing_map = {e["id"]: e for e in existing}
            print(f"  기존 데이터 로드: {len(existing_map)}개")
        except Exception:
            pass

    # 아카이브 로드 (과거 행사 누적)
    archive_path = PROJECT_ROOT / "data/processed/events_archive.json"
    archive_map = {}
    if archive_path.exists():
        try:
            archive = json.loads(archive_path.read_text())
            archive_map = {e["id"]: e for e in archive}
        except Exception:
            pass

    processed = []

    for item in raw:
        if not item.get("title"):
            continue

        slug = make_slug(item["content_id"], item["title"])
        category = detect_category(item["title"], item.get("overview", ""))
        free = is_free(item.get("fee", ""), item["title"])

        def fmt(d):
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d

        # 기존 AI 데이터 보존 (seo_title 있으면 그대로 유지)
        existing = existing_map.get(slug, {})

        processed.append({
            "id": slug,
            "content_id": item["content_id"],
            "title": item["title"],
            "category": category,
            "region": item["region"],
            "area_code": item["area_code"],
            "sigungu_code": item.get("sigungu_code", ""),
            "address": item["address"],
            "lat": item["lat"],
            "lng": item["lng"],
            "start_date": item["start_date"],
            "end_date": item["end_date"],
            "start_date_fmt": fmt(item["start_date"]),
            "end_date_fmt": fmt(item["end_date"]),
            "place": item.get("place", ""),
            "fee": item.get("fee", ""),
            "is_free": free,
            "organizer": item.get("organizer", ""),
            "overview": item.get("overview", "")[:500],
            "thumbnail": item.get("thumbnail", ""),
            "homepage": item.get("homepage", ""),
            "tel": item.get("tel", ""),
            "images": item.get("images") or existing.get("images") or (
                [{"origin": item["thumbnail"], "small": item.get("thumbnail_small", item["thumbnail"])}]
                if item.get("thumbnail") else []
            ),
            # AI 생성 필드 — 기존 값 보존, 없으면 빈값
            "seo_slug": existing.get("seo_slug", ""),
            "summary": existing.get("summary", ""),
            "highlight": existing.get("highlight", ""),
            "target_audience": existing.get("target_audience", ""),
            "tips": existing.get("tips", []),
            "seo_title": existing.get("seo_title", ""),
            "meta_description": existing.get("meta_description", ""),
            "tags": existing.get("tags", []),
        })

    # 활성 / 종료 분리
    active = [e for e in processed if e["end_date"] >= today]
    ended = [e for e in processed if e["end_date"] < today]

    # 아카이브 업데이트: 기존 + 새로 종료된 행사 병합 (AI 캐시 보존)
    for e in ended:
        eid = e["id"]
        if eid not in archive_map:
            archive_map[eid] = e
        else:
            # AI 필드는 기존 아카이브 값 우선 보존
            for field in ("seo_slug", "seo_title", "meta_description", "summary", "highlight",
                          "target_audience", "tips", "tags"):
                if archive_map[eid].get(field):
                    e[field] = archive_map[eid][field]
            archive_map[eid] = e

    by_region = {}
    by_month = {}
    for e in active:
        by_region.setdefault(e["region"], []).append(e)
        by_month.setdefault(e["start_date"][:6], []).append(e)

    out = PROJECT_ROOT / "data/processed"
    out.mkdir(parents=True, exist_ok=True)

    # 활성 행사만 events.json (AI 생성·빌드 대상)
    (out / "events.json").write_text(
        json.dumps(active, ensure_ascii=False, indent=2))
    (out / "events_by_region.json").write_text(
        json.dumps(by_region, ensure_ascii=False, indent=2))
    (out / "events_by_month.json").write_text(
        json.dumps(by_month, ensure_ascii=False, indent=2))
    (out / "free_events.json").write_text(
        json.dumps([e for e in active if e["is_free"]], ensure_ascii=False, indent=2))

    # 아카이브 저장 (누적)
    archive_list = sorted(archive_map.values(), key=lambda x: x["end_date"], reverse=True)
    (out / "events_archive.json").write_text(
        json.dumps(archive_list, ensure_ascii=False, indent=2))

    print(f"정제 완료: 활성 {len(active)}개 (무료: {sum(1 for e in active if e['is_free'])}개), "
          f"아카이브 {len(archive_list)}개")
    return active


if __name__ == "__main__":
    import glob
    tour_files = sorted(glob.glob(str(PROJECT_ROOT / "data/raw/events_*.json")), reverse=True)

    if not tour_files:
        print("Tour raw 데이터 없음. fetch_tour.py 먼저 실행하세요.")
    else:
        process_events(tour_files[0])
