# CLAUDE.md — uapress.kr (문화행사·축제 캘린더)

## 프로젝트 개요

**도메인:** https://uapress.kr
**레포 위치:** `ua-sites/uapress/`
**CF Pages 프로젝트명:** `uapress`
**사이트 성격:** 전국 문화행사·축제 캘린더 + 무료행사 특화
**이전 플랫폼:** WordPress (Cloudways) → 완전 폐기, 정적 사이트로 전환
**AdSense:** 기승인 완료 — publisher ID를 base.html에 그대로 삽입하면 즉시 광고 노출

---

## ⚠️ 전환 전 필수 확인 (Claude Code 작업 시작 전 마스터가 직접)

```
체크리스트:
[ ] Cloudflare에 uapress.kr 사이트 추가 완료
[ ] 도메인 등록기관에서 네임서버 → Cloudflare로 변경 완료
[ ] Cloudflare 네임서버 전파 확인 (https://dnschecker.org/#NS/uapress.kr)
[ ] AdSense 대시보드에서 publisher ID 복사해두기 (ca-pub-XXXXXXXXXX)
[ ] Google Search Console에서 기존 sitemap 삭제
    (Search Console → uapress.kr → Sitemaps → 기존 항목 제거)
```

위 체크리스트 완료 후 Claude Code 작업 시작.

---

## 기술 스택

| 레이어 | 선택 | 비고 |
|--------|------|------|
| 빌더 | Python 3.11 + Jinja2 | 정적 HTML 생성 |
| 데이터 | 한국관광공사 Tour API | 무료, 일 10만건 |
| 데이터 보완 | 문화체육관광부 문화행사 API | 무료 |
| 달력 UI | FullCalendar 6.x (CDN) | 무료 오픈소스 |
| 검색 | Fuse.js (CDN) | 클라이언트 사이드, 서버 불필요 |
| CSS | Tailwind CSS CDN Play | 빌드 없음 |
| 폰트 | Noto Sans KR (Google Fonts) | 한국어 최적화 |
| 배포 | Cloudflare Pages | 무료, 트래픽 무제한 |
| CI/CD | GitHub Actions (Public repo) | 무료 무제한 |
| AI | Claude Haiku 4.5 Batch API | 행사 요약·주간 큐레이션 |
| 광고 | Google AdSense (기승인) | publisher ID 그대로 사용 |

---

## 디렉토리 구조

```
ua-sites/uapress/
├── CLAUDE.md                        # 이 파일
├── requirements.txt
├── .env.example
├── .gitignore
├── .github/
│   └── workflows/
│       └── deploy.yml               # 자동 배포 워크플로우
├── data/
│   ├── raw/                         # API 원본 (git 제외)
│   ├── processed/
│   │   ├── events.json              # 전체 행사 목록
│   │   ├── events_by_region.json    # 지역별
│   │   ├── events_by_month.json     # 월별
│   │   ├── free_events.json         # 무료 행사만
│   │   └── search_index.json        # Fuse.js 검색 인덱스
│   └── content/
│       ├── weekly_picks/            # 주간 AI 큐레이션 JSON
│       └── festival_guides/         # 축제 가이드 JSON
├── scripts/
│   ├── fetch_tour.py                # Tour API 수집
│   ├── fetch_culture.py             # 문화부 API 수집
│   ├── process_events.py            # 데이터 정제·분류
│   ├── generate_content.py          # Claude Batch AI 콘텐츠
│   ├── build_search_index.py        # Fuse.js 인덱스 생성
│   └── build_site.py               # Jinja2 → HTML 빌드
├── templates/
│   ├── base.html                    # 공통 레이아웃 (AdSense 포함)
│   ├── index.html                   # 메인
│   ├── event.html                   # 행사 상세 (SEO 핵심)
│   ├── region.html                  # 지역별 목록
│   ├── monthly.html                 # 월별 캘린더
│   ├── category.html                # 카테고리별
│   ├── free.html                    # 무료 행사 특화
│   ├── weekly_pick.html             # 주간 AI 큐레이션
│   └── festival_guide.html          # 축제 가이드
├── static/
│   ├── css/
│   │   └── custom.css               # Tailwind 보완용 최소 CSS
│   ├── js/
│   │   └── main.js                  # 지역 탭 필터, 달력 초기화
│   └── img/
│       └── og-default.png           # OG 기본 이미지
└── dist/                            # 빌드 결과물 (CF Pages 배포 루트)
    └── .gitkeep
```

---

## Step 1: 환경 설정

### `.env.example`

```bash
# Tour API (data.go.kr → "한국관광공사_관광정보서비스_GW" 신청)
TOUR_API_KEY=

# 문화부 API (data.go.kr → "문화체육관광부_공연전시정보" 신청)
CULTURE_API_KEY=

# Claude API
ANTHROPIC_API_KEY=

# AdSense (기승인 — 대시보드에서 복사)
ADSENSE_PUBLISHER_ID=ca-pub-XXXXXXXXXX

# AdSense 광고 단위 ID (AdSense → 광고 → 광고 단위 기준에서 생성)
ADSENSE_UNIT_BANNER=
ADSENSE_UNIT_RECTANGLE=
ADSENSE_UNIT_INFEED=

# Cloudflare
CLOUDFLARE_API_TOKEN=
CLOUDFLARE_ACCOUNT_ID=

# 사이트
SITE_DOMAIN=https://uapress.kr
SITE_NAME=이번주 행사
```

