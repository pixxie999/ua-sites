# CLAUDE.md — my-sites 레포 전체 통합 가이드

## 레포 전체 구조

```
ua-sites/                              ← GitHub 레포 루트
├── CLAUDE.md                          ← 이 파일 (레포 전체 가이드)
│
├── .github/
│   └── workflows/
│       └── deploy_all.yml             ← 6개 사이트 통합 배포
│
├── shared/                            ← 6개 사이트 공통 코드
│   └── utils/
│       ├── claude_batch.py            ← Claude Batch API 헬퍼
│       ├── seo_helpers.py             ← sitemap, robots, JSON-LD
│       └── adsense.py                 ← AdSense 광고 관리
│
├── qualpass/                          ← Phase 1: 자격증 합격률
│   └── CLAUDE.md
│
├── todaymarket/                       ← Phase 1: 농산물 도매가격
│   └── CLAUDE.md
│
├── bizgrant/                          ← Phase 2: 소상공인 지원금
│   └── CLAUDE.md
│
├── lawsummary/                        ← Phase 2: 판결문 AI 요약
│   └── CLAUDE.md
│
├── beachsafe/                         ← Phase 3: 해수욕장 안전
│   └── CLAUDE.md
│
└── uapress/                          ← Phase 3: 문화행사 캘린더
    └── CLAUDE.md
```

---

## 통합 GitHub Actions (`.github/workflows/deploy_all.yml`)

```yaml
name: Deploy All Sites

on:
  # 수동 실행 (단일 사이트 또는 전체 선택)
  workflow_dispatch:
    inputs:
      site:
        description: '배포할 사이트 (all / qualpass / todaymarket / bizgrant / lawsummary / beachsafe / uapress)'
        required: true
        default: 'all'

  # 자동 스케줄 (사이트별 최적 주기)
  schedule:
    - cron: '0 20 * * *'      # 매일 오전 5시 KST (qualpass, todaymarket)
    - cron: '0 19 * * 0,3'    # 일·수 오전 4시 KST (bizgrant)
    - cron: '0 19 * * 1,4'    # 화·금 오전 4시 KST (lawsummary, uapress)
    - cron: '0 20 * * 0'      # 매주 일 오전 5시 KST (beachsafe 비수기)

# 공통 환경변수
env:
  PYTHON_VERSION: '3.11'

jobs:

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Phase 1 — Site 1: qualpass (자격증 합격률)
  # 주기: 매일 / 데이터: Q-Net + 공공데이터포털
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  deploy-qualpass:
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' &&
      (github.event.inputs.site == 'all' || github.event.inputs.site == 'qualpass') ||
      github.event.schedule == '0 20 * * *'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-qualpass-${{ hashFiles('qualpass/requirements.txt') }}

      - run: pip install -r qualpass/requirements.txt

      - name: Fetch Q-Net data
        run: python qualpass/scripts/fetch_qnet.py
        env:
          DATA_GOV_API_KEY: ${{ secrets.DATA_GOV_API_KEY }}

      - name: Process data
        run: python qualpass/scripts/process_data.py

      - name: Generate AI content (weekly only)
        if: github.event.schedule == '0 20 * * 0' || github.event_name == 'workflow_dispatch'
        run: python qualpass/scripts/generate_content.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Build site
        run: python qualpass/scripts/build_site.py

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy qualpass/dist --project-name=qualpass
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Phase 1 — Site 2: todaymarket (농산물 도매가)
  # 주기: 매일 / 데이터: KAMIS API
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  deploy-todaymarket:
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' &&
      (github.event.inputs.site == 'all' || github.event.inputs.site == 'todaymarket') ||
      github.event.schedule == '0 20 * * *'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-todaymarket-${{ hashFiles('todaymarket/requirements.txt') }}

      - run: pip install -r todaymarket/requirements.txt

      - name: Fetch KAMIS prices
        run: python todaymarket/scripts/fetch_kamis.py
        env:
          KAMIS_API_KEY: ${{ secrets.KAMIS_API_KEY }}
          KAMIS_CERT_ID: ${{ secrets.KAMIS_CERT_ID }}

      - name: Process price data
        run: python todaymarket/scripts/process_prices.py

      - name: Generate weekly report (Friday only)
        if: github.event.schedule == '0 19 * * 4' || github.event_name == 'workflow_dispatch'
        run: python todaymarket/scripts/generate_content.py --type weekly_report
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Build site
        run: python todaymarket/scripts/build_site.py

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy todaymarket/dist --project-name=todaymarket
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Phase 2 — Site 3: bizgrant (소상공인 지원금)
  # 주기: 주 2회 (일·수) / 데이터: 기업마당 + 소진공
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  deploy-bizgrant:
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' &&
      (github.event.inputs.site == 'all' || github.event.inputs.site == 'bizgrant') ||
      github.event.schedule == '0 19 * * 0,3'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-bizgrant-${{ hashFiles('bizgrant/requirements.txt') }}

      - run: pip install -r bizgrant/requirements.txt

      - name: Fetch bizinfo data
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

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Phase 2 — Site 4: lawsummary (판결문 AI 요약)
  # 주기: 주 2회 (화·금) / 데이터: 대법원 판결서
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  deploy-lawsummary:
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' &&
      (github.event.inputs.site == 'all' || github.event.inputs.site == 'lawsummary') ||
      github.event.schedule == '0 19 * * 1,4'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-lawsummary-${{ hashFiles('lawsummary/requirements.txt') }}

      - run: pip install -r lawsummary/requirements.txt

      - name: Fetch new court cases
        run: python lawsummary/scripts/fetch_court.py

      - name: Summarize with Claude Batch
        run: python lawsummary/scripts/summarize_cases.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Build site
        run: python lawsummary/scripts/build_site.py

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy lawsummary/dist --project-name=lawsummary
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Phase 3 — Site 5: beachsafe (해수욕장 안전)
  # 주기: 여름 매일 / 비수기 주 1회
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  deploy-beachsafe:
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' &&
      (github.event.inputs.site == 'all' || github.event.inputs.site == 'beachsafe') ||
      github.event.schedule == '0 20 * * *' ||
      github.event.schedule == '0 20 * * 0'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-beachsafe-${{ hashFiles('beachsafe/requirements.txt') }}

      - run: pip install -r beachsafe/requirements.txt

      - name: Fetch beach & weather data
        run: python beachsafe/scripts/fetch_mof.py
        env:
          MOF_API_KEY: ${{ secrets.MOF_API_KEY }}
          KMA_API_KEY: ${{ secrets.KMA_API_KEY }}

      - name: Generate AI guides (weekly)
        if: github.event.schedule == '0 20 * * 0' || github.event_name == 'workflow_dispatch'
        run: python beachsafe/scripts/generate_guides.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Build site
        run: python beachsafe/scripts/build_site.py

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy beachsafe/dist --project-name=beachsafe
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # Phase 3 — Site 6: uapress (문화행사 캘린더)
  # 주기: 주 2회 (화·금) / 데이터: Tour API + 문화부
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  deploy-uapress:
    runs-on: ubuntu-latest
    if: |
      github.event_name == 'workflow_dispatch' &&
      (github.event.inputs.site == 'all' || github.event.inputs.site == 'uapress') ||
      github.event.schedule == '0 19 * * 1,4'
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Cache pip
        uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: pip-uapress-${{ hashFiles('uapress/requirements.txt') }}

      - run: pip install -r uapress/requirements.txt

      - name: Fetch Tour API events
        run: python uapress/scripts/fetch_tour_api.py
        env:
          TOUR_API_KEY: ${{ secrets.TOUR_API_KEY }}
          CULTURE_API_KEY: ${{ secrets.CULTURE_API_KEY }}

      - name: Generate AI content
        run: python uapress/scripts/generate_content.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Build site
        run: python uapress/scripts/build_site.py

      - name: Deploy to Cloudflare Pages
        run: npx wrangler pages deploy uapress/dist --project-name=uapress
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## GitHub Secrets 전체 목록

| Secret 이름 | 사용 사이트 | 획득처 |
|------------|------------|--------|
| `ANTHROPIC_API_KEY` | 전체 | console.anthropic.com |
| `CLOUDFLARE_API_TOKEN` | 전체 | CF 대시보드 → API Tokens → Pages 권한 |
| `CLOUDFLARE_ACCOUNT_ID` | 전체 | CF 대시보드 우측 하단 |
| `DATA_GOV_API_KEY` | qualpass | data.go.kr 회원가입 후 API 신청 |
| `KAMIS_API_KEY` | todaymarket | data.go.kr "농산물유통정보" |
| `KAMIS_CERT_ID` | todaymarket | KAMIS 인증 ID |
| `BIZINFO_API_KEY` | bizgrant | data.go.kr "기업마당 지원사업" |
| `MOF_API_KEY` | beachsafe | data.go.kr "해수욕장 정보" |
| `KMA_API_KEY` | beachsafe | data.go.kr "기상청 단기예보" |
| `TOUR_API_KEY` | uapress | data.go.kr "관광정보서비스" |
| `CULTURE_API_KEY` | uapress | data.go.kr "문화행사 정보" |
| `ADSENSE_PUBLISHER_ID` | 전체 | AdSense 대시보드 (승인 후) |

---

## Cloudflare Pages 프로젝트 초기 생성 (1회)

```bash
# wrangler 전역 설치
npm install -g wrangler

