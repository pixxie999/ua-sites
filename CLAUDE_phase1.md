# CLAUDE.md — Phase 1 공통 인프라 & 운영 가이드

## Phase 1 개요

**운영 사이트:** 2개 동시 구축·운영
1. `qualpass` — 자격증 합격률 통계 사이트
2. `todaymarket` — 농산물 도매가격 사이트

**공통 원칙:**
- 서버 비용 0원 (Cloudflare Pages 무료 + GitHub Actions Public Repo 무료)
- Claude API는 Batch 모드만 사용 (50% 할인)
- 모든 데이터 수집은 공공API 또는 합법적 스크래핑
- 마스터 개입 없이 95% 자동 운영

---

## 공통 폴더 구조 (모노레포)

```
ua-sites/
├── CLAUDE.md                          # 이 파일 (공통 가이드)
├── qualpass/                          # 사이트 1
│   └── CLAUDE.md                      # 사이트별 상세 가이드
├── todaymarket/                       # 사이트 2
│   └── CLAUDE.md
├── shared/
│   ├── utils/
│   │   ├── claude_batch.py            # Claude Batch API 공통 헬퍼
│   │   ├── seo_helpers.py             # 공통 SEO 유틸 (sitemap, robots)
│   │   ├── adsense.py                 # AdSense 코드 관리
│   │   └── cloudflare_deploy.py      # CF Pages 배포 헬퍼
│   └── templates/
│       ├── _adsense_unit.html         # AdSense 광고 단위 공통
│       └── _coupang_banner.html       # 쿠팡파트너스 공통
└── .env.example                       # 환경변수 예시
```

---

## 공통 Claude Batch API 헬퍼 (`shared/utils/claude_batch.py`)

```python
"""
Claude Haiku 4.5 Batch API 공통 헬퍼
- Phase 1 두 사이트 공통 사용
- 50% 할인 적용 (Batch API)
- 비용: 입력 $0.5/MTok, 출력 $2.5/MTok
"""

import anthropic
import json
import time
from pathlib import Path
from typing import Optional

client = anthropic.Anthropic()

MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1000  # 콘텐츠 생성 기본값


def submit_batch(requests: list, batch_name: str) -> str:
    """
    Batch 요청 제출
    
    Args:
        requests: [{"custom_id": str, "params": {...}} ...]
        batch_name: 로깅용 이름
    
    Returns:
        batch_id: str
    """
    print(f"[{batch_name}] Batch 제출: {len(requests)}개 요청")
    
    batch = client.beta.messages.batches.create(requests=requests)
    batch_id = batch.id
    
    print(f"[{batch_name}] Batch ID: {batch_id}")
    print(f"[{batch_name}] 예상 비용: ${estimate_cost(requests):.4f}")
    
    # batch_id 저장 (재시작 대비)
    Path(f"data/.batch_ids/{batch_name}.txt").write_text(batch_id)
    
    return batch_id


def poll_batch(batch_id: str, max_wait_hours: int = 24) -> dict:
    """
    Batch 완료 대기 및 결과 수집
    
    Returns:
        {custom_id: content_dict}
    """
    print(f"Batch {batch_id} 폴링 시작...")
    
    for attempt in range(max_wait_hours * 6):  # 10분 간격
        batch = client.beta.messages.batches.retrieve(batch_id)
        
        if batch.processing_status == "ended":
            break
        
        print(f"상태: {batch.processing_status} "
              f"(완료: {batch.request_counts.succeeded}, "
              f"대기: {batch.request_counts.processing})")
        time.sleep(600)  # 10분 대기
    
    # 결과 수집
    results = {}
    for result in client.beta.messages.batches.results(batch_id):
        if result.result.type == "succeeded":
            content = result.result.message.content[0].text
            try:
                results[result.custom_id] = json.loads(content)
            except json.JSONDecodeError:
                # JSON 파싱 실패 시 raw 텍스트 저장
                results[result.custom_id] = {"raw": content}
    
    print(f"완료: {len(results)}개 수집")
    return results


def estimate_cost(requests: list) -> float:
    """
    Batch 예상 비용 계산 (USD)
    Haiku 4.5 Batch: 입력 $0.5/MTok, 출력 $2.5/MTok
    """
    total_input = 0
    total_output = 0
    
    for req in requests:
        # 프롬프트 토큰 추정 (문자당 약 0.3토큰)
        prompt_len = len(str(req["params"].get("messages", "")))
        system_len = len(str(req["params"].get("system", "")))
        
        total_input += (prompt_len + system_len) * 0.3
        total_output += req["params"].get("max_tokens", 1000) * 0.5  # 평균 50% 사용
    
    input_cost = (total_input / 1_000_000) * 0.5
    output_cost = (total_output / 1_000_000) * 2.5
    
    return input_cost + output_cost


def run_batch_pipeline(
    requests: list,
    output_path: str,
    batch_name: str,
    force_refresh: bool = False
) -> dict:
    """
    전체 Batch 파이프라인 실행
    - 기존 결과 있으면 재사용 (비용 절감)
    - 없으면 새로 실행
    """
    output_file = Path(output_path)
    
    # 기존 결과 재사용
    if output_file.exists() and not force_refresh:
        print(f"기존 결과 로드: {output_path}")
        return json.loads(output_file.read_text())
    
    # 새 Batch 실행
    batch_id = submit_batch(requests, batch_name)
    results = poll_batch(batch_id)
    
    # 결과 저장
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    
    return results
```

