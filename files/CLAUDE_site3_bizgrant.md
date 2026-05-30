# CLAUDE.md — 소상공인·창업 지원금 종합 안내 사이트

## 프로젝트 개요

**사이트명:** 지원금 인포 (가칭: `bizgrant.kr`)
**레포 위치:** `my-sites/bizgrant/`
**목적:** 기업마당·소상공인진흥공단 공고를 AI로 분류·요약 → 검색 유입 → 정책자금 컨설팅 CPA + AdSense
**핵심 가치:** 흩어진 정부 지원사업을 한 곳에서 필터링 + AI 요약으로 빠르게 파악
**아키텍처:** Python 빌더 → 완전 정적 HTML → Cloudflare Pages
**자동화:** GitHub Actions 주 2회 (월·목) 데이터 갱신 + 빌드
**AI 활용:** Claude Haiku 4.5 Batch API — 공고문 요약 + 카테고리 자동 분류

---

## 기술 스택

| 레이어 | 선택 | 이유 |
|--------|------|------|
| 빌더 | Python 3.11 + Jinja2 | 공통 스택 통일 |
| 검색/필터 | Fuse.js (CDN, 클라이언트 사이드) | 서버 없이 실시간 검색 |
| CSS | Tailwind CSS CDN | 빌드 불필요 |
| 배포 | Cloudflare Pages | 무료 |
| CI/CD | GitHub Actions (my-sites 레포 공유) | 무료 |
| 데이터 | 기업마당 API + 소상공인진흥공단 공고 스크래핑 | 무료 |
| AI | Claude Haiku 4.5 Batch API | 공고 요약·분류 |

---

## 디렉토리 구조

```
my-sites/bizgrant/
├── CLAUDE.md
├── requirements.txt
├── data/
│   ├── raw/                        # 원본 공고 JSON (git 제외)
│   ├── processed/
│   │   ├── grants.json             # 전체 지원사업 목록
│   │   ├── grants_by_category.json # 카테고리별 분류
│   │   └── grants_search_index.json # Fuse.js 검색 인덱스
│   └── content/
│       └── posts/                  # AI 생성 가이드 포스트
├── scripts/
│   ├── fetch_bizinfo.py            # 기업마당 API 수집
│   ├── fetch_semas.py              # 소상공인진흥공단 스크래핑
│   ├── classify_grants.py          # Claude Batch로 분류·요약
│   ├── build_search_index.py       # Fuse.js 인덱스 생성
│   └── build_site.py              # Jinja2 → HTML 빌드
├── templates/
│   ├── base.html
│   ├── index.html                  # 메인 (필터 + 검색)
│   ├── grant.html                  # 지원사업 상세 페이지 (SEO 핵심)
│   ├── category.html               # 카테고리 페이지
│   ├── calculator.html             # 지원금 자격 계산기
│   └── guide_post.html             # 가이드 블로그 포스트
└── dist/
```

---

## Step 1: 데이터 수집

### A. 기업마당 API (`scripts/fetch_bizinfo.py`)