# CF 로그인
wrangler login

# 6개 프로젝트 생성 (빈 프로젝트 — 이후 GitHub Actions가 배포)
npx wrangler pages project create qualpass
npx wrangler pages project create todaymarket
npx wrangler pages project create bizgrant
npx wrangler pages project create lawsummary
npx wrangler pages project create beachsafe
npx wrangler pages project create uapress

# 각 프로젝트에 커스텀 도메인 연결 (CF 대시보드에서)
# qualpass → qualpass.kr
# todaymarket → todaymarket.kr (또는 farmtoday.kr)
# bizgrant → bizgrant.kr
# lawsummary → lawsummary.kr
# beachsafe → beachsafe.kr
# uapress → uapress.kr
```

---

## 전체 구축 로드맵 요약

```
Week 1-2: Phase 1 구축·배포
  → qualpass (자격증 합격률)
  → todaymarket (농산물 도매가)
  → Search Console 등록, AdSense 신청

Week 3-4: Phase 1 SEO 안정화 + Phase 2 구축
  → bizgrant (소상공인 지원금)
  → lawsummary (판결문 AI 요약)
  → Phase 1 AdSense 승인 목표

Week 5-6: Phase 2 배포 + Phase 3 구축
  → beachsafe (해수욕장 — 여름 전 선제 구축)
  → uapress (문화행사 캘린더)

Week 7-12: 전체 자동 운영
  → GitHub Actions 6개 job 자동 실행
  → 마스터 개입 없이 95% 자동화
  → CPA 제휴 순차 활성화
```

---

## 긴급 수동 배포 방법

```bash
# 특정 사이트만 즉시 배포 (GitHub Actions UI)
# GitHub → my-sites 레포 → Actions → Deploy All Sites
# → Run workflow → site: qualpass → Run

# 또는 로컬에서 직접 배포
cd my-sites/qualpass
python scripts/fetch_qnet.py && python scripts/build_site.py
npx wrangler pages deploy dist --project-name=qualpass
```
