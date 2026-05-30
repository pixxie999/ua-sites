# CLAUDE.md — 농산물 도매가격 실시간 정보 사이트

## 프로젝트 개요

**사이트명:** 오늘 장보기 (가칭: `todaymarket.kr` 또는 `farmtoday.kr`)
**목적:** KAMIS 농산물 도매가격 데이터 시각화 + AI 가격 분석 콘텐츠 → AdSense + 쿠팡파트너스 수익화
**아키텍처:** 하이브리드 정적 사이트
- 가격 데이터: Cloudflare Workers (일 1회 KAMIS API → KV 저장 → 정적 페이지에 주입)
- 블로그 콘텐츠: Python 빌더 → 완전 정적 HTML
**자동화:** GitHub Actions (일 1회) + Cloudflare Workers Cron
**AI 활용:** Claude Haiku 4.5 Batch API로 주간 가격 분석 리포트 + 장보기 가이드 생성

---

## 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 가격 데이터 | Cloudflare Workers + KV | 서버리스, 일 1회 갱신으로 충분 |
| 정적 빌드 | Python + Jinja2 | 블로그·분석 페이지 생성 |
| 차트 | Chart.js + ApexCharts (CDN) | 가격 추이 시각화 |
| CSS | Tailwind CSS (CDN Play) | 빌드 없음 |
| 배포 | Cloudflare Pages | 무료, KV 연동 가능 |
| 데이터 소스 | KAMIS API (농림축산식품부) | 무료, 공식 API |
| AI 콘텐츠 | Claude Haiku 4.5 Batch API | 최저 비용 |

---

## 디렉토리 구조

```
todaymarket/
├── CLAUDE.md                      # 이 파일
├── requirements.txt
├── wrangler.toml                  # Cloudflare Workers 설정
├── .github/
│   └── workflows/
│       ├── daily_update.yml       # 매일 오전 5시 데이터 갱신 + 빌드
│       └── weekly_content.yml     # 주 1회 AI 분석 리포트 생성
├── worker/
│   └── index.js                   # Cloudflare Worker (KAMIS API 프록시)
├── data/
│   ├── raw/                       # KAMIS 원본 JSON
│   ├── processed/
│   │   ├── items.json             # 농산물 품목 목록 (500종)
│   │   ├── prices_today.json      # 오늘 도매가격
│   │   ├── prices_weekly.json     # 주간 가격 추이
│   │   └── prices_yearly.json     # 연간 가격 데이터
│   └── content/
│       ├── weekly_reports/        # 주간 AI 분석 리포트
│       └── guides/                # 장보기 가이드 포스트
├── scripts/
│   ├── fetch_kamis.py             # KAMIS API 데이터 수집
│   ├── process_prices.py          # 가격 정제·이상치 제거
│   ├── generate_content.py        # Claude Batch API 콘텐츠 생성
│   └── build_site.py              # 정적 사이트 빌드
├── templates/
│   ├── base.html                  # 공통 레이아웃
│   ├── index.html                 # 메인 (오늘의 주요 가격 + 급등락 알림)
│   ├── item.html                  # 품목별 상세 페이지 (SEO 핵심)
│   ├── category.html              # 카테고리 (채소/과일/수산/축산)
│   ├── weekly_report.html         # 주간 가격 리포트
│   ├── shopping_guide.html        # 장보기 가이드 포스트
│   └── price_calendar.html        # 월별 가격 달력
└── dist/
    └── .gitkeep
```

---

## Step 1: KAMIS API 데이터 수집 (`scripts/fetch_kamis.py`)

### KAMIS API 정보

```
공식명: 농산물유통정보(KAMIS) 서비스
API URL: https://www.kamis.or.kr/service/price/xml.do
인증: apikey (data.go.kr에서 신청)
무료 한도: 일 1,000회 (운영계정 신청 시 일 10만회)

주요 엔드포인트:
- 도매가격: action=dailyPriceByCategoryList
- 소매가격: action=dailyPriceList
- 연간통계: action=monthSalesList
```