### `.gitignore`

```
.env
data/raw/
data/processed/
data/content/
dist/
__pycache__/
*.pyc
.venv/
```

### `requirements.txt`

```
anthropic>=0.40.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
jinja2>=3.1.0
python-dotenv>=1.0.0
pytz>=2024.1
```

---

## Step 2: Tour API 수집 (`scripts/fetch_tour.py`)

```python
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
API_KEY = os.getenv("TOUR_API_KEY")

# 17개 시도 지역코드
AREA_CODES = {
    "1": "서울", "2": "인천", "3": "대전", "4": "대구",
    "5": "광주", "6": "부산", "7": "울산", "8": "세종",
    "31": "경기", "32": "강원", "33": "충북", "34": "충남",
    "35": "경북", "36": "경남", "37": "전북", "38": "전남",
    "39": "제주"
}

def fetch_events(start_date: str, end_date: str) -> list:
    """
    기간별 전국 행사 수집
    start_date, end_date: YYYYMMDD
    """
    all_events = []

    for area_code, area_name in AREA_CODES.items():
        page = 1
        while True:
            params = {
                "serviceKey": API_KEY,
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
    """행사 상세 정보 (관람료·주최·설명)"""
    params = {
        "serviceKey": API_KEY,
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
    """행사 소개 정보 (관람료·공연시간 등)"""
    params = {
        "serviceKey": API_KEY,
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
    # 오늘 ~ 3개월 후까지 수집
    today = datetime.now()
    end = today + timedelta(days=90)

    start_str = today.strftime("%Y%m%d")
    end_str = end.strftime("%Y%m%d")

    print(f"수집 기간: {start_str} ~ {end_str}")
    events = fetch_events(start_str, end_str)

    # 상세 정보 추가 (상위 500개만 — API 호출 제한)
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

    # 저장
    Path("data/raw").mkdir(parents=True, exist_ok=True)
    out = Path(f"data/raw/events_{start_str}.json")
    out.write_text(json.dumps(events, ensure_ascii=False, indent=2))
    print(f"\n저장 완료: {out} ({len(events)}개)")
```

---

## Step 3: 데이터 정제 (`scripts/process_events.py`)

```python
"""
원본 행사 데이터 정제·분류·슬러그 생성
"""

import json
import re
from pathlib import Path
from datetime import datetime

def make_slug(content_id: str, title: str) -> str:
    """URL 슬러그 생성"""
    # 한글 제거 후 영문·숫자만
    en = re.sub(r'[^a-zA-Z0-9\s]', '', title).strip()
    en = re.sub(r'\s+', '-', en).lower()[:40]
    return f"{content_id}-{en}" if en else content_id


def detect_category(title: str, overview: str) -> str:
    """제목·설명으로 카테고리 자동 분류"""
    text = title + " " + overview

    rules = {
        "축제": ["축제", "페스티벌", "festival", "잔치", "한마당"],
        "공연": ["공연", "콘서트", "뮤지컬", "연극", "오페라", "국악", "클래식"],
        "전시": ["전시", "박람회", "엑스포", "아트페어", "갤러리"],
        "체험": ["체험", "만들기", "클래스", "워크숍", "교육"],
        "스포츠": ["마라톤", "달리기", "자전거", "스포츠", "경기", "대회"],
        "문화행사": [],  # 기본값
    }

    for category, keywords in rules.items():
        if any(kw in text for kw in keywords):
            return category
    return "문화행사"


def is_free(fee: str, title: str) -> bool:
    """무료 여부 판단"""
    if not fee:
        return False
    free_keywords = ["무료", "free", "0원", "없음"]
    paid_keywords = ["유료", "원", "₩"]
    fee_lower = fee.lower()
    if any(kw in fee_lower for kw in free_keywords):
        return True
    if any(kw in fee for kw in paid_keywords):
        return False
    # 제목에 무료 포함
    return "무료" in title


def process_events(raw_path: str) -> list:
    raw = json.loads(Path(raw_path).read_text())
    today = datetime.now().strftime("%Y%m%d")
    processed = []

    for item in raw:
        # 이미 종료된 행사 제외
        if item.get("end_date", "") < today:
            continue
        # 제목 없는 항목 제외
        if not item.get("title"):
            continue

        slug = make_slug(item["content_id"], item["title"])
        category = detect_category(item["title"], item.get("overview", ""))
        free = is_free(item.get("fee", ""), item["title"])

        # 날짜 포맷 변환 (YYYYMMDD → YYYY-MM-DD)
        def fmt(d):
            return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d

        processed.append({
            "id": slug,
            "content_id": item["content_id"],
            "title": item["title"],
            "category": category,
            "region": item["region"],
            "area_code": item["area_code"],
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
            # AI 생성 필드 (generate_content.py에서 채움)
            "summary": "",
            "highlight": "",
            "target_audience": "",
            "tips": [],
            "seo_title": "",
            "meta_description": "",
            "tags": [],
        })

    # 지역별 저장
    by_region = {}
    by_month = {}

    for e in processed:
        r = e["region"]
        by_region.setdefault(r, []).append(e)

        m = e["start_date"][:6]  # YYYYMM
        by_month.setdefault(m, []).append(e)

    out = Path("data/processed")
    out.mkdir(parents=True, exist_ok=True)

    (out / "events.json").write_text(
        json.dumps(processed, ensure_ascii=False, indent=2))
    (out / "events_by_region.json").write_text(
        json.dumps(by_region, ensure_ascii=False, indent=2))
    (out / "events_by_month.json").write_text(
        json.dumps(by_month, ensure_ascii=False, indent=2))
    (out / "free_events.json").write_text(
        json.dumps([e for e in processed if e["is_free"]],
                   ensure_ascii=False, indent=2))

    print(f"정제 완료: {len(processed)}개 (무료: {sum(1 for e in processed if e['is_free'])}개)")
    return processed


if __name__ == "__main__":
    import glob
    files = sorted(glob.glob("data/raw/events_*.json"), reverse=True)
    if not files:
        print("raw 데이터 없음. fetch_tour.py 먼저 실행하세요.")
    else:
        process_events(files[0])
```

