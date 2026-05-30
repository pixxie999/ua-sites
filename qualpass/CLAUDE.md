# CLAUDE.md — 자격증 합격률 통계 사이트

## 프로젝트 개요

**사이트명:** 자격증 합격률 인포 (가칭: `qualpass.kr` 또는 `qualpass.com`)
**목적:** 국가자격증 합격률·일정 데이터를 시각화해 SEO 트래픽 확보 → AdSense + 인강 CPA 수익화
**아키텍처:** 완전 정적 사이트 (Python 빌더 → HTML 생성 → Cloudflare Pages 배포)
**자동화:** GitHub Actions (일 1회 데이터 갱신 + 빌드 + 배포)
**AI 활용:** Claude Haiku 4.5 Batch API로 자격증별 블로그 포스트 자동 생성

---

## 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 빌더 | Python 3.11 + Jinja2 | 마스터 주력 언어, 정적 HTML 생성 최적 |
| 차트 | Chart.js (CDN) | 번들러 불필요, 정적 HTML에 인라인 |
| CSS | Tailwind CSS (CDN Play) | 빌드 불필요 버전 |
| 배포 | Cloudflare Pages | 무료, 트래픽 무제한 |
| CI/CD | GitHub Actions | Public repo 무료 무제한 |
| 데이터 | Q-Net 스크래핑 + 공공데이터포털 CSV | 무료 |
| AI 콘텐츠 | Claude Haiku 4.5 Batch API | 최저 비용 ($0.5/$2.5 per MTok) |

---

## 디렉토리 구조

```
qualpass/
├── CLAUDE.md                    # 이 파일
├── requirements.txt
├── .github/
│   └── workflows/
│       ├── daily_build.yml      # 매일 오전 6시 데이터 갱신 + 빌드
│       └── content_gen.yml      # 주 2회 AI 블로그 생성
├── data/
│   ├── raw/                     # Q-Net 원본 CSV (git 추적 안 함)
│   ├── processed/
│   │   ├── qualifications.json  # 자격증 기본 정보 (500종)
│   │   ├── pass_rates.json      # 연도별 합격률 데이터
│   │   └── schedules.json       # 2025~2026 시험 일정
│   └── content/
│       └── posts/               # AI 생성 블로그 포스트 JSON
├── scripts/
│   ├── fetch_qnet.py            # Q-Net 데이터 수집
│   ├── fetch_hrd.py             # 공공데이터포털 HRD 데이터
│   ├── process_data.py          # 데이터 정제·병합
│   ├── generate_content.py      # Claude Batch API 콘텐츠 생성
│   └── build_site.py            # Jinja2 → HTML 빌드
├── templates/
│   ├── base.html                # 공통 레이아웃 (AdSense 코드 포함)
│   ├── index.html               # 메인 페이지
│   ├── category.html            # 카테고리 페이지 (산업기사, 기사 등)
│   ├── qualification.html       # 자격증 개별 페이지 (SEO 핵심)
│   ├── compare.html             # 자격증 비교 페이지
│   ├── schedule.html            # 시험 일정 페이지
│   └── post.html                # 블로그 포스트 페이지
└── dist/                        # 빌드 결과물 (Cloudflare Pages 배포 루트)
    └── .gitkeep
```

---

## Step 1: 데이터 수집 (`scripts/fetch_qnet.py`)

### 수집 대상
- **Q-Net 공개 통계:** https://www.q-net.or.kr/crf005.do (종목별 합격률)
- **공공데이터포털:** `한국산업인력공단_국가기술자격 검정현황` CSV
  - URL: https://www.data.go.kr 검색 키워드: "국가기술자격 검정현황"
- **시험 일정:** Q-Net 일정 페이지 스크래핑