```python
# fetch_kamis.py 구현 요구사항

import requests
import json
from datetime import datetime, timedelta
from pathlib import Path

KAMIS_BASE = "http://www.kamis.or.kr/service/price/xml.do"

# 수집 대상 품목 코드 (KAMIS 분류)
CATEGORY_CODES = {
    "100": "식량작물",    # 쌀, 보리, 콩 등
    "200": "채소류",      # 배추, 무, 파, 양파 등 (검색량 최상위)
    "300": "특용작물",    # 참깨, 들깨 등
    "400": "과일류",      # 사과, 배, 수박 등
    "500": "축산물",      # 쇠고기, 돼지고기, 닭고기
    "600": "수산물",      # 명태, 갈치, 고등어
}

# SEO 핵심 품목 (검색량 상위)
HIGH_PRIORITY_ITEMS = [
    "배추", "무", "파", "양파", "마늘", "고추", "시금치",
    "사과", "배", "포도", "수박", "딸기", "감귤",
    "돼지고기", "쇠고기", "닭고기",
    "명태", "고등어", "갈치", "오징어"
]

def fetch_daily_prices(date: str = None) -> dict:
    """오늘 도매가격 수집"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")
    
    params = {
        "action": "dailyPriceByCategoryList",
        "p_cert_key": "KAMIS_API_KEY",  # 환경변수로 주입
        "p_cert_id": "KAMIS_CERT_ID",
        "p_returntype": "json",
        "p_yyyy": date[:4],
        "p_mm": date[5:7],
        "p_dd": date[8:10],
        "p_period": "1",
        "p_convert_kg_yn": "Y"
    }
    # ... 구현

def fetch_yearly_trend(item_code: str, years: int = 5) -> list:
    """품목별 연간 가격 추이 (계절성 분석용)"""
    # ... 구현

# 출력 스키마
PRICE_SCHEMA = {
    "item_code": "str",
    "item_name": "str",
    "category": "str",
    "unit": "str",            # "kg" 또는 "개"
    "today_price": "float",   # 오늘 도매가 (원)
    "yesterday_price": "float",
    "week_ago_price": "float",
    "month_ago_price": "float",
    "year_ago_price": "float",
    "change_pct": "float",    # 전일 대비 등락률
    "5year_avg": "float",     # 5년 평균가
    "vs_avg_pct": "float",    # 5년 평균 대비 현재가 비율
    "updated_at": "str"       # ISO datetime
}
```

### 가격 급등락 감지 로직

```python
def detect_price_surge(prices: dict) -> list:
    """
    가격 이상 감지 (SEO·바이럴 콘텐츠 자동 생성 트리거)
    
    급등: 전주 대비 +20% 이상
    급락: 전주 대비 -20% 이상
    이상 고가: 5년 평균 대비 +50% 이상
    이상 저가: 5년 평균 대비 -30% 이하
    """
    alerts = []
    for item in prices:
        change = (item["today_price"] - item["week_ago_price"]) / item["week_ago_price"] * 100
        if abs(change) >= 20:
            alerts.append({
                "item": item["item_name"],
                "change_pct": change,
                "type": "급등" if change > 0 else "급락",
                "today": item["today_price"],
                "week_ago": item["week_ago_price"]
            })
    return sorted(alerts, key=lambda x: abs(x["change_pct"]), reverse=True)
```

---

## Step 2: AI 콘텐츠 생성 (`scripts/generate_content.py`)

### 생성 콘텐츠 유형

#### A. 주간 가격 분석 리포트 (Claude Haiku Batch)

```python
WEEKLY_REPORT_PROMPT = """당신은 농산물 가격 전문 분석가입니다.
이번 주 농산물 가격 데이터를 바탕으로 소비자와 자영업자를 위한 실용적인 분석 리포트를 작성하세요.

출력 형식 (JSON):
{
  "title": "이번 주 장보기 가이드: {날짜} 농산물 가격 총정리",
  "summary": "이번 주 핵심 가격 변동 요약 (200자)",
  "highlights": [
    {"item": "품목명", "situation": "급등/급락/안정", "reason": "원인 분석 (100자)", "tip": "소비자 팁"}
  ],
  "best_buy_items": ["이번 주 가성비 TOP 5 품목"],
  "avoid_items": ["가격 높은 품목 (대체재 제안)"],
  "next_week_outlook": "다음 주 가격 전망 (200자)",
  "seasonal_tip": "이 시기 제철 식재료 추천",
  "recipe_suggestion": "저렴한 식재료로 만드는 요리 아이디어"
}"""

# 데이터 입력 형식
def format_weekly_data(prices: list, alerts: list) -> str:
    """API 프롬프트용 데이터 포매팅"""
    lines = ["=== 이번 주 주요 농산물 가격 ===\n"]
    for p in prices[:30]:  # 상위 30개 품목
        change_str = f"+{p['change_pct']:.1f}%" if p['change_pct'] > 0 else f"{p['change_pct']:.1f}%"
        lines.append(f"- {p['item_name']}: {p['today_price']:,}원/{p['unit']} (전주比 {change_str})")
    
    if alerts:
        lines.append("\n=== 이상 가격 감지 ===")
        for a in alerts[:5]:
            lines.append(f"- {a['item']}: {a['type']} {a['change_pct']:.1f}%")
    
    return "\n".join(lines)
```