---

## Step 4: AI 콘텐츠 생성 (`scripts/generate_content.py`)

```python
"""
Claude Haiku 4.5 Batch API — 행사 요약 + 주간 큐레이션
비용: $0.5/$2.5 per MTok (Batch 50% 할인)
행사 1건 평균: 입력 ~600토큰 + 출력 ~400토큰
1,000건 처리 비용: 약 $1.3
"""

import anthropic
import json
import time
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = "claude-haiku-4-5-20251001"

# ─────────────────────────────────────────
# A. 행사별 SEO 요약 (Batch)
# ─────────────────────────────────────────

EVENT_SYSTEM = """문화행사 큐레이션 전문가입니다. 주어진 행사 정보로 SEO 최적화 콘텐츠를 작성하세요.
반드시 JSON만 출력 (마크다운 코드블록 없이):
{
  "seo_title": "SEO 제목 60자 이내 (지역명+행사명+특징 키워드 포함)",
  "meta_description": "메타 설명 155자 이내 (언제·어디서·무엇을·왜 가야 하는지)",
  "summary": "행사 핵심 요약 3줄 (각 줄 60자 이내, \\n 구분)",
  "highlight": "이 행사만의 특별한 포인트 100자",
  "target_audience": "가족여행|커플|친구모임|혼자|어린이동반",
  "target_reason": "추천 대상 이유 60자",
  "tips": ["방문 팁 1", "방문 팁 2", "방문 팁 3"],
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"]
}"""

def build_event_requests(events: list) -> list:
    reqs = []
    for e in events:
        # 이미 AI 콘텐츠 있으면 스킵
        if e.get("seo_title"):
            continue

        msg = f"""행사명: {e['title']}
지역: {e['region']} {e.get('address', '')}
장소: {e.get('place', '')}
기간: {e['start_date_fmt']} ~ {e['end_date_fmt']}
관람료: {e.get('fee', '미확인')}
주최: {e.get('organizer', '')}
설명: {e.get('overview', '')[:400]}"""

        reqs.append({
            "custom_id": f"event-{e['id']}",
            "params": {
                "model": MODEL,
                "max_tokens": 500,
                "system": EVENT_SYSTEM,
                "messages": [{"role": "user", "content": msg}]
            }
        })
    return reqs


def run_event_batch(events: list) -> dict:
    reqs = build_event_requests(events)
    if not reqs:
        print("모든 행사 AI 콘텐츠 이미 존재")
        return {}

    print(f"Batch 제출: {len(reqs)}개")
    batch = client.beta.messages.batches.create(requests=reqs)
    batch_id = batch.id
    print(f"Batch ID: {batch_id}")

    # 폴링
    while True:
        b = client.beta.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            break
        print(f"  처리 중... (완료: {b.request_counts.succeeded})")
        time.sleep(300)  # 5분 대기

    # 결과 수집
    results = {}
    for r in client.beta.messages.batches.results(batch_id):
        if r.result.type == "succeeded":
            try:
                results[r.custom_id] = json.loads(
                    r.result.message.content[0].text)
            except Exception:
                pass

    print(f"Batch 완료: {len(results)}개 성공")
    return results


# ─────────────────────────────────────────
# B. 주간 AI 큐레이션 (단일 호출 — 주 1회)
# ─────────────────────────────────────────

WEEKLY_SYSTEM = """주말 나들이 전문 에디터입니다. 이번 주 추천 행사 TOP 5를 선정하세요.
JSON만 출력:
{
  "title": "이번 주 가볼 만한 행사 TOP 5 (날짜 포함)",
  "intro": "이번 주 행사 트렌드 요약 200자",
  "picks": [
    {
      "rank": 1,
      "event_id": "행사 id",
      "title": "행사명",
      "reason": "추천 이유 100자",
      "must_see": "꼭 봐야 할 포인트 80자",
      "tip": "실용 방문 팁 80자"
    }
  ],
  "hidden_gem": "덜 알려진 추천 행사 소개 200자",
  "next_week_preview": "다음 주 주목 행사 100자"
}"""

def generate_weekly_pick(events: list) -> dict:
    today = datetime.now()
    week_end = today + timedelta(days=7)

    # 이번 주 행사 필터
    this_week = [
        e for e in events
        if (e["start_date"] <= week_end.strftime("%Y%m%d")
            and e["end_date"] >= today.strftime("%Y%m%d"))
    ]

    # 후보 30개 (무료 우선 정렬)
    candidates = sorted(this_week, key=lambda x: x["is_free"], reverse=True)[:30]

    prompt = f"이번 주 ({today.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')}) 행사 후보:\n"
    for i, e in enumerate(candidates, 1):
        free_tag = "[무료] " if e["is_free"] else ""
        prompt += f"{i}. {free_tag}[{e['region']}] {e['title']} (id: {e['id']}, {e['start_date_fmt']}~{e['end_date_fmt']})\n"

    resp = client.messages.create(
        model=MODEL,
        max_tokens=700,
        system=WEEKLY_SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )

    result = json.loads(resp.content[0].text)
    week_str = today.strftime("%Y-W%V")

    out_dir = Path("data/content/weekly_picks")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{week_str}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2))

    print(f"주간 큐레이션 생성: {week_str}")
    return result


# ─────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────

if __name__ == "__main__":
    import sys

    events_path = Path("data/processed/events.json")
    if not events_path.exists():
        print("process_events.py 먼저 실행하세요.")
        sys.exit(1)

    events = json.loads(events_path.read_text())

    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode in ("all", "events"):
        # 행사 AI 요약 Batch
        results = run_event_batch(events)

        # 결과 병합
        id_map = {e["id"]: e for e in events}
        for custom_id, ai_data in results.items():
            event_id = custom_id.replace("event-", "", 1)
            if event_id in id_map:
                id_map[event_id].update(ai_data)

        events = list(id_map.values())
        events_path.write_text(json.dumps(events, ensure_ascii=False, indent=2))
        print("행사 AI 콘텐츠 병합 완료")

    if mode in ("all", "weekly"):
        generate_weekly_pick(events)
```