```python
"""
기업마당 (중소벤처기업부) 지원사업 공고 수집
API: https://www.bizinfo.go.kr/web/lay1/bbs/S1T122C128/AS/74/list.do
공공데이터포털: "중소기업 지원사업 공고정보" 검색
"""

import requests
import json
from pathlib import Path
from datetime import datetime

BIZINFO_API = "https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do"

# 수집 파라미터
PARAMS = {
    "crtfcKey": "BIZINFO_API_KEY",  # 환경변수
    "dataType": "json",
    "pageUnit": "100",
    "pageIndex": "1",
    # 지원분야 코드
    # 01: 자금, 02: 기술, 03: 인력, 04: 수출, 05: 내수,
    # 06: 창업, 07: 경영, 08: 정보화, 09: 연구개발
}

# 출력 스키마
GRANT_SCHEMA = {
    "id": "str",                    # 공고번호 slug
    "title": "str",                 # 공고명
    "agency": "str",                # 주관기관
    "category": "str",              # 분류 (AI 자동 분류)
    "subcategory": "str",           # 세부 분류
    "target": "str",                # 지원대상 (요약)
    "amount": "str",                # 지원금액
    "period_start": "str",          # 접수 시작일
    "period_end": "str",            # 접수 마감일
    "region": "str",                # 지역 (전국/서울/경기 등)
    "business_type": "list",        # 업종 (제조업, 서비스업 등)
    "company_size": "str",          # 기업규모 (소기업/중기업/소상공인)
    "founding_year": "int",         # 창업 연차 조건
    "summary": "str",               # AI 생성 3줄 요약
    "ai_eligibility": "str",        # AI 생성 자격요건 설명
    "ai_how_to_apply": "str",       # AI 생성 신청방법
    "difficulty": "str",            # AI 분석 신청 난이도 (하/중/상)
    "tags": "list",                 # SEO 태그
    "original_url": "str",          # 원문 링크
    "is_active": "bool",            # 마감 여부
    "updated_at": "str"
}

def fetch_all_grants() -> list:
    """전체 지원사업 공고 수집 (페이지네이션)"""
    all_grants = []
    page = 1

    while True:
        PARAMS["pageIndex"] = str(page)
        resp = requests.get(BIZINFO_API, params=PARAMS, timeout=30)
        data = resp.json()

        items = data.get("items", [])
        if not items:
            break

        all_grants.extend(items)
        print(f"페이지 {page}: {len(items)}개 수집 (누적: {len(all_grants)})")

        if len(items) < 100:
            break
        page += 1

    return all_grants
```

### B. 소상공인진흥공단 (`scripts/fetch_semas.py`)

```python
"""
소상공인시장진흥공단 지원사업 수집
URL: https://www.semas.or.kr/web/main/index.kmdc
공공데이터포털 API 또는 스크래핑
"""

import requests
from bs4 import BeautifulSoup

SEMAS_URL = "https://www.semas.or.kr/web/SUB02/SUB0201/SUB020101/board.kmdc"

def fetch_semas_grants() -> list:
    """소상공인진흥공단 공고 수집"""
    grants = []
    headers = {"User-Agent": "Mozilla/5.0"}

    for page in range(1, 10):
        resp = requests.get(
            SEMAS_URL,
            params={"pageIndex": page},
            headers=headers,
            timeout=15
        )
        # 요청 간격 준수
        import time; time.sleep(2)

        soup = BeautifulSoup(resp.text, "lxml")
        rows = soup.select("table.board_list tbody tr")

        if not rows:
            break

        for row in rows:
            cols = row.select("td")
            if len(cols) < 4:
                continue

            grants.append({
                "title": cols[1].get_text(strip=True),
                "agency": "소상공인시장진흥공단",
                "period": cols[2].get_text(strip=True),
                "status": cols[3].get_text(strip=True),
                "url": "https://www.semas.or.kr" + cols[1].select_one("a")["href"]
            })

    return grants
```

---

## Step 2: AI 분류·요약 (`scripts/classify_grants.py`)

### Claude Haiku Batch로 공고 처리

