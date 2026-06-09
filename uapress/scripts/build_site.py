"""
Jinja2 → 정적 HTML 빌드
"""

import json
import shutil
import os
import sys
import calendar as cal_module
from pathlib import Path
from datetime import datetime, date
from jinja2 import Environment, FileSystemLoader

# scripts/ 디렉터리에서 실행될 때 프로젝트 루트를 기준으로 경로 잡기
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

SITE_DOMAIN = os.getenv("SITE_DOMAIN", "https://uapress.kr")
SITE_NAME = os.getenv("SITE_NAME", "전국축제정보")
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

# 시즌 정의
SEASONS = [
    {
        "slug": "spring", "name": "봄", "emoji": "🌸",
        "months": [3, 4, 5], "months_str": "3~5월",
        "color_from": "#f9a8d4", "color_to": "#86efac",
        "desc": "봄꽃이 피어나는 3~5월은 전국 축제 시즌의 시작입니다. 벚꽃 축제, 봄나들이 행사, 야외 공연 등 다양한 행사가 열립니다. 따뜻한 날씨에 가족·연인과 함께하기 좋은 시기입니다.",
    },
    {
        "slug": "summer", "name": "여름", "emoji": "🌊",
        "months": [6, 7, 8], "months_str": "6~8월",
        "color_from": "#38bdf8", "color_to": "#4ade80",
        "desc": "무더운 여름 6~8월에는 물 축제, 해변 행사, 야외 음악 페스티벌이 풍성합니다. 시원한 물놀이 행사와 야간 축제를 즐기기 좋은 계절입니다.",
    },
    {
        "slug": "autumn", "name": "가을", "emoji": "🍂",
        "months": [9, 10, 11], "months_str": "9~11월",
        "color_from": "#fb923c", "color_to": "#facc15",
        "desc": "단풍이 물드는 9~11월은 한 해 중 가장 많은 축제가 열리는 시즌입니다. 지역 특산물 축제, 단풍 나들이, 문화 공연 등 볼거리가 가득합니다.",
    },
    {
        "slug": "winter", "name": "겨울", "emoji": "❄️",
        "months": [12, 1, 2], "months_str": "12~2월",
        "color_from": "#818cf8", "color_to": "#67e8f9",
        "desc": "눈꽃 축제와 빙판 행사가 열리는 12~2월 겨울 시즌입니다. 크리스마스 마켓, 겨울 빛 축제, 설 관련 문화 행사 등 실내외 다양한 프로그램을 즐길 수 있습니다.",
    },
]