---

## Step 5: 검색 인덱스 (`scripts/build_search_index.py`)

```python
"""Fuse.js 검색 인덱스 생성"""

import json
from pathlib import Path
from datetime import datetime

def build_index():
    events = json.loads(Path("data/processed/events.json").read_text())
    today = datetime.now().strftime("%Y%m%d")

    index = []
    for e in events:
        if e["end_date"] < today:
            continue
        index.append({
            "id": e["id"],
            "title": e["title"],
            "region": e["region"],
            "category": e["category"],
            "is_free": e["is_free"],
            "start_date": e["start_date"],
            "end_date": e["end_date"],
            "start_date_fmt": e.get("start_date_fmt", ""),
            "place": e.get("place", ""),
            "tags": e.get("tags", []),
            "url": f"/event/{e['id']}/"
        })

    out = {
        "updated_at": datetime.now().isoformat(),
        "total": len(index),
        "events": index
    }

    Path("dist").mkdir(exist_ok=True)
    Path("dist/search-index.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")))

    print(f"검색 인덱스 생성: {len(index)}개")


if __name__ == "__main__":
    build_index()
```

---

## Step 6: 사이트 빌드 (`scripts/build_site.py`)

```python
"""
Jinja2 → 정적 HTML 빌드
생성 페이지:
  / → 메인 (이번 주 행사 + 지역 탭)
  /event/{id}/ → 행사 상세 (SEO 핵심, 수천 개)
  /region/{slug}/ → 17개 지역별 목록
  /2026/06/ → 월별 캘린더
  /category/{slug}/ → 5개 카테고리
  /free/ → 무료 행사 특화
  /weekly/{week}/ → 주간 AI 큐레이션
  /sitemap.xml, /robots.txt
"""

import json
import shutil
import os
from pathlib import Path
from datetime import datetime
from jinja2 import Environment, FileSystemLoader

load_dotenv = __import__("dotenv").load_dotenv
load_dotenv()

SITE_DOMAIN = os.getenv("SITE_DOMAIN", "https://uapress.kr")
SITE_NAME = os.getenv("SITE_NAME", "이번주 행사")
ADSENSE_PUBLISHER_ID = os.getenv("ADSENSE_PUBLISHER_ID", "")
ADSENSE_UNIT_BANNER = os.getenv("ADSENSE_UNIT_BANNER", "")
ADSENSE_UNIT_RECTANGLE = os.getenv("ADSENSE_UNIT_RECTANGLE", "")

DIST = Path("dist")
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
    events = json.loads(Path("data/processed/events.json").read_text())
    by_region = json.loads(Path("data/processed/events_by_region.json").read_text())
    by_month = json.loads(Path("data/processed/events_by_month.json").read_text())
    free_events = json.loads(Path("data/processed/free_events.json").read_text())

    weekly_files = sorted(Path("data/content/weekly_picks").glob("*.json"), reverse=True)
    weekly_pick = json.loads(weekly_files[0].read_text()) if weekly_files else {}

    return events, by_region, by_month, free_events, weekly_pick


def setup_env():
    env = Environment(loader=FileSystemLoader("templates"), autoescape=True)

    # 공통 컨텍스트
    env.globals.update({
        "site_domain": SITE_DOMAIN,
        "site_name": SITE_NAME,
        "build_date": BUILD_DATE,
        "adsense_publisher_id": ADSENSE_PUBLISHER_ID,
        "adsense_unit_banner": ADSENSE_UNIT_BANNER,
        "adsense_unit_rectangle": ADSENSE_UNIT_RECTANGLE,
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

    # dist 초기화
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    # 정적 파일 복사
    if Path("static").exists():
        shutil.copytree("static", DIST / "static")

    events, by_region, by_month, free_events, weekly_pick = load_data()
    env = setup_env()

    today = datetime.now().strftime("%Y%m%d")
    active = [e for e in events if e["end_date"] >= today]

    # 1. 메인 페이지
    tmpl = env.get_template("index.html")
    this_week_events = sorted(active, key=lambda x: x["start_date"])[:60]
    write(DIST / "index.html", tmpl.render(
        events=this_week_events,
        free_count=len(free_events),
        weekly_pick=weekly_pick,
        page_url="/"
    ))
    print(f"  메인 생성")

    # 2. 행사 상세 페이지 (핵심 SEO)
    tmpl = env.get_template("event.html")
    for e in active:
        path = DIST / "event" / e["id"] / "index.html"
        write(path, tmpl.render(event=e, page_url=f"/event/{e['id']}/"))
    print(f"  행사 상세: {len(active)}개")

    # 3. 지역별 페이지
    tmpl = env.get_template("region.html")
    for region, slug in REGION_SLUGS.items():
        region_events = [e for e in active if e["region"] == region]
        if not region_events:
            continue
        path = DIST / "region" / slug / "index.html"
        write(path, tmpl.render(
            region=region,
            slug=slug,
            events=region_events,
            page_url=f"/region/{slug}/"
        ))
    print(f"  지역별: {len(REGION_SLUGS)}개")

    # 4. 월별 페이지
    tmpl = env.get_template("monthly.html")
    for month_key, month_events in by_month.items():
        year = month_key[:4]
        month = month_key[4:6]
        path = DIST / year / month / "index.html"
        active_month = [e for e in month_events if e["end_date"] >= today]
        if not active_month:
            continue
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

    # 6. 무료 행사 특화 페이지
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

    # 8. 검색 인덱스 복사
    idx = Path("dist/search-index.json")
    if not idx.exists():
        __import__("build_search_index").build_index()

    # 9. sitemap.xml
    build_sitemap(active, env)

    # 10. robots.txt
    (DIST / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_DOMAIN}/sitemap.xml\n"
    )

    total = sum(1 for _ in DIST.rglob("*.html"))
    print(f"\n빌드 완료: {total}개 HTML 페이지")


def build_sitemap(events: list, env):
    urls = [
        {"loc": "/", "priority": "1.0", "changefreq": "daily"},
        {"loc": "/free/", "priority": "0.9", "changefreq": "daily"},
    ]

    for region_slug in REGION_SLUGS.values():
        urls.append({"loc": f"/region/{region_slug}/", "priority": "0.8", "changefreq": "weekly"})

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
```

