# CLAUDE.md — 전국 문화행사·축제 캘린더 사이트

## 프로젝트 개요

**사이트명:** 이번주 행사 (가칭: `eventcal.kr`)
**레포 위치:** `my-sites/eventcal/`
**목적:** 한국관광공사 Tour API 기반 무료 문화행사·축제 정보 → SEO 트래픽 → 숙박 CPA + AdSense
**핵심 가치:** "이번 주말 우리 동네 무료 행사 뭐 있나?" — 가족·커플 주말 계획 수요 직접 공략
**아키텍처:** Python 빌더 → 완전 정적 HTML → Cloudflare Pages
**자동화:** GitHub Actions 주 2회 (화·금) 신규 행사 수집 + 빌드
**AI 활용:** Claude Haiku 4.5 Batch API — 행사 요약 + 지역별 주말 가이드 생성

---

## 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 빌더 | Python 3.11 + Jinja2 | 공통 스택 |
| 데이터 | 한국관광공사 Tour API | 무료, 품질 우수 |
| 달력 UI | FullCalendar (CDN) | 무료 오픈소스 |
| CSS | Tailwind CSS CDN | 빌드 불필요 |
| 배포 | Cloudflare Pages | 무료 |
| CI/CD | GitHub Actions | my-sites 레포 공유 |
| AI | Claude Haiku 4.5 Batch API | 행사 요약·가이드 |

---

## 디렉토리 구조

```
my-sites/eventcal/
├── CLAUDE.md
├── requirements.txt
├── data/
│   ├── raw/
│   ├── processed/
│   │   ├── events.json              # 전체 행사 목록 (월별 갱신)
│   │   ├── events_by_region.json    # 지역별 행사
│   │   ├── events_by_month.json     # 월별 행사
│   │   ├── festivals.json           # 축제 특화 목록
│   │   └── free_events.json         # 무료 행사만 필터
│   └── content/
│       ├── weekly_picks/            # 주간 AI 큐레이션
│       ├── region_guides/           # 지역별 행사 가이드
│       └── festival_guides/         # 축제 상세 가이드
├── scripts/
│   ├── fetch_tour_api.py            # 한국관광공사 Tour API
│   ├── fetch_culture.py             # 문화체육관광부 문화행사 API
│   ├── generate_content.py          # AI 큐레이션·가이드 생성
│   └── build_site.py
├── templates/
│   ├── base.html
│   ├── index.html                   # 메인 (이번 주 행사 + 달력)
│   ├── event.html                   # 행사 상세 (SEO 핵심)
│   ├── region.html                  # 지역별 행사 목록
│   ├── monthly.html                 # 월별 행사 캘린더
│   ├── weekly_pick.html             # 주간 AI 큐레이션 포스트
│   ├── festival_guide.html          # 축제 가이드 포스트
│   └── category.html                # 카테고리별 (공연/전시/축제/스포츠)
└── dist/
```

---

## Step 1: 데이터 수집

### A. 한국관광공사 Tour API (`scripts/fetch_tour_api.py`)

