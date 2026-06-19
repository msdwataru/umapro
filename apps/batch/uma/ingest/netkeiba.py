"""netkeibaからレース情報・出馬表・オッズを取得するスクレイパー"""
import logging
import re
import time
from datetime import date
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://race.netkeiba.com"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}
REQUEST_INTERVAL = 1.5  # seconds between requests


def _get(client: httpx.Client, url: str) -> BeautifulSoup:
    time.sleep(REQUEST_INTERVAL)
    resp = client.get(url, headers=HEADERS, follow_redirects=True)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "lxml")


def _racecourse_code_to_name(code: str) -> tuple[str, str]:
    """JRAの場コード→（名前, 略称）"""
    table = {
        "01": ("札幌", "札"),
        "02": ("函館", "函"),
        "03": ("福島", "福"),
        "04": ("新潟", "新"),
        "05": ("東京", "東"),
        "06": ("中山", "中山"),
        "07": ("中京", "中京"),
        "08": ("京都", "京"),
        "09": ("阪神", "阪"),
        "10": ("小倉", "小"),
    }
    return table.get(code, (f"場{code}", code))


def fetch_race_list(target_date: date) -> list[dict[str, Any]]:
    """指定日の全レースIDリストを取得する"""
    date_str = target_date.strftime("%Y%m%d")
    url = f"{BASE_URL}/top/race_list_sub.html?kaisai_date={date_str}"
    races: list[dict[str, Any]] = []

    with httpx.Client(timeout=30) as client:
        try:
            soup = _get(client, url)
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch race list: %s", e)
            return []

        seen: set[str] = set()
        for a in soup.select("a[href*='race_id']"):
            href = a.get("href", "")
            m = re.search(r"race_id=(\d{12})", href)
            if not m:
                continue
            race_id = m.group(1)
            if race_id not in seen:
                seen.add(race_id)
                races.append({"netkeiba_race_id": race_id})

    logger.info("Found %d races for %s", len(races), target_date)
    return races