# 지역별 소개 정보
REGION_INFO = {
    "서울": {"emoji": "🏙️", "tags": ["도심 축제", "무료 행사 多", "대중교통 편리"], "desc": "대한민국 수도 서울은 연중 다양한 문화행사가 열리는 문화 중심지입니다. 한강 공원 행사, 광화문 광장 축제, 각 구별 지역 축제까지 볼거리가 풍부합니다.", "tips": ["대중교통 이용 권장", "주말 무료 행사 多", "한강 나들이 병행"]},
    "경기": {"emoji": "🌿", "tags": ["수도권 접근성", "넓은 야외 공간", "가족 행사 多"], "desc": "서울과 인접한 경기도는 접근성이 좋고 넓은 야외 공간을 활용한 대형 축제가 많습니다. 수원, 고양, 성남 등 각 도시마다 특색 있는 행사가 열립니다.", "tips": ["서울서 1시간 이내", "주차 비교적 편리", "가족 나들이 최적"]},
    "부산": {"emoji": "🌊", "tags": ["해변 축제", "불꽃 축제", "야경 명소"], "desc": "제2의 도시 부산은 해운대·광안리 해변을 무대로 한 축제와 공연이 유명합니다. 부산국제영화제, 광안리 불꽃 축제 등 전국적인 행사도 다수 개최됩니다.", "tips": ["해변 행사 봄~가을 집중", "KTX 2시간 30분", "숙박 미리 예약 필수"]},
    "제주": {"emoji": "🌺", "tags": ["자연 축제", "유채꽃", "한라산"], "desc": "사계절 아름다운 자연을 배경으로 제주만의 독특한 축제가 열립니다. 봄 유채꽃 축제, 여름 바다 행사, 가을 억새, 겨울 동백 축제까지 연중 볼거리가 있습니다.", "tips": ["항공권 미리 예매", "렌터카 필수", "날씨 변화 잦음"]},
    "강원": {"emoji": "🏔️", "tags": ["눈꽃 축제", "산악 행사", "청정 자연"], "desc": "설악산과 동해를 품은 강원도는 사계절 자연 축제의 고장입니다. 겨울 빙어 축제, 봄 산나물 축제, 여름 바다 축제, 가을 단풍 행사 등 자연과 함께하는 행사가 많습니다.", "tips": ["고속버스·KTX 이용", "계절별 특산 축제 확인", "산악 행사 복장 준비"]},
    "전북": {"emoji": "🥁", "tags": ["전통 문화", "판소리·가야금", "한옥마을"], "desc": "전주 한옥마을로 유명한 전북은 우리 전통문화를 잇는 행사가 많습니다. 전주비빔밥 축제, 전주국제영화제, 무주 반딧불 축제 등 다양한 문화 행사가 열립니다.", "tips": ["전주 한옥마을 연계", "전통 음식 체험", "KTX 전주역 이용"]},
    "전남": {"emoji": "🌻", "tags": ["꽃 축제", "해남", "순천만"], "desc": "순천만과 보성 녹차밭 등 아름다운 자연을 배경으로 한 축제가 많습니다. 함평 나비 축제, 영광 모시 축제, 해남 땅끝 행사 등 지역 특색이 담긴 행사를 즐길 수 있습니다.", "tips": ["순천만 국가정원 연계", "해산물 먹거리 풍부", "광주에서 1시간"]},
    "경북": {"emoji": "🏯", "tags": ["역사 문화", "유교 문화", "안동"], "desc": "안동 하회마을, 경주 등 유네스코 유산을 배경으로 한 역사·문화 행사가 풍성합니다. 안동 국제탈춤 축제, 경주 벚꽃 축제, 청도 소싸움 축제가 대표적입니다.", "tips": ["경주·안동 연계 여행", "유적지 관람 병행", "KTX 신경주역"]},
    "경남": {"emoji": "⚓", "tags": ["진해 벚꽃", "남해 섬 축제", "통영"], "desc": "진해 군항제(벚꽃 축제), 통영 한산대첩 축제, 남해 보물섬 축제 등 경남만의 특색 있는 행사가 많습니다. 해안을 따라 아름다운 경치와 함께 축제를 즐길 수 있습니다.", "tips": ["진해 3월 벚꽃 필수", "통영 케이블카 연계", "거제도 당일치기"]},
    "충남": {"emoji": "🌾", "tags": ["머드 축제", "백제 문화", "보령"], "desc": "보령 머드 축제로 유명한 충남은 백제 역사문화와 서해안 갯벌 체험 행사가 풍부합니다. 부여 백제 문화제, 아산 봄꽃 축제, 태안 튤립 축제가 대표적입니다.", "tips": ["보령 머드 축제 7~8월", "서해안 드라이브 병행", "KTX 천안아산역"]},
    "충북": {"emoji": "🌿", "tags": ["청주 직지", "속리산", "단양 관광"], "desc": "청주 직지 축제, 단양 소백산 철쭉 축제, 제천 국제음악영화제 등 내륙 도시의 다채로운 행사가 열립니다. 속리산, 월악산 등 국립공원 연계 행사도 많습니다.", "tips": ["단양 관광지 연계", "내륙 교통 확인", "자연 체험 행사 多"]},
    "대구": {"emoji": "🎭", "tags": ["컬러풀 대구", "치맥 페스티벌", "섬유 박물관"], "desc": "대구 치맥 페스티벌, 대구 국제 뮤지컬 축제(DIMF), 컬러풀 대구 축제 등 개성 넘치는 행사로 유명합니다. 팔공산 단풍, 앞산 야경과 함께 즐길 수 있는 행사도 많습니다.", "tips": ["KTX 동대구역", "치맥 축제 여름 필수", "도심 행사 많음"]},
    "광주": {"emoji": "🎨", "tags": ["미디어아트", "빛 축제", "5.18 문화"], "desc": "아시아 문화의 도시 광주는 광주 비엔날레, 광주 빛 축제, 추억의 충장 축제 등 예술·문화 행사가 풍성합니다. KTX로 서울에서 90분이면 도착합니다.", "tips": ["KTX 광주송정역", "국립아시아문화전당", "빛 축제 겨울 필수"]},
    "대전": {"emoji": "🔬", "tags": ["사이언스 페스티벌", "한밭 문화제", "엑스포"], "desc": "과학 도시 대전은 대전 사이언스 페스티벌, 한밭 문화제, 대동 하늘공원 행사 등 과학·문화가 어우러진 독특한 축제를 즐길 수 있습니다.", "tips": ["KTX 대전역·서대전역", "엑스포 과학공원", "계룡산 등산 병행"]},
    "인천": {"emoji": "✈️", "tags": ["인천 차이나타운", "강화도", "송도 행사"], "desc": "차이나타운 문화 축제, 강화 고인돌 문화제, 송도 국제도시 행사 등 다양한 행사가 열립니다. 서울과 가까워 당일치기 여행으로도 좋습니다.", "tips": ["수도권 전철 이용", "강화도 연계 여행", "인천공항 입국 연계"]},
    "울산": {"emoji": "🐳", "desc": "고래 도시 울산은 장생포 고래 축제, 울산 옹기 축제, 울산 마두희 축제 등 지역 특색이 담긴 행사가 많습니다. 태화강 국가정원의 봄꽃과 가을 억새 행사도 인기입니다.", "tags": ["고래 축제", "태화강 정원", "산업 관광"], "tips": ["KTX 울산역", "태화강 산책 병행", "부산에서 40분"]},
    "세종": {"emoji": "🏛️", "tags": ["행정 도시", "호수공원", "새로운 축제"], "desc": "신도시 세종은 세종 호수공원 축제, 세종 문화 예술제 등 새로운 도시만의 신선한 행사가 열립니다. 깔끔한 도시 환경과 함께 가족 나들이를 즐기기 좋습니다.", "tips": ["KTX 오송역 이용", "호수공원 산책", "대전·청주 연계"]},
}