```python
"""
한국관광공사 Tour API 1.0
공식: https://api.visitkorea.or.kr/
공공데이터포털: "관광정보서비스" 검색
무료, 일 10만건 한도

주요 contentTypeId:
- 15: 축제공연행사 (핵심)
- 14: 문화시설
- 25: 여행코스
"""

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path

TOUR_API_BASE = "https://apis.data.go.kr/B551011/KorService1"

CONTENT_TYPES = {
    "15": "축제·공연·행사",   # 핵심
    "14": "문화시설",
    "28": "레포츠",
}

# 지역 코드 (areaCode)
AREA_CODES = {
    "1": "서울", "2": "인천", "3": "대전", "4": "대구",
    "5": "광주", "6": "부산", "7": "울산", "8": "세종",
    "31": "경기", "32": "강원", "33": "충북", "34": "충남",
    "35": "경북", "36": "경남", "37": "전북", "38": "전남",
    "39": "제주"
}

EVENT_SCHEMA = {
    "id": "str",                     # contentId slug
    "content_id": "str",             # Tour API contentId
    "title": "str",                  # 행사명
    "category": "str",               # 축제/공연/전시/스포츠/기타
    "region": "str",                 # 시도명
    "city": "str",                   # 시군구
    "address": "str",
    "lat": "float",
    "lng": "float",
    "start_date": "str",             # YYYYMMDD
    "end_date": "str",
    "place": "str",                  # 행사 장소명
    "is_free": "bool",               # 무료 여부
    "fee": "str",                    # 관람료 (무료/유료/상이)
    "organizer": "str",              # 주최기관
    "tel": "str",
    "homepage": "str",
    "thumbnail": "str",              # 대표 이미지 URL
    "description": "str",            # 원문 설명
    # AI 생성
    "summary": "str",                # 3줄 요약
    "highlight": "str",              # 이 행사의 하이라이트
    "target_audience": "str",        # 추천 대상 (가족/커플/혼자)
    "tips": "list",                  # 방문 팁 3가지
    "nearby_food": "str",            # 근처 맛집 추천 (AI)
    "seo_title": "str",
    "meta_description": "str",
    "tags": "list"
}

def fetch_events_by_period(start: str, end: str) -> list:
    """
    기간별 행사 수집
    start, end: YYYYMMDD 형식
    """
    all_events = []

    for area_code, area_name in AREA_CODES.items():
        params = {
            "serviceKey": "TOUR_API_KEY",
            "numOfRows": 100,
            "pageNo": 1,
            "MobileOS": "ETC",
            "MobileApp": "eventcal",
            "_type": "json",
            "listYN": "Y",
            "arrange": "A",
            "contentTypeId": "15",   # 축제·공연·행사
            "areaCode": area_code,
            "eventStartDate": start,
            "eventEndDate": end
        }

        resp = requests.get(
            f"{TOUR_API_BASE}/searchFestival1",
            params=params,
            timeout=30
        )
        import time; time.sleep(0.5)

        data = resp.json()
        items = data.get("response", {}).get("body", {}).get("items", {}).get("item", [])

        if isinstance(items, dict):
            items = [items]

        for item in items:
            all_events.append({
                "content_id": str(item.get("contentid", "")),
                "title": item.get("title", ""),
                "region": area_name,
                "address": item.get("addr1", ""),
                "lat": float(item.get("mapy", 0)),
                "lng": float(item.get("mapx", 0)),
                "start_date": item.get("eventstartdate", ""),
                "end_date": item.get("eventenddate", ""),
                "place": item.get("eventplace", ""),
                "thumbnail": item.get("firstimage", ""),
                "homepage": item.get("homepage", "")
            })

        print(f"{area_name}: {len(items)}개 행사 수집")

    return all_events

def fetch_event_detail(content_id: str) -> dict:
    """행사 상세 정보 수집 (관람료, 주최 등)"""
    params = {
        "serviceKey": "TOUR_API_KEY",
        "contentId": content_id,
        "contentTypeId": "15",
        "MobileOS": "ETC",
        "MobileApp": "eventcal",
        "_type": "json",
        "defaultYN": "Y",
        "firstImageYN": "Y",
        "addrinfoYN": "Y",
        "overviewYN": "Y"
    }
    resp = requests.get(f"{TOUR_API_BASE}/detailCommon1", params=params, timeout=15)
    data = resp.json()
    item = data.get("response", {}).get("body", {}).get("items", {}).get("item", [{}])
    return item[0] if isinstance(item, list) else item
```

### B. 문화체육관광부 문화행사 API (`scripts/fetch_culture.py`)

```python
"""
문화포털 문화행사 정보
공공데이터포털: "문화체육관광부_문화행사 정보" 검색
Tour API 보완용
"""

CULTURE_API = "https://www.culture.go.kr/openapi/rest/publicperformancedisplays/period"

def fetch_culture_events(from_date: str, to_date: str) -> list:
    """공연·전시 행사 수집"""
    params = {
        "serviceKey": "CULTURE_API_KEY",
        "from": from_date,    # YYYYMMDD
        "to": to_date,
        "rows": 100,
        "cPage": 1,
        "sortStdr": "1"
    }
    # ... 구현
```

---

## Step 2: AI 콘텐츠 생성 (`scripts/generate_content.py`)

### A. 행사별 요약 (Batch)