#### B. 품목별 SEO 페이지 설명 (1회 생성 후 유지)

```python
ITEM_PAGE_PROMPT = """농산물 품목 정보 페이지용 SEO 텍스트를 작성하세요.
출력 (JSON):
{
  "title": "{품목명} 도매가격 오늘 시세 - 실시간 업데이트",
  "meta_description": "{품목명} 오늘 도매가격과 최근 가격 추이. KAMIS 실시간 데이터. (155자 이내)",
  "item_description": "품목 설명 (200자, 계절성·특징 포함)",
  "price_guide": "가격 보는 법 (소비자 관점, 150자)",
  "buying_season": "최저가 시즌 (월 기준)",
  "storage_tips": "보관법 (100자)",
  "faq": [{"q": "질문", "a": "답변"}]  // 3개
}"""
```

#### C. 이슈 발생 시 즉시 생성 (급등락 감지 트리거)

```python
SURGE_ARTICLE_PROMPT = """긴급 농산물 가격 기사를 작성하세요.
대상 독자: 장보기에 민감한 주부, 식당 운영자
어조: 실용적, 간결, 대안 제시

출력 (JSON):
{
  "title": "긴급: {품목명} 가격 {변동률}% {급등/급락}... 원인과 대처법",
  "body": "기사 본문 (500자, 원인-현황-대안 구조)",
  "alternatives": ["대체 식재료 3가지"],
  "price_prediction": "향후 2주 전망"
}"""
```

---

## Step 3: 사이트 빌드 (`scripts/build_site.py`)

### 생성 페이지 목록

```python
def build_all():
    """전체 페이지 빌드"""
    
    build_index()           # / - 오늘의 급등락 + 주요 가격
    build_categories()      # /category/vegetable/ 등 6개
    build_item_pages()      # /item/cabbage/ 등 500개 (SEO 핵심)
    build_weekly_reports()  # /report/2026-05-30/ 등 주간 누적
    build_guides()          # /guide/cheap-vegetables-may/ 등
    build_price_calendar()  # /calendar/cabbage/2026/ 등
    build_sitemap()         # /sitemap.xml
```

### 품목 상세 페이지 구성 (`templates/item.html`)

```
1. H1: "{품목명} 오늘 도매가격 - {날짜} 기준 실시간"
2. 오늘 가격 카드
   - 현재 도매가: XXX원/kg
   - 전일 대비: ▲▼ XX%
   - 5년 평균 대비: XX% (비싼편/저렴한편)
3. 가격 추이 차트 (30일 라인 차트 + 1년 바 차트)
4. 연도별 월평균 가격 테이블 (최저가 시즌 하이라이트)
5. AI 분석 텍스트 (저렴한 이유, 비싼 이유, 대안)
6. [쿠팡파트너스] 이 식재료로 만드는 상품 추천
7. 관련 품목 링크
8. FAQ (구조화 데이터)
```

### 가격 카드 컴포넌트 (Tailwind)

```html
<!-- templates/components/price_card.html -->
<div class="bg-white rounded-xl shadow p-6 border-l-4 
  {% if item.change_pct > 10 %}border-red-500
  {% elif item.change_pct < -10 %}border-blue-500
  {% else %}border-gray-300{% endif %}">
  
  <div class="flex justify-between items-start">
    <div>
      <h3 class="text-xl font-bold">{{ item.item_name }}</h3>
      <p class="text-gray-500 text-sm">{{ item.unit }} 기준</p>
    </div>
    <span class="text-2xl font-black {% if item.change_pct > 0 %}text-red-500{% else %}text-blue-500{% endif %}">
      {{ item.today_price | format_price }}원
    </span>
  </div>
  
  <div class="mt-3 flex gap-4 text-sm">
    <span class="{% if item.change_pct > 0 %}text-red-600{% else %}text-blue-600{% endif %} font-semibold">
      {{ "▲" if item.change_pct > 0 else "▼" }} {{ item.change_pct | abs | round(1) }}%
    </span>
    <span class="text-gray-500">5년 평균 대비 {{ item.vs_avg_pct | round(0) }}%</span>
  </div>
  
  <!-- 가성비 뱃지 -->
  {% if item.vs_avg_pct < -20 %}
  <div class="mt-2 inline-block bg-green-100 text-green-700 text-xs font-bold px-2 py-1 rounded-full">
    💚 지금이 사기 좋은 시기
  </div>
  {% elif item.vs_avg_pct > 30 %}
  <div class="mt-2 inline-block bg-red-100 text-red-700 text-xs font-bold px-2 py-1 rounded-full">
    🔴 평균보다 {{ item.vs_avg_pct | round(0) }}% 비쌈
  </div>
  {% endif %}
</div>
```