```python
"""
공고문 → AI 분류 + 3줄 요약 + 자격요건 설명
Batch API 사용으로 비용 50% 절감
"""

import anthropic
import json
from pathlib import Path
import sys
sys.path.append("../shared/utils")
from claude_batch import run_batch_pipeline

client = anthropic.Anthropic()

CLASSIFY_SYSTEM = """당신은 정부 지원사업 전문 분석가입니다.
소상공인과 창업자가 이해하기 쉽게 공고를 분석해주세요.

반드시 JSON만 출력하세요 (마크다운 코드블록 없이):
{
  "category": "자금지원|기술지원|인력지원|창업지원|수출지원|컨설팅|교육훈련|기타",
  "subcategory": "세부 분류명",
  "target_summary": "지원대상 한 줄 요약 (50자 이내)",
  "amount_summary": "지원금액 한 줄 (예: 최대 5천만원 융자)",
  "region": "전국|서울|경기|부산|기타지역명",
  "company_size": "소기업|중기업|소상공인|스타트업|전체",
  "founding_condition": "창업 N년 이내 또는 제한없음",
  "summary_3lines": "3줄 요약 (각 줄 50자 이내, \\n으로 구분)",
  "eligibility_plain": "자격요건을 쉬운 말로 설명 (200자)",
  "how_to_apply": "신청방법 단계별 설명 (150자)",
  "difficulty": "하|중|상",
  "difficulty_reason": "난이도 판단 이유 (50자)",
  "tags": ["태그1", "태그2", "태그3"],
  "seo_title": "SEO 최적화 제목 (60자 이내, 키워드 포함)",
  "meta_description": "메타 설명 (155자 이내)"
}"""

def build_classify_requests(grants: list) -> list:
    """Batch 요청 생성"""
    requests = []
    for grant in grants:
        user_msg = f"""공고명: {grant['title']}
주관기관: {grant.get('agency', '')}
접수기간: {grant.get('period', '')}
공고내용: {grant.get('content', grant.get('title', ''))[:1000]}"""

        requests.append({
            "custom_id": f"grant-{grant['id']}",
            "params": {
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 800,
                "system": CLASSIFY_SYSTEM,
                "messages": [{"role": "user", "content": user_msg}]
            }
        })
    return requests

def classify_all_grants(grants: list) -> list:
    """전체 공고 분류 실행"""
    requests = build_classify_requests(grants)

    results = run_batch_pipeline(
        requests=requests,
        output_path="data/processed/classified_results.json",
        batch_name="bizgrant_classify"
    )

    # 원본 데이터와 AI 결과 병합
    enriched = []
    for grant in grants:
        key = f"grant-{grant['id']}"
        ai_data = results.get(key, {})
        enriched.append({**grant, **ai_data})

    return enriched
```

### AI 가이드 포스트 생성

```python
GUIDE_POST_SYSTEM = """소상공인과 예비창업자를 위한 실용적인 지원금 가이드를 작성하세요.
검색 의도: 지원금 찾는 방법, 신청 방법, 자격 확인

JSON 출력:
{
  "title": "SEO 제목",
  "meta_description": "메타 설명",
  "intro": "도입부 (300자)",
  "sections": [
    {"heading": "소제목", "content": "내용 (300자)"}
  ],
  "checklist": ["신청 전 확인사항 5가지"],
  "faq": [{"q": "질문", "a": "답변"}]
}"""

# 생성할 가이드 포스트 주제
GUIDE_TOPICS = [
    "소상공인 지원금 신청 완전 가이드 2026",
    "창업 1년차가 받을 수 있는 정부 지원금 총정리",
    "식당 창업 지원금 종류와 신청 방법",
    "온라인 쇼핑몰 창업 지원사업 모음",
    "소상공인 저금리 대출 지원사업 비교",
    "기업마당 사용법 완벽 가이드",
    "폐업 소상공인을 위한 지원제도",
    "청년 창업 지원금 한눈에 보기",
    "여성 창업자 전용 지원사업",
    "지역별 소상공인 지원사업 찾는 법"
]
```

---

## Step 3: 클라이언트 사이드 검색 (Fuse.js)

### 검색 인덱스 생성 (`scripts/build_search_index.py`)

```python
"""
Fuse.js용 검색 인덱스 JSON 생성
서버 없이 브라우저에서 실시간 검색 가능
"""

import json
from pathlib import Path

def build_search_index(grants: list) -> dict:
    """
    Fuse.js가 읽을 수 있는 경량 인덱스 생성
    상세 데이터는 개별 페이지에 있으므로 핵심 필드만 포함
    """
    index = []
    for grant in grants:
        if not grant.get("is_active", True):
            continue

        index.append({
            "id": grant["id"],
            "title": grant["title"],
            "agency": grant["agency"],
            "category": grant.get("category", ""),
            "region": grant.get("region", "전국"),
            "company_size": grant.get("company_size", ""),
            "amount_summary": grant.get("amount_summary", ""),
            "tags": grant.get("tags", []),
            "period_end": grant.get("period_end", ""),
            "url": f"/grant/{grant['id']}/"
        })

    # 파일 크기 최소화 (gzip 전 약 2MB 이내 유지)
    output = {
        "updated_at": __import__("datetime").datetime.now().isoformat(),
        "total": len(index),
        "grants": index
    }

    Path("dist/search-index.json").write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    )
    print(f"검색 인덱스 생성: {len(index)}개")
    return output
```