---

## 공통 SEO 헬퍼 (`shared/utils/seo_helpers.py`)

```python
"""공통 SEO 유틸리티"""

from datetime import datetime
from pathlib import Path
import xml.etree.ElementTree as ET


def generate_sitemap(urls: list, domain: str, output_path: str):
    """
    sitemap.xml 생성
    
    Args:
        urls: [{"loc": "/q/electric-engineer/", "priority": 0.9, "changefreq": "daily"}]
        domain: "https://qualpass.kr"
    """
    root = ET.Element("urlset")
    root.set("xmlns", "http://www.sitemaps.org/schemas/sitemap/0.9")
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    for url_data in urls:
        url_elem = ET.SubElement(root, "url")
        ET.SubElement(url_elem, "loc").text = domain + url_data["loc"]
        ET.SubElement(url_elem, "lastmod").text = today
        ET.SubElement(url_elem, "changefreq").text = url_data.get("changefreq", "weekly")
        ET.SubElement(url_elem, "priority").text = str(url_data.get("priority", 0.5))
    
    tree = ET.ElementTree(root)
    Path(output_path).write_bytes(
        b'<?xml version="1.0" encoding="UTF-8"?>\n' + 
        ET.tostring(root, encoding="unicode").encode()
    )
    print(f"Sitemap 생성: {len(urls)}개 URL")


def generate_robots_txt(domain: str, sitemap_path: str) -> str:
    """robots.txt 생성"""
    return f"""User-agent: *
Allow: /

# 관리자 페이지 차단
Disallow: /admin/
Disallow: /api/
Disallow: /.github/

Sitemap: {domain}{sitemap_path}
"""


def make_slug(korean_text: str) -> str:
    """한국어 → URL 슬러그 변환"""
    # 기본 매핑 테이블 (필요시 확장)
    SLUG_MAP = {
        "전기기사": "electric-engineer",
        "정보처리기사": "information-processing-engineer",
        "배추": "cabbage",
        "양파": "onion",
        # ... 확장
    }
    return SLUG_MAP.get(korean_text, korean_text.replace(" ", "-").lower())


def build_json_ld_article(title: str, description: str, url: str, 
                            publish_date: str, modified_date: str) -> dict:
    """Article 구조화 데이터"""
    return {
        "@context": "https://schema.org",
        "@type": "Article",
        "headline": title,
        "description": description,
        "url": url,
        "datePublished": publish_date,
        "dateModified": modified_date,
        "publisher": {
            "@type": "Organization",
            "name": "오늘장보기"
        }
    }


def build_json_ld_faq(faqs: list) -> dict:
    """FAQPage 구조화 데이터 (구글 리치 스니펫)"""
    return {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": faq["q"],
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": faq["a"]
                }
            }
            for faq in faqs
        ]
    }
```

