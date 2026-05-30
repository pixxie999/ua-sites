# CLAUDE.md — 생활밀착형 판결문 AI 요약 사이트

## 프로젝트 개요

**사이트명:** 판례 쉽게 (가칭: `lawsummary.kr`)
**레포 위치:** `my-sites/lawsummary/`
**목적:** 대법원 공개 판결문을 AI로 일반인 눈높이 요약 → 법률 관련 SEO 트래픽 → 법률상담 CPA + AdSense
**핵심 가치:** "나랑 비슷한 상황에서 법원은 어떻게 판결했나?" — 일반인이 판례를 쉽게 찾고 이해하도록
**아키텍처:** Python 빌더 → 완전 정적 HTML → Cloudflare Pages
**자동화:** GitHub Actions 주 2회 (화·금) 신규 판결문 수집 + 요약
**AI 활용:** Claude Haiku 4.5 Batch API — 판결문 요약 + 쟁점 분류 + FAQ 생성

---

## 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 빌더 | Python 3.11 + Jinja2 | 공통 스택 |
| CSS | Tailwind CSS CDN | 빌드 불필요 |
| 배포 | Cloudflare Pages | 무료 |
| CI/CD | GitHub Actions | my-sites 레포 공유 |
| 데이터 | 대법원 판결서 열람 시스템 | 공개 데이터 |
| AI | Claude Haiku 4.5 Batch API | 판결문 요약 |

---

## 디렉토리 구조

```
my-sites/lawsummary/
├── CLAUDE.md
├── requirements.txt
├── data/
│   ├── raw/                         # 원본 판결문 텍스트 (git 제외)
│   ├── processed/
│   │   ├── cases.json               # 전체 사건 목록
│   │   ├── cases_by_topic.json      # 주제별 분류
│   │   └── latest_cases.json        # 최신 30건
│   └── content/
│       └── guides/                  # 법률 가이드 포스트
├── scripts/
│   ├── fetch_court.py               # 대법원 판결서 수집
│   ├── summarize_cases.py           # Claude Batch 요약
│   ├── generate_guides.py           # 법률 가이드 포스트 생성
│   └── build_site.py
├── templates/
│   ├── base.html
│   ├── index.html                   # 메인 (주제별 판례 탐색)
│   ├── case.html                    # 판례 상세 (SEO 핵심)
│   ├── topic.html                   # 주제별 판례 목록
│   ├── search.html                  # 판례 검색
│   └── guide_post.html              # 법률 가이드
└── dist/
```

---

## Step 1: 데이터 수집 (`scripts/fetch_court.py`)

### 대법원 판결서 열람 시스템