### 구현 지침
```python
# fetch_qnet.py 구현 요구사항

import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from pathlib import Path

# 1. 공공데이터포털 CSV 다운로드 (연도별 합격률)
# - 파일명 패턴: "국가기술자격검정현황_YYYY.csv"
# - 컬럼: 종목명, 등급, 응시인원, 합격인원, 합격률
# - 최근 10개년 데이터 수집

# 2. Q-Net 시험 일정 스크래핑
# - 타겟 URL: https://www.q-net.or.kr/crf005.do?id=crf00503&gSite=Q
# - 필요 필드: 종목명, 회차, 필기원서접수, 필기시험일, 합격발표일, 실기접수, 실기시험일

# 3. 출력 JSON 스키마
QUALIFICATION_SCHEMA = {
    "id": "str",           # 영문 slug (예: "electric-engineer")
    "name_ko": "str",      # 한국어 종목명 (예: "전기기사")
    "category": "str",     # 대분류 (예: "전기·전자")
    "level": "str",        # 등급 (기사/산업기사/기능사/기능장/기술사)
    "pass_rates": [        # 연도별 합격률
        {
            "year": "int",
            "written_applicants": "int",
            "written_passers": "int",
            "written_rate": "float",
            "practical_applicants": "int",
            "practical_passers": "int",
            "practical_rate": "float"
        }
    ],
    "schedules": [         # 시험 일정
        {
            "year": "int",
            "round": "int",
            "written_apply_start": "str",  # ISO date
            "written_exam_date": "str",
            "practical_apply_start": "str",
            "practical_exam_date": "str",
            "result_date": "str"
        }
    ],
    "description": "str",  # AI 생성 설명 (나중에 채움)
    "difficulty": "str",   # AI 분석 난이도 (상/중/하)
    "related_jobs": []     # 관련 직종
}

# 저장 경로
OUTPUT_DIR = Path("data/processed")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
```

### 수집 자격증 우선순위 (500종 중 SEO 상위 50종 먼저)
```
1순위 (검색량 최상위): 전기기사, 정보처리기사, 건축기사, 소방설비기사, 
                       위험물산업기사, 전기산업기사, 토목기사, 기계기사
2순위 (검색량 상위): 전기공사기사, 화학분석기사, 식품기사, 환경기사,
                     산업안전기사, 품질경영기사, 용접기사
3순위 (롱테일): 나머지 485종 (자동화로 일괄 처리)
```

---

## Step 2: AI 콘텐츠 생성 (`scripts/generate_content.py`)

### Claude Haiku 4.5 Batch API 사용

```python
# generate_content.py 구현 요구사항

import anthropic
import json
from pathlib import Path

client = anthropic.Anthropic()  # ANTHROPIC_API_KEY 환경변수 사용

# Batch API로 자격증별 SEO 블로그 포스트 생성
# 1회 배치: 100개 요청 (API 한도 내)

SYSTEM_PROMPT = """당신은 자격증 정보 전문 블로그 작가입니다.
주어진 자격증 데이터를 바탕으로 SEO 최적화된 한국어 블로그 포스트를 작성하세요.

출력 형식 (JSON만 출력, 마크다운 코드블록 없이):
{
  "title": "SEO 제목 (자격증명 + 핵심 키워드 포함, 30자 이내)",
  "meta_description": "메타 설명 (155자 이내, 합격률과 취득 가치 포함)",
  "h1": "페이지 H1 태그",
  "intro": "도입부 (200자, 검색 의도 충족)",
  "difficulty_analysis": "난이도 분석 (300자, 합격률 데이터 기반)",
  "study_tips": "학습 팁 3가지 (각 100자)",
  "career_prospects": "취업 전망 (200자)",
  "faq": [{"q": "질문", "a": "답변"}] // 3개
}"""

def create_batch_requests(qualifications: list) -> list:
    """자격증 리스트를 Batch API 요청으로 변환"""
    requests = []
    for qual in qualifications:
        # 합격률 요약 (최근 5년)
        recent_rates = qual["pass_rates"][-5:]
        avg_written = sum(r["written_rate"] for r in recent_rates) / len(recent_rates)
        avg_practical = sum(r["practical_rate"] for r in recent_rates if r["practical_rate"] > 0) 
        
        user_message = f"""
자격증명: {qual['name_ko']} ({qual['level']})
분류: {qual['category']}
최근 5년 평균 필기 합격률: {avg_written:.1f}%
최근 5년 합격률 추이: {[f"{r['year']}년 {r['written_rate']}%" for r in recent_rates]}
응시인원 (최근): {recent_rates[-1]['written_applicants']:,}명
"""
        requests.append({
            "custom_id": f"qual-{qual['id']}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 1000,
                "system": SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": user_message}]
            }
        })
    return requests

# 사용법:
# batch = client.beta.messages.batches.create(requests=create_batch_requests(quals))
# 결과는 batch.id로 폴링하여 수집
```

### 생성할 콘텐츠 유형

| 타입 | 개수 | 주기 | 키워드 예시 |
|------|------|------|------------|
| 자격증 소개 포스트 | 500개 | 1회 생성 | "전기기사 합격률 분석" |
| 비교 포스트 | 50개 | 1회 생성 | "기사 vs 산업기사 합격률 비교" |
| 연도별 트렌드 | 20개 | 연 1회 갱신 | "2026 자격증 합격률 변화" |
| 취득 가이드 | 30개 | 분기 1회 | "전기기사 독학 합격 전략" |

