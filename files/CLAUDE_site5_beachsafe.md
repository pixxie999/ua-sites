# CLAUDE.md — 전국 해수욕장·물놀이 안전정보 사이트

## 프로젝트 개요

**사이트명:** 해수욕장 인포 (가칭: `beachsafe.kr`)
**레포 위치:** `my-sites/beachsafe/`
**목적:** 해양수산부·행안부 공공데이터 기반 해수욕장 정보 제공 → 여름 시즌 집중 트래픽 → AdSense + 숙박·여행 CPA
**핵심 가치:** "이 해수욕장 지금 안전한가? 물놀이 가능한가?" — 여름 외출 전 필수 체크
**아키텍처:** Python 빌더 → 완전 정적 HTML → Cloudflare Pages
**자동화:** GitHub Actions 일 1회 (여름 시즌) / 주 1회 (비수기)
**비수기 전략:** 겨울 낚시 정보 + 해안 드라이브 코스로 전환해 연중 트래픽 유지

---

## 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 빌더 | Python 3.11 + Jinja2 | 공통 스택 |
| 날씨 | 기상청 API (무료) | 실시간 날씨 |
| 지도 | Kakao Map API (무료 티어) | 해수욕장 위치 |
| CSS | Tailwind CSS CDN | 빌드 불필요 |
| 배포 | Cloudflare Pages | 무료 |
| CI/CD | GitHub Actions | my-sites 레포 공유 |
| AI | Claude Haiku 4.5 Batch API | 여행 가이드 콘텐츠 |

---

## 디렉토리 구조

```
my-sites/beachsafe/
├── CLAUDE.md
├── requirements.txt
├── data/
│   ├── raw/
│   ├── processed/
│   │   ├── beaches.json            # 전국 해수욕장 기본 정보
│   │   ├── beaches_safety.json     # 안전 정보 (위험구역, 익사사고 통계)
│   │   ├── fishing_spots.json      # 낚시 포인트 (비수기용)
│   │   └── drive_routes.json       # 해안 드라이브 코스
│   └── content/
│       ├── beach_guides/           # 해수욕장별 여행 가이드
│       └── seasonal/               # 계절별 콘텐츠
├── scripts/
│   ├── fetch_mof.py                # 해양수산부 해수욕장 API
│   ├── fetch_weather.py            # 기상청 날씨 API
│   ├── fetch_safety.py             # 행안부 물놀이 위험구역
│   ├── generate_guides.py          # AI 여행 가이드 생성
│   └── build_site.py
├── templates/
│   ├── base.html
│   ├── index.html                  # 메인 (지역별 해수욕장 지도)
│   ├── beach.html                  # 해수욕장 상세 (SEO 핵심)
│   ├── region.html                 # 지역별 목록 (강원/충남/전남/경남/제주)
│   ├── safety_guide.html           # 물놀이 안전 가이드
│   ├── fishing.html                # 낚시 정보 (비수기)
│   └── drive_route.html            # 해안 드라이브 코스
└── dist/
```

---

## Step 1: 데이터 수집

### A. 해양수산부 해수욕장 API (`scripts/fetch_mof.py`)