---

## Step 7: 핵심 템플릿

### `templates/base.html`

```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{% block title %}{{ site_name }}{% endblock %}</title>
  <meta name="description" content="{% block description %}전국 문화행사·축제 정보. 이번 주 가볼 만한 행사를 찾아보세요.{% endblock %}">
  <link rel="canonical" href="{{ site_domain }}{{ page_url }}">

  <!-- OG 태그 -->
  <meta property="og:title" content="{% block og_title %}{{ site_name }}{% endblock %}">
  <meta property="og:description" content="{% block og_desc %}전국 문화행사·축제 캘린더{% endblock %}">
  <meta property="og:url" content="{{ site_domain }}{{ page_url }}">
  <meta property="og:type" content="website">
  <meta property="og:image" content="{{ site_domain }}/static/img/og-default.png">
  <meta property="og:locale" content="ko_KR">
  <meta property="og:site_name" content="{{ site_name }}">

  <!-- Naver 사이트 인증 (기존 WP에서 복사) -->
  <meta name="naver-site-verification" content="d9098da3005c33ec5e401f6bb8f34215638f8fc6">

  <!-- Google 사이트 인증 (기존 WP에서 복사) -->
  <meta name="google-site-verification" content="FLkAJP2PIXUYwJ6e4k01ES5SMguaeHbrG3VhsuyT5BM">

  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>

  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">

  <!-- AdSense (기승인 publisher ID 그대로 사용) -->
  {% if adsense_publisher_id %}
  <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={{ adsense_publisher_id }}"
    crossorigin="anonymous"></script>
  {% endif %}

  <!-- 구조화 데이터 -->
  {% block json_ld %}{% endblock %}

  <style>
    body { font-family: 'Noto Sans KR', sans-serif; }
    .line-clamp-2 { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  </style>
</head>
<body class="bg-gray-50 text-gray-800">

  <!-- 헤더 -->
  <header class="bg-white shadow-sm sticky top-0 z-50">
    <div class="max-w-6xl mx-auto px-4 py-3 flex justify-between items-center">
      <a href="/" class="text-xl font-bold text-blue-600">🎪 {{ site_name }}</a>
      <nav class="hidden md:flex gap-6 text-sm font-medium text-gray-600">
        <a href="/free/" class="hover:text-blue-600">무료행사</a>
        <a href="/category/festival/" class="hover:text-blue-600">축제</a>
        <a href="/category/performance/" class="hover:text-blue-600">공연</a>
        <a href="/category/exhibition/" class="hover:text-blue-600">전시</a>
      </nav>
    </div>
  </header>

  <!-- 메인 콘텐츠 -->
  <main class="max-w-6xl mx-auto px-4 py-8">
    {% block content %}{% endblock %}
  </main>

  <!-- 광고 매크로 -->
  {% macro adsense_banner() %}
  {% if adsense_publisher_id and adsense_unit_banner %}
  <div class="my-6">
    <ins class="adsbygoogle"
      style="display:block"
      data-ad-client="{{ adsense_publisher_id }}"
      data-ad-slot="{{ adsense_unit_banner }}"
      data-ad-format="auto"
      data-full-width-responsive="true"></ins>
    <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
  </div>
  {% endif %}
  {% endmacro %}

  {% macro adsense_rectangle() %}
  {% if adsense_publisher_id and adsense_unit_rectangle %}
  <div class="my-4 text-center">
    <ins class="adsbygoogle"
      style="display:inline-block;width:336px;height:280px"
      data-ad-client="{{ adsense_publisher_id }}"
      data-ad-slot="{{ adsense_unit_rectangle }}"></ins>
    <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
  </div>
  {% endif %}
  {% endmacro %}

  <!-- 푸터 -->
  <footer class="bg-white border-t mt-16 py-8 text-sm text-gray-500 text-center">
    <div class="max-w-6xl mx-auto px-4">
      <p>© {{ now_year }} {{ site_name }} | 행사 정보는 한국관광공사 Tour API 기반이며 변경될 수 있습니다.</p>
      <p class="mt-1">
        <a href="/privacy-policy/" class="hover:text-blue-600 mx-2">개인정보처리방침</a>
        <a href="mailto:contact@uapress.kr" class="hover:text-blue-600 mx-2">문의</a>
      </p>
    </div>
  </footer>

  <script src="/static/js/main.js"></script>
</body>
</html>
```

