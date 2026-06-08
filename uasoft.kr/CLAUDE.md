# CLAUDE.md - 카페24 인스타그램 피드 앱 (uasoft.kr)

## 프로젝트 개요

카페24 앱스토어에 등록하는 인스타그램 최신 게시물 위젯 서비스.
Apify로 스크랩 → GitHub Actions로 WebP 변환 → Cloudflare R2 저장 → 카페24 쇼핑몰에 위젯 노출.

---

## 기술 스택

| 레이어 | 기술 | 용도 |
|--------|------|------|
| API 서버 | Python FastAPI (Railway) | 위젯 API, 관리자 API, 인증 |
| 스케줄러 | GitHub Actions (Cron) | Apify 배치 실행, 이미지 처리 |
| 이미지 처리 | Node.js sharp | WebP 변환 (600px, quality 80) |
| 스토리지 | Cloudflare R2 | WebP 이미지 영구 보존 |
| CDN | cdn.uasoft.kr (R2 커스텀 도메인) | 이미지 서빙 |
| DB | PostgreSQL (Railway 내장) | 쇼핑몰 정보, 피드 메타데이터 |
| 스크랩 | Apify Instagram Scraper | 인스타그램 피드 수집 |
| DNS/프록시 | Cloudflare | 전체 도메인 관리 |

---

## 도메인 구성

```
uasoft.kr         → Cloudflare Pages (서비스 소개 랜딩)
api.uasoft.kr     → Railway FastAPI 서버
cdn.uasoft.kr     → Cloudflare R2 (WebP 이미지 CDN)
admin.uasoft.kr   → 관리자 대시보드
```

---

## 디렉토리 구조

```
/
├── CLAUDE.md                    # 이 파일
├── api/                         # FastAPI 서버
│   ├── main.py                  # 앱 엔트리포인트
│   ├── routers/
│   │   ├── widget.py            # GET /feed/{shop_id} - 위젯용
│   │   ├── admin.py             # 관리자 설정 API
│   │   └── auth.py              # 카페24 OAuth 처리
│   ├── models/
│   │   ├── shop.py              # 쇼핑몰 모델
│   │   ├── feed.py              # 피드/게시물 모델
│   │   └── account.py          # 인스타 계정 모델
│   ├── services/
│   │   ├── apify.py             # Apify API 클라이언트
│   │   ├── feed.py              # 피드 조회/저장 로직
│   │   └── plan.py              # 플랜별 제한 로직
│   ├── db.py                    # DB 연결 (SQLAlchemy)
│   └── config.py                # 환경변수 관리
├── batch/                       # GitHub Actions 배치
│   ├── run_batch.js             # 메인 배치 스크립트
│   ├── apify_client.js          # Apify 호출
│   ├── image_converter.js       # sharp WebP 변환
│   └── r2_uploader.js           # R2 업로드
├── .github/
│   └── workflows/
│       ├── batch_basic.yml      # 매일 자정 - 베이직 전체
│       └── batch_premium.yml    # 6시간마다 - 프리미엄만
├── widget/                      # 카페24에 삽입되는 JS
│   ├── widget.js                # 위젯 렌더링 스크립트
│   └── widget.css               # 위젯 스타일
├── landing/                     # Cloudflare Pages 랜딩
│   └── index.html
└── sql/
    └── schema.sql               # DB 스키마
```

---

## DB 스키마

```sql
-- 가입 쇼핑몰
CREATE TABLE shops (
    id            SERIAL PRIMARY KEY,
    shop_id       VARCHAR(100) UNIQUE NOT NULL,  -- 카페24 쇼핑몰 ID
    plan          VARCHAR(20) DEFAULT 'free',     -- free | basic | premium
    created_at    TIMESTAMP DEFAULT NOW(),
    updated_at    TIMESTAMP DEFAULT NOW()
);

-- 연결된 인스타그램 계정
CREATE TABLE accounts (
    id            SERIAL PRIMARY KEY,
    shop_id       VARCHAR(100) REFERENCES shops(shop_id),
    instagram_handle VARCHAR(100) NOT NULL,       -- @없는 계정명
    is_active     BOOLEAN DEFAULT true,
    created_at    TIMESTAMP DEFAULT NOW()
);

-- 스크랩된 게시물 캐시
CREATE TABLE feeds (
    id            SERIAL PRIMARY KEY,
    instagram_handle VARCHAR(100) NOT NULL,
    post_id       VARCHAR(200) UNIQUE NOT NULL,   -- 인스타 게시물 ID
    image_url     TEXT,                           -- R2 WebP URL
    caption       TEXT,
    permalink     TEXT,                           -- 원본 인스타 링크
    posted_at     TIMESTAMP,
    fetched_at    TIMESTAMP DEFAULT NOW()
);

-- 위젯 설정
CREATE TABLE widget_settings (
    shop_id       VARCHAR(100) PRIMARY KEY REFERENCES shops(shop_id),
    layout        VARCHAR(20) DEFAULT 'grid',     -- grid | slider | gallery
    columns       INT DEFAULT 3,
    show_caption  BOOLEAN DEFAULT false,
    watermark     BOOLEAN DEFAULT true
);
```

