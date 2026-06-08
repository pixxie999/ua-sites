"""
매일 오전 8시 KST — 오늘의 추천 축제 정보를 텔레그램으로 전송
생성 내용: 인스타그램용 후킹 멘트 5개 + 이미지 생성 프롬프트 5개
"""

import json
import os
import sys
import requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
load_dotenv(PROJECT_ROOT / ".env")

KST = timezone(timedelta(hours=9))


# ─────────────────────────────────────────
# 오늘의 행사 선정
# ─────────────────────────────────────────

def pick_today_event(events: list) -> dict | None:
    today = datetime.now(KST)
    today_str = today.strftime("%Y%m%d")

    # 진행 중이거나 7일 이내 시작하는 행사
    week_later = (today + timedelta(days=7)).strftime("%Y%m%d")
    candidates = [
        e for e in events
        if e.get("end_date", "") >= today_str
        and e.get("start_date", "") <= week_later
        and e.get("thumbnail")  # 썸네일 있는 것만
    ]

    if not candidates:
        # 썸네일 없어도 포함해서 재시도
        candidates = [
            e for e in events
            if e.get("end_date", "") >= today_str
            and e.get("start_date", "") <= week_later
        ]

    if not candidates:
        return None

    # 날짜 기반 순환 (매일 다른 행사)
    day_of_year = today.timetuple().tm_yday
    return candidates[day_of_year % len(candidates)]


# ─────────────────────────────────────────
# Claude API로 콘텐츠 생성
# ─────────────────────────────────────────

def generate_content(event: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today_str = datetime.now(KST).strftime("%Y년 %m월 %d일")
    free_tag = "무료입장 " if event.get("is_free") else ""
    fee_info = event.get("fee") or ("무료" if event.get("is_free") else "유료")

    prompt = f"""오늘 날짜: {today_str}

아래 축제 정보를 바탕으로 인스타그램 콘텐츠를 작성해줘.

[축제 정보]
이름: {event['title']}
지역: {event['region']} {event.get('place', '')}
기간: {event['start_date_fmt']} ~ {event['end_date_fmt']}
관람료: {fee_info}
카테고리: {event.get('category', '')}
설명: {event.get('overview', '')[:300]}

[요청 1] 인스타그램 후킹 멘트 5개
각 멘트는 아래 스타일로 1개씩, 2~4줄 분량, 이모지 포함:
1. 감성형 (분위기·감정 자극)
2. 정보형 (실용적 정보 강조)
3. 질문형 (팔로워에게 질문)
4. 긴급형 (D-day·마감 강조)
5. 공감형 (공감·경험 자극)

[요청 2] 이미지 생성 프롬프트 5개 (Midjourney 또는 ChatGPT 이미지용 영문)
축제 분위기에 맞는 인스타그램용 정사각형(1:1) 이미지 프롬프트.
각각 다른 구도/분위기로 작성. 한 줄씩.

반드시 아래 JSON 형식으로만 출력 (다른 텍스트 없이):
{{
  "hooks": [
    "멘트1 내용",
    "멘트2 내용",
    "멘트3 내용",
    "멘트4 내용",
    "멘트5 내용"
  ],
  "image_prompts": [
    "prompt1 in english",
    "prompt2 in english",
    "prompt3 in english",
    "prompt4 in english",
    "prompt5 in english"
  ]
}}"""

    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = resp.content[0].text.strip()

    # JSON 파싱
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import re
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"JSON 파싱 실패: {raw[:200]}")


# ─────────────────────────────────────────
# 텔레그램 전송
# ─────────────────────────────────────────

def send_telegram(text: str):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    resp = requests.post(url, json={
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }, timeout=30)
    resp.raise_for_status()
    return resp.json()


def format_message(event: dict, content: dict) -> str:
    today_str = datetime.now(KST).strftime("%Y년 %m월 %d일 (%a)")
    free_tag = " 🆓무료" if event.get("is_free") else ""
    site_url = f"https://uapress.kr/event/{event['id']}/"

    hooks_text = "\n".join(
        f"{i+1}. {h}" for i, h in enumerate(content.get("hooks", []))
    )
    prompts_text = "\n".join(
        f"{i+1}. {p}" for i, p in enumerate(content.get("image_prompts", []))
    )

    return f"""🎪 <b>오늘의 추천 축제</b> — {today_str}

📍 <b>{event['title']}</b>{free_tag}
🗓 {event['start_date_fmt']} ~ {event['end_date_fmt']}
📌 {event['region']} {event.get('place', '')}
💰 {event.get('fee') or ('무료' if event.get('is_free') else '유료')}

━━━━━━━━━━━━━━━━━━
✍️ <b>인스타 후킹 멘트 5개</b>
━━━━━━━━━━━━━━━━━━
{hooks_text}

━━━━━━━━━━━━━━━━━━
🎨 <b>이미지 생성 프롬프트 5개</b>
━━━━━━━━━━━━━━━━━━
{prompts_text}

🔗 <a href="{site_url}">uapress.kr 상세보기</a>"""


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────

def main():
    events_path = PROJECT_ROOT / "data" / "processed" / "events.json"
    if not events_path.exists():
        print("events.json 없음 — 종료")
        sys.exit(1)

    events = json.loads(events_path.read_text())
    event = pick_today_event(events)

    if not event:
        print("오늘 추천할 행사 없음")
        sys.exit(0)

    print(f"선정된 행사: {event['title']} ({event['region']})")

    print("Claude API로 콘텐츠 생성 중...")
    content = generate_content(event)

    print("텔레그램 전송 중...")
    msg = format_message(event, content)
    send_telegram(msg)

    print("전송 완료!")
    print(f"  후킹 멘트: {len(content.get('hooks', []))}개")
    print(f"  이미지 프롬프트: {len(content.get('image_prompts', []))}개")


if __name__ == "__main__":
    main()
