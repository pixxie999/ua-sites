"""
Jinja2 → 정적 HTML 빌드
"""

import json
import shutil
import os
import sys
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

# scripts/ 디렉터리에서 실행될 때 프로젝트 루트를 기준으로 경로 잡기
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SITE_DOMAIN = os.getenv("SITE_DOMAIN", "https://uapress.kr")
SITE_NAME = os.getenv("SITE_NAME", "이번주 행사")
ADSENSE_PUBLISHER_ID = os.getenv("ADSENSE_PUBLISHER_ID", "")
ADSENSE_UNIT_BANNER = os.getenv("ADSENSE_UNIT_BANNER", "")
ADSENSE_UNIT_RECTANGLE = os.getenv("ADSENSE_UNIT_RECTANGLE", "")
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID", "")

DIST = PROJECT_ROOT / "dist"
BUILD_DATE = datetime.now().strftime("%Y-%m-%d")

REGION_SLUGS = {
    "서울": "seoul", "인천": "incheon", "대전": "daejeon",
    "대구": "daegu", "광주": "gwangju", "부산": "busan",
    "울산": "ulsan", "세종": "sejong", "경기": "gyeonggi",
    "강원": "gangwon", "충북": "chungbuk", "충남": "chungnam",
    "경북": "gyeongbuk", "경남": "gyeongnam", "전북": "jeonbuk",
    "전남": "jeonnam", "제주": "jeju"
}

CATEGORY_SLUGS = {
    "축제": "festival", "공연": "performance",
    "전시": "exhibition", "체험": "experience",
    "스포츠": "sports", "문화행사": "culture"
}


def load_data():
    base = PROJECT_ROOT / "data" / "processed"
    events = json.loads((base / "events.json").read_text())
    by_region = json.loads((base / "events_by_region.json").read_text())
    by_month = json.loads((base / "events_by_month.json").read_text())
    free_events = json.loads((base / "free_events.json").read_text())

    weekly_files = sorted(
        (PROJECT_ROOT / "data" / "content" / "weekly_picks").glob("*.json"),
        reverse=True
    )
    weekly_pick = json.loads(weekly_files[0].read_text()) if weekly_files else {}

    return events, by_region, by_month, free_events, weekly_pick