---

## 플랜 정책

| 플랜 | 가격 | 갱신 주기 | 노출 수 | 워터마크 | 다중 계정 |
|------|------|-----------|---------|---------|---------|
| free | 0원 | 주 1회 | 4개 | 강제 | ❌ |
| basic | 9,900원/월 | 매일 1회 (자정) | 12개 | 제거 가능 | ❌ |
| premium | 29,900원/월 | 6시간마다 | 무제한 | 제거 가능 | ✅ 최대 3개 |

### 플랜별 API 제한 로직 (api/services/plan.py)

```python
PLAN_CONFIG = {
    "free":    {"max_posts": 4,  "watermark": True,  "multi_account": False},
    "basic":   {"max_posts": 12, "watermark": False, "multi_account": False},
    "premium": {"max_posts": 999,"watermark": False, "multi_account": True},
}

def get_feed_limit(plan: str) -> int:
    return PLAN_CONFIG[plan]["max_posts"]
```

---

## GitHub Actions 배치 워크플로우

### batch_basic.yml (매일 자정)

```yaml
name: Batch Basic & Free
on:
  schedule:
    - cron: '0 15 * * *'   # UTC 15:00 = KST 00:00
  workflow_dispatch:

jobs:
  batch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci --prefix batch
      - run: node batch/run_batch.js --plan=basic,free
        env:
          APIFY_TOKEN: ${{ secrets.APIFY_TOKEN }}
          R2_ACCESS_KEY: ${{ secrets.R2_ACCESS_KEY }}
          R2_SECRET_KEY: ${{ secrets.R2_SECRET_KEY }}
          R2_BUCKET: ${{ secrets.R2_BUCKET }}
          R2_ENDPOINT: ${{ secrets.R2_ENDPOINT }}
          API_SECRET: ${{ secrets.API_SECRET }}
          API_BASE_URL: https://api.uasoft.kr
```

### batch_premium.yml (6시간마다)

```yaml
name: Batch Premium
on:
  schedule:
    - cron: '0 0,6,12,18 * * *'   # UTC 기준 (KST 9,15,21,3시)
  workflow_dispatch:

jobs:
  batch:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: '20'
      - run: npm ci --prefix batch
      - run: node batch/run_batch.js --plan=premium
        env:
          APIFY_TOKEN: ${{ secrets.APIFY_TOKEN }}
          R2_ACCESS_KEY: ${{ secrets.R2_ACCESS_KEY }}
          R2_SECRET_KEY: ${{ secrets.R2_SECRET_KEY }}
          R2_BUCKET: ${{ secrets.R2_BUCKET }}
          R2_ENDPOINT: ${{ secrets.R2_ENDPOINT }}
          API_SECRET: ${{ secrets.API_SECRET }}
          API_BASE_URL: https://api.uasoft.kr
```

---

## 이미지 처리 규칙

```javascript
// batch/image_converter.js
// WebP 변환 표준 사양 - 절대 변경하지 말 것
const CONVERT_OPTIONS = {
  width: 600,
  height: 600,
  fit: 'cover',
  quality: 80,
  effort: 4,
};

// R2 저장 경로 규칙
// r2://[bucket]/feeds/[instagram_handle]/[post_id].webp
// CDN URL: https://cdn.uasoft.kr/feeds/[instagram_handle]/[post_id].webp
```

---

## API 엔드포인트 명세

### 위젯용 (공개)

```
GET /feed/{shop_id}
  - 플랜에 따라 게시물 수 제한 적용
  - 워터마크 여부 응답에 포함
  - Response: { posts: [...], watermark: bool, layout: string }

GET /health
  - 서버 상태 확인
```

### 관리자용 (API Key 인증)

```
POST /admin/shop                    # 쇼핑몰 등록
PUT  /admin/shop/{shop_id}/plan     # 플랜 변경
POST /admin/shop/{shop_id}/account  # 인스타 계정 연결
DELETE /admin/shop/{shop_id}/account/{handle}

GET  /admin/stats                   # 전체 현황 조회
```

### 배치용 (Internal Secret)

```
GET  /batch/targets?plan=basic      # 배치 대상 계정 목록
POST /batch/feeds                   # 스크랩 결과 저장
  - Header: X-Batch-Secret: [API_SECRET]
  - Body: { handle, posts: [...] }
```

---

## 환경변수 목록

### Railway (api/ 서버)