### 검색 UI 컴포넌트 (템플릿 내 인라인)

```html
<!-- templates/index.html 검색 섹션 -->

<!-- Fuse.js CDN -->
<script src="https://cdn.jsdelivr.net/npm/fuse.js@7.0.0/dist/fuse.min.js"></script>

<div class="search-section">
  <!-- 키워드 검색 -->
  <input type="text" id="search-input"
    placeholder="키워드 검색 (예: 음식점, 창업, 서울)"
    class="w-full px-4 py-3 rounded-xl border-2 border-gray-200 focus:border-blue-500 text-lg">

  <!-- 필터 -->
  <div class="filters mt-4 flex flex-wrap gap-2">
    <select id="filter-category" class="filter-select">
      <option value="">전체 분류</option>
      <option value="자금지원">자금지원</option>
      <option value="창업지원">창업지원</option>
      <option value="기술지원">기술지원</option>
      <option value="인력지원">인력지원</option>
      <option value="수출지원">수출지원</option>
    </select>

    <select id="filter-region" class="filter-select">
      <option value="">전체 지역</option>
      <option value="전국">전국</option>
      <option value="서울">서울</option>
      <option value="경기">경기</option>
      <!-- ... -->
    </select>

    <select id="filter-size" class="filter-select">
      <option value="">전체 규모</option>
      <option value="소상공인">소상공인</option>
      <option value="소기업">소기업</option>
      <option value="스타트업">스타트업</option>
    </select>

    <label class="flex items-center gap-2 cursor-pointer">
      <input type="checkbox" id="filter-active" checked>
      <span>접수 중만 보기</span>
    </label>
  </div>

  <!-- 결과 카운트 -->
  <p class="mt-3 text-gray-500">
    <span id="result-count">0</span>개 지원사업
  </p>

  <!-- 결과 목록 -->
  <div id="results-grid" class="mt-4 grid gap-4"></div>
</div>

<script>
  let fuseInstance = null;
  let allGrants = [];

  // 검색 인덱스 로드
  fetch("/search-index.json")
    .then(r => r.json())
    .then(data => {
      allGrants = data.grants;
      fuseInstance = new Fuse(allGrants, {
        keys: [
          { name: "title", weight: 0.4 },
          { name: "tags", weight: 0.3 },
          { name: "agency", weight: 0.2 },
          { name: "category", weight: 0.1 }
        ],
        threshold: 0.3,
        includeScore: true
      });
      renderResults(allGrants);
    });

  function getFiltered() {
    const query = document.getElementById("search-input").value.trim();
    const category = document.getElementById("filter-category").value;
    const region = document.getElementById("filter-region").value;
    const size = document.getElementById("filter-size").value;
    const activeOnly = document.getElementById("filter-active").checked;

    let results = query
      ? fuseInstance.search(query).map(r => r.item)
      : [...allGrants];

    if (category) results = results.filter(g => g.category === category);
    if (region) results = results.filter(g => g.region === region || g.region === "전국");
    if (size) results = results.filter(g => g.company_size === size || g.company_size === "전체");
    if (activeOnly) {
      const today = new Date().toISOString().split("T")[0];
      results = results.filter(g => !g.period_end || g.period_end >= today);
    }

    return results;
  }

  function renderResults(grants) {
    document.getElementById("result-count").textContent = grants.length;
    const grid = document.getElementById("results-grid");
    grid.innerHTML = grants.slice(0, 30).map(g => `
      <a href="${g.url}" class="block bg-white rounded-xl p-5 shadow hover:shadow-md transition border border-gray-100">
        <div class="flex justify-between items-start">
          <span class="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full">${g.category}</span>
          <span class="text-xs text-gray-400">${g.region}</span>
        </div>
        <h3 class="mt-2 font-bold text-gray-800 line-clamp-2">${g.title}</h3>
        <p class="mt-1 text-sm text-gray-500">${g.agency}</p>
        <div class="mt-2 flex gap-2 flex-wrap">
          ${(g.tags || []).slice(0, 3).map(t => `
            <span class="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">${t}</span>
          `).join("")}
        </div>
        <p class="mt-2 text-sm font-semibold text-green-700">${g.amount_summary || ""}</p>
      </a>
    `).join("");
  }

  // 이벤트 바인딩 (debounce)
  let timer;
  ["search-input", "filter-category", "filter-region", "filter-size", "filter-active"]
    .forEach(id => {
      document.getElementById(id).addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(() => renderResults(getFiltered()), 200);
      });
    });
</script>
```

