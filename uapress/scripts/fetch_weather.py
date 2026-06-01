"""
기상청 단기예보 API — 17개 지역 주말 날씨 수집
data.go.kr: 기상청_단기예보((구)_기상청_동네예보_정보조회서비스)
무료 API
"""

import requests
import json
import time
import os
from pathlib import Path
from datetime import datetime, timedelta
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

load_dotenv(PROJECT_ROOT / ".env")

API_URL = "https://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"

WEATHER_DIR = PROJECT_ROOT / "data/content/weather"

# 지역별 기상청 격자 좌표 (nx, ny)
REGION_GRID = {
    "서울":  (60, 127), "인천":  (55, 124), "대전":  (67, 100),
    "대구":  (89,  90), "광주":  (58,  74), "부산":  (98,  76),
    "울산":  (102, 84), "세종":  (66, 103), "경기":  (60, 120),
    "강원":  (73, 134), "충북":  (76, 113), "충남":  (68, 100),
    "경북":  (91, 106), "경남":  (91,  77), "전북":  (63,  89),
    "전남":  (51,  67), "제주":  (52,  38),
}

# 날씨 코드 → 아이콘/설명
SKY_MAP = {
    "1": ("☀️", "맑음"),
    "3": ("⛅", "구름 많음"),
    "4": ("☁️", "흐림"),
}

PTY_MAP = {  # 강수 형태 (우선)
    "0": None,
    "1": ("🌧️", "비"),
    "2": ("🌨️", "비/눈"),
    "3": ("❄️", "눈"),
    "4": ("🌦️", "소나기"),
}


def _get_api_key():
    return os.environ["KMA_API_KEY"]


def get_weekend_dates():
    """이번 주 토·일 날짜 반환"""
    today = datetime.now()
    days_to_saturday = (5 - today.weekday()) % 7
    saturday = today + timedelta(days=days_to_saturday)
    sunday = saturday + timedelta(days=1)
    return saturday, sunday


def fetch_forecast(nx: int, ny: int, base_date: str, base_time: str = "0500") -> list:
    """단기예보 조회"""
    params = {
        "serviceKey": _get_api_key(),
        "pageNo": 1,
        "numOfRows": 1000,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }
    try:
        resp = requests.get(API_URL, params=params, timeout=15)
        data = resp.json()
        items = (data.get("response", {})
                    .get("body", {})
                    .get("items", {})
                    .get("item", []))
        return items if isinstance(items, list) else []
    except Exception as e:
        print(f"  날씨 API 오류 ({nx},{ny}): {e}")
        return []


def parse_weekend_weather(items: list, saturday: datetime, sunday: datetime) -> dict:
    """토·일 오후 날씨 추출"""
    sat_str = saturday.strftime("%Y%m%d")
    sun_str = sunday.strftime("%Y%m%d")

    # 토·일 오후 12시~18시 데이터
    target_times = {"1200", "1500", "1800"}
    target_dates = {sat_str, sun_str}

    sky_codes = []
    pty_codes = []
    temps = []

    for item in items:
        if item.get("fcstDate") not in target_dates:
            continue
        if item.get("fcstTime") not in target_times:
            continue
        cat = item.get("category", "")
        val = item.get("fcstValue", "")
        if cat == "SKY":
            sky_codes.append(val)
        elif cat == "PTY":
            pty_codes.append(val)
        elif cat == "TMP":
            try:
                temps.append(float(val))
            except ValueError:
                pass

    # 대표값 선택 (최빈값)
    pty = max(set(pty_codes), key=pty_codes.count) if pty_codes else "0"
    sky = max(set(sky_codes), key=sky_codes.count) if sky_codes else "1"
    avg_temp = round(sum(temps) / len(temps)) if temps else None

    # 날씨 결정: 강수 우선
    if pty != "0" and pty in PTY_MAP:
        icon, condition = PTY_MAP[pty]
    else:
        icon, condition = SKY_MAP.get(sky, ("🌤️", "대체로 맑음"))

    # 한줄 요약
    temp_str = f" · {avg_temp}°C" if avg_temp is not None else ""
    summary = f"이번 주말 {condition}{temp_str} — 야외 행사 {'나들이 최적! 🎉' if pty == '0' else '우산 챙기세요 ☂️'}"

    return {
        "icon": icon,
        "condition": condition,
        "avg_temp": avg_temp,
        "summary": summary,
        "updated_at": datetime.now().isoformat(),
        "saturday": sat_str,
        "sunday": sun_str,
    }


def fetch_all():
    WEATHER_DIR.mkdir(parents=True, exist_ok=True)

    saturday, sunday = get_weekend_dates()
    base_date = datetime.now().strftime("%Y%m%d")

    # 발표 시각 선택 (가장 최근 예보)
    hour = datetime.now().hour
    if hour >= 23:
        base_time = "2300"
    elif hour >= 20:
        base_time = "2000"
    elif hour >= 17:
        base_time = "1700"
    elif hour >= 14:
        base_time = "1400"
    elif hour >= 11:
        base_time = "1100"
    elif hour >= 8:
        base_time = "0800"
    elif hour >= 5:
        base_time = "0500"
    else:
        # 자정~5시: 전날 23시 예보 사용
        base_date = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
        base_time = "2300"

    print(f"날씨 수집: {saturday.strftime('%m/%d')}(토) ~ {sunday.strftime('%m/%d')}(일) 기준")

    all_weather = {}
    for region, (nx, ny) in REGION_GRID.items():
        items = fetch_forecast(nx, ny, base_date, base_time)
        if not items:
            print(f"  {region}: 데이터 없음")
            continue

        weather = parse_weekend_weather(items, saturday, sunday)
        weather["region"] = region

        # 개별 파일 저장
        (WEATHER_DIR / f"{region}.json").write_text(
            json.dumps(weather, ensure_ascii=False, indent=2))
        all_weather[region] = weather
        print(f"  {region}: {weather['icon']} {weather['condition']}"
              + (f" {weather['avg_temp']}°C" if weather['avg_temp'] else ""))
        time.sleep(0.2)

    # 전체 요약 저장
    (WEATHER_DIR / "all.json").write_text(
        json.dumps(all_weather, ensure_ascii=False, indent=2))
    print(f"\n날씨 수집 완료: {len(all_weather)}개 지역")


if __name__ == "__main__":
    fetch_all()