---

## Step 3: 사이트 빌드 (`scripts/build_site.py`)

### 생성할 페이지 구조

```python
# build_site.py 구현 요구사항

from jinja2 import Environment, FileSystemLoader
import json
import shutil
from pathlib import Path

DIST_DIR = Path("dist")

def build_all():
    """전체 사이트 빌드"""
    
    # 1. dist 초기화
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    DIST_DIR.mkdir()
    
    # 2. 정적 자산 복사
    shutil.copytree("static", DIST_DIR / "static")
    
    # 3. 페이지 생성
    build_index()           # dist/index.html
    build_categories()      # dist/category/{slug}/index.html
    build_qualifications()  # dist/q/{slug}/index.html  ← SEO 핵심
    build_compare_pages()   # dist/compare/{slug-vs-slug}/index.html
    build_schedule_pages()  # dist/schedule/{year}/index.html
    build_blog_posts()      # dist/blog/{slug}/index.html
    build_sitemap()         # dist/sitemap.xml
    build_robots()          # dist/robots.txt

# URL 구조 (SEO 최적화)
URL_STRUCTURE = {
    "메인":        "/",
    "카테고리":    "/category/electric/",
    "자격증상세":  "/q/electric-engineer/",       # 핵심 SEO 페이지
    "합격률":      "/q/electric-engineer/pass-rate/",
    "시험일정":    "/q/electric-engineer/schedule/",
    "비교":        "/compare/electric-engineer-vs-industrial/",
    "블로그":      "/blog/electric-engineer-pass-rate-2026/",
    "연도별":      "/stats/2026/",
}
```

### SEO 필수 요소 (모든 페이지 공통)

```html
<!-- templates/base.html에 반드시 포함 -->

<!-- 1. 구조화 데이터 (JSON-LD) -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "Article",  <!-- 또는 FAQPage, Dataset -->
  "name": "{{ page.title }}",
  "description": "{{ page.meta_description }}",
  "dateModified": "{{ build_date }}"
}
</script>

<!-- 2. OG 태그 -->
<meta property="og:title" content="{{ page.title }}">
<meta property="og:description" content="{{ page.meta_description }}">
<meta property="og:type" content="website">

<!-- 3. 정규 URL -->
<link rel="canonical" href="https://qualpass.kr{{ page.url }}">

<!-- 4. AdSense (승인 후 코드 삽입) -->
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-XXXXXXXXXXXXXXXX" crossorigin="anonymous"></script>
```

### 자격증 상세 페이지 구성 (`templates/qualification.html`)

```
페이지 구성 순서:
1. H1: "{자격증명} 합격률 총정리 ({최신연도})"
2. 핵심 지표 카드 (필기 합격률, 실기 합격률, 응시인원, 난이도)
3. Chart.js 합격률 추이 그래프 (10년치 라인 차트)
4. 연도별 상세 테이블
5. 시험 일정 (다음 회차)
6. AI 생성 분석 텍스트
7. 관련 자격증 링크
8. FAQ (Schema 구조화 데이터 포함)
9. [CPA 배너] 관련 인강 추천 (에듀윌/해커스 제휴)
```

---

## Step 4: GitHub Actions 자동화

### `.github/workflows/daily_build.yml`

```yaml
name: Daily Data Update & Build

on:
  schedule:
    - cron: '0 21 * * *'  # 매일 오전 6시 KST (UTC 21:00)
  workflow_dispatch:       # 수동 실행 가능

jobs:
  build-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: pip install -r requirements.txt
        
      - name: Fetch latest data
        run: python scripts/fetch_qnet.py
        env:
          DATA_GOV_API_KEY: ${{ secrets.DATA_GOV_API_KEY }}
          
      - name: Process data
        run: python scripts/process_data.py
        
      - name: Build site
        run: python scripts/build_site.py
        
      - name: Deploy to Cloudflare Pages
        uses: cloudflare/pages-action@v1
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          projectName: qualpass
          directory: dist
          gitHubToken: ${{ secrets.GITHUB_TOKEN }}
```

### `.github/workflows/content_gen.yml`