---

## Step 4: Cloudflare Worker (실시간 가격 API)

### `worker/index.js`

```javascript
// Cloudflare Worker - KAMIS 가격 데이터 캐싱
// KV Namespace: PRICE_DATA

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    
    // CORS 설정
    const headers = {
      "Access-Control-Allow-Origin": "https://todaymarket.kr",
      "Content-Type": "application/json",
      "Cache-Control": "public, max-age=3600"  // 1시간 캐시
    };
    
    if (url.pathname === "/api/prices/today") {
      const data = await env.PRICE_DATA.get("today", { type: "json" });
      return new Response(JSON.stringify(data), { headers });
    }
    
    if (url.pathname.startsWith("/api/prices/item/")) {
      const itemCode = url.pathname.split("/").pop();
      const data = await env.PRICE_DATA.get(`item_${itemCode}`, { type: "json" });
      return new Response(JSON.stringify(data), { headers });
    }
    
    return new Response("Not Found", { status: 404 });
  },
  
  // Cron: 매일 오전 4시 KAMIS 데이터 갱신
  async scheduled(event, env) {
    const response = await fetch(
      `http://www.kamis.or.kr/service/price/xml.do?action=dailyPriceByCategoryList&...`
    );
    const data = await response.json();
    
    // KV에 저장 (TTL 25시간)
    await env.PRICE_DATA.put("today", JSON.stringify(data), {
      expirationTtl: 90000
    });
  }
};
```

### `wrangler.toml`

```toml
name = "todaymarket-prices"
main = "worker/index.js"
compatibility_date = "2025-01-01"

[[kv_namespaces]]
binding = "PRICE_DATA"
id = "YOUR_KV_NAMESPACE_ID"

[triggers]
crons = ["0 19 * * *"]  # 매일 오전 4시 KST
```

---

## Step 5: GitHub Actions 자동화

### `.github/workflows/daily_update.yml`

```yaml
name: Daily Price Update & Build

on:
  schedule:
    - cron: '0 20 * * *'  # 오전 5시 KST
  workflow_dispatch:

jobs:
  update-and-build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: pip install -r requirements.txt
        
      - name: Fetch KAMIS prices
        run: python scripts/fetch_kamis.py
        env:
          KAMIS_API_KEY: ${{ secrets.KAMIS_API_KEY }}
          KAMIS_CERT_ID: ${{ secrets.KAMIS_CERT_ID }}
          
      - name: Process price data
        run: python scripts/process_prices.py
        
      - name: Build static site
        run: python scripts/build_site.py
        env:
          BUILD_DATE: ${{ github.run_number }}
          
      - name: Deploy to Cloudflare Pages
        uses: cloudflare/pages-action@v1
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          projectName: todaymarket
          directory: dist
          gitHubToken: ${{ secrets.GITHUB_TOKEN }}
```

### `.github/workflows/weekly_content.yml`

```yaml
name: Weekly AI Content & Analysis

on:
  schedule:
    - cron: '0 19 * * 4'  # 매주 금요일 오전 4시 KST
  workflow_dispatch:

jobs:
  generate-weekly-report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: pip install -r requirements.txt
        
      - name: Generate weekly AI report
        run: python scripts/generate_content.py --type weekly_report
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          KAMIS_API_KEY: ${{ secrets.KAMIS_API_KEY }}
          
      - name: Rebuild with new content
        run: python scripts/build_site.py
        
      - name: Deploy
        uses: cloudflare/pages-action@v1
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          projectName: todaymarket
          directory: dist
          gitHubToken: ${{ secrets.GITHUB_TOKEN }}
```

---

## Step 6: 수익화 설정

### 쿠팡파트너스 연동

```python
# 품목별 쿠팡파트너스 링크 매핑
COUPANG_MAPPING = {
    "cabbage": {
        "keyword": "배추",
        "url": "https://link.coupang.com/a/XXXXXX",  # 파트너스 링크
        "type": "fresh"
    },
    "garlic": {
        "keyword": "마늘",
        "url": "https://link.coupang.com/a/XXXXXX",
        "type": "processed"  # 깐마늘, 마늘분말 등
    }
    # 식재료별 쿠팡파트너스 매핑
}

