"""
매일 오전 8시 KST — 오늘의 추천 축제 정보를 텔레그램으로 전송
생성 내용: 인스타그램용 후킹 멘트 5개 + 이미지 생성 프롬프트 5개
+ 요일별 테마 선정 + 지역·카테고리별 해시태그 자동 추가
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
# 요일별 테마 설정
# ─────────────────────────────────────────

# 월=0, 화=1, 수=2, 목=3, 금=4, 토=5, 일=6
WEEKDAY_THEME = {
    0: {"label": "월요일 🆓 무료행사",    "category": "무료",  "emoji": "🎟",  "filter": "free"},
    1: {"label": "화요일 🎆 축제",        "category": "축제",  "emoji": "🎆",  "filter": "category"},
    2: {"label": "수요일 🎭 공연",        "category": "공연",  "emoji": "🎭",  "filter": "category"},
    3: {"label": "목요일 🖼 전시",        "category": "전시",  "emoji": "🖼",  "filter": "category"},
    4: {"label": "금요일 🎨 체험",        "category": "체험",  "emoji": "🎨",  "filter": "category"},
    5: {"label": "토요일 🏃 이번 주말 추천", "category": None, "emoji": "🌟",  "filter": "weekend"},
    6: {"label": "일요일 🌟 이번 주 인기", "category": None,  "emoji": "🔥",  "filter": "all"},
}


# ─────────────────────────────────────────
# 해시태그 생성
# ─────────────────────────────────────────

REGION_TAGS = {
    "서울": "#서울축제 #서울행사 #서울나들이 #서울여행",
    "인천": "#인천축제 #인천행사 #인천나들이 #인천여행",
    "대전": "#대전축제 #대전행사 #대전나들이 #대전여행",
    "대구": "#대구축제 #대구행사 #대구나들이 #대구여행",
    "광주": "#광주축제 #광주행사 #광주나들이 #광주여행",
    "부산": "#부산축제 #부산행사 #부산나들이 #부산여행",
    "울산": "#울산축제 #울산행사 #울산나들이 #울산여행",
    "세종": "#세종축제 #세종행사 #세종나들이",
    "경기": "#경기축제 #경기행사 #경기도나들이 #수도권행사",
    "강원": "#강원축제 #강원행사 #강원여행 #강원도",
    "충북": "#충북축제 #충북행사 #충청북도여행",
    "충남": "#충남축제 #충남행사 #충청남도여행",
    "경북": "#경북축제 #경북행사 #경상북도여행",
    "경남": "#경남축제 #경남행사 #경상남도여행",
    "전북": "#전북축제 #전북행사 #전라북도여행",
    "전남": "#전남축제 #전남행사 #전라남도여행",
    "제주": "#제주축제 #제주행사 #제주여행 #제주도",
}

CATEGORY_TAGS = {
    "축제":   "#축제 #지역축제 #한국축제 #주말축제",
    "공연":   "#공연 #공연정보 #문화공연 #공연추천",
    "전시":   "#전시 #전시회 #전시정보 #미술전시",
    "체험":   "#체험 #체험행사 #문화체험 #체험프로그램",
    "스포츠": "#스포츠행사 #마라톤 #스포츠",
    "문화행사": "#문화행사 #문화축제 #지역행사",
}

COMMON_TAGS = "#전국축제정보 #축제정보 #행사정보 #주말나들이 #주말행사 #나들이 #가볼만한곳 #한국여행 #uapress"


def build_hashtags(event: dict) -> str:
    region = event.get("region", "")
    category = event.get("category", "")
    free_tag = "#무료행사 #무료입장 " if event.get("is_free") else ""

    region_tags = REGION_TAGS.get(region, f"#{region}축제 #{region}행사")
    category_tags = CATEGORY_TAGS.get(category, f"#{category}")

    return f"{free_tag}{region_tags} {category_tags} {COMMON_TAGS}"


# ─────────────────────────────────────────
# 오늘의 행사 선정 (요일 테마 반영)
# ─────────────────────────────────────────

def pick_today_event(events: list) -> tuple[dict | None, dict]:
    today = datetime.now(KST)
    today_str = today.strftime("%Y%m%d")
    weekday = today.weekday()
    theme = WEEKDAY_THEME[weekday]

    week_later = (today + timedelta(days=7)).strftime("%Y%m%d")

    # 기본 풀: 진행 중이거나 7일 이내 시작
    base_pool = [
        e for e in events
        if e.get("end_date", "") >= today_str
        and e.get("start_date", "") <= week_later
    ]

    # 요일 테마에 맞게 필터
    if theme["filter"] == "free":
        candidates = [e for e in base_pool if e.get("is_free")]
    elif theme["filter"] == "category":
        candidates = [e for e in base_pool if e.get("category") == theme["category"]]
    elif theme["filter"] == "weekend":
        # 토요일: 이번 주말 시작/진행 중
        sat = (today + timedelta(days=(5 - weekday) % 7)).strftime("%Y%m%d")
        sun = (today + timedelta(days=(6 - weekday) % 7)).strftime("%Y%m%d")
        candidates = [
            e for e in base_pool
            if e.get("start_date", "") <= sun and e.get("end_date", "") >= sat
        ]
    else:
        candidates = base_pool

    # 필터 결과 없으면 전체 풀로 폴백
    if not candidates:
        candidates = base_pool

    # 썸네일 있는 것 우선
    with_thumb = [e for e in candidates if e.get("thumbnail")]
    pool = with_thumb if with_thumb else candidates

    if not pool:
        return None, theme

    # 날짜 기반 순환으로 매일 다른 행사 선정
    day_of_year = today.timetuple().tm_yday
    return pool[day_of_year % len(pool)], theme


# ─────────────────────────────────────────
# Claude API로 콘텐츠 생성
# ─────────────────────────────────────────

def generate_content(event: dict, theme: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today_str = datetime.now(KST).strftime("%Y년 %m월 %d일")
    fee_info = event.get("fee") or ("무료" if event.get("is_free") else "유료")
    theme_label = theme["label"]

    prompt = f"""오늘 날짜: {today_str}