```python
EVENT_SUMMARY_SYSTEM = """당신은 주말 나들이 전문 큐레이터입니다.
주어진 문화행사 정보를 바탕으로 사람들이 꼭 가고 싶어지도록 매력적으로 소개하세요.

JSON 출력:
{
  "summary": "이 행사의 핵심 매력 3줄 (각 줄 60자)",
  "highlight": "절대 놓치면 안 되는 포인트 (100자)",
  "target_audience": "가족여행|커플|친구모임|혼자",
  "target_reason": "추천 대상인 이유 (80자)",
  "tips": ["방문 팁 3가지 (각 60자)"],
  "best_time": "하루 중 방문 최적 시간대 (오전/오후/저녁, 이유 포함)",
  "nearby_food_keywords": ["근처 맛집 검색 키워드 3개"],
  "is_free_confirmed": true,
  "seo_title": "SEO 제목 (60자, 지역명+행사명+특징)",
  "meta_description": "메타 설명 (155자, 언제·어디서·무엇을 포함)",
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"]
}"""

def build_event_requests(events: list) -> list:
    requests = []
    for event in events:
        user_msg = f"""행사명: {event['title']}
지역: {event['region']} {event.get('city', '')}
장소: {event.get('place', '')}
기간: {event['start_date']} ~ {event['end_date']}
관람료: {event.get('fee', '미확인')}
설명: {event.get('description', '')[:500]}"""

        requests.append({
            "custom_id": f"event-{event['id']}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 600,
                "system": EVENT_SUMMARY_SYSTEM,
                "messages": [{"role": "user", "content": user_msg}]
            }
        })
    return requests
```

### B. 주간 AI 큐레이션 포스트 (매주 자동 생성)

```python
WEEKLY_PICK_SYSTEM = """주말 나들이 전문 에디터로서 이번 주 추천 행사 TOP 5를 선정하세요.
독자: 주말 계획을 세우는 2030~4050 가족/커플

JSON 출력:
{
  "title": "이번 주 가볼 만한 행사 TOP 5 ({날짜})",
  "intro": "이번 주 행사 트렌드 요약 (200자)",
  "picks": [
    {
      "rank": 1,
      "event_id": "선택한 행사 id",
      "reason": "추천 이유 (100자)",
      "must_see": "꼭 봐야 할 포인트 (80자)",
      "tip": "실용적인 방문 팁 (80자)"
    }
  ],
  "hidden_gem": "덜 알려졌지만 추천하는 행사 1개 소개 (200자)",
  "next_week_preview": "다음 주 주목할 행사 (100자)"
}"""

def generate_weekly_picks(events: list, week_str: str) -> dict:
    """이번 주 행사 중 TOP 5 AI 큐레이션"""

    # 이번 주 행사 필터
    today = datetime.now()
    week_end = today + timedelta(days=7)
    this_week = [
        e for e in events
        if e["start_date"] <= week_end.strftime("%Y%m%d")
        and e["end_date"] >= today.strftime("%Y%m%d")
    ]

    # 상위 30개만 AI에 전달 (토큰 절약)
    candidates = sorted(this_week, key=lambda x: x.get("score", 0), reverse=True)[:30]

    prompt = f"이번 주 ({week_str}) 추천 행사 후보:\n"
    for i, e in enumerate(candidates, 1):
        prompt += f"{i}. [{e['region']}] {e['title']} ({e['start_date'][:4]}/{e['start_date'][4:6]}/{e['start_date'][6:]}~, {e.get('fee', '미확인')})\n"

    # 단일 API 호출 (배치 불필요 — 주 1회)
    client = anthropic.Anthropic()
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=800,
        system=WEEKLY_PICK_SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )
    return json.loads(resp.content[0].text)
```

### C. 지역별 축제 가이드 (1회 생성, 연 1회 갱신)

```python
FESTIVAL_GUIDE_SYSTEM = """지역 축제 전문 여행 작가로서 상세한 방문 가이드를 작성하세요.

JSON 출력:
{
  "title": "가이드 SEO 제목",
  "meta_description": "메타 설명",
  "overview": "축제 개요 (300자)",
  "history": "축제 역사·의미 (200자)",
  "highlights": ["볼거리·즐길거리 5가지 (각 100자)"],
  "practical_info": {
    "how_to_get": "교통편 (200자)",
    "parking": "주차 정보 (100자)",
    "best_time_to_visit": "방문 최적 시간대",
    "what_to_bring": "챙겨야 할 것들"
  },
  "nearby_restaurants": "근처 맛집 키워드",
  "accommodation_tip": "숙박 추천 (100자)",
  "faq": [{"q": "질문", "a": "답변"}]
}"""

# 대형 축제 가이드 생성 대상 (연 1회 업데이트)
MAJOR_FESTIVALS = [
    "진해 군항제", "보령 머드축제", "화천 산천어축제",
    "부산 국제영화제", "광주 김치축제", "강릉 단오제",
    "이천 도자기축제", "안동 국제탈춤페스티벌",
    "자라섬 재즈페스티벌", "울산 옹기축제"
]
```

