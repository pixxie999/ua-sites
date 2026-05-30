"""
Claude Haiku 4.5 Batch API — 행사 요약 + 주간 큐레이션
비용: $0.5/$2.5 per MTok (Batch 50% 할인)
행사 1건 평균: 입력 ~600토큰 + 출력 ~400토큰
1,000건 처리 비용: 약 $1.3
"""

import anthropic
import json
import time
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()
MODEL = "claude-haiku-4-5-20251001"


def _get_client():
    return anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


EVENT_SYSTEM = """문화행사 큐레이션 전문가입니다. 주어진 행사 정보로 SEO 최적화 콘텐츠를 작성하세요.
반드시 JSON만 출력 (마크다운 코드블록 없이):
{
  "seo_title": "SEO 제목 60자 이내 (지역명+행사명+특징 키워드 포함)",
  "meta_description": "메타 설명 155자 이내 (언제·어디서·무엇을·왜 가야 하는지)",
  "summary": "행사 핵심 요약 3줄 (각 줄 60자 이내, \\n 구분)",
  "highlight": "이 행사만의 특별한 포인트 100자",
  "target_audience": "가족여행|커플|친구모임|혼자|어린이동반",
  "target_reason": "추천 대상 이유 60자",
  "tips": ["방문 팁 1", "방문 팁 2", "방문 팁 3"],
  "tags": ["태그1", "태그2", "태그3", "태그4", "태그5"]
}"""

WEEKLY_SYSTEM = """주말 나들이 전문 에디터입니다. 이번 주 추천 행사 TOP 5를 선정하세요.
JSON만 출력:
{
  "title": "이번 주 가볼 만한 행사 TOP 5 (날짜 포함)",
  "intro": "이번 주 행사 트렌드 요약 200자",
  "picks": [
    {
      "rank": 1,
      "event_id": "행사 id",
      "title": "행사명",
      "reason": "추천 이유 100자",
      "must_see": "꼭 봐야 할 포인트 80자",
      "tip": "실용 방문 팁 80자"
    }
  ],
  "hidden_gem": "덜 알려진 추천 행사 소개 200자",
  "next_week_preview": "다음 주 주목 행사 100자"
}"""


def build_event_requests(events: list) -> list:
    reqs = []
    for e in events:
        if e.get("seo_title"):
            continue

        msg = f"""행사명: {e['title']}
지역: {e['region']} {e.get('address', '')}
장소: {e.get('place', '')}
기간: {e['start_date_fmt']} ~ {e['end_date_fmt']}
관람료: {e.get('fee', '미확인')}
주최: {e.get('organizer', '')}
설명: {e.get('overview', '')[:400]}"""

        reqs.append({
            "custom_id": f"event-{e['id']}",
            "params": {
                "model": MODEL,
                "max_tokens": 500,
                "system": EVENT_SYSTEM,
                "messages": [{"role": "user", "content": msg}]
            }
        })
    return reqs


def run_event_batch(events: list) -> dict:
    client = _get_client()
    reqs = build_event_requests(events)
    if not reqs:
        print("모든 행사 AI 콘텐츠 이미 존재")
        return {}

    print(f"Batch 제출: {len(reqs)}개")
    batch = client.beta.messages.batches.create(requests=reqs)
    batch_id = batch.id
    print(f"Batch ID: {batch_id}")

    while True:
        b = client.beta.messages.batches.retrieve(batch_id)
        if b.processing_status == "ended":
            break
        print(f"  처리 중... (완료: {b.request_counts.succeeded})")
        time.sleep(300)

    results = {}
    for r in client.beta.messages.batches.results(batch_id):
        if r.result.type == "succeeded":
            try:
                text = r.result.message.content[0].text.strip()
                # 코드블록 제거 (```json ... ```)
                if text.startswith("```"):
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                results[r.custom_id] = json.loads(text)
            except Exception as ex:
                print(f"  파싱 실패 {r.custom_id}: {ex}")

    print(f"Batch 완료: {len(results)}개 성공")
    return results


def generate_weekly_pick(events: list) -> dict:
    client = _get_client()
    today = datetime.now()
    week_end = today + timedelta(days=7)

    this_week = [
        e for e in events
        if (e["start_date"] <= week_end.strftime("%Y%m%d")
            and e["end_date"] >= today.strftime("%Y%m%d"))
    ]

    candidates = sorted(this_week, key=lambda x: x["is_free"], reverse=True)[:30]

    prompt = f"이번 주 ({today.strftime('%Y-%m-%d')} ~ {week_end.strftime('%Y-%m-%d')}) 행사 후보:\n"
    for i, e in enumerate(candidates, 1):
        free_tag = "[무료] " if e["is_free"] else ""
        prompt += f"{i}. {free_tag}[{e['region']}] {e['title']} (id: {e['id']}, {e['start_date_fmt']}~{e['end_date_fmt']})\n"

    resp = client.messages.create(
        model=MODEL,
        max_tokens=700,
        system=WEEKLY_SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )

    text = resp.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    result = json.loads(text)

    week_str = today.strftime("%Y-W%V")
    out_dir = Path("data/content/weekly_picks")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{week_str}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2))

    print(f"주간 큐레이션 생성: {week_str}")
    return result


if __name__ == "__main__":
    import sys

    events_path = Path("data/processed/events.json")
    if not events_path.exists():
        print("process_events.py 먼저 실행하세요.")
        sys.exit(1)

    events = json.loads(events_path.read_text())
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    if mode in ("all", "events"):
        results = run_event_batch(events)

        id_map = {e["id"]: e for e in events}
        for custom_id, ai_data in results.items():
            event_id = custom_id.replace("event-", "", 1)
            if event_id in id_map:
                id_map[event_id].update(ai_data)

        events = list(id_map.values())
        events_path.write_text(json.dumps(events, ensure_ascii=False, indent=2))
        print("행사 AI 콘텐츠 병합 완료")

    if mode in ("all", "weekly"):
        generate_weekly_pick(events)
