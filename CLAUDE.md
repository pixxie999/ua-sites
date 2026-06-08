# CLAUDE.md — ua-sites 레포 전체 가이드

---

## ⛔ 절대 금지 — git 커밋 규칙

> **이 규칙은 Claude Code가 반드시 따라야 하는 최우선 규칙입니다.**

### ua-sites 레포에서 커밋 허용 폴더 (화이트리스트)

| 폴더 | 배포 워크플로우 | 허용 |
|------|----------------|------|
| `uapress/` | `deploy_uapress.yml` | ✅ |
| `uasoft.kr/` | `deploy_uasoft.yml` | ✅ |
| `.github/` | 워크플로우 파일 | ✅ |
| `CLAUDE.md` | 레포 가이드 | ✅ |
| `.gitignore` | git 설정 | ✅ |

### 절대 커밋 금지 폴더

```
brainplayzone/   ← 별도 프로젝트, 이 레포와 무관
kschoolfood/     ← 별도 프로젝트, 이 레포와 무관
qualpass/        ← 워크플로우 없음 (추후 추가 시까지 금지)
todaymarket/     ← 워크플로우 없음 (추후 추가 시까지 금지)
bizgrant/        ← 워크플로우 없음
lawsummary/      ← 워크플로우 없음
beachsafe/       ← 워크플로우 없음
files/           ← 임시 작업 파일
tmp/             ← 임시 파일
uasoft.kr/tmp/  ← 임시 파일
```

### 새 사이트 추가 시 순서

```
1. .github/workflows/deploy_{사이트명}.yml 작성 (워크플로우 먼저)
2. 해당 사이트 폴더를 .gitignore에서 제거
3. 그 다음 사이트 폴더 커밋
```

> ⚠️ **`git add .` 또는 `git add -A` 절대 사용 금지**
> 반드시 파일/폴더를 명시적으로 지정해서 add:
> ```bash
> git add uapress/scripts/build_site.py   # ✅ 명시적 경로
> git add uapress/templates/              # ✅ 허용 폴더
> git add -A                              # ❌ 절대 금지
> git add .                               # ❌ 절대 금지
> ```

---

## 레포 개요

**레포명:** `ua-sites`
**목적:** 공공데이터 기반 정적 사이트 다수 운영 (모노레포)
**배포:** Cloudflare Pages (사이트별 개별 프로젝트)
**CI/CD:** GitHub Actions — 사이트별 job 병렬 실행
**공통 원칙:**
- 서버 비용 0원 (Cloudflare Pages 무료 + GitHub Actions Public Repo 무료)
- Claude API는 Batch 모드만 사용 (50% 할인)
- 모든 데이터는 공공API 또는 합법적 스크래핑
- 마스터 개입 없이 95% 자동 운영

---

## 현재 레포 구조

```
ua-sites/                              ← GitHub 레포 루트
├── CLAUDE.md                          ← 이 파일 (레포 전체 가이드)
│
├── .github/
│   └── workflows/
│       └── deploy_all.yml             ← 전체 사이트 통합 배포
│
├── shared/                            ← 전 사이트 공통 유틸
│   └── utils/
│       ├── claude_batch.py            ← Claude Batch API 헬퍼
│       ├── seo_helpers.py             ← sitemap, robots, JSON-LD
│       └── adsense.py                 ← AdSense 광고 단위 관리
│
└── uapress/                           ← ✅ 현재 운영 중 (1순위)
    └── CLAUDE.md                      ← uapress 상세 가이드

# ── 추후 추가 예정 ──────────────────────────────
# qualpass/      Phase 1: 자격증 합격률
# todaymarket/   Phase 1: 농산물 도매가격
# bizgrant/      Phase 2: 소상공인 지원금
# lawsummary/    Phase 2: 판결문 AI 요약
# beachsafe/     Phase 3: 해수욕장 안전
```

---

## 사이트 현황

| 사이트 | 도메인 | 상태 | 우선순위 |
|--------|--------|------|---------|
| uapress | uapress.kr | ✅ 구축 중 | 1순위 — AdSense 기승인 |
| qualpass | qualpass.kr | ⏳ 추후 | Phase 1 |
| todaymarket | todaymarket.kr | ⏳ 추후 | Phase 1 |
| bizgrant | bizgrant.kr | ⏳ 추후 | Phase 2 |
| lawsummary | lawsummary.kr | ⏳ 추후 | Phase 2 |
| beachsafe | beachsafe.kr | ⏳ 추후 | Phase 3 |

---

## GitHub Actions (`.github/workflows/deploy_all.yml`)