---

## Step 3: 사이트 빌드 (`scripts/build_site.py`)

### 생성 페이지 구조

```python
def build_all():
    # 메인
    build_index()               # / — 이번 주 행사 + 다음 주 예고

    # 행사 목록
    build_region_pages()        # /region/seoul/ 등 17개
    build_monthly_pages()       # /2026/06/ 등 월별
    build_category_pages()      # /category/festival/ 등 5개
    build_free_events_page()    # /free/ — 무료 행사만 특화

    # 상세
    build_event_pages()         # /event/{id}/ — 행사별 (SEO 핵심)

    # 콘텐츠
    build_weekly_picks()        # /weekly/{YYYY-WW}/ — 주간 큐레이션
    build_festival_guides()     # /guide/{slug}/ — 축제 가이드

    # 기술
    build_sitemap()
    build_robots()
```

### 메인 페이지 구성 (`templates/index.html`)

```html
<!-- 이번 주 주요 행사 -->
<section class="this-week">
  <h1>이번 주 가볼 만한 행사</h1>

  <!-- AI 픽 배지 -->
  <div class="ai-pick-banner bg-gradient-to-r from-purple-600 to-blue-600 text-white p-4 rounded-xl">
    <p class="text-sm opacity-80">✨ AI 에디터 추천</p>
    <h2 class="text-xl font-bold">{{ weekly_pick.picks[0].title }}</h2>
    <p>{{ weekly_pick.picks[0].reason }}</p>
    <a href="/event/{{ weekly_pick.picks[0].event_id }}/">자세히 보기 →</a>
  </div>

  <!-- 지역 필터 탭 -->
  <div class="region-tabs flex gap-2 overflow-x-auto mt-6">
    <button class="tab active" data-region="all">전체</button>
    <button class="tab" data-region="서울">서울</button>
    <button class="tab" data-region="경기">경기</button>
    <button class="tab" data-region="강원">강원</button>
    <!-- ... -->
  </div>

  <!-- 행사 카드 그리드 -->
  <div class="events-grid grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mt-4">
    {% for event in this_week_events %}
    <a href="/event/{{ event.id }}/" class="event-card" data-region="{{ event.region }}">
      {% if event.thumbnail %}
      <img src="{{ event.thumbnail }}" alt="{{ event.title }}"
           class="w-full h-48 object-cover rounded-t-xl">
      {% endif %}
      <div class="p-4">
        <div class="flex justify-between items-start">
          <span class="badge badge-{{ event.category }}">{{ event.category }}</span>
          {% if event.is_free %}
          <span class="badge-free bg-green-100 text-green-700 text-xs px-2 py-0.5 rounded-full">무료</span>
          {% endif %}
        </div>
        <h3 class="mt-2 font-bold line-clamp-2">{{ event.title }}</h3>
        <p class="text-sm text-gray-500 mt-1">📍 {{ event.region }} · {{ event.place }}</p>
        <p class="text-sm text-blue-600 mt-1">
          📅 {{ event.start_date | format_date }} ~
          {% if event.start_date != event.end_date %}{{ event.end_date | format_date }}{% endif %}
        </p>
        <p class="text-sm text-gray-600 mt-2 line-clamp-2">{{ event.summary_first_line }}</p>
      </div>
    </a>
    {% endfor %}
  </div>
</section>

<!-- 다음 달 주요 축제 예고 -->
<section class="next-month">
  <h2>다음 달 주목할 축제</h2>
  <!-- ... -->
</section>

<!-- AdSense -->
{{ adsense.render("banner_bottom") }}
```

### 행사 상세 페이지 (`templates/event.html`)

