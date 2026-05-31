"""
Tour API + 문화부 API 데이터 병합 후 저장
process_events.py 실행 이후 호출
"""

import json
import glob
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
from process_events import merge_culture

if __name__ == "__main__":
    culture_files = sorted(
        glob.glob(str(PROJECT_ROOT / "data/raw/culture_*.json")), reverse=True
    )

    if not culture_files:
        print("문화부 raw 데이터 없음 — 스킵")
        sys.exit(0)

    events_path = PROJECT_ROOT / "data/processed/events.json"
    if not events_path.exists():
        print("events.json 없음 — process_events.py 먼저 실행하세요.")
        sys.exit(1)

    events = json.loads(events_path.read_text())
    before = len(events)

    events = merge_culture(events, culture_files[0])

    # 분류 재계산
    by_region = {}
    by_month = {}
    for e in events:
        by_region.setdefault(e["region"], []).append(e)
        by_month.setdefault(e["start_date"][:6], []).append(e)
    free = [e for e in events if e["is_free"]]

    out = PROJECT_ROOT / "data/processed"
    (out / "events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2))
    (out / "events_by_region.json").write_text(
        json.dumps(by_region, ensure_ascii=False, indent=2))
    (out / "events_by_month.json").write_text(
        json.dumps(by_month, ensure_ascii=False, indent=2))
    (out / "free_events.json").write_text(
        json.dumps(free, ensure_ascii=False, indent=2))

    print(f"병합 완료: {before}개 → {len(events)}개 (무료: {len(free)}개)")