```yaml
name: Deploy All Sites

on:
  workflow_dispatch:
    inputs:
      site:
        description: '배포할 사이트 선택 (uapress / qualpass / todaymarket / bizgrant / lawsummary / beachsafe / all)'
        required: true
        default: 'uapress'

  schedule:
    # uapress: 화·금 오전 4시 KST
    - cron: '0 19 * * 1,4'
    # uapress 주간 큐레이션: 일 오전 4시 KST
    - cron: '0 19 * * 0'

    # ── 추후 사이트 추가 시 스케줄 추가 ──
    # qualpass, todaymarket: 매일 오전 5시 KST
    # - cron: '0 20 * * *'
    # bizgrant: 일·수 오전 4시 KST
    # - cron: '0 19 * * 0,3'
    # lawsummary: 화·금 오전 4시 KST (uapress와 동일)
    # - cron: '0 19 * * 1,4'
    # beachsafe 비수기: 매주 일 오전 5시 KST
    # - cron: '0 20 * * 0'

env:
  PYTHON_VERSION: '3.11'

jobs:

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # ✅ uapress.kr — 문화행사 캘린더 (현재 운영)
  # 주기: 화·금 데이터 갱신 / 일 주간 큐레이션
  # 데이터: 한국관광공사 Tour API
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  deploy-uapress:
    runs-on: ubuntu-latest
    if: |
      (github.event_name == 'workflow_dispatch' &&
      (github.event.inputs.site == 'all' || github.event.inputs.site == 'uapress')) ||
      github.event.schedule == '0 19 * * 1,4' ||
      github.event.schedule == '0 19 * * 0'
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

      - name: Install dependencies
        run: pip install -r uapress/requirements.txt

      - name: Fetch Tour API events
        run: python uapress/scripts/fetch_tour.py
        env:
          TOUR_API_KEY: ${{ secrets.TOUR_API_KEY }}

      - name: Process events
        run: python uapress/scripts/process_events.py

      - name: Generate AI content (event summaries)
        run: python uapress/scripts/generate_content.py events
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Generate weekly pick (Sunday only)
        if: github.event.schedule == '0 19 * * 0' || github.event_name == 'workflow_dispatch'
        run: python uapress/scripts/generate_content.py weekly
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}

      - name: Build search index
        run: python uapress/scripts/build_search_index.py

      - name: Build site
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

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # ⏳ qualpass — 자격증 합격률 (Phase 1 추후 추가)
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # deploy-qualpass:
  #   runs-on: ubuntu-latest
  #   if: |
  #     (github.event_name == 'workflow_dispatch' &&
  #     (github.event.inputs.site == 'all' || github.event.inputs.site == 'qualpass')) ||
  #     github.event.schedule == '0 20 * * *'
  #   steps:
  #     - uses: actions/checkout@v4
  #     - uses: actions/setup-python@v5
  #       with:
  #         python-version: ${{ env.PYTHON_VERSION }}
  #     - name: Cache pip
  #       uses: actions/cache@v4
  #       with:
  #         path: ~/.cache/pip
  #         key: pip-qualpass-${{ hashFiles('qualpass/requirements.txt') }}
  #     - run: pip install -r qualpass/requirements.txt
  #     - name: Fetch Q-Net data
  #       run: python qualpass/scripts/fetch_qnet.py
  #       env:
  #         DATA_GOV_API_KEY: ${{ secrets.DATA_GOV_API_KEY }}
  #     - name: Process data
  #       run: python qualpass/scripts/process_data.py
  #     - name: Generate AI content (weekly only)
  #       if: github.event.schedule == '0 20 * * 0' || github.event_name == 'workflow_dispatch'
  #       run: python qualpass/scripts/generate_content.py
  #       env:
  #         ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  #     - name: Build site
  #       run: python qualpass/scripts/build_site.py
  #     - name: Deploy to Cloudflare Pages
  #       run: npx wrangler pages deploy qualpass/dist --project-name=qualpass
  #       env:
  #         CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  #         CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # ⏳ todaymarket — 농산물 도매가격 (Phase 1 추후 추가)
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # deploy-todaymarket:
  #   runs-on: ubuntu-latest
  #   if: |
  #     (github.event_name == 'workflow_dispatch' &&
  #     (github.event.inputs.site == 'all' || github.event.inputs.site == 'todaymarket')) ||
  #     github.event.schedule == '0 20 * * *'
  #   steps:
  #     - uses: actions/checkout@v4
  #     - uses: actions/setup-python@v5
  #       with:
  #         python-version: ${{ env.PYTHON_VERSION }}
  #     - name: Cache pip
  #       uses: actions/cache@v4
  #       with:
  #         path: ~/.cache/pip
  #         key: pip-todaymarket-${{ hashFiles('todaymarket/requirements.txt') }}
  #     - run: pip install -r todaymarket/requirements.txt
  #     - name: Fetch KAMIS prices
  #       run: python todaymarket/scripts/fetch_kamis.py
  #       env:
  #         KAMIS_API_KEY: ${{ secrets.KAMIS_API_KEY }}
  #         KAMIS_CERT_ID: ${{ secrets.KAMIS_CERT_ID }}
  #     - name: Process price data
  #       run: python todaymarket/scripts/process_prices.py
  #     - name: Generate weekly report (Friday only)
  #       if: github.event.schedule == '0 19 * * 4' || github.event_name == 'workflow_dispatch'
  #       run: python todaymarket/scripts/generate_content.py --type weekly_report
  #       env:
  #         ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  #     - name: Build site
  #       run: python todaymarket/scripts/build_site.py
  #     - name: Deploy to Cloudflare Pages
  #       run: npx wrangler pages deploy todaymarket/dist --project-name=todaymarket
  #       env:
  #         CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  #         CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # ⏳ bizgrant — 소상공인 지원금 (Phase 2 추후 추가)
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # deploy-bizgrant:
  #   runs-on: ubuntu-latest
  #   if: |
  #     (github.event_name == 'workflow_dispatch' &&
  #     (github.event.inputs.site == 'all' || github.event.inputs.site == 'bizgrant')) ||
  #     github.event.schedule == '0 19 * * 0,3'
  #   steps:
  #     - uses: actions/checkout@v4
  #     - uses: actions/setup-python@v5
  #       with:
  #         python-version: ${{ env.PYTHON_VERSION }}
  #     - name: Cache pip
  #       uses: actions/cache@v4
  #       with:
  #         path: ~/.cache/pip
  #         key: pip-bizgrant-${{ hashFiles('bizgrant/requirements.txt') }}
  #     - run: pip install -r bizgrant/requirements.txt
  #     - name: Fetch bizinfo data
  #       run: python bizgrant/scripts/fetch_bizinfo.py
  #       env:
  #         BIZINFO_API_KEY: ${{ secrets.BIZINFO_API_KEY }}
  #     - name: Fetch SEMAS data
  #       run: python bizgrant/scripts/fetch_semas.py
  #     - name: Classify with Claude Batch
  #       run: python bizgrant/scripts/classify_grants.py
  #       env:
  #         ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  #     - name: Build search index
  #       run: python bizgrant/scripts/build_search_index.py
  #     - name: Build site
  #       run: python bizgrant/scripts/build_site.py
  #     - name: Deploy to Cloudflare Pages
  #       run: npx wrangler pages deploy bizgrant/dist --project-name=bizgrant
  #       env:
  #         CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  #         CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # ⏳ lawsummary — 판결문 AI 요약 (Phase 2 추후 추가)
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # deploy-lawsummary:
  #   runs-on: ubuntu-latest
  #   if: |
  #     (github.event_name == 'workflow_dispatch' &&
  #     (github.event.inputs.site == 'all' || github.event.inputs.site == 'lawsummary')) ||
  #     github.event.schedule == '0 19 * * 1,4'
  #   steps:
  #     - uses: actions/checkout@v4
  #     - uses: actions/setup-python@v5
  #       with:
  #         python-version: ${{ env.PYTHON_VERSION }}
  #     - name: Cache pip
  #       uses: actions/cache@v4
  #       with:
  #         path: ~/.cache/pip
  #         key: pip-lawsummary-${{ hashFiles('lawsummary/requirements.txt') }}
  #     - run: pip install -r lawsummary/requirements.txt
  #     - name: Fetch new court cases
  #       run: python lawsummary/scripts/fetch_court.py
  #     - name: Summarize with Claude Batch
  #       run: python lawsummary/scripts/summarize_cases.py
  #       env:
  #         ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  #     - name: Build site
  #       run: python lawsummary/scripts/build_site.py
  #     - name: Deploy to Cloudflare Pages
  #       run: npx wrangler pages deploy lawsummary/dist --project-name=lawsummary
  #       env:
  #         CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  #         CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}

  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # ⏳ beachsafe — 해수욕장 안전 (Phase 3 추후 추가)
  # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # deploy-beachsafe:
  #   runs-on: ubuntu-latest
  #   if: |
  #     (github.event_name == 'workflow_dispatch' &&
  #     (github.event.inputs.site == 'all' || github.event.inputs.site == 'beachsafe')) ||
  #     github.event.schedule == '0 20 * * *' ||
  #     github.event.schedule == '0 20 * * 0'
  #   steps:
  #     - uses: actions/checkout@v4
  #     - uses: actions/setup-python@v5
  #       with:
  #         python-version: ${{ env.PYTHON_VERSION }}
  #     - name: Cache pip
  #       uses: actions/cache@v4
  #       with:
  #         path: ~/.cache/pip
  #         key: pip-beachsafe-${{ hashFiles('beachsafe/requirements.txt') }}
  #     - run: pip install -r beachsafe/requirements.txt
  #     - name: Fetch beach & weather data
  #       run: python beachsafe/scripts/fetch_mof.py
  #       env:
  #         MOF_API_KEY: ${{ secrets.MOF_API_KEY }}
  #         KMA_API_KEY: ${{ secrets.KMA_API_KEY }}
  #     - name: Generate AI guides (weekly)
  #       if: github.event.schedule == '0 20 * * 0' || github.event_name == 'workflow_dispatch'
  #       run: python beachsafe/scripts/generate_guides.py
  #       env:
  #         ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
  #     - name: Build site
  #       run: python beachsafe/scripts/build_site.py
  #     - name: Deploy to Cloudflare Pages
  #       run: npx wrangler pages deploy beachsafe/dist --project-name=beachsafe
  #       env:
  #         CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
  #         CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CLOUDFLARE_ACCOUNT_ID }}
```