### `templates/event.html` (핵심 SEO 페이지)

```html
{% extends "base.html" %}

{% block title %}{{ event.seo_title or event.title }} - {{ site_name }}{% endblock %}
{% block description %}{{ event.meta_description or event.title }}{% endblock %}
{% block og_title %}{{ event.seo_title or event.title }}{% endblock %}
{% block og_desc %}{{ event.meta_description or event.summary }}{% endblock %}

{% block json_ld %}
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Event",
  "name": "{{ event.title }}",
  "description": "{{ event.meta_description or event.summary }}",
  "startDate": "{{ event.start_date_fmt }}",
  "endDate": "{{ event.end_date_fmt }}",
  "eventStatus": "https://schema.org/EventScheduled",
  "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode",
  "location": {
    "@type": "Place",
    "name": "{{ event.place or event.address }}",
    "address": {
      "@type": "PostalAddress",
      "streetAddress": "{{ event.address }}",
      "addressRegion": "{{ event.region }}",
      "addressCountry": "KR"
    }
  },
  "isAccessibleForFree": {{ "true" if event.is_free else "false" }},
  {% if event.organizer %}"organizer": {"@type": "Organization", "name": "{{ event.organizer }}"},{% endif %}
  {% if event.thumbnail %}"image": "{{ event.thumbnail }}"{% endif %}
}
</script>
{% endblock %}

{% block content %}
<!-- 썸네일 -->
{% if event.thumbnail %}
<div class="rounded-2xl overflow-hidden mb-6 max-h-80">
  <img src="{{ event.thumbnail }}" alt="{{ event.title }}"
       class="w-full object-cover">
</div>
{% endif %}

<!-- 제목·메타 -->
<div class="mb-6">
  <div class="flex flex-wrap gap-2 mb-3">
    <span class="bg-blue-100 text-blue-700 text-xs font-bold px-3 py-1 rounded-full">
      {{ event.category }}
    </span>
    {% if event.is_free %}
    <span class="bg-green-100 text-green-700 text-xs font-bold px-3 py-1 rounded-full">
      🎟 무료입장
    </span>
    {% endif %}
    <span class="bg-gray-100 text-gray-600 text-xs px-3 py-1 rounded-full">
      📍 {{ event.region }}
    </span>
  </div>
  <h1 class="text-2xl md:text-3xl font-bold leading-tight">
    {{ event.seo_title or event.title }}
  </h1>
</div>

<!-- 핵심 정보 카드 -->
<div class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
  <div class="bg-white rounded-xl p-4 shadow-sm text-center">
    <p class="text-2xl">📅</p>
    <p class="text-xs text-gray-500 mt-1">기간</p>
    <p class="text-sm font-semibold mt-1">
      {{ event.start_date_fmt }}<br>~ {{ event.end_date_fmt }}
    </p>
  </div>
  <div class="bg-white rounded-xl p-4 shadow-sm text-center">
    <p class="text-2xl">📍</p>
    <p class="text-xs text-gray-500 mt-1">장소</p>
    <p class="text-sm font-semibold mt-1">{{ event.place or event.region }}</p>
  </div>
  <div class="bg-white rounded-xl p-4 shadow-sm text-center">
    <p class="text-2xl">💰</p>
    <p class="text-xs text-gray-500 mt-1">관람료</p>
    <p class="text-sm font-semibold mt-1">{{ event.fee or ("무료" if event.is_free else "미확인") }}</p>
  </div>
  <div class="bg-white rounded-xl p-4 shadow-sm text-center">
    <p class="text-2xl">👥</p>
    <p class="text-xs text-gray-500 mt-1">추천 대상</p>
    <p class="text-sm font-semibold mt-1">{{ event.target_audience or "전체" }}</p>
  </div>
</div>

<!-- AI 하이라이트 -->
{% if event.highlight %}
<div class="bg-amber-50 border-l-4 border-amber-400 rounded-xl p-5 mb-6">
  <h2 class="font-bold text-amber-800 mb-2">✨ 이 행사의 하이라이트</h2>
  <p class="text-gray-700">{{ event.highlight }}</p>
  {% if event.target_reason %}
  <p class="text-sm text-amber-700 mt-2">👉 {{ event.target_reason }}</p>
  {% endif %}
</div>
{% endif %}

<!-- AdSense 광고 1 -->
{% if adsense_publisher_id and adsense_unit_rectangle %}
<div class="my-6 text-center">
  <ins class="adsbygoogle"
    style="display:inline-block;width:336px;height:280px"
    data-ad-client="{{ adsense_publisher_id }}"
    data-ad-slot="{{ adsense_unit_rectangle }}"></ins>
  <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
</div>
{% endif %}

<!-- 방문 팁 -->
{% if event.tips %}
<div class="bg-white rounded-xl p-5 shadow-sm mb-6">
  <h2 class="font-bold text-lg mb-3">💡 방문 팁</h2>
  <ul class="space-y-2">
    {% for tip in event.tips %}
    <li class="flex items-start gap-2 text-gray-700">
      <span class="text-blue-500 mt-0.5">•</span> {{ tip }}
    </li>
    {% endfor %}
  </ul>
</div>
{% endif %}

<!-- 행사 소개 -->
{% if event.overview %}
<div class="bg-white rounded-xl p-5 shadow-sm mb-6">
  <h2 class="font-bold text-lg mb-3">📋 행사 소개</h2>
  <p class="text-gray-700 leading-relaxed">{{ event.overview }}</p>
</div>
{% endif %}

<!-- 숙박 CPA -->
<div class="bg-gray-800 text-white rounded-xl p-5 mb-6">
  <h2 class="font-bold mb-1">🏨 근처 숙박 예약</h2>
  <p class="text-gray-300 text-sm mb-3">{{ event.region }} 숙박은 미리 예약하세요</p>
  <div class="flex gap-3">
    <a href="https://www.yanolja.com/search?keyword={{ event.region }}&ref=uapress"
       target="_blank" rel="noopener sponsored"
       class="flex-1 bg-pink-500 hover:bg-pink-600 text-white text-center py-2 rounded-lg text-sm font-bold">
      야놀자
    </a>
    <a href="https://www.yeogi.com/search?q={{ event.region }}&ref=uapress"
       target="_blank" rel="noopener sponsored"
       class="flex-1 bg-blue-500 hover:bg-blue-600 text-white text-center py-2 rounded-lg text-sm font-bold">
      여기어때
    </a>
  </div>
</div>

<!-- 공식 홈페이지 -->
{% if event.homepage %}
<div class="text-center mb-6">
  <a href="{{ event.homepage }}" target="_blank" rel="noopener"
     class="inline-block border-2 border-blue-500 text-blue-600 px-8 py-3 rounded-xl hover:bg-blue-50 font-medium">
    공식 홈페이지 바로가기 →
  </a>
</div>
{% endif %}

<!-- AdSense 광고 2 (하단) -->
{% if adsense_publisher_id and adsense_unit_banner %}
<div class="my-6">
  <ins class="adsbygoogle"
    style="display:block"
    data-ad-client="{{ adsense_publisher_id }}"
    data-ad-slot="{{ adsense_unit_banner }}"
    data-ad-format="auto"
    data-full-width-responsive="true"></ins>
  <script>(adsbygoogle = window.adsbygoogle || []).push({});</script>
</div>
{% endif %}

<!-- 태그 -->
{% if event.tags %}
<div class="flex flex-wrap gap-2 mt-4">
  {% for tag in event.tags %}
  <span class="bg-gray-100 text-gray-600 text-xs px-3 py-1 rounded-full">#{{ tag }}</span>
  {% endfor %}
</div>
{% endif %}
{% endblock %}
```