---

## 공통 AdSense 관리 (`shared/utils/adsense.py`)

```python
"""
AdSense 광고 단위 관리
승인 전: 코드 비활성화 (빈 div만 남김)
승인 후: ADSENSE_PUBLISHER_ID 환경변수 설정하면 자동 활성화
"""

import os

PUBLISHER_ID = os.getenv("ADSENSE_PUBLISHER_ID", "")  # ca-pub-XXXXXX

# 광고 단위 ID (AdSense 대시보드에서 생성 후 환경변수로 관리)
AD_UNITS = {
    "banner_top": os.getenv("ADSENSE_UNIT_BANNER_TOP", ""),
    "rectangle_mid": os.getenv("ADSENSE_UNIT_RECTANGLE", ""),
    "banner_bottom": os.getenv("ADSENSE_UNIT_BANNER_BOTTOM", ""),
    "infeed": os.getenv("ADSENSE_UNIT_INFEED", ""),
}


def render_ad(unit_type: str, css_class: str = "") -> str:
    """
    광고 HTML 렌더링
    PUBLISHER_ID 미설정 시 플레이스홀더 반환
    """
    if not PUBLISHER_ID:
        return f'<div class="ad-placeholder {css_class}" style="min-height:90px;background:#f5f5f5;display:flex;align-items:center;justify-content:center;"><span style="color:#999">광고 영역</span></div>'
    
    unit_id = AD_UNITS.get(unit_type, "")
    if not unit_id:
        return ""
    
    return f"""
<ins class="adsbygoogle {css_class}"
     style="display:block"
     data-ad-client="{PUBLISHER_ID}"
     data-ad-slot="{unit_id}"
     data-ad-format="auto"
     data-full-width-responsive="true"></ins>
<script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
"""
```

---

## 환경변수 통합 (`.env.example`)

```bash
# === Claude API ===
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxx

# === 공공데이터 ===
DATA_GOV_API_KEY=                    # data.go.kr API 키
KAMIS_API_KEY=                       # KAMIS 인증키
KAMIS_CERT_ID=                       # KAMIS 인증ID

# === Cloudflare ===
CLOUDFLARE_API_TOKEN=                # Pages 배포용 토큰
CLOUDFLARE_ACCOUNT_ID=               # 계정 ID (CF 대시보드 우측)

# === AdSense (승인 후 설정) ===
ADSENSE_PUBLISHER_ID=ca-pub-XXXXXXXXXX
ADSENSE_UNIT_BANNER_TOP=XXXXXXXXXX
ADSENSE_UNIT_RECTANGLE=XXXXXXXXXX
ADSENSE_UNIT_BANNER_BOTTOM=XXXXXXXXXX

# === 쿠팡파트너스 ===
COUPANG_AFFILIATE_ID=                # 파트너스 ID

# === 사이트 설정 ===
QUALPASS_DOMAIN=https://qualpass.kr
TODAYMARKET_DOMAIN=https://todaymarket.kr
```

---

## 클로드 코드 전체 실행 순서 (Phase 1 처음 구축)

