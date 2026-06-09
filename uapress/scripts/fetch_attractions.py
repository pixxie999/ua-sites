"""
한국관광공사 Tour API — 17개 지역 관광지 수집
build_site.py에서 인근 관광지 섹션에 사용
- attractions.json이 없거나 7일 이상 지났을 때만 재수집
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

OUT_PATH = PROJECT_ROOT / "data" / "raw" / "attractions.json"
REFRESH_DAYS = 7  # 7일마다 재수집


def should_refresh() -> bool:
    if not OUT_PATH.exists():
        return True
    age = datetime.now() - datetime.fromtimestamp(OUT_PATH.stat().st_mtime)
    return age > timedelta(days=REFRESH_DAYS)


if __name__ == "__main__":
    if should_refresh():
        print("관광지 데이터 수집 시작...")
        from fetch_tour import fetch_all_attractions
        fetch_all_attractions()
    else:
        age_hours = (datetime.now() - datetime.fromtimestamp(OUT_PATH.stat().st_mtime)).seconds // 3600
        print(f"관광지 데이터 최신 상태 — 스킵 (최근 업데이트: {age_hours}시간 전)")