def load_data():
    base = PROJECT_ROOT / "data" / "processed"
    events = json.loads((base / "events.json").read_text())
    by_region = json.loads((base / "events_by_region.json").read_text())
    by_month = json.loads((base / "events_by_month.json").read_text())
    free_events = json.loads((base / "free_events.json").read_text())

    # 아카이브 (종료된 행사 — 상세 페이지용)
    archive_path = base / "events_archive.json"
    archive = json.loads(archive_path.read_text()) if archive_path.exists() else []

    # 주간 큐레이션 — 최신순 전체 로드
    weekly_files = sorted(
        (PROJECT_ROOT / "data" / "content" / "weekly_picks").glob("*.json"),
        reverse=True
    )
    weekly_pick = json.loads(weekly_files[0].read_text()) if weekly_files else {}

    # 전체 주간 큐레이션 목록 (아카이브용) — {week, pick} 리스트
    weekly_list = []
    for wf in weekly_files:
        week_str = wf.stem  # "2026-W23"
        try:
            weekly_list.append({
                "week": week_str,
                "pick": json.loads(wf.read_text()),
            })
        except Exception:
            pass

    return events, by_region, by_month, free_events, archive, weekly_pick, weekly_list


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

    events, by_region, by_month, free_events, archive, weekly_pick, weekly_list = load_data()
    env = setup_env()

    # 지역별 행사 사전 (nearby_events 용)
    region_events_map = {}
    for e in events:
        region_events_map.setdefault(e["region"], []).append(e)

    today = datetime.now().strftime("%Y%m%d")
    today_dt = datetime.now()
    active = events  # process_events.py에서 이미 활성만 필터됨

    # 날씨 데이터 로드
    weather_dir = PROJECT_ROOT / "data/content/weather"
    weather_all = {}
    if weather_dir.exists():
        all_path = weather_dir / "all.json"
        if all_path.exists():
            try:
                weather_all = json.loads(all_path.read_text())
            except Exception:
                pass

    # 카페 후기 건수 사전 로드 (카드 뱃지용)
    reviews_dir = PROJECT_ROOT / "data/content/cafe_reviews"
    review_counts = {}  # event_id → 후기 건수
    if reviews_dir.exists():
        for rp in reviews_dir.glob("*.json"):
            try:
                data = json.loads(rp.read_text())
                cnt = len(data.get("reviews", []))
                if cnt > 0:
                    review_counts[rp.stem] = cnt
            except Exception:
                pass

    # 1. 메인
    tmpl = env.get_template("index.html")
    this_week_events = sorted(active, key=lambda x: x["start_date"])[:120]
    write(DIST / "index.html", tmpl.render(
        events=this_week_events,
        free_count=len(free_events),
        weekly_pick=weekly_pick,
        review_counts=review_counts,
        page_url="/"
    ))
    print("  메인 생성")

    # 2. 행사 상세 (활성 + 아카이브 모두 빌드 — SEO 유지)
    tmpl = env.get_template("event.html")
    reviews_dir = PROJECT_ROOT / "data/content/cafe_reviews"
    all_events_for_detail = active + archive

    for e in all_events_for_detail:
        review_path = reviews_dir / f"{e['id']}.json"
        cafe_reviews = []
        if review_path.exists():
            try:
                cafe_data = json.loads(review_path.read_text())
                cafe_reviews = cafe_data.get("reviews", [])
            except Exception:
                pass
        is_ended = e["end_date"] < today
        # 같은 지역 다른 행사 (자기 자신 제외, 최대 6개)
        same_region = [x for x in region_events_map.get(e.get("region", ""), [])
                       if x["id"] != e["id"]][:6]
        path = DIST / "event" / e["id"] / "index.html"
        write(path, tmpl.render(
            event=e,
            cafe_reviews=cafe_reviews,
            is_ended=is_ended,
            nearby_events=same_region,
            reviewed_date=BUILD_DATE,
            page_url=f"/event/{e['id']}/"
        ))
    print(f"  행사 상세: 활성 {len(active)}개 + 아카이브 {len(archive)}개")

    # 3. 지역별 (허브 페이지)
    tmpl = env.get_template("region.html")
    for region, slug in REGION_SLUGS.items():
        region_events = [e for e in active if e["region"] == region]
        if not region_events:
            continue
        free_cnt = sum(1 for e in region_events if e["is_free"])
        region_info = REGION_INFO.get(region, {
            "emoji": "📍", "tags": [], "desc": f"{region} 지역 문화행사·축제 정보입니다.", "tips": []
        })
        path = DIST / "region" / slug / "index.html"
        write(path, tmpl.render(
            region=region, slug=slug,
            events=region_events,
            free_count=free_cnt,
            region_info=region_info,
            weather=weather_all.get(region),
            review_counts=review_counts,
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
            review_counts=review_counts,
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
            review_counts=review_counts,
            page_url=f"/category/{slug}/"
        ))
    print(f"  카테고리: {len(CATEGORY_SLUGS)}개")

    # 6. 무료 행사
    tmpl = env.get_template("free.html")
    write(DIST / "free" / "index.html", tmpl.render(
        events=free_events,
        review_counts=review_counts,
        page_url="/free/"
    ))
    print(f"  무료 행사: {len(free_events)}개")

    # 6-1. 시즌 특집 페이지
    tmpl = env.get_template("season.html")
    current_month = today_dt.month
    for season in SEASONS:
        season_events = [e for e in active if int(e["start_date"][4:6]) in season["months"]
                         or int(e["end_date"][4:6]) in season["months"]]
        if not season_events:
            continue
        # 카테고리별 건수
        cat_counts = {}
        for e in season_events:
            cat_counts[e["category"]] = cat_counts.get(e["category"], 0) + 1
        cat_counts = dict(sorted(cat_counts.items(), key=lambda x: x[1], reverse=True))

        path = DIST / "season" / season["slug"] / "index.html"
        write(path, tmpl.render(
            season_slug=season["slug"],
            season_name=season["name"],
            season_emoji=season["emoji"],
            season_months=season["months_str"],
            season_color_from=season["color_from"],
            season_color_to=season["color_to"],
            season_desc=season["desc"],
            year=today_dt.year,
            events=season_events,
            free_count=sum(1 for e in season_events if e["is_free"]),
            region_count=len(set(e["region"] for e in season_events)),
            category_counts=cat_counts,
            review_counts=review_counts,
            all_seasons=SEASONS,
            page_url=f"/season/{season['slug']}/"
        ))
    print(f"  시즌 특집: {len(SEASONS)}개")

    # 7. 주간 큐레이션 — 개별 페이지 (전체) + 목록 페이지
    tmpl_pick = env.get_template("weekly_pick.html")
    for item in weekly_list:
        week_str = item["week"]
        path = DIST / "weekly" / week_str / "index.html"
        write(path, tmpl_pick.render(
            pick=item["pick"],
            week=week_str,
            page_url=f"/weekly/{week_str}/"
        ))
    if weekly_list:
        print(f"  주간 큐레이션: {len(weekly_list)}개")

    # 7-1. 주간 큐레이션 목록 (모아보기)
    tmpl_archive = env.get_template("weekly_archive.html")
    write(DIST / "weekly" / "index.html", tmpl_archive.render(
        weekly_list=weekly_list,
        page_url="/weekly/"
    ))
    print(f"  주간 큐레이션 모아보기: {len(weekly_list)}개")

    # 7-2. 지나간 행사 아카이브 목록 페이지
    tmpl_past = env.get_template("past.html")
    past_regions = sorted(set(e["region"] for e in archive)) if archive else []
    write(DIST / "past" / "index.html", tmpl_past.render(
        archive=archive,
        regions=past_regions,
        page_url="/past/"
    ))
    print(f"  지나간 행사 아카이브: {len(archive)}개")

    # 7-3. About 페이지
    tmpl_about = env.get_template("about.html")
    write(DIST / "about" / "index.html", tmpl_about.render(
        page_url="/about/"
    ))
    print("  About 페이지 생성")

    # 7-4. 캘린더
    calendar_months = build_calendars(active, env, today_dt)

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
    build_sitemap(active, archive)

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


