"""
JRA公式サイトの重賞成績ページからレース結果データを取得するスクレイパー。

対象: https://www.jra.go.jp/datafile/seiseki/replay/{year}/jyusyo.html

Usage:
    uv run python -m uma.ingest.jra_job --year 2026
"""
import logging
import re
import time
from datetime import date
from typing import Any

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

JRA_BASE = "https://www.jra.go.jp"
REQUEST_INTERVAL = 2.0  # JRA は少し長めに間隔を取る
ENCODING = "shift_jis"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

# 競馬場名 → external_racecourse_code マッピング
VENUE_CODE: dict[str, str] = {
    "札幌": "01", "函館": "02", "福島": "03", "新潟": "04",
    "東京": "05", "中山": "06", "中京": "07", "京都": "08",
    "阪神": "09", "小倉": "10",
}
VENUE_SHORT: dict[str, str] = {
    "札幌": "札", "函館": "函", "福島": "福", "新潟": "新",
    "東京": "東", "中山": "中山", "中京": "中京", "京都": "京",
    "阪神": "阪", "小倉": "小",
}


def _get(client: httpx.Client, url: str) -> BeautifulSoup:
    time.sleep(REQUEST_INTERVAL)
    resp = client.get(url, headers=HEADERS, follow_redirects=True)
    resp.raise_for_status()
    return BeautifulSoup(resp.content.decode(ENCODING, errors="replace"), "lxml")


def _parse_date(text: str) -> str | None:
    """'2026年1月4日（日曜）' → '2026-01-04'"""
    m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if not m:
        return None
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"


def _parse_distance(text: str) -> tuple[str, int | None]:
    """'芝2,000メートル' → ('芝', 2000)  /  'ダート1,600メートル' → ('ダート', 1600)"""
    t = "芝" if "芝" in text else ("障害" if "障" in text else "ダート")
    m = re.search(r"([\d,]+)\s*メートル", text)
    dist = int(m.group(1).replace(",", "")) if m else None
    return t, dist