```python
"""
해양수산부 국가해수욕장 정보
공공데이터포털: "해수욕장 정보" 검색
API 엔드포인트: https://api.odcloud.kr/api/15077489/v1/uddi...
"""

import requests
import json
from pathlib import Path

MOF_API = "https://api.odcloud.kr/api/15077489/v1/uddi:..."

# 수집 필드
BEACH_SCHEMA = {
    "id": "str",                     # slug
    "name": "str",                   # 해수욕장명
    "region": "str",                 # 시도 (강원/충남/전남/경남/제주 등)
    "city": "str",                   # 시군구
    "address": "str",                # 주소
    "lat": "float",                  # 위도
    "lng": "float",                  # 경도
    "length": "float",               # 해안선 길이 (m)
    "area": "float",                 # 면적
    "season_start": "str",           # 개장일 (보통 7월 초)
    "season_end": "str",             # 폐장일 (보통 8월 말)
    "facilities": "list",            # 시설 (주차장/샤워실/화장실/구조대)
    "water_quality": "str",          # 수질 등급 (1~4등급)
    "safety_grade": "str",           # 안전등급
    "lifeguard": "bool",             # 인명구조대 운영 여부
    "danger_zones": "list",          # 위험구역 좌표
    "avg_wave": "float",             # 평균 파고 (m)
    "parking_capacity": "int",       # 주차 대수
    "nearby_attractions": "list",    # 주변 관광지
    "nearby_restaurants": "list",    # 주변 맛집 (AI 큐레이션)
    "nearby_accommodations": "list", # 주변 숙박
    # AI 생성
    "guide_intro": "str",            # 여행 가이드 도입부
    "best_time": "str",              # 방문 최적 시기
    "tips": "list",                  # 방문 팁 5가지
    "meta_description": "str",
    "tags": "list"
}

REGIONS = {
    "강원": ["속초", "강릉", "동해", "삼척"],
    "충남": ["태안", "보령", "서산"],
    "전북": ["부안", "고창"],
    "전남": ["여수", "완도", "신안"],
    "경남": ["거제", "통영", "남해"],
    "경북": ["포항", "영덕", "울진"],
    "제주": ["제주시", "서귀포시"],
    "부산": ["해운대", "광안리", "송도"],
    "인천": ["을왕리", "왕산"],
}

def fetch_all_beaches() -> list:
    """전국 해수욕장 전체 수집"""
    params = {
        "serviceKey": "MOF_API_KEY",  # 환경변수
        "type": "json",
        "numOfRows": 500,
        "pageNo": 1
    }
    resp = requests.get(MOF_API, params=params, timeout=30)
    data = resp.json()
    return data.get("items", [])
```

### B. 기상청 날씨 API (`scripts/fetch_weather.py`)

```python
"""
기상청 단기예보 API (해수욕장 위치 기반)
무료 API: https://www.data.go.kr/tcs/dss/selectApiDataDetailView.do?publicDataPk=15084084
"""

def fetch_beach_weather(lat: float, lng: float) -> dict:
    """해수욕장 좌표 기반 3일 날씨 예보"""
    # 기상청 격자 좌표로 변환 필요 (LCC 변환)
    nx, ny = latlon_to_grid(lat, lng)

    params = {
        "serviceKey": "KMA_API_KEY",
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": today_str(),
        "base_time": "0500",
        "nx": nx,
        "ny": ny
    }
    resp = requests.get(KMA_URL, params=params, timeout=15)
    data = resp.json()

    return {
        "wave_height": extract_value(data, "WAV"),   # 파고 (m)
        "temp": extract_value(data, "TMP"),           # 기온
        "rain_prob": extract_value(data, "POP"),      # 강수확률
        "wind_speed": extract_value(data, "WSD"),     # 풍속
        "sky": extract_value(data, "SKY"),            # 하늘상태
        "updated_at": now_str()
    }

# 날씨 데이터는 Cloudflare Workers KV에 일 1회 저장
# 정적 HTML에는 "로딩 중" → JS로 KV에서 가져와 렌더링
```

### C. 행안부 물놀이 위험구역 (`scripts/fetch_safety.py`)

