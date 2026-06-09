"""
한국관광공사 Tour API — 17개 지역 관광지 수집
build_site.py에서 인근 관광지 섹션에 사용
"""

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from fetch_tour import fetch_all_attractions

if __name__ == "__main__":
    fetch_all_attractions()