CAT_COLORS = {
    "축제":   "bg-orange-400",
    "공연":   "bg-purple-400",
    "전시":   "bg-blue-400",
    "체험":   "bg-green-400",
    "스포츠": "bg-red-400",
    "문화행사": "bg-gray-400",
}

MONTH_KR = ["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"]


def build_calendars(active: list, env, today_dt: datetime):
    """월별 캘린더 페이지 생성"""
    tmpl = env.get_template("calendar.html")

    # 행사가 있는 월 수집 (시작월 기준)
    months = sorted(set(e["start_date"][:6] for e in active))
    # 종료월도 포함 (시작은 이전 달이지만 이번 달에 끝나는 행사)
    months = sorted(set(
        months + [e["end_date"][:6] for e in active]
    ))

    built = []
    for ym in months:
        year_int = int(ym[:4])
        month_int = int(ym[4:6])

        # 해당 월에 시작하거나 종료하는 행사
        month_events = [
            e for e in active
            if e["start_date"][:6] == ym or e["end_date"][:6] == ym
        ]
        if not month_events:
            continue

        # day_events: {day: {'start': [...], 'end': [...]}}
        day_events = {}
        for e in month_events:
            # 시작일
            if e["start_date"][:6] == ym:
                d = int(e["start_date"][6:8])
                day_events.setdefault(d, {"start": [], "end": []})["start"].append(e)
            # 종료일
            if e["end_date"][:6] == ym:
                d = int(e["end_date"][6:8])
                day_events.setdefault(d, {"start": [], "end": []})["end"].append(e)

        # 해당 월 전체 행사 목록 (시작일순)
        month_all = sorted(month_events, key=lambda x: x["start_date"])

        # 캘린더 계산 (월요일=0 시작)
        first_weekday = cal_module.monthrange(year_int, month_int)[0]  # 0=월, 6=일
        days_in_month = cal_module.monthrange(year_int, month_int)[1]

        # 이전/다음 달
        if month_int == 1:
            prev_y, prev_m = year_int - 1, 12
        else:
            prev_y, prev_m = year_int, month_int - 1
        if month_int == 12:
            next_y, next_m = year_int + 1, 1
        else:
            next_y, next_m = year_int, month_int + 1

        prev_month = f"{prev_y}/{prev_m:02d}"
        next_month = f"{next_y}/{next_m:02d}"
        prev_label = f"{prev_y}년 {MONTH_KR[prev_m-1]}"
        next_label = f"{next_y}년 {MONTH_KR[next_m-1]}"

        # 오늘 날짜 (같은 월이면 표시)
        today_day = today_dt.day if (today_dt.year == year_int and today_dt.month == month_int) else None

        # 월 빠른이동 링크 (현재 월 ±3개월)
        month_links = []
        for delta in range(-2, 4):
            m2 = month_int + delta
            y2 = year_int
            while m2 < 1:
                m2 += 12; y2 -= 1
            while m2 > 12:
                m2 -= 12; y2 += 1
            if any(e["start_date"][:6] == f"{y2}{m2:02d}" for e in active):
                month_links.append({"url": f"{y2}/{m2:02d}", "label": f"{MONTH_KR[m2-1]}"})

        path = DIST / "calendar" / str(year_int) / f"{month_int:02d}" / "index.html"
        write(path, tmpl.render(
            year=str(year_int),
            month_int=month_int,
            month_name=MONTH_KR[month_int - 1],
            first_weekday=first_weekday,
            days_in_month=days_in_month,
            day_events=day_events,
            month_all_events=month_all,
            total_events=len(set(e["id"] for e in month_events)),
            today_day=today_day,
            prev_month=prev_month,
            next_month=next_month,
            prev_label=prev_label,
            next_label=next_label,
            month_links=month_links,
            cat_colors=CAT_COLORS,
            page_url=f"/calendar/{year_int}/{month_int:02d}/"
        ))
        built.append(ym)

    # /calendar/ 인덱스 → 현재 달로 리다이렉트(meta refresh)
    current_ym = today_dt.strftime("%Y/%m")
    index_html = f"""<!DOCTYPE html><html><head>
<meta charset="UTF-8">
<meta http-equiv="refresh" content="0;url=/calendar/{current_ym}/">
<title>캘린더 — {SITE_NAME}</title>
</head><body>
<a href="/calendar/{current_ym}/">캘린더로 이동</a>
</body></html>"""
    write(DIST / "calendar" / "index.html", index_html)

    print(f"  캘린더: {len(built)}개 월")
    return built