```html
<!-- 1. 히어로 이미지 -->
{% if event.thumbnail %}
<div class="hero-image">
  <img src="{{ event.thumbnail }}" alt="{{ event.title }}">
</div>
{% endif %}

<!-- 2. 기본 정보 -->
<div class="event-info">
  <h1>{{ event.seo_title }}</h1>
  <div class="badges">
    <span class="badge">{{ event.category }}</span>
    {% if event.is_free %}<span class="badge-free">무료</span>{% endif %}
    <span class="badge-region">{{ event.region }}</span>
  </div>

  <div class="key-info grid grid-cols-2 gap-3 mt-4">
    <div><span class="icon">📅</span> {{ event.start_date | format_date }} ~ {{ event.end_date | format_date }}</div>
    <div><span class="icon">📍</span> {{ event.place }}</div>
    <div><span class="icon">💰</span> {{ event.fee or "무료" }}</div>
    <div><span class="icon">📞</span> {{ event.tel or "정보 없음" }}</div>
  </div>
</div>

<!-- 3. AI 요약 하이라이트 박스 -->
<div class="highlight-box bg-amber-50 border-l-4 border-amber-400 p-5">
  <h2 class="font-bold text-amber-800 mb-2">✨ 이 행사의 하이라이트</h2>
  <p>{{ event.highlight }}</p>
  <div class="mt-3 text-sm text-amber-700">
    👥 추천 대상: {{ event.target_audience }} — {{ event.target_reason }}
  </div>
</div>

<!-- 4. 방문 팁 -->
<section>
  <h2>💡 방문 팁</h2>
  <ul>{% for tip in event.tips %}<li>{{ tip }}</li>{% endfor %}</ul>
</section>

<!-- 5. AdSense -->
{{ adsense.render("rectangle_mid") }}

<!-- 6. 숙박 CPA -->
{% if event.start_date != event.end_date %}
<div class="accommodation-cta">
  <h2>🏨 근처 숙박 예약</h2>
  <p class="text-sm text-gray-500">{{ event.title }} 기간 중 {{ event.region }} 숙박이 빨리 마감됩니다</p>
  <div class="flex gap-3 mt-3">
    <a href="{{ cpa.yanolja }}" class="flex-1 btn-primary text-center">야놀자</a>
    <a href="{{ cpa.yeogi }}" class="flex-1 btn-secondary text-center">여기어때</a>
  </div>
</div>
{% endif %}

<!-- 7. 공식 홈페이지 / 원문 -->
{% if event.homepage %}
<a href="{{ event.homepage }}" target="_blank" rel="noopener">공식 홈페이지 →</a>
{% endif %}

<!-- 8. 관련 행사 -->
<section>
  <h2>이 지역 다른 행사</h2>
  <!-- 같은 지역 행사 카드 4개 -->
</section>
```

---

## Step 4: SEO 전략

### URL 구조

```
/                           → 메인 (이번 주 행사)
/region/seoul/              → 서울 행사 목록
/region/gangwon/            → 강원 행사 목록
/2026/07/                   → 2026년 7월 행사 달력
/event/{content-id}-{slug}/ → 행사 상세 (SEO 핵심)
/category/festival/         → 축제만 모아보기
/free/                      → 무료 행사만
/weekly/2026-W22/           → 주간 AI 큐레이션
/guide/boryeong-mud-festival/ → 보령 머드축제 가이드
```

### 키워드 타겟

| 키워드 | 페이지 | 월 검색량 | 경쟁도 |
|--------|--------|---------|--------|
| 이번 주 행사 | 메인 | 높음 | 낮음 |
| {지역} 축제 {월} | 지역·월별 | 높음 | 낮음 |
| {행사명} | 상세 | 중간 | 없음 |
| 주말 무료 행사 | /free/ | 높음 | 낮음 |
| {지역} 이번 주말 | 지역 | 높음 | 낮음 |
| {축제명} 주차 팁 | 가이드 | 낮음 | 없음 |

### 구조화 데이터

```python
# 행사 → Event 스키마 (구글 Rich Result 지원)
JSON_LD_EVENT = {
    "@context": "https://schema.org",
    "@type": "Event",
    "name": event["title"],
    "description": event["meta_description"],
    "startDate": event["start_date"],
    "endDate": event["end_date"],
    "location": {
        "@type": "Place",
        "name": event["place"],
        "address": {
            "@type": "PostalAddress",
            "addressLocality": event["city"],
            "addressRegion": event["region"],
            "addressCountry": "KR"
        },
        "geo": {
            "@type": "GeoCoordinates",
            "latitude": event["lat"],
            "longitude": event["lng"]
        }
    },
    "isAccessibleForFree": event["is_free"],
    "organizer": {
        "@type": "Organization",
        "name": event["organizer"]
    },
    "image": event["thumbnail"]
}
```

> Event 스키마는 구글 검색 결과에 날짜·장소 리치 스니펫으로 표시됨 — CTR 대폭 향상

---

## Step 5: 수익화