```python
"""
대법원 판결서 인터넷 열람 시스템
URL: https://www.scourt.go.kr/portal/dcboard/DcboardListAction.work
공공데이터포털: "대법원 판결문 정보" (일부 API 제공)

수집 전략:
1. 공공데이터포털 API (우선)
2. 대법원 열람 시스템 스크래핑 (보조)
3. 법령정보센터 판례 데이터

수집 범위: 생활밀착형 민사·형사 사건만 (형사 중 경미 사건 포함)
"""

import requests
from bs4 import BeautifulSoup
import json
import time
from pathlib import Path

# 생활밀착형 주제 분류 (SEO 키워드 기반)
TOPIC_CATEGORIES = {
    "층간소음": {
        "keywords": ["층간소음", "소음", "진동", "생활방해"],
        "courts": ["민사"],
        "seo_volume": "very_high"
    },
    "전세사기": {
        "keywords": ["전세보증금", "임대차", "보증금반환", "전세사기"],
        "courts": ["민사", "형사"],
        "seo_volume": "very_high"
    },
    "임금체불": {
        "keywords": ["임금", "퇴직금", "해고", "근로계약"],
        "courts": ["민사", "형사"],
        "seo_volume": "high"
    },
    "교통사고": {
        "keywords": ["교통사고", "손해배상", "과실"],
        "courts": ["민사", "형사"],
        "seo_volume": "high"
    },
    "개물림": {
        "keywords": ["개물림", "반려동물", "동물", "펫"],
        "courts": ["민사"],
        "seo_volume": "medium"
    },
    "직장갑질": {
        "keywords": ["직장내괴롭힘", "갑질", "폭언", "왕따"],
        "courts": ["민사", "형사"],
        "seo_volume": "high"
    },
    "명예훼손": {
        "keywords": ["명예훼손", "모욕", "허위사실"],
        "courts": ["형사"],
        "seo_volume": "high"
    },
    "사기": {
        "keywords": ["사기", "편취", "보이스피싱"],
        "courts": ["형사"],
        "seo_volume": "very_high"
    },
    "이혼재산분할": {
        "keywords": ["이혼", "재산분할", "위자료", "양육권"],
        "courts": ["가사"],
        "seo_volume": "very_high"
    },
    "입주민분쟁": {
        "keywords": ["아파트", "관리비", "하자", "공용부분"],
        "courts": ["민사"],
        "seo_volume": "medium"
    }
}

# 출력 스키마
CASE_SCHEMA = {
    "id": "str",                     # 사건번호 slug
    "case_number": "str",            # 원본 사건번호
    "court": "str",                  # 법원명
    "court_level": "str",            # 심급 (1심/2심/3심)
    "case_type": "str",              # 민사/형사/가사
    "topic": "str",                  # 생활 주제 분류
    "decision_date": "str",          # 선고일
    "result": "str",                 # 판결 결과 (인용/기각/일부인용)
    # AI 생성 필드
    "title_plain": "str",            # 일반인 제목 (SEO)
    "summary_one_line": "str",       # 한 줄 요약
    "situation": "str",              # 사건 상황 설명 (200자)
    "court_reasoning": "str",        # 법원 판단 이유 (200자)
    "key_point": "str",              # 핵심 포인트 (150자)
    "citizen_lesson": "str",         # 일반인이 얻는 교훈 (150자)
    "similar_cases_note": "str",     # 비슷한 상황 주의사항
    "faq": "list",                   # FAQ 3개
    "meta_description": "str",
    "seo_title": "str",
    "tags": "list",
    # 원본
    "source_url": "str",
    "raw_text_length": "int"
}

def fetch_public_cases() -> list:
    """공공데이터포털 판결문 API"""
    API_URL = "https://api.odcloud.kr/api/15069932/v1/uddi:..."
    # data.go.kr에서 "대법원 판결" 검색 후 정확한 엔드포인트 확인
    ...

def fetch_scourt_cases(topic: str, keywords: list, max_cases: int = 100) -> list:
    """대법원 열람 시스템 스크래핑"""
    cases = []
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"
    }

    for keyword in keywords:
        url = f"https://casenote.kr/search?q={keyword}"
        # casenote.kr: 판례 검색 전문 사이트 (공개 데이터 활용)
        resp = requests.get(url, headers=headers, timeout=15)
        time.sleep(2)  # 요청 간격

        soup = BeautifulSoup(resp.text, "lxml")
        # 파싱 로직...

    return cases
```

---

## Step 2: AI 요약 (`scripts/summarize_cases.py`)

### Claude Haiku Batch — 판결문 요약