def build_sitemap(events: list, archive: list = None):
    urls = [
        {"loc": "/", "priority": "1.0", "changefreq": "daily"},
        {"loc": "/free/", "priority": "0.9", "changefreq": "daily"},
        {"loc": "/calendar/", "priority": "0.9", "changefreq": "daily"},
        {"loc": "/weekly/", "priority": "0.9", "changefreq": "weekly"},
        {"loc": "/past/", "priority": "0.7", "changefreq": "weekly"},
        {"loc": "/about/", "priority": "0.6", "changefreq": "monthly"},
    ]

    # 캘린더 월별 URL
    cal_months = sorted(set(e["start_date"][:6] for e in events))
    for ym in cal_months:
        urls.append({"loc": f"/calendar/{ym[:4]}/{ym[4:6]}/", "priority": "0.8", "changefreq": "daily"})

    for region_slug in REGION_SLUGS.values():
        urls.append({"loc": f"/region/{region_slug}/", "priority": "0.8", "changefreq": "weekly"})

    for season in SEASONS:
        urls.append({"loc": f"/season/{season['slug']}/", "priority": "0.8", "changefreq": "weekly"})

    for category_slug in CATEGORY_SLUGS.values():
        urls.append({"loc": f"/category/{category_slug}/", "priority": "0.8", "changefreq": "weekly"})

    # 활성 행사
    for e in events:
        urls.append({"loc": f"/event/{e['id']}/", "priority": "0.7", "changefreq": "weekly"})

    # 아카이브 행사 — 낮은 priority, 변경 없음
    for e in (archive or []):
        urls.append({"loc": f"/event/{e['id']}/", "priority": "0.4", "changefreq": "monthly"})

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
