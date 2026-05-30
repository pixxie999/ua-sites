"""Fuse.js 검색 인덱스 생성"""

import json
from pathlib import Path
from datetime import datetime


def build_index():
    events = json.loads(Path("data/processed/events.json").read_text())
    today = datetime.now().strftime("%Y%m%d")

    index = []
    for e in events:
        if e["end_date"] < today:
            continue
        index.append({
            "id": e["id"],
            "title": e["title"],
            "region": e["region"],
            "category": e["category"],
            "is_free": e["is_free"],
            "start_date": e["start_date"],
            "end_date": e["end_date"],
            "start_date_fmt": e.get("start_date_fmt", ""),
            "place": e.get("place", ""),
            "tags": e.get("tags", []),
            "url": f"/event/{e['id']}/"
        })

    out = {
        "updated_at": datetime.now().isoformat(),
        "total": len(index),
        "events": index
    }

    Path("dist").mkdir(exist_ok=True)
    Path("dist/search-index.json").write_text(
        json.dumps(out, ensure_ascii=False, separators=(",", ":")))

    print(f"검색 인덱스 생성: {len(index)}개")


if __name__ == "__main__":
    build_index()