def fetch_race_detail(netkeiba_race_id: str) -> dict[str, Any] | None:
    """レース詳細・出馬表を取得する"""
    url = f"{BASE_URL}/race/shutuba.html?race_id={netkeiba_race_id}"

    with httpx.Client(timeout=30) as client:
        try:
            soup = _get(client, url)
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch race %s: %s", netkeiba_race_id, e)
            return None

        # race_id から場コード・年・回などを解析
        # 形式: YYYYCCDDRRNN (年4桁, 場2桁, 回2桁, 日2桁, レース2桁)
        rid = netkeiba_race_id
        year = int(rid[0:4])
        course_code = rid[4:6]
        race_number = int(rid[10:12])
        name, short_name = _racecourse_code_to_name(course_code)

        # レース情報パース
        race_data: dict[str, Any] = {
            "netkeiba_race_id": netkeiba_race_id,
            "racecourse_code": course_code,
            "racecourse_name": name,
            "racecourse_short": short_name,
            "race_number": race_number,
            "race_name": None,
            "track_type": None,
            "distance_m": None,
            "going": None,
            "class_name": None,
            "field_size": None,
            "year": year,
        }

        # レース名 — 実際のHTML: <h1 class="RaceName">
        title_el = soup.select_one("h1.RaceName, .RaceTitle, h1.Race_Name")
        if title_el:
            race_data["race_name"] = title_el.get_text(strip=True)

        # コース・距離 — 実際のHTML: "09:55発走 / ダ1400m (左) / 天候:小雨 / 馬場:重"
        data_el = soup.select_one(".RaceData01, .mainrace_data")
        if data_el:
            text = data_el.get_text(" ", strip=True)
            # "芝2000m" or "ダ1400m" or "障2000m"
            m_track = re.search(r"(芝|ダ|障)\s*(\d{3,4})", text)
            if m_track:
                t = m_track.group(1)
                race_data["track_type"] = "芝" if t == "芝" else ("障害" if t == "障" else "ダート")
                race_data["distance_m"] = int(m_track.group(2))
            m_going = re.search(r"馬場[:：]\s*(良|稍重|重|不良)", text)
            if m_going:
                race_data["going"] = m_going.group(1)

        # 出馬表 — 実際のHTML: tr.HorseList 各行
        entries: list[dict[str, Any]] = []
        for row in soup.select("tr.HorseList"):
            cells = row.find_all("td")
            if len(cells) < 9:
                continue
            try:
                horse_num = int(cells[1].get_text(strip=True))
            except ValueError:
                continue

            # 枠番
            try:
                bracket_num = int(cells[0].get_text(strip=True))
            except ValueError:
                bracket_num = None

            # 馬: https://db.netkeiba.com/horse/XXXXXXXX
            horse_link = row.select_one("a[href*='/horse/']")
            horse_code = None
            if horse_link:
                m_hc = re.search(r"/horse/(\d+)", horse_link.get("href", ""))
                if m_hc:
                    horse_code = m_hc.group(1)

            # 騎手: https://db.netkeiba.com/jockey/result/recent/XXXXX/
            jockey_link = row.select_one("a[href*='/jockey/']")
            jockey_code = None
            if jockey_link:
                m_jk = re.search(r"/jockey/(?:result/recent/)?(\w+)/?$", jockey_link.get("href", ""))
                if m_jk:
                    jockey_code = m_jk.group(1)

            # 調教師: https://db.netkeiba.com/trainer/result/recent/XXXXX/
            trainer_link = row.select_one("a[href*='/trainer/']")
            trainer_code = None
            if trainer_link:
                m_tr = re.search(r"/trainer/(?:result/recent/)?(\w+)/?$", trainer_link.get("href", ""))
                if m_tr:
                    trainer_code = m_tr.group(1)

            # 性齢: td[4] class="Barei"
            sex_age = cells[4].get_text(strip=True) if len(cells) > 4 else None

            # 馬体重: td[8] class="Weight" → "486(+6)"
            declared_weight_kg = None
            declared_weight_diff_kg = None
            weight_el = cells[8] if len(cells) > 8 else None
            if weight_el:
                wt = weight_el.get_text(strip=True)
                m_w = re.search(r"(\d+)\s*\(([+-]?\d+)\)", wt)
                if m_w:
                    declared_weight_kg = int(m_w.group(1))
                    declared_weight_diff_kg = int(m_w.group(2))

            entries.append({
                "horse_number": horse_num,
                "bracket_number": bracket_num,
                "horse_external_code": horse_code,
                "horse_name": horse_link.get_text(strip=True) if horse_link else None,
                "jockey_external_code": jockey_code,
                "jockey_name": jockey_link.get_text(strip=True) if jockey_link else None,
                "trainer_external_code": trainer_code,
                "trainer_name": trainer_link.get_text(strip=True) if trainer_link else None,
                "sex_age": sex_age,
                "declared_weight_kg": declared_weight_kg,
                "declared_weight_diff_kg": declared_weight_diff_kg,
            })

        race_data["entries"] = entries
        race_data["field_size"] = len(entries)
        return race_data


def fetch_odds(netkeiba_race_id: str) -> dict[str, Any]:
    """単勝・複勝オッズを取得する"""
    url = f"{BASE_URL}/odds/index.html?race_id={netkeiba_race_id}&type=b1"

    with httpx.Client(timeout=30) as client:
        try:
            soup = _get(client, url)
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch odds %s: %s", netkeiba_race_id, e)
            return {}

        odds_by_num: dict[int, dict[str, Any]] = {}
        for row in soup.select("tr.HorseList, .odds-table tr"):
            cells = row.select("td")
            if len(cells) < 3:
                continue
            try:
                horse_num = int(cells[0].get_text(strip=True))
                win_odds_text = cells[1].get_text(strip=True).replace(",", "")
                win_odds = float(win_odds_text) if win_odds_text and win_odds_text != "---" else None
            except (ValueError, IndexError):
                continue

            pop_el = row.select_one(".Ninki")
            popularity = None
            if pop_el:
                try:
                    popularity = int(pop_el.get_text(strip=True))
                except ValueError:
                    pass

            odds_by_num[horse_num] = {
                "latest_win_odds": win_odds,
                "morning_line_popularity": popularity,
            }

        return odds_by_num