오늘의 테마: {theme_label}

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


def format_message(event: dict, content: dict, theme: dict) -> str:
    today_str = datetime.now(KST).strftime("%Y년 %m월 %d일 (%a)")
    free_tag = " 🆓무료" if event.get("is_free") else ""
    site_url = f"https://uapress.kr/event/{event['id']}/"

    hooks_text = "\n\n".join(
        f"<b>[{i+1}]</b> {h}" for i, h in enumerate(content.get("hooks", []))
    )
    prompts_text = "\n".join(
        f"{i+1}. {p}" for i, p in enumerate(content.get("image_prompts", []))
    )
    hashtags = build_hashtags(event)

    return f"""{theme['emoji']} <b>{theme['label']}</b> — {today_str}

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

━━━━━━━━━━━━━━━━━━
#️⃣ <b>해시태그</b>
━━━━━━━━━━━━━━━━━━
{hashtags}

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
    event, theme = pick_today_event(events)

    if not event:
        print("오늘 추천할 행사 없음")
        sys.exit(0)

    print(f"오늘 테마: {theme['label']}")
    print(f"선정된 행사: {event['title']} ({event['region']})")

    print("Claude API로 콘텐츠 생성 중...")
    content = generate_content(event, theme)

    print("텔레그램 전송 중...")
    msg = format_message(event, content, theme)
    send_telegram(msg)

    print("전송 완료!")
    print(f"  후킹 멘트: {len(content.get('hooks', []))}개")
    print(f"  이미지 프롬프트: {len(content.get('image_prompts', []))}개")
    print(f"  해시태그: {build_hashtags(event)[:60]}...")


if __name__ == "__main__":
    main()