```python
"""
판결문 → 일반인 눈높이 AI 요약
입력: 판결문 원문 (최대 3,000자로 트리밍)
출력: 구조화된 JSON
비용: Haiku Batch $0.5/$2.5 per MTok
판결문 1건 평균: 입력 4,000토큰 + 출력 800토큰
→ 1,000건 처리 비용: 약 $4
"""

import sys
sys.path.append("../shared/utils")
from claude_batch import run_batch_pipeline

SUMMARIZE_SYSTEM = """당신은 법률 전문가이면서 동시에 일반인 소통 전문가입니다.
판결문을 읽어본 적 없는 일반인이 이해할 수 있도록 쉽게 풀어서 설명하세요.
전문 법률 용어는 반드시 괄호 안에 쉬운 말로 병기하세요.

반드시 JSON만 출력 (마크다운 없이):
{
  "title_plain": "일반인이 검색할 제목 (예: '이웃 층간소음으로 손해배상 받은 판결')",
  "summary_one_line": "판결을 한 문장으로 (70자 이내)",
  "situation": "어떤 상황이었나 (200자, 쉬운 말로)",
  "plaintiff_claim": "원고(피해자 측)가 무엇을 요구했나 (100자)",
  "court_decision": "법원이 어떻게 판단했나 (200자, 핵심 이유 포함)",
  "key_point": "이 판결에서 가장 중요한 포인트 (150자)",
  "citizen_lesson": "비슷한 상황의 시민이 얻어야 할 교훈 (150자)",
  "what_mattered": "승패를 가른 결정적 요소 (100자)",
  "warning": "조심해야 할 점 (100자)",
  "faq": [
    {"q": "자주 묻는 질문", "a": "쉬운 답변 (100자)"}
  ],
  "related_topics": ["관련 키워드 5개"],
  "seo_title": "SEO 제목 (60자, 검색 키워드 포함)",
  "meta_description": "메타 설명 (155자, 상황과 판결 결과 포함)",
  "tags": ["태그1", "태그2", "태그3"]
}"""

def build_summary_requests(cases: list) -> list:
    requests = []
    for case in cases:
        # 판결문 원문 앞 3,000자만 사용 (토큰 절약)
        raw_text = case.get("raw_text", "")[:3000]

        user_msg = f"""사건번호: {case['case_number']}
법원: {case['court']} ({case['court_level']})
선고일: {case['decision_date']}
사건유형: {case['case_type']}
주제분류: {case['topic']}

[판결문 원문 (일부)]
{raw_text}"""

        requests.append({
            "custom_id": f"case-{case['id']}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 900,
                "system": SUMMARIZE_SYSTEM,
                "messages": [{"role": "user", "content": user_msg}]
            }
        })
    return requests
```

### 법률 가이드 포스트 생성

```python
GUIDE_SYSTEM = """법률 정보 블로그 작가로서 일반 시민을 위한 실용적인 가이드를 작성하세요.
법률 용어는 쉬운 말로 설명하고, 실제 판례를 근거로 제시하세요.

JSON 출력:
{
  "title": "가이드 제목",
  "meta_description": "메타 설명",
  "intro": "도입부 (300자)",
  "sections": [
    {
      "heading": "소제목",
      "content": "내용 (400자)",
      "case_reference": "참고 판례 번호 (있으면)"
    }
  ],
  "dos_and_donts": {
    "do": ["해야 할 것 5가지"],
    "dont": ["하지 말아야 할 것 5가지"]
  },
  "faq": [{"q": "질문", "a": "답변"}],
  "disclaimer": "법률 면책 고지"
}"""

# 생성할 가이드 주제
GUIDE_TOPICS = [
    "층간소음 손해배상 청구 방법 — 판례로 보는 성공 조건",
    "전세보증금 못 받을 때 법적 대응 순서",
    "직장 내 괴롭힘 신고 전 알아야 할 판례",
    "개에 물렸을 때 손해배상 청구하는 법",
    "임금 체불 시 노동청 신고 vs 민사소송",
    "온라인 명예훼손 고소하기 전 알아야 할 것",
    "이혼 시 재산분할 — 법원은 어떻게 나누나",
    "교통사고 합의금 — 판례 기준 적정 금액은",
    "보이스피싱 피해 — 법적으로 구제받을 수 있나",
    "아파트 하자 분쟁 — 건설사 상대로 이기는 법"
]
```

---

## Step 3: 사이트 빌드 (`scripts/build_site.py`)

### 생성 페이지 목록

```python
def build_all():
    build_index()           # / — 주제별 판례 탐색 허브
    build_topic_pages()     # /topic/층간소음/ 등 10개 주제
    build_case_pages()      # /case/{id}/ — 판례별 상세 (SEO 핵심)
    build_guide_posts()     # /guide/{slug}/ — 법률 가이드
    build_latest()          # /latest/ — 최신 판례
    build_search()          # /search/ — 클라이언트 사이드 검색
    build_sitemap()
    build_robots()
```

### 판례 상세 페이지 구성 (`templates/case.html`)