---

## Step 4: 지원사업 상세 페이지 (`templates/grant.html`)

```
페이지 구성:
1. H1: "{공고명} - {주관기관} 지원사업 안내"
2. 핵심 정보 카드
   - 지원금액 / 지원대상 / 접수마감 / 지역
3. 자격요건 체크리스트 (AI 생성, 체크박스 UI)
4. 3줄 요약 박스 (강조)
5. 신청방법 단계별 안내 (AI 생성)
6. 난이도 표시 (하/중/상 + 이유)
7. [CPA 배너] "전문가 컨설팅 받기" (정책자금 컨설팅 업체)
8. 원문 바로가기 버튼
9. 관련 지원사업 추천
10. FAQ (구조화 데이터)
```

### 자격요건 체크리스트 UI

```html
<!-- 체크리스트 컴포넌트 -->
<div class="eligibility-checker bg-blue-50 rounded-xl p-6">
  <h2 class="text-lg font-bold mb-4">✅ 내가 신청 가능한지 확인하기</h2>
  <div class="space-y-3">
    {% for item in grant.eligibility_checklist %}
    <label class="flex items-start gap-3 cursor-pointer">
      <input type="checkbox" class="mt-1 w-5 h-5 rounded">
      <span class="text-gray-700">{{ item }}</span>
    </label>
    {% endfor %}
  </div>
  <div id="eligibility-result" class="mt-4 hidden p-3 rounded-lg text-center font-bold"></div>
  <button onclick="checkEligibility()"
    class="mt-3 w-full bg-blue-600 text-white py-2 rounded-lg hover:bg-blue-700">
    자격 확인하기
  </button>
</div>
```

---

## Step 5: SEO 전략

### 핵심 키워드 타겟

| 키워드 | 월 검색량 | 경쟁도 | 페이지 유형 |
|--------|---------|--------|-----------|
| 소상공인 지원금 2026 | 매우 높음 | 중 | 메인/가이드 |
| 식당 창업 지원금 | 높음 | 낮음 | 카테고리 |
| 기업마당 신청방법 | 중간 | 낮음 | 가이드 |
| [공고명] 신청 | 낮음 | 없음 | 상세 페이지 |
| 소상공인 저금리 대출 | 높음 | 중 | 가이드 |

### 구조화 데이터

```python
# 지원사업 → Event 스키마 (마감일 포함)
JSON_LD_GRANT = {
    "@context": "https://schema.org",
    "@type": "GovernmentService",
    "name": grant["title"],
    "description": grant["summary_3lines"],
    "provider": {
        "@type": "GovernmentOrganization",
        "name": grant["agency"]
    },
    "availableChannel": {
        "@type": "ServiceChannel",
        "serviceUrl": grant["original_url"]
    }
}
```

---

## Step 6: 수익화

### CPA 배너 — 정책자금 컨설팅