---

## GitHub Secrets

### 현재 등록 필요 (uapress 운영용)

| Secret | 설명 | 획득처 |
|--------|------|--------|
| `ANTHROPIC_API_KEY` | Claude API | console.anthropic.com |
| `CLOUDFLARE_API_TOKEN` | CF Pages 배포 토큰 | CF 대시보드 → API Tokens |
| `CLOUDFLARE_ACCOUNT_ID` | CF 계정 ID | CF 대시보드 우측 하단 |
| `TOUR_API_KEY` | 한국관광공사 Tour API | data.go.kr 신청 |
| `ADSENSE_PUBLISHER_ID` | AdSense publisher ID (기승인) | AdSense 대시보드 |
| `ADSENSE_UNIT_BANNER` | 반응형 배너 광고 단위 ID | AdSense → 광고 단위 생성 |
| `ADSENSE_UNIT_RECTANGLE` | 사각형 광고 단위 ID | AdSense → 광고 단위 생성 |

### 추후 추가 예정 (사이트 추가 시)

| Secret | 사이트 |
|--------|--------|
| `DATA_GOV_API_KEY` | qualpass |
| `KAMIS_API_KEY` / `KAMIS_CERT_ID` | todaymarket |
| `BIZINFO_API_KEY` | bizgrant |
| `MOF_API_KEY` / `KMA_API_KEY` | beachsafe |