def _parse_weight(text: str) -> tuple[int | None, int | None]:
    """'478(+2)' → (478, 2)  /  '計不' → (None, None)"""
    m = re.search(r"(\d+)\s*\(([+-]?\d+)\)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def fetch_jra_index(year: int) -> list[dict[str, Any]]:
    """
    jyusyo.html から重賞レース一覧を取得する。
    各要素: {path, race_name, venue, date_str, track_type, distance_m}
    """
    url = f"{JRA_BASE}/datafile/seiseki/replay/{year}/jyusyo.html"
    races: list[dict[str, Any]] = []

    with httpx.Client(timeout=30) as client:
        try:
            soup = _get(client, url)
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch JRA index: %s", e)
            return []

        # テーブルの各行
        table = soup.find("table", class_="basic")
        if not table:
            logger.warning("No table found on index page")
            return []

        for row in table.find_all("tr")[1:]:  # ヘッダー行をスキップ
            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            date_raw = cells[0].get_text(strip=True)
            race_name_raw = cells[1].get_text(strip=True)
            venue = cells[2].get_text(strip=True).strip()
            course_raw = cells[4].get_text(strip=True)
            track_type, distance_m = _parse_distance(course_raw)

            # 結果リンク
            link = cells[7].find("a")
            if not link:
                continue
            path = link.get("href", "")

            # 日付: "1月4日日曜" → 年を補完
            m = re.search(r"(\d{1,2})月(\d{1,2})日", date_raw)
            if m:
                date_str = f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"
            else:
                date_str = None

            races.append({
                "path": path,
                "race_name": race_name_raw,
                "venue": venue,
                "date_str": date_str,
                "track_type": track_type,
                "distance_m": distance_m,
            })

    logger.info("Found %d races in JRA index for %d", len(races), year)
    return races


def fetch_jra_g1_index(year: int) -> list[dict[str, Any]]:
    """
    g1.html から GⅠレース一覧を取得する。
    各要素: {path, race_name, venue, date_str, track_type, distance_m, grade}
    結果リンクがない（未開催）レースはスキップ。
    """
    url = f"{JRA_BASE}/datafile/seiseki/replay/{year}/g1.html"
    races: list[dict[str, Any]] = []

    with httpx.Client(timeout=30) as client:
        try:
            soup = _get(client, url)
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch JRA G1 index: %s", e)
            return []

        table = soup.find("table", class_="basic")
        if not table:
            logger.warning("No table found on G1 index page")
            return []

        for row in table.find_all("tr")[1:]:
            cells = row.find_all("td")
            if len(cells) < 8:
                continue

            date_raw = cells[0].get_text(strip=True)
            race_name_raw = cells[1].get_text(strip=True)
            venue = cells[2].get_text(strip=True).strip()
            course_raw = cells[4].get_text(strip=True)
            track_type, distance_m = _parse_distance(course_raw)

            # g1.html の結果セルは [index_link, result_link] の2リンク
            links = [a.get("href", "") for a in cells[7].find_all("a")]
            if not links:
                continue  # 未開催（リンクなし）はスキップ
            # 結果ページは2番目のリンク（1番目はインデックス）
            path = links[1] if len(links) > 1 else links[0]
            if not path:
                continue

            m = re.search(r"(\d{1,2})月(\d{1,2})日", date_raw)
            date_str = f"{year}-{int(m.group(1)):02d}-{int(m.group(2)):02d}" if m else None

            # グレードをレース名から抽出
            grade = None
            for g in ("J・GⅠ", "GⅠ"):
                if g in race_name_raw:
                    grade = g
                    break

            races.append({
                "path": path,
                "race_name": race_name_raw,
                "venue": venue,
                "date_str": date_str,
                "track_type": track_type,
                "distance_m": distance_m,
                "grade": grade,
            })

    logger.info("Found %d completed G1 races in JRA G1 index for %d", len(races), year)
    return races


def fetch_jra_result(path: str) -> dict[str, Any] | None:
    """
    個別結果ページを取得してパースする。
    Returns: {race_meta, entries}
    """
    url = JRA_BASE + path if path.startswith("/") else path

    with httpx.Client(timeout=30) as client:
        try:
            soup = _get(client, url)
        except httpx.HTTPStatusError as e:
            logger.warning("Failed to fetch JRA result %s: %s", path, e)
            return None

        # --- レースメタデータ ---
        meta: dict[str, Any] = {"path": path}

        # メタ情報テーブル（1行目の大きなセル）
        first_table = soup.find("table", class_="basic")
        if first_table:
            header_row = first_table.find("tr")
            if header_row:
                header_text = header_row.get_text(" ", strip=True)
                meta["date_str"] = _parse_date(header_text)

                # 開催場: "1回中山1日" → 中山
                m_venue = re.search(r"\d回(\S+?)\d日", header_text)
                if m_venue:
                    meta["venue"] = m_venue.group(1)

                # 天候
                m_weather = re.search(r"天候\s+(晴|曇|雨|雪|小雨|小雪)", header_text)
                meta["weather"] = m_weather.group(1) if m_weather else None

                # 馬場状態（芝/ダート + 良/稍重/重/不良）
                m_going = re.search(r"(?:芝|ダート|障害)\s+(良|稍重|重|不良)", header_text)
                meta["going"] = m_going.group(1) if m_going else None

                # コース・距離
                m_dist = re.search(r"([\d,]+)\s*メートル", header_text)
                if m_dist:
                    meta["distance_m"] = int(m_dist.group(1).replace(",", ""))
                m_track = re.search(r"（(芝|ダート|障害)・", header_text)
                if m_track:
                    meta["track_type"] = m_track.group(1)
                elif m_dist:
                    # フォールバック: テキスト中の「芝」「ダート」で判定
                    if "芝" in header_text:
                        meta["track_type"] = "芝"
                    elif "障" in header_text:
                        meta["track_type"] = "障害"
                    else:
                        meta["track_type"] = "ダート"

        # レース名（sr-only/title クラスを除いた最初のh2）
        h2 = soup.find("h2", class_=lambda c: not c or ("sr-only" not in c and "title" not in c))
        meta["race_name"] = h2.get_text(strip=True) if h2 else None

        # ラップタイム
        lap_table = soup.find("table", class_=lambda c: c and "narrow" in c and "narrow-xy" not in c)
        if lap_table:
            rows = lap_table.find_all("tr")
            if rows:
                meta["lap_text"] = rows[0].get_text(" ", strip=True)

        # --- 着順テーブル ---
        result_table = soup.find("table", class_=lambda c: c and "striped" in (c or []))
        entries: list[dict[str, Any]] = []
        if result_table:
            for row in result_table.find_all("tr")[1:]:  # ヘッダースキップ
                cells = row.find_all("td")
                if len(cells) < 10:
                    continue

                pos_text = cells[0].get_text(strip=True)
                # 着順: 数字以外 (取消, 中止, 失格 etc.) は None
                try:
                    finish_position = int(pos_text)
                except ValueError:
                    finish_position = None
                    abnormal = pos_text  # "取消", "除外", "中止", "失格"
                else:
                    abnormal = None

                bracket_num = cells[1].get_text(strip=True)
                horse_num_text = cells[2].get_text(strip=True)
                try:
                    horse_num = int(horse_num_text)
                except ValueError:
                    continue

                horse_name = cells[3].get_text(strip=True)
                sex_age = cells[4].get_text(strip=True)
                jockey_name = cells[6].get_text(strip=True).replace("　", " ")
                finish_time = cells[7].get_text(strip=True)
                margin_text = cells[8].get_text(strip=True)
                passing_order = cells[9].get_text(strip=True)

                last3f_text = cells[10].get_text(strip=True)
                try:
                    last3f = float(last3f_text)
                except ValueError:
                    last3f = None

                weight_text = cells[11].get_text(strip=True) if len(cells) > 11 else ""
                body_weight, weight_diff = _parse_weight(weight_text)

                entries.append({
                    "finish_position": finish_position,
                    "bracket_number": int(bracket_num) if bracket_num.isdigit() else None,
                    "horse_number": horse_num,
                    "horse_name": horse_name,
                    "sex_age": sex_age,
                    "jockey_name": jockey_name,
                    "finish_time": finish_time if finish_time else None,
                    "margin_text": margin_text,
                    "passing_order_text": passing_order,
                    "last3f": last3f,
                    "declared_weight_kg": body_weight,
                    "declared_weight_diff_kg": weight_diff,
                    "abnormal_result_code": abnormal,
                })

        return {"meta": meta, "entries": entries}