```html
<!-- 페이지 구성 -->

<!-- 1. 헤더 -->
<h1>{{ case.seo_title }}</h1>
<div class="case-meta">
  {{ case.court }} · {{ case.decision_date }} · {{ case.case_type }}
</div>

<!-- 2. 한 줄 요약 박스 (강조) -->
<div class="summary-box bg-yellow-50 border-l-4 border-yellow-400 p-4">
  <p class="font-bold text-lg">💡 {{ case.summary_one_line }}</p>
</div>

<!-- 3. 어떤 상황이었나 -->
<section>
  <h2>어떤 상황이었나요?</h2>
  <p>{{ case.situation }}</p>
</section>

<!-- 4. 법원의 판단 -->
<section>
  <h2>법원은 어떻게 판단했나요?</h2>
  <p>{{ case.court_decision }}</p>
  <div class="verdict-badge {% if '인용' in case.result %}bg-green-100{% else %}bg-red-100{% endif %}">
    판결: {{ case.result }}
  </div>
</section>

<!-- 5. 승패를 가른 결정적 요소 -->
<section>
  <h2>🔑 승패를 가른 핵심 포인트</h2>
  <p>{{ case.what_mattered }}</p>
</section>

<!-- 6. 시민 교훈 -->
<section class="bg-blue-50 rounded-xl p-5">
  <h2>📌 비슷한 상황이라면?</h2>
  <p>{{ case.citizen_lesson }}</p>
  <div class="warning mt-3 text-orange-700">
    ⚠️ {{ case.warning }}
  </div>
</section>

<!-- 7. CPA 배너 — 법률상담 -->
<div class="cpa-banner bg-gray-800 text-white rounded-xl p-5">
  <p class="font-bold">비슷한 상황에 처해 계신가요?</p>
  <p class="text-gray-300 text-sm mt-1">법률 전문가에게 무료로 상담받아보세요</p>
  <a href="{{ cpa_url }}" class="mt-3 inline-block bg-blue-500 px-6 py-2 rounded-lg">
    무료 법률상담 받기 →
  </a>
</div>

<!-- 8. FAQ (Schema 포함) -->
<section>
  <h2>자주 묻는 질문</h2>
  {% for faq in case.faq %}
  <details class="faq-item">
    <summary>{{ faq.q }}</summary>
    <p>{{ faq.a }}</p>
  </details>
  {% endfor %}
</section>

<!-- 9. 원문 링크 (면책 고지) -->
<div class="disclaimer">
  <p>※ 이 페이지는 공개된 판결문을 AI로 요약한 정보입니다.
  법적 판단을 위해서는 반드시 전문 법률가와 상담하세요.</p>
  <a href="{{ case.source_url }}" target="_blank">원문 판결서 보기</a>
</div>
```

---

## Step 4: SEO 전략

### 핵심 키워드 타겟

| 키워드 패턴 | 예시 | 검색 의도 | 경쟁도 |
|------------|------|---------|--------|
| {주제} 판례 | 층간소음 판례 | 정보 탐색 | 낮음 |
| {주제} 손해배상 판결 | 층간소음 손해배상 판결 | 정보 탐색 | 없음 |
| {상황} 법적 대응 | 개물림 법적 대응 | 행동 의도 | 낮음 |
| {주제} 얼마나 받나 | 교통사고 합의금 얼마나 | 정보 탐색 | 중간 |
| {주제} 고소 방법 | 명예훼손 고소 방법 | 행동 의도 | 낮음 |

### 주제 페이지 구조 (`templates/topic.html`)

```
/topic/층간소음/ 페이지:
1. H1: "층간소음 판례 모음 — 법원은 어떻게 판결했나"
2. 주제 개요 (AI 생성, 300자)
3. 핵심 통계 (수집 판례 N건, 인용 비율 X%)
4. 판례 카드 그리드 (한 줄 요약 + 결과 배지)
5. 관련 가이드 포스트 링크
6. [CPA] 층간소음 전문 법률 상담
7. 관련 주제 링크
```

### 구조화 데이터