---

## Step 8: GitHub Actions (`.github/workflows/deploy.yml`)

```yaml
name: Build & Deploy uapress.kr

on:
  schedule:
    - cron: '0 19 * * 1,4'   # 화·금 오전 4시 KST (데이터 갱신)
    - cron: '0 19 * * 0'     # 일 오전 4시 KST (주간 큐레이션)
  workflow_dispatch:
    inputs:
      mode:
        description: '실행 모드 (full / build_only / weekly)'
        required: true
        default: 'full'

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-${{ hashFiles('uapress/requirements.txt') }}

      - name: Install dependencies
        run: pip install -r uapress/requirements.txt

      - name: Fetch Tour API data
        if: inputs.mode != 'build_only'
        run: python uapress/scripts/fetch_tour.py
        env:
          TOUR_API_KEY: ${{ secrets.TOUR_API_KEY }}

      - name: Process events
        if: inputs.mode != 'build_only'
        run: python uapress/scripts/process_events.py

      - name: Generate AI content (event summaries)
        if: inputs.mode != 'build_only'
        run: python uapress/scripts/generate_content.py events
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Generate weekly pick
        if: inputs.mode == 'weekly' || github.event.schedule == '0 19 * * 0'
        run: python uapress/scripts/generate_content.py weekly
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Build search index
        run: python uapress/scripts/build_search_index.py

      - name: Build static site
        run: python uapress/scripts/build_site.py
        env:
          SITE_DOMAIN: https://uapress.kr
          SITE_NAME: 이번주 행사
          ADSENSE_PUBLISHER_ID: ${{ secrets.ADSENSE_PUBLISHER_ID }}
          ADSENSE_UNIT_BANNER: ${{ secrets.ADSENSE_UNIT_BANNER }}
          ADSENSE_UNIT_RECTANGLE: ${{ secrets.ADSENSE_UNIT_RECTANGLE }}

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy uapress/dist --project-name=uapress
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## Step 9: Search Console 재설정 (마스터 직접)

```
1. Google Search Console → uapress.kr 속성
2. Sitemaps → 기존 WordPress sitemap 제거
3. 새 사이트 배포 완료 후:
   → Sitemaps → 새 sitemap 추가: https://uapress.kr/sitemap.xml