# 페이지별 CTA 전략:
# - 오늘 가격이 5년 평균보다 30% 이상 비쌀 때 → 가공식품/통조림 쿠팡 링크
# - 가격 저점일 때 → "지금 구매하기" 신선식품 쿠팡 링크
```

### AdSense 광고 배치

```
[메인 페이지]
- 급등락 알림 박스 아래: 반응형 광고
- 카테고리 그리드 사이: 네이티브 광고

[품목 상세 페이지]
- 가격 카드 아래: 디스플레이 광고 (336×280)
- 연간 추이 차트 아래: 반응형 광고
- 페이지 하단: 반응형 광고

[주간 리포트]
- 분석 섹션 중간: 인피드 광고
```

---

## SEO 전략

### 핵심 키워드 타겟

| 키워드 유형 | 예시 | 월 검색량 | 경쟁도 |
|------------|------|---------|--------|
| 오늘 가격 | "배추 오늘 가격" | 높음 | 낮음 |
| 도매가 | "양파 도매가격" | 중간 | 낮음 |
| 왜 비싸 | "파 가격 왜 이렇게 비싸" | 높음 (이슈) | 없음 |
| 제철 | "5월 저렴한 채소" | 중간 | 낮음 |
| 비교 | "사과 vs 배 가격 비교" | 낮음 | 없음 |

### 구조화 데이터 (필수)

```json
// 품목 페이지 JSON-LD
{
  "@context": "https://schema.org",
  "@type": "Dataset",
  "name": "배추 도매가격 실시간 데이터",
  "description": "KAMIS 기반 배추 도매가격 일별 시계열",
  "temporalCoverage": "2015/2026",
  "creator": {
    "@type": "Organization",
    "name": "오늘장보기"
  },
  "distribution": {
    "@type": "DataDownload",
    "encodingFormat": "text/html"
  }
}
```

---

## requirements.txt

```
anthropic>=0.40.0
requests>=2.31.0
pandas>=2.0.0
jinja2>=3.1.0
python-dotenv>=1.0.0
pytz>=2024.1
```

---

## 환경변수 (GitHub Secrets)

| 변수명 | 설명 |
|--------|------|
| `ANTHROPIC_API_KEY` | Claude API |
| `KAMIS_API_KEY` | KAMIS 인증키 (data.go.kr 신청) |
| `KAMIS_CERT_ID` | KAMIS 인증ID |
| `CLOUDFLARE_API_TOKEN` | Pages 배포 토큰 |
| `CLOUDFLARE_ACCOUNT_ID` | CF 계정 ID |

---

## 클로드 코드 실행 순서

```bash
# 1. 프로젝트 초기화
git init todaymarket && cd todaymarket

# 2. 구조 생성
mkdir -p data/{raw,processed,content/{weekly_reports,guides}}
mkdir -p scripts templates static dist worker
mkdir -p .github/workflows

# 3. Cloudflare KV 네임스페이스 생성 (wrangler 필요)
npm install -g wrangler
wrangler kv:namespace create "PRICE_DATA"
# → wrangler.toml에 id 기입

# 4. 첫 데이터 수집
python scripts/fetch_kamis.py

# 5. 데이터 처리
python scripts/process_prices.py

# 6. AI 콘텐츠 첫 생성 (주요 품목 50개)
python scripts/generate_content.py --type item_pages --limit 50

# 7. 첫 빌드
python scripts/build_site.py

# 8. 로컬 확인
cd dist && python -m http.server 8001

# 9. Worker 배포
wrangler deploy worker/index.js

# 10. Pages 배포
git add . && git commit -m "init: Phase 1 todaymarket site"
git push origin main
```

---

## 성공 지표 (90일)

| 지표 | 최악 | 보통 |
|------|------|------|
| 일 방문자 | 30명 | 300명 |
| 이슈 스파이크 시 최대 | 500명 | 5,000명 |
| AdSense RPM | 400원 | 1,000원 |
| 쿠팡파트너스 월 수익 | 0원 | 15,000원 |
| 월 총 수익 | 450원 | 25,800원 |

---

## 주의사항

- KAMIS API 서비스 점검: 매주 화요일 새벽 (GitHub Actions 스케줄 피하기)
- 가격 이상치 처리: 0원, 999,999원 등 오류값 필터링 로직 필수
- robots.txt: 데이터 수집 페이지(`/api/*`) 크롤링 차단
- 쿠팡파트너스: 광고 표시 의무 ("이 포스팅은 파트너스 활동으로 수수료를 받습니다")