```env
DATABASE_URL=postgresql://...
APIFY_TOKEN=apify_api_...
API_SECRET=...                    # 배치 통신용 내부 시크릿
CAFE24_CLIENT_ID=...
CAFE24_CLIENT_SECRET=...
ALLOWED_ORIGINS=https://uasoft.kr,https://api.uasoft.kr
```

### GitHub Actions Secrets

```
APIFY_TOKEN
R2_ACCESS_KEY
R2_SECRET_KEY
R2_BUCKET
R2_ENDPOINT                       # https://[account_id].r2.cloudflarestorage.com
API_SECRET
API_BASE_URL                      # https://api.uasoft.kr
```

---

## 카페24 위젯 삽입 방식

카페24 앱 설치 시 쇼핑몰 HTML에 아래 스크립트 자동 삽입:

```html
<!-- uasoft 인스타그램 피드 위젯 -->
<div id="uasoft-instagram-feed"></div>
<script>
  window.UASOFT_SHOP_ID = "{{shop_id}}";
</script>
<script src="https://cdn.uasoft.kr/widget/widget.js" async></script>
```

### 워터마크 HTML (무료 플랜)

```html
<div class="uasoft-watermark">
  <a href="https://uasoft.kr?ref={{shop_id}}" 
     target="_blank" 
     rel="dofollow">
    📸 Instagram Feed by uasoft
  </a>
</div>
```

---

## 개발 우선순위 (구현 순서)

```
Phase 1 - 핵심 백엔드 (1주차)
  [ ] sql/schema.sql 작성 및 Railway PostgreSQL 적용
  [ ] api/db.py - SQLAlchemy 연결
  [ ] api/routers/widget.py - GET /feed/{shop_id}
  [ ] api/services/plan.py - 플랜 제한 로직
  [ ] api/routers/batch_receiver.py - POST /batch/feeds

Phase 2 - 배치 파이프라인 (2주차)
  [ ] batch/apify_client.js - Apify Actor 호출
  [ ] batch/image_converter.js - sharp WebP 변환
  [ ] batch/r2_uploader.js - R2 업로드
  [ ] batch/run_batch.js - 메인 오케스트레이터
  [ ] .github/workflows/batch_basic.yml
  [ ] .github/workflows/batch_premium.yml

Phase 3 - 위젯 & 관리자 (3주차)
  [ ] widget/widget.js - 렌더링 스크립트
  [ ] widget/widget.css - 그리드/슬라이더/갤러리 스타일
  [ ] api/routers/admin.py - 관리자 API
  [ ] landing/index.html - 서비스 소개 페이지

Phase 4 - 카페24 연동 & 심사 (4주차)
  [ ] api/routers/auth.py - 카페24 OAuth 2.0
  [ ] 앱스토어 등록 서류 준비
  [ ] 개인정보처리방침, 환불정책 페이지
  [ ] 심사 제출
```

---

## 코딩 에이전트 실행 규칙

1. **Phase 순서 준수** - Phase 1 완료 확인 후 Phase 2 진행
2. **환경변수 하드코딩 금지** - 반드시 config.py 또는 .env 참조
3. **DB 스키마 변경 시** - sql/schema.sql 먼저 수정 후 모델 반영
4. **R2 경로 규칙 준수** - `feeds/{handle}/{post_id}.webp` 고정
5. **플랜 로직 중앙화** - plan.py 외부에서 직접 플랜 판단 금지
6. **배치 스크립트** - Node.js 20 + ESM 방식으로 작성
7. **API 서버** - Python 3.11 + FastAPI + Pydantic v2

---

## 레포지토리 정책
- 메인 레포: Private (비즈니스 로직 보호)
- widget 렌더링 코드만 별도 Public 레포 분리 가능
- Secrets는 GitHub Actions Secrets에만 저장, 코드 내 하드코딩 절대 금지

---

## 참고 링크

- Apify Instagram Scraper: https://apify.com/apify/instagram-scraper
- Cloudflare R2 SDK: https://developers.cloudflare.com/r2/api/s3/sdk/
- 카페24 앱스토어 개발 가이드: https://developers.cafe24.com
- Railway 배포: https://railway.app
- sharp 문서: https://sharp.pixelplumbing.com


## 플랫폼 정책
- uasoft.kr은 멀티 서비스 SaaS 플랫폼
- 신규 서비스는 uasoft.kr/[서비스명] 경로로 추가
- API는 api.uasoft.kr/[서비스명]/... 경로로 네임스페이스 분리
- DB 테이블은 [서비스명]_ 접두사로 구분
- 공통 리소스: 인증, 결제, 개인정보처리방침, 푸터

## 현재 서비스
- instafeeds: 인스타그램 피드 위젯 (개발 중)

## 서비스 추가 체크리스트
  [ ] landing/[서비스명]/index.html 생성
  [ ] api/routers/[서비스명]/ 디렉토리 생성
  [ ] DB 테이블 [서비스명]_ 접두사로 추가
  [ ] main.py에 라우터 등록

  