```python
# 숙박 CPA (핵심 수익원)
ACCOMMODATION_CPA = {
    "yanolja": {
        "url": "https://www.yanolja.com/?ref=eventcal",
        "commission": "예약 건당 2,000~5,000원",
        "tracking": "UTM 파라미터로 행사별 추적"
    },
    "yeogi": {
        "url": "https://www.yeogi.com/?ref=eventcal",
        "commission": "예약 건당 1,500~4,000원"
    }
}

# 행사 유형별 CPA 전략
CPA_STRATEGY = {
    "당일치기 행사": "음식점·카페 쿠팡이츠 연계",
    "1박 이상 축제": "야놀자·여기어때 숙박 CPA 강조",
    "공연·전시": "인터파크 티켓 제휴 (수수료 검토)",
    "스포츠": "스포츠용품 쿠팡파트너스"
}

# AdSense 배치
ADSENSE_PLACEMENT = {
    "메인": "AI픽 배너 아래 + 행사 그리드 6번째마다",
    "상세": "하이라이트 박스 아래 + 숙박CTA 아래 + 하단",
    "주간픽": "2번째 추천 아래 + 5번째 추천 아래"
}
```

---

## GitHub Actions Job

```yaml
deploy-eventcal:
  runs-on: ubuntu-latest
  if: github.event_name == 'workflow_dispatch' ||
      github.event.schedule == '0 19 * * 1,4'   # 화·금 오전 4시 KST
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - run: pip install -r eventcal/requirements.txt

    - name: Fetch Tour API events
      run: python eventcal/scripts/fetch_tour_api.py
      env:
        TOUR_API_KEY: ${{ secrets.TOUR_API_KEY }}
        CULTURE_API_KEY: ${{ secrets.CULTURE_API_KEY }}

    - name: Generate AI content
      run: python eventcal/scripts/generate_content.py
      env:
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

    - name: Build site
      run: python eventcal/scripts/build_site.py

    - name: Deploy
      run: npx wrangler pages deploy eventcal/dist --project-name=eventcal
      env:
        CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## 환경변수 추가분

| 변수명 | 설명 |
|--------|------|
| `TOUR_API_KEY` | 한국관광공사 Tour API (data.go.kr 신청) |
| `CULTURE_API_KEY` | 문화체육관광부 문화행사 API |

---

## 클로드 코드 실행 순서

```bash
cd my-sites/eventcal

# 1. API 키 준비
# - data.go.kr: 한국관광공사 Tour API 1.0 신청 (승인 1~2일 소요)
# - data.go.kr: 문화체육관광부 문화행사 API

# 2. 이번 달 + 다음 달 행사 수집
python scripts/fetch_tour_api.py

# 3. 문화행사 보완 수집
python scripts/fetch_culture.py

# 4. AI 요약 생성 (Batch, 약 1시간)
python scripts/generate_content.py --type event_summaries

# 5. 주간 AI 큐레이션 생성
python scripts/generate_content.py --type weekly_picks

# 6. 주요 축제 가이드 생성 (10개)
python scripts/generate_content.py --type festival_guides

# 7. 빌드
python scripts/build_site.py

# 8. 로컬 확인
python -m http.server 8005 --directory dist &

# 9. 배포
npx wrangler pages project create eventcal
npx wrangler pages deploy dist --project-name=eventcal
```

---

## 성공 지표 (90일)

| 지표 | 최악 | 보통 |
|------|------|------|
| 수집 행사 수 | 500건/월 | 3,000건/월 |
| 정적 페이지 수 | 1,000개 | 5,000개+ |
| 일 방문자 | 50명 | 600명 |
| Event 리치 스니펫 노출 | 10개 | 200개+ |
| 숙박 CPA 월 건수 | 0건 | 8건 (×3,000원) |
| AdSense 월 수익 | 750원 | 28,800원 |
| **월 총 수익** | **750원** | **52,800원** |

---

## 주의사항

- Tour API 이미지 URL: 직접 임베드 가능 (관광공사 이용 허가)
- 행사 취소·변경 시: `is_cancelled: true` 처리 + 페이지 상단 "행사 정보가 변경될 수 있습니다" 고지
- 구글 Event 스키마: 취소된 행사는 `eventStatus: "EventCancelled"` 업데이트 필수
- 숙박 CPA: 행사 기간·장소 기반 딥링크 생성으로 전환율 향상
  - 예: `https://www.yanolja.com/search?keyword=보령&checkIn=20260718&checkOut=20260719`