---

## Cloudflare Pages 프로젝트 초기 설정

```bash
# wrangler 설치
npm install -g wrangler

# CF 로그인
wrangler login

# uapress 프로젝트 생성 (1회)
npx wrangler pages project create uapress

# CF 대시보드에서 커스텀 도메인 연결
# Pages → uapress → Custom Domains → uapress.kr 추가

# ── 추후 사이트 추가 시 ──
# npx wrangler pages project create qualpass
# npx wrangler pages project create todaymarket
# npx wrangler pages project create bizgrant
# npx wrangler pages project create lawsummary
# npx wrangler pages project create beachsafe
```

---

## 새 사이트 추가하는 법 (나중에 참고)

Phase 1~3 사이트 추가할 때 3가지만 하면 됨:

```
1. ua-sites/{사이트명}/CLAUDE.md 작성 후 폴더 구조 생성
2. deploy_all.yml에서 해당 job 주석 해제
3. 필요한 GitHub Secrets 추가 등록
```

---

## 로드맵

```
현재: uapress.kr 구축·배포
  → AdSense 즉시 수익화 (기승인)
  → Cloudways WordPress 해지

uapress 안정화 후 (2~4주):
  → qualpass (자격증 합격률) 추가
  → todaymarket (농산물 도매가) 추가

Phase 2 (2개월 후):
  → bizgrant, lawsummary 추가

Phase 3 (3개월 후):
  → beachsafe 추가
```

---

## 긴급 수동 배포

```bash
# GitHub Actions UI에서
# ua-sites 레포 → Actions → Deploy All Sites
# → Run workflow → site: uapress → Run

# 로컬 직접 배포
cd ua-sites/uapress
python scripts/fetch_tour.py
python scripts/process_events.py
python scripts/build_site.py
npx wrangler pages deploy dist --project-name=uapress
```