```yaml
name: Weekly AI Content Generation

on:
  schedule:
    - cron: '0 20 * * 0'  # 매주 일요일 오전 5시 KST
  workflow_dispatch:

jobs:
  generate-content:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          
      - name: Install dependencies
        run: pip install -r requirements.txt
        
      - name: Generate AI content (Batch API)
        run: python scripts/generate_content.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          
      - name: Rebuild site with new content
        run: python scripts/build_site.py
        
      - name: Deploy
        uses: cloudflare/pages-action@v1
        with:
          apiToken: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          accountId: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
          projectName: qualpass
          directory: dist
          gitHubToken: ${{ secrets.GITHUB_TOKEN }}
```

---

## Step 5: 수익화 설정

### AdSense 광고 위치

```
[자격증 상세 페이지]
- 상단: 반응형 배너 (728×90 데스크탑 / 320×50 모바일)
- 합격률 그래프 아래: 직사각형 (336×280)
- 페이지 하단: 반응형 배너

[블로그 포스트]
- 본문 중간 (2번째 단락 후): 인피드 광고
- 페이지 하단: 반응형 배너
```

### CPA 제휴 배너 (인강)

```python
# 자격증별 관련 인강 CPA 매핑
CPA_MAPPING = {
    "electric-engineer": {
        "partner": "에듀윌",
        "url": "https://www.eduwill.net/?ref=qualpass",
        "banner_text": "전기기사 합격의 지름길 → 에듀윌 전기기사"
    },
    "information-processing": {
        "partner": "수제비",
        "url": "https://sujebi.co.kr/?ref=qualpass",
        "banner_text": "정보처리기사 합격률 1위 교재"
    },
    # ... 자격증별 매핑
}
# CPA 단가: 건당 5,000~15,000원 (제휴사별 상이)
```

---

## requirements.txt

```
anthropic>=0.40.0
requests>=2.31.0
beautifulsoup4>=4.12.0
lxml>=5.0.0
pandas>=2.0.0
jinja2>=3.1.0
python-dotenv>=1.0.0
schedule>=1.2.0
```

---

## 환경변수 목록 (GitHub Secrets에 등록)

| 변수명 | 설명 | 획득 방법 |
|--------|------|---------|
| `ANTHROPIC_API_KEY` | Claude API 키 | console.anthropic.com |
| `DATA_GOV_API_KEY` | 공공데이터포털 API 키 | data.go.kr 회원가입 후 신청 |
| `CLOUDFLARE_API_TOKEN` | Cloudflare Pages 배포 토큰 | CF 대시보드 → API Tokens |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare 계정 ID | CF 대시보드 우측 하단 |

---

## 클로드 코드 실행 순서 (처음 구축 시)

```bash
# 1. 프로젝트 초기화
git init qualpass && cd qualpass

# 2. 디렉토리 구조 생성
mkdir -p data/{raw,processed,content/posts} scripts templates static dist
mkdir -p .github/workflows

# 3. 의존성 설치
pip install -r requirements.txt

# 4. 데이터 첫 수집 (수동)
python scripts/fetch_qnet.py

# 5. 데이터 정제
python scripts/process_data.py

# 6. AI 콘텐츠 1차 생성 (50개 자격증)
python scripts/generate_content.py --limit 50

# 7. 사이트 첫 빌드
python scripts/build_site.py

# 8. 로컬 확인
cd dist && python -m http.server 8000

# 9. GitHub push → Cloudflare Pages 자동 배포
git add . && git commit -m "init: Phase 1 qualpass site"
git push origin main
```

---

## 성공 지표 (90일 기준)

| 지표 | 최악 | 보통 | 측정 도구 |
|------|------|------|---------|
| 구글 인덱싱 페이지 수 | 100개 | 400개+ | Search Console |
| 일 유기 방문자 | 50명 | 400명+ | GA4 |
| AdSense RPM | 500원 | 1,200원 | AdSense 대시보드 |
| 인강 CPA 월 건수 | 0건 | 5건+ | 제휴사 대시보드 |
| 월 수익 합계 | 750원 | 54,400원 | 자체 집계 |

---

## 주의사항 및 면책

- Q-Net 스크래핑 시 `robots.txt` 확인 필수, 요청 간격 2초 이상 유지
- 공공데이터포털 API: 일 10만건 한도 (운영계정 신청 필요)
- 합격률 데이터 오류 가능성 → 페이지 하단 "출처: Q-Net, 공공데이터포털 / 오류 신고" 링크 삽입
- AdSense 정책: 자동 생성 콘텐츠 허용이나 품질 기준 충족 필요 → AI 생성 후 핵심 페이지 10% 수동 검토