```python
"""
행정안전부 물놀이 안전사고 현황 + 위험구역
공공데이터포털: "물놀이 안전사고" 검색
"""

SAFETY_DATA_SOURCES = {
    "위험구역": "행안부 물놀이 위험구역 고시",
    "사고통계": "소방청 수난사고 통계",
    "수질": "해양수산부 해수욕장 수질 등급"
}

# 안전 점수 계산 로직
def calculate_safety_score(beach: dict) -> dict:
    """
    해수욕장 안전 종합 점수 산출
    - 수질 등급 (30점)
    - 인명구조대 운영 (30점)
    - 위험구역 유무 (20점)
    - 최근 3년 사고 통계 (20점)
    """
    score = 0
    details = []

    if beach.get("water_quality") == "1등급":
        score += 30
        details.append("✅ 수질 1등급 (매우 좋음)")
    elif beach.get("water_quality") == "2등급":
        score += 20
        details.append("✅ 수질 2등급 (좋음)")
    else:
        details.append("⚠️ 수질 확인 필요")

    if beach.get("lifeguard"):
        score += 30
        details.append("✅ 인명구조대 운영")
    else:
        details.append("❌ 인명구조대 없음 — 주의 필요")

    if not beach.get("danger_zones"):
        score += 20
        details.append("✅ 위험구역 없음")
    else:
        details.append(f"⚠️ 위험구역 {len(beach['danger_zones'])}개 지정")

    grade = "안전" if score >= 70 else "주의" if score >= 40 else "위험"

    return {
        "score": score,
        "grade": grade,
        "details": details,
        "badge_color": "green" if grade == "안전" else "yellow" if grade == "주의" else "red"
    }
```

---

## Step 2: AI 가이드 생성 (`scripts/generate_guides.py`)

```python
BEACH_GUIDE_SYSTEM = """해수욕장 여행 전문 블로그 작가입니다.
가족 여행객, 연인, 서핑러를 위한 실용적인 해수욕장 가이드를 작성하세요.

JSON 출력:
{
  "guide_intro": "이 해수욕장의 매력 도입부 (200자)",
  "best_for": ["이런 분께 추천 3가지"],
  "best_time": "방문 최적 시기 (월 기준, 이유 포함, 100자)",
  "tips": ["방문 팁 5가지 (각 50자)"],
  "cautions": ["주의사항 3가지"],
  "nearby_must": "근처 꼭 가볼 곳 (100자)",
  "parking_tip": "주차 팁 (100자)",
  "seo_title": "SEO 제목 (60자, 지역명+해수욕장명+특징)",
  "meta_description": "메타 설명 (155자)"
}"""

# 생성 대상: 전국 248개 해수욕장 × 1개 가이드
# 추가: 지역별 해수욕장 TOP 5 비교 포스트 17개 (시도별)
```

---

## Step 3: 사이트 빌드

### 해수욕장 상세 페이지 구성 (`templates/beach.html`)

```html
<!-- 1. 히어로 섹션 -->
<div class="hero relative">
  <img src="{{ beach.thumbnail }}" alt="{{ beach.name }}">
  <div class="hero-overlay">
    <h1>{{ beach.name }}</h1>
    <p>{{ beach.region }} · {{ beach.city }}</p>

    <!-- 안전등급 뱃지 -->
    <div class="safety-badge bg-{{ beach.safety.badge_color }}-500">
      {{ beach.safety.grade }} · {{ beach.safety.score }}점
    </div>
  </div>
</div>

<!-- 2. 오늘 날씨 (JS로 동적 로딩) -->
<div id="weather-widget" data-beach-id="{{ beach.id }}">
  <div class="loading">날씨 로딩 중...</div>
</div>

<!-- 3. 핵심 정보 카드 -->
<div class="info-grid grid grid-cols-2 md:grid-cols-4 gap-4">
  <div class="info-card">
    <span class="icon">🏊</span>
    <span class="label">수질</span>
    <span class="value">{{ beach.water_quality }}</span>
  </div>
  <div class="info-card">
    <span class="icon">🚑</span>
    <span class="label">구조대</span>
    <span class="value">{{ "운영" if beach.lifeguard else "없음" }}</span>
  </div>
  <div class="info-card">
    <span class="icon">📅</span>
    <span class="label">개장</span>
    <span class="value">{{ beach.season_start }}~{{ beach.season_end }}</span>
  </div>
  <div class="info-card">
    <span class="icon">🅿️</span>
    <span class="label">주차</span>
    <span class="value">{{ beach.parking_capacity }}대</span>
  </div>
</div>

<!-- 4. 안전정보 상세 -->
<section class="safety-section">
  <h2>⚠️ 안전정보</h2>
  {% for detail in beach.safety.details %}
  <div class="safety-item">{{ detail }}</div>
  {% endfor %}
  {% if beach.danger_zones %}
  <div class="danger-zone-map" data-zones="{{ beach.danger_zones | tojson }}">
    <!-- Kakao Map으로 위험구역 표시 -->
  </div>
  {% endif %}
</section>

<!-- 5. AI 여행 가이드 -->
<section>
  <h2>📍 여행 가이드</h2>
  <p>{{ beach.guide_intro }}</p>
  <h3>이런 분께 추천</h3>
  <ul>{% for item in beach.best_for %}<li>{{ item }}</li>{% endfor %}</ul>
  <h3>방문 팁</h3>
  <ul>{% for tip in beach.tips %}<li>{{ tip }}</li>{% endfor %}</ul>
</section>

<!-- 6. AdSense -->
{{ adsense.render("rectangle_mid") }}

<!-- 7. CPA — 숙박 예약 -->
<div class="accommodation-cta">
  <h2>🏨 근처 숙박 예약</h2>
  <a href="{{ cpa.yanolja_url }}" class="btn-yanolja">야놀자에서 보기</a>
  <a href="{{ cpa.yeogi_url }}" class="btn-yeogi">여기어때에서 보기</a>
</div>

<!-- 8. 주변 정보 -->
<section>
  <h2>📍 주변 관광지</h2>
  <!-- ... -->
</section>
```