def setup_env():
    env = Environment(
        loader=FileSystemLoader(str(PROJECT_ROOT / "templates")),
        autoescape=True
    )
    env.globals.update({
        "site_domain": SITE_DOMAIN,
        "site_name": SITE_NAME,
        "build_date": BUILD_DATE,
        "adsense_publisher_id": ADSENSE_PUBLISHER_ID,
        "adsense_unit_banner": ADSENSE_UNIT_BANNER,
        "adsense_unit_rectangle": ADSENSE_UNIT_RECTANGLE,
        "ga_measurement_id": GA_MEASUREMENT_ID,
        "region_slugs": REGION_SLUGS,
        "category_slugs": CATEGORY_SLUGS,
        "now_year": datetime.now().year,
    })
    return env


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_all():
    print("빌드 시작...")

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    static = PROJECT_ROOT / "static"
    if static.exists():
        shutil.copytree(str(static), str(DIST / "static"))

    # 루트 배치 파일 (인증 파일 등) — static/root/ → dist/ 루트로 복사
    root_files = PROJECT_ROOT / "static" / "root"
    if root_files.exists():
        for f in root_files.iterdir():
            shutil.copy(str(f), str(DIST / f.name))

    events, by_region, by_month, free_events, weekly_pick = load_data()
    env = setup_env()

    today = datetime.now().strftime("%Y%m%d")
    active = [e for e in events if e["end_date"] >= today]

    # 1. 메인
    tmpl = env.get_template("index.html")
    # Tour API(썸네일·상세정보 있음) 우선, 이후 문화부 보완 — 최대 120개
    tour_active = [e for e in active if e.get("source") != "culture"]
    culture_active = [e for e in active if e.get("source") == "culture"]
    this_week_events = (
        sorted(tour_active, key=lambda x: x["start_date"])[:80]
        + sorted(culture_active, key=lambda x: x["start_date"])[:40]
    )
    write(DIST / "index.html", tmpl.render(
        events=this_week_events,
        free_count=len(free_events),
        weekly_pick=weekly_pick,
        page_url="/"
    ))
    print("  메인 생성")

    # 2. 행사 상세
    tmpl = env.get_template("event.html")
    for e in active:
        path = DIST / "event" / e["id"] / "index.html"
        write(path, tmpl.render(event=e, page_url=f"/event/{e['id']}/"))
    print(f"  행사 상세: {len(active)}개")

    # 3. 지역별
    tmpl = env.get_template("region.html")
    for region, slug in REGION_SLUGS.items():
        region_events = [e for e in active if e["region"] == region]
        if not region_events:
            continue
        path = DIST / "region" / slug / "index.html"
        write(path, tmpl.render(
            region=region, slug=slug,
            events=region_events,
            page_url=f"/region/{slug}/"
        ))
    print(f"  지역별: {len(REGION_SLUGS)}개")

    # 4. 월별
    tmpl = env.get_template("monthly.html")
    for month_key, month_events in by_month.items():
        year = month_key[:4]
        month = month_key[4:6]
        active_month = [e for e in month_events if e["end_date"] >= today]
        if not active_month:
            continue
        path = DIST / year / month / "index.html"
        write(path, tmpl.render(
            year=year, month=month,
            events=active_month,
            page_url=f"/{year}/{month}/"
        ))
    print(f"  월별: {len(by_month)}개")

    # 5. 카테고리별
    tmpl = env.get_template("category.html")
    for category, slug in CATEGORY_SLUGS.items():
        cat_events = [e for e in active if e["category"] == category]
        if not cat_events:
            continue
        path = DIST / "category" / slug / "index.html"
        write(path, tmpl.render(
            category=category, slug=slug,
            events=cat_events,
            page_url=f"/category/{slug}/"
        ))
    print(f"  카테고리: {len(CATEGORY_SLUGS)}개")

    # 6. 무료 행사
    tmpl = env.get_template("free.html")
    write(DIST / "free" / "index.html", tmpl.render(
        events=free_events,
        page_url="/free/"
    ))
    print(f"  무료 행사: {len(free_events)}개")

    # 7. 주간 큐레이션
    if weekly_pick:
        tmpl = env.get_template("weekly_pick.html")
        week_str = datetime.now().strftime("%Y-W%V")
        path = DIST / "weekly" / week_str / "index.html"
        write(path, tmpl.render(
            pick=weekly_pick,
            week=week_str,
            page_url=f"/weekly/{week_str}/"
        ))
        print(f"  주간 큐레이션: {week_str}")

    # 8. 검색 인덱스
    idx_src = Path("dist/search-index.json")
    idx_dst = DIST / "search-index.json"
    if idx_src.exists() and not idx_dst.exists():
        shutil.copy(str(idx_src), str(idx_dst))
    elif not idx_dst.exists():
        # build_search_index를 직접 호출
        sys.path.insert(0, str(SCRIPT_DIR))
        import build_search_index
        build_search_index.build_index()

    # 9. sitemap.xml
    build_sitemap(active)

    # 10. robots.txt
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_DOMAIN}/sitemap.xml\n"
    )

    # 11. ads.txt (Google AdSense 필수)
    # ADSENSE_PUBLISHER_ID는 ca-pub-XXX 형식 — ads.txt는 pub-XXX 형식 필요
    if ADSENSE_PUBLISHER_ID:
        pub_id = ADSENSE_PUBLISHER_ID.replace("ca-", "", 1)
        (DIST / "ads.txt").write_text(
            f"google.com, {pub_id}, DIRECT, f08c47fec0942fa0\n"
        )
        print(f"  ads.txt: {pub_id}")

    # 11. 개인정보처리방침
    tmpl = env.get_template("privacy.html")
    write(DIST / "privacy-policy" / "index.html", tmpl.render(page_url="/privacy-policy/"))

    total = sum(1 for _ in DIST.rglob("*.html"))
    print(f"\n빌드 완료: {total}개 HTML 페이지")


def build_sitemap(events: list):
    urls = [
        {"loc": "/", "priority": "1.0", "changefreq": "daily"},
        {"loc": "/free/", "priority": "0.9", "changefreq": "daily"},
    ]

    for region_slug in REGION_SLUGS.values():
        urls.append({"loc": f"/region/{region_slug}/", "priority": "0.8", "changefreq": "weekly"})

    for category_slug in CATEGORY_SLUGS.values():
        urls.append({"loc": f"/category/{category_slug}/", "priority": "0.8", "changefreq": "weekly"})

    for e in events:
        urls.append({"loc": f"/event/{e['id']}/", "priority": "0.7", "changefreq": "weekly"})

    sitemap_lines = ['<?xml version="1.0" encoding="UTF-8"?>']
    sitemap_lines.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for u in urls:
        sitemap_lines.append(f"""  <url>
    <loc>{SITE_DOMAIN}{u['loc']}</loc>
    <lastmod>{BUILD_DATE}</lastmod>
    <changefreq>{u['changefreq']}</changefreq>
    <priority>{u['priority']}</priority>
  </url>""")
    sitemap_lines.append("</urlset>")

    (DIST / "sitemap.xml").write_text("\n".join(sitemap_lines))
    print(f"  sitemap.xml: {len(urls)}개 URL")


if __name__ == "__main__":
    build_all()
