"""
한국문화정보원 문화예술공연 통합 API (CNV_060)
https://api.kcisa.kr/openapi/CNV_060/request
XML 응답 / 총 ~59,000건
"""

import requests
import json
import re
import time
import hashlib
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv
import os

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

API_URL = "https://api.kcisa.kr/openapi/CNV_060/request"

# 지역명 추출용 키워드
REGIONS = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종",
           "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]

SITE_TO_CATEGORY = {
    "연극": "공연", "뮤지컬": "공연", "오페라": "공연",
    "음악": "공연", "콘서트": "공연", "국악": "공연", "무용": "공연",
    "전시": "전시", "미술": "전시", "사진": "전시", "갤러리": "전시",
    "축제": "축제", "페스티벌": "축제",
    "체험": "체험", "교육": "체험", "워크숍": "체험",
}


def _get_api_key():
    return os.environ["CULTURE_API_KEY"]


def detect_category(title: str, site: str) -> str:
    text = title + " " + site
    for keyword, category in SITE_TO_CATEGORY.items():
        if keyword in text:
            return category
    return "문화행사"


def detect_region(site: str) -> str:
    for r in REGIONS:
        if r in site:
            return r
    return "기타"


def parse_date(period_str: str) -> tuple[str, str]:
    """'20260529 ~ 20260607' → ('20260529', '20260607')"""
    if not period_str:
        return "", ""
    parts = period_str.strip().replace("~", " ").split()
    parts = [p.strip().replace("-", "").replace(".", "")[:8] for p in parts if p.strip()]
    if len(parts) >= 2:
        return parts[0], parts[1]
    elif len(parts) == 1:
        return parts[0], parts[0]
    return "", ""


def make_slug(title: str, start: str) -> str:
    """제목+시작일 해시 기반 안정 ID — 수집 순서가 바뀌어도 동일 ID 유지"""
    key = f"{title.strip()}_{start}"
    h = hashlib.md5(key.encode()).hexdigest()[:8]
    en = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip()
    en = re.sub(r'\s+', '-', en).lower()[:25]
    return f"kc-{h}-{en}" if en else f"kc-{h}"


def scrape_fee_from_url(url: str) -> str:
    """공식 URL 페이지에서 요금 정보 추출 (무료 스크래핑, AI 불필요)"""
    if not url:
        return ""
    try:
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return ""
        # HTML 태그 제거 후 텍스트
        text = re.sub(r'<[^>]+>', ' ', resp.text)
        text = re.sub(r'\s+', ' ', text)

        # 요금 관련 키워드 근처 텍스트 추출
        fee_patterns = [
            r'(?:관람료|입장료|이용료|참가비|티켓가격|요금)[^\n。]{0,80}',
            r'(?:무료|유료)\s*[^\n。]{0,60}',
            r'\d[\d,]+\s*원[^\n。]{0,40}',
        ]
        for pattern in fee_patterns:
            m = re.search(pattern, text)
            if m:
                fee = m.group(0).strip()[:100]
                # 의미 있는 내용인지 확인 (너무 짧거나 숫자만 있는 경우 제외)
                if len(fee) > 3:
                    return fee
    except Exception:
        pass
    return ""


def strip_html(text: str) -> str:
    """HTML 태그 및 엔티티 제거"""
    if not text:
        return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
    text = text.replace('&nbsp;', ' ').replace('&laquo;', '«').replace('&raquo;', '»')
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:500]


def fetch_page(start_date: str, end_date: str, page: int) -> tuple[list, int]:
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
            print(f"  HTTP {resp.status_code}")
            return [], 0

        root = ET.fromstring(resp.text)
        result_code = root.findtext(".//resultCode", "")
        if result_code != "0000":
            print(f"  API 오류: {root.findtext('.//resultMsg', '')}")
            return [], 0

        total = int(root.findtext(".//totalCount", "0") or 0)
        items = root.findall(".//item")
        return items, total

    except Exception as e:
        print(f"  페이지 {page} 오류: {e}")
        return [], 0


def fetch_all_events(start_date: str, end_date: str) -> list:
    all_events = []
    today = datetime.now().strftime("%Y%m%d")
    page = 1

    # URL→fee 캐시 (이전 수집 결과 재사용, 중복 스크래핑 방지)
    fee_cache_path = PROJECT_ROOT / "data/raw/culture_fee_cache.json"
    fee_cache: dict = {}
    if fee_cache_path.exists():
        try:
            fee_cache = json.loads(fee_cache_path.read_text())
        except Exception:
            pass
    scraped_count = 0

    while True:
        items, total_count = fetch_page(start_date, end_date, page)
        if not items:
            break

        count = 0
        for item in items:
            title = (item.findtext("title") or "").strip()
            if not title:
                continue

            period = item.findtext("eventPeriod") or item.findtext("period") or ""
            start, end = parse_date(period)
            if not start or not end:
                continue
            if end < today:
                continue

            site = (item.findtext("eventSite") or "").strip()
            region = detect_region(site)
            category = detect_category(title, site)

            charge = (item.findtext("charge") or "").strip()
            url = (item.findtext("url") or "").strip()

            # charge 없으면 공식 URL에서 스크래핑 시도 (무료, AI 불필요)
            # 캐시 우선, 신규는 회당 최대 200건만 (타임아웃 방지)
            if not charge and url:
                if url in fee_cache:
                    charge = fee_cache[url]
                elif scraped_count < 200:
                    charge = scrape_fee_from_url(url)
                    fee_cache[url] = charge
                    scraped_count += 1

            # is_free 판정: 명시적 "무료"만 True, 혼합/미상은 False
            if not charge:
                is_free = False
            elif "유료" in charge and "무료" in charge:
                is_free = False
            elif "무료" in charge or charge in ("0", "0원"):
                is_free = True
            else:
                is_free = False

            description = strip_html(item.findtext("description") or "")
            thumbnail = (item.findtext("imageObject") or "").strip()
            contact = (item.findtext("contactPoint") or "").strip()

            def fmt(d):
                return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d

            slug = make_slug(title, start)

            all_events.append({
                "id": slug,
                "content_id": slug,
                "source": "culture",
                "title": title,
                "category": category,
                "region": region,
                "area_code": "",
                "address": site,
                "lat": 0.0,
                "lng": 0.0,
                "start_date": start,
                "end_date": end,
                "start_date_fmt": fmt(start),
                "end_date_fmt": fmt(end),
                "place": site,
                "fee": charge,
                "is_free": is_free,
                "organizer": "",
                "overview": description,
                "thumbnail": thumbnail,
                "homepage": url,
                "tel": contact,
                "summary": "",
                "highlight": "",
                "target_audience": "",
                "tips": [],
                "seo_title": "",
                "meta_description": "",
                "tags": [],
            })
            count += 1

        print(f"  페이지 {page}: {count}개 (누적 {len(all_events)}/{total_count})")

        if len(all_events) >= total_count or len(items) < 100:
            break

        # 너무 많으면 3,000개까지만 (API 부하 방지)
        if len(all_events) >= 3000:
            print("  3,000개 제한 도달 — 중단")
            break

        page += 1
        time.sleep(0.3)

    # fee 캐시 저장 (다음 실행에서 재사용)
    if scraped_count > 0:
        fee_cache_path.write_text(json.dumps(fee_cache, ensure_ascii=False))
        print(f"URL 요금 스크래핑: {scraped_count}건 신규, 캐시 {len(fee_cache)}건 보유")

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