---

## Step 4: 비수기 콘텐츠 (겨울 트래픽 유지)

### 낚시 포인트 페이지 (`templates/fishing.html`)

```python
# 해수욕장 → 낚시 포인트 연계
FISHING_SPOTS = {
    "해운대해수욕장": {
        "fishing_name": "해운대 방파제 낚시",
        "species": ["감성돔", "볼락", "고등어"],
        "best_season": ["10월", "11월", "12월", "1월"],
        "difficulty": "초보",
        "equipment": ["릴낚시", "원투낚시"],
        "tip": "서방파제 끝부분이 포인트"
    }
}

# 낚시 관련 쿠팡파트너스 (CPC 높음)
FISHING_CPA = {
    "릴낚시대": "https://link.coupang.com/a/fishing-rod",
    "루어": "https://link.coupang.com/a/lure",
    "낚시가방": "https://link.coupang.com/a/fishing-bag"
}
```

### 해안 드라이브 코스 페이지

```python
DRIVE_ROUTES = [
    {
        "name": "동해안 해안도로 드라이브",
        "region": "강원",
        "distance_km": 150,
        "duration_hr": 3,
        "highlights": ["경포대", "정동진", "망상해수욕장"],
        "best_season": "연중",
        "seo_keywords": ["동해 드라이브 코스", "강원도 해안도로"]
    },
    {
        "name": "남해 독일마을 해안도로",
        "region": "경남",
        "distance_km": 80,
        "duration_hr": 2,
        "highlights": ["독일마을", "물건방조어부림", "미조항"],
        "seo_keywords": ["남해 드라이브", "경남 해안도로"]
    }
    # ... 전국 17개 코스
]
```

---

## Step 5: SEO 전략

### 시즌별 키워드

| 시기 | 키워드 | 검색량 |
|------|--------|--------|
| 6~8월 | {지역} 해수욕장 추천 | 매우 높음 |
| 6~8월 | {해수욕장명} 수질 | 높음 |
| 6~8월 | 해수욕장 물놀이 안전 | 높음 |
| 9~11월 | {해수욕장} 낚시 | 중간 |
| 10~2월 | {해안} 드라이브 코스 | 중간 |
| 연중 | {지역} 바다 여행 | 높음 |

### 지역 페이지 구조 (`/region/gangwon/`)

```
강원도 해수욕장 TOP 10 페이지:
1. H1: "강원도 해수욕장 추천 TOP 10 — 수질·안전 비교"
2. 비교 테이블 (수질/안전등급/시설/거리)
3. 지도 (Kakao Map 마커)
4. 각 해수욕장 카드 (링크)
5. 강원도 해수욕장 여행 팁 (AI 생성)
6. 숙박 CPA
```