4. URL 검사 → https://uapress.kr/ → 색인 생성 요청
5. 기존 저품질 페이지 자동 404 → 구글이 색인에서 자연 제거
   (수동 제거 불필요, 2~4주 소요)
```

---

## 첫 실행 순서 (Claude Code)

```bash
cd my-sites/uapress

# 1. 의존성 설치
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. .env 파일 생성 (.env.example 복사 후 값 입력)
cp .env.example .env
# → TOUR_API_KEY, ANTHROPIC_API_KEY, ADSENSE_PUBLISHER_ID 필수 입력

# 3. Tour API 데이터 첫 수집 (~10분)
python scripts/fetch_tour.py

# 4. 데이터 정제
python scripts/process_events.py

# 5. AI 콘텐츠 생성 — Batch 제출 후 완료까지 대기 (~1~2시간)
python scripts/generate_content.py events

# 6. 주간 큐레이션 생성
python scripts/generate_content.py weekly

# 7. 검색 인덱스 빌드
python scripts/build_search_index.py

# 8. 사이트 빌드
python scripts/build_site.py

# 9. 로컬 확인 (http://localhost:8000)
python -m http.server 8000 --directory dist

# 10. GitHub push
git add . && git commit -m "feat: uapress.kr eventcal initial build"
git push origin main

# 11. CF Pages 프로젝트 생성 (1회)
npx wrangler pages project create uapress

# 12. 첫 배포
npx wrangler pages deploy dist --project-name=uapress

# 13. CF Pages 대시보드 → uapress 프로젝트
#     → Custom Domains → uapress.kr 추가
#     (CF가 자동으로 CNAME 레코드 생성)

# 14. GitHub Secrets 등록
#     TOUR_API_KEY / ANTHROPIC_API_KEY
#     ADSENSE_PUBLISHER_ID / ADSENSE_UNIT_BANNER / ADSENSE_UNIT_RECTANGLE
#     CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID

# 15. Cloudways WordPress 해지 (CF Pages 정상 확인 후)
```

---

## GitHub Secrets 목록

| Secret | 값 |
|--------|-----|
| `TOUR_API_KEY` | data.go.kr Tour API 키 |
| `ANTHROPIC_API_KEY` | Claude API 키 |
| `ADSENSE_PUBLISHER_ID` | `ca-pub-XXXXXXXXXX` (기승인) |
| `ADSENSE_UNIT_BANNER` | 반응형 배너 광고 단위 ID |
| `ADSENSE_UNIT_RECTANGLE` | 336×280 광고 단위 ID |
| `CLOUDFLARE_API_TOKEN` | CF Pages 배포 토큰 |
| `CLOUDFLARE_ACCOUNT_ID` | CF 계정 ID |

> AdSense 광고 단위는 AdSense 대시보드 → 광고 → 광고 단위 기준 → 새 광고 단위 만들기에서 생성

---

## 완료 체크리스트

```
인프라:
[ ] Cloudflare 네임서버 전파 완료
[ ] CF Pages uapress 프로젝트 생성
[ ] uapress.kr 커스텀 도메인 연결
[ ] HTTPS 정상 (자동)

콘텐츠:
[ ] Tour API 데이터 수집 완료 (최소 200개 행사)
[ ] AI 요약 생성 완료
[ ] 빌드 HTML 500개+ 확인

수익화:
[ ] AdSense 코드 base.html 삽입 확인
[ ] 광고 단위 2개 생성 (배너, 사각형)
[ ] 실제 광고 노출 확인 (배포 후 수분 내)

SEO:
[ ] Search Console 기존 sitemap 제거
[ ] 새 sitemap.xml 제출
[ ] robots.txt 정상 확인
[ ] 메인 페이지 색인 요청

운영:
[ ] GitHub Actions 자동 배포 첫 실행 확인
[ ] Cloudways 해지
```