```bash
# ===== 환경 준비 =====

# 1. Python 가상환경
python3.11 -m venv .venv
source .venv/bin/activate

# 2. 공통 의존성 설치
pip install anthropic requests beautifulsoup4 lxml pandas jinja2 python-dotenv

# 3. Node.js (Wrangler용, todaymarket만)
npm install -g wrangler

# ===== 사이트 1: qualpass =====

cd qualpass

# 4. 공공데이터 API 키 확인 (data.go.kr에서 미리 신청 필요)
echo "DATA_GOV_API_KEY 설정 확인"

# 5. Q-Net 데이터 첫 수집 (시간 소요: 약 10분)
python scripts/fetch_qnet.py

# 6. 데이터 처리
python scripts/process_data.py

# 7. AI 콘텐츠 1차 생성 (Batch - 약 1시간 대기)
python scripts/generate_content.py --limit 50 --type item_pages

# 8. 첫 빌드 (약 500개 HTML 생성)
python scripts/build_site.py

# 9. 로컬 확인
python -m http.server 8000 --directory dist &

# 10. GitHub + Cloudflare Pages 연결
git init && git remote add origin https://github.com/YOUR_USERNAME/qualpass
git add . && git commit -m "feat: initial build with 500 qualification pages"
git push -u origin main
# → CF Pages 대시보드에서 프로젝트 생성, dist 폴더 지정

# ===== 사이트 2: todaymarket =====

cd ../todaymarket

# 11. Cloudflare KV 생성
wrangler kv:namespace create "PRICE_DATA"
# → 출력된 id를 wrangler.toml에 기입

# 12. KAMIS 데이터 첫 수집
python scripts/fetch_kamis.py

# 13. Worker 배포
wrangler deploy

# 14. 첫 빌드
python scripts/build_site.py

# 15. GitHub + CF Pages 배포
git init && git remote add origin https://github.com/YOUR_USERNAME/todaymarket
git add . && git commit -m "feat: initial build with 500 item price pages"
git push -u origin main

# ===== GitHub Secrets 등록 =====
# (GitHub 레포 → Settings → Secrets → Actions)
# ANTHROPIC_API_KEY
# DATA_GOV_API_KEY
# KAMIS_API_KEY / KAMIS_CERT_ID
# CLOUDFLARE_API_TOKEN
# CLOUDFLARE_ACCOUNT_ID

echo "Phase 1 구축 완료!"
echo "다음 단계: Google Search Console 등록 + AdSense 신청"
```

---

## Phase 1 완료 체크리스트

### 구축 완료 확인
- [ ] qualpass: 최소 500개 HTML 페이지 생성
- [ ] qualpass: 로컬에서 모든 내부 링크 정상 작동
- [ ] todaymarket: 가격 데이터 정상 로딩 (500개 품목)
- [ ] todaymarket: Cloudflare Worker 배포 완료
- [ ] 두 사이트 모두 GitHub Actions 워크플로우 활성화

### SEO 초기 설정
- [ ] Google Search Console 두 사이트 등록
- [ ] sitemap.xml 각 사이트 제출
- [ ] robots.txt 배포 확인
- [ ] 구조화 데이터 (JSON-LD) 검증 (Google Rich Results Test)

### 수익화 준비
- [ ] AdSense 계정 신청 (사이트당 별도)
- [ ] 쿠팡파트너스 가입 + 링크 생성
- [ ] 에듀윌/해커스 제휴 문의 (qualpass)

### 모니터링
- [ ] Google Analytics 4 두 사이트 설치
- [ ] GitHub Actions 워크플로우 첫 자동 실행 확인
- [ ] Cloudflare Pages 빌드 로그 확인

---

## Phase 2로 넘어가는 조건

Phase 2 (소상공인 지원금 + 판결문 AI 요약) 시작 기준:

| 조건 | 기준값 |
|------|--------|
| Phase 1 두 사이트 정상 운영 | ✅ GitHub Actions 자동 빌드 3회 이상 |
| SEO 인덱싱 | qualpass 100페이지+, todaymarket 200페이지+ |
| 수익 신호 | AdSense 승인 OR CPA 첫 전환 |
| 구축 후 경과 | 최소 14일 (SEO 안정화 대기) |

---

## 예상 비용 재확인 (Phase 1만)

| 항목 | 금액 |
|------|------|
| Claude Code 구축 (Sonnet 4.6 기준) | 36,000원 |
| 도메인 2개 연간 | 32,600원 |
| Claude API 월 운영 (Haiku Batch) | 1,243원/월 |
| 서버·CDN·CI/CD | 0원 |
| **첫 달 총비용** | **약 70,843원** |
| **이후 월 운영비** | **약 4,000원** |