---

## Step 6: 수익화

```python
# 여름 시즌 수익원
SUMMER_REVENUE = {
    "adsense": "RPM 1,200~2,000원 (여행 카테고리 고단가)",
    "숙박_yanolja": "예약 건당 2,000~5,000원 CPA",
    "숙박_yeogi": "예약 건당 1,500~4,000원 CPA",
    "선크림_쿠팡": "구매액 3% 파트너스",
    "물놀이용품_쿠팡": "구매액 3% 파트너스"
}

# 비수기 수익원
WINTER_REVENUE = {
    "낚시용품_쿠팡": "구매액 3% (낚시 CPC 매우 높음)",
    "adsense": "RPM 700~1,200원",
    "숙박": "겨울 바다 여행 수요"
}
```

---

## GitHub Actions Job

```yaml
deploy-beachsafe:
  runs-on: ubuntu-latest
  if: |
    github.event_name == 'workflow_dispatch' ||
    (github.event.schedule == '0 20 * * *' &&
     (fromJSON(env.CURRENT_MONTH) >= 6 && fromJSON(env.CURRENT_MONTH) <= 8)) ||
    github.event.schedule == '0 20 * * 0'
  # 여름(6~8월): 매일 / 비수기: 주 1회
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - run: pip install -r beachsafe/requirements.txt

    - name: Fetch beach data
      run: python beachsafe/scripts/fetch_mof.py
      env:
        MOF_API_KEY: ${{ secrets.MOF_API_KEY }}
        KMA_API_KEY: ${{ secrets.KMA_API_KEY }}

    - name: Generate AI guides (weekly)
      if: github.event.schedule == '0 20 * * 0'
      run: python beachsafe/scripts/generate_guides.py
      env:
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

    - name: Build site
      run: python beachsafe/scripts/build_site.py

    - name: Deploy
      run: npx wrangler pages deploy beachsafe/dist --project-name=beachsafe
      env:
        CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## 환경변수 추가분

| 변수명 | 설명 |
|--------|------|
| `MOF_API_KEY` | 해양수산부 API (data.go.kr 신청) |
| `KMA_API_KEY` | 기상청 단기예보 API (data.go.kr 신청) |
| `KAKAO_MAP_API_KEY` | Kakao Map JS API 키 (kakao developers) |

---

## 클로드 코드 실행 순서

```bash
cd my-sites/beachsafe

# 1. API 키 준비
# - data.go.kr: 해양수산부 해수욕장, 기상청 단기예보
# - kakao developers: JS 지도 API

# 2. 기본 데이터 수집
python scripts/fetch_mof.py       # 해수욕장 248개
python scripts/fetch_safety.py    # 안전정보

# 3. AI 가이드 생성 (248개 해수욕장, Batch)
python scripts/generate_guides.py

# 4. 빌드
python scripts/build_site.py

# 5. 로컬 확인
python -m http.server 8004 --directory dist &

# 6. 배포
npx wrangler pages project create beachsafe
npx wrangler pages deploy dist --project-name=beachsafe
```

---

## 성공 지표 (90일 — 여름 런칭 기준)

| 지표 | 최악 | 보통 |
|------|------|------|
| 해수욕장 페이지 | 248개 | 248개 + 드라이브·낚시 300개+ |
| 시즌 피크 일 방문자 | 500명 | 5,000명 |
| 여름 3개월 누적 | 15,000명 | 150,000명 |
| AdSense 여름 수익 | 15,000원 | 270,000원 |
| 숙박 CPA 여름 수익 | 0원 | 100,000원+ |
| **여름 3개월 총 수익** | **15,000원** | **370,000원** |

> ⏰ 런칭 타이밍이 핵심: 3~4월 구축 완료, 5월 Search Console 등록, 6월 이전 인덱싱 목표