```python
# 판례 페이지 → LegalCase 스키마
JSON_LD_CASE = {
    "@context": "https://schema.org",
    "@type": "Article",
    "articleSection": "법률정보",
    "name": case["seo_title"],
    "description": case["meta_description"],
    "about": {
        "@type": "LegalCase",
        "name": case["case_number"],
        "court": {"@type": "Court", "name": case["court"]},
        "dateDecided": case["decision_date"]
    },
    "dateModified": build_date
}
```

---

## Step 5: 수익화

### 법률상담 CPA 매핑

```python
CPA_MAPPING = {
    "default": {
        "partner": "로톡",
        "url": "https://www.lawtalk.co.kr/?ref=lawsummary",
        "cpa_price": "유료 상담 전환 건당 5,000~15,000원",
        "text": "전국 변호사 무료 법률상담"
    },
    "이혼재산분할": {
        "partner": "이혼 전문 법무법인",
        "cpa_price": "리드 건당 10,000~30,000원"
    },
    "임금체불": {
        "partner": "노무사 플랫폼",
        "cpa_price": "리드 건당 5,000~15,000원"
    },
    "교통사고": {
        "partner": "손해사정사 플랫폼",
        "cpa_price": "리드 건당 8,000~20,000원"
    }
}
```

### AdSense 배치

```
판례 상세 페이지:
- 상황 설명 섹션 아래: 336×280 광고
- CPA 배너 아래: 반응형 광고
- 페이지 하단: 반응형 광고

주제 페이지:
- 판례 카드 4번째마다: 네이티브 광고
```

---

## GitHub Actions Job (추가분)

```yaml
deploy-lawsummary:
  runs-on: ubuntu-latest
  if: github.event_name == 'workflow_dispatch' ||
      github.event.schedule == '0 19 * * 1,4'   # 화·금 오전 4시 KST
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - run: pip install -r lawsummary/requirements.txt

    - name: Fetch new cases
      run: python lawsummary/scripts/fetch_court.py

    - name: Summarize with Claude Batch
      run: python lawsummary/scripts/summarize_cases.py
      env:
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

    - name: Build site
      run: python lawsummary/scripts/build_site.py

    - name: Deploy
      run: npx wrangler pages deploy lawsummary/dist --project-name=lawsummary
      env:
        CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## 클로드 코드 실행 순서

```bash
cd my-sites/lawsummary

# 1. 판례 데이터 첫 수집 (주제별 100건씩)
python scripts/fetch_court.py

# 2. Claude Batch 요약 (약 2시간 소요, 1,000건 기준)
python scripts/summarize_cases.py

# 3. 가이드 포스트 생성 (10개)
python scripts/generate_guides.py

# 4. 빌드
python scripts/build_site.py

# 5. 로컬 확인
python -m http.server 8003 --directory dist &

# 6. CF Pages 배포
npx wrangler pages project create lawsummary
npx wrangler pages deploy dist --project-name=lawsummary
```

---

## 성공 지표 (90일)

| 지표 | 최악 | 보통 |
|------|------|------|
| 수집 판례 수 | 500건 | 3,000건+ |
| 인덱싱 페이지 | 200개 | 1,500개+ |
| 일 방문자 | 80명 | 500명 |
| 법률상담 CPA 월 건수 | 0건 | 4건 (×15,000원) |
| AdSense 월 수익 | 1,200원 | 18,000원 |
| **월 총 수익** | **1,200원** | **78,000원** |

---

## 법적 주의사항 (필수)

- **저작권:** 판결문은 공공저작물 — 원문 그대로 대량 게시는 피하고, 요약·분석만 게시
- **면책 고지:** 모든 페이지 하단에 "이 정보는 참고용이며, 법적 자문이 아닙니다. 전문가 상담 필수" 표시
- **명예훼손 방지:** 개인 식별 가능한 정보 (이름, 주소 등) 전면 마스킹
- **정확성:** AI 요약 오류 신고 이메일 기재 필수
- **로톡 CPA:** 변호사 광고 규정 준수 (법률서비스 중개 플랫폼 이용 시 심의 불필요)