```python
# 공고 카테고리별 CPA 매핑
CPA_MAPPING = {
    "자금지원": {
        "partner": "정책자금 컨설팅 A사",
        "cpa_price": "리드당 20,000~50,000원",
        "banner_text": "정책자금 신청, 전문가와 함께하면 성공률이 달라집니다",
        "url": "https://partner-link.kr/bizgrant-ref"
    },
    "창업지원": {
        "partner": "창업 컨설팅 B사",
        "cpa_price": "리드당 15,000~30,000원",
        "banner_text": "창업 지원금 신청 대행 서비스"
    }
}
```

### AdSense 배치

```
메인 페이지: 검색결과 상단 + 그리드 중간 (5번째마다)
상세 페이지: 핵심 정보 카드 아래 + 페이지 하단
가이드 포스트: 본문 중간 + 하단
```

---

## GitHub Actions (my-sites 레포 공유)

```yaml
# .github/workflows/deploy_all.yml 에 추가할 job

deploy-bizgrant:
  runs-on: ubuntu-latest
  if: github.event_name == 'workflow_dispatch' ||
      github.event.schedule == '0 20 * * 0,3'   # 일·수 오전 5시 KST
  steps:
    - uses: actions/checkout@v4

    - uses: actions/setup-python@v5
      with:
        python-version: '3.11'

    - run: pip install -r bizgrant/requirements.txt

    - name: Fetch grant data
      run: python bizgrant/scripts/fetch_bizinfo.py
      env:
        BIZINFO_API_KEY: ${{ secrets.BIZINFO_API_KEY }}

    - name: Fetch SEMAS data
      run: python bizgrant/scripts/fetch_semas.py

    - name: Classify with Claude Batch
      run: python bizgrant/scripts/classify_grants.py
      env:
        ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

    - name: Build search index
      run: python bizgrant/scripts/build_search_index.py

    - name: Build site
      run: python bizgrant/scripts/build_site.py

    - name: Deploy to Cloudflare Pages
      run: npx wrangler pages deploy bizgrant/dist --project-name=bizgrant
      env:
        CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## 환경변수 (GitHub Secrets 추가분)

| 변수명 | 설명 |
|--------|------|
| `BIZINFO_API_KEY` | 기업마당 API 키 (data.go.kr 신청) |

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
```

---

## 클로드 코드 실행 순서

```bash
cd my-sites/bizgrant

# 1. 기업마당 API 키 신청 후 설정
# data.go.kr → "기업마당 지원사업 공고정보" 검색 → 활용신청

# 2. 데이터 첫 수집
python scripts/fetch_bizinfo.py
python scripts/fetch_semas.py

# 3. Claude Batch 분류 (약 1~2시간 소요)
python scripts/classify_grants.py

# 4. 검색 인덱스 생성
python scripts/build_search_index.py

# 5. 사이트 빌드
python scripts/build_site.py

# 6. 로컬 확인
python -m http.server 8002 --directory dist &

# 7. CF Pages 프로젝트 생성 (1회)
npx wrangler pages project create bizgrant

# 8. 배포
npx wrangler pages deploy dist --project-name=bizgrant
```

---

## 성공 지표 (90일)

| 지표 | 최악 | 보통 |
|------|------|------|
| 인덱싱 페이지 | 200개 | 1,500개+ |
| 일 방문자 | 100명 | 800명 |
| 컨설팅 CPA 월 건수 | 0건 | 3건 (×30,000원) |
| AdSense 월 수익 | 1,500원 | 28,800원 |
| **월 총 수익** | **1,500원** | **118,800원** |

---

## 주의사항

- 기업마당 공고 원문 저작권: 요약·분석은 허용, 전문 복사는 금지
- 마감된 공고: 삭제하지 말고 `is_active: false` 처리 후 유지 (SEO 자산)
- 지원금 금액 오기재 시 민원 발생 가능 → 반드시 "원문 확인 필수" 고지
- 컨설팅 CPA 광고: 금융광고 심의 필요 여부 확인 (정책자금 대행은 심의 불필요)
