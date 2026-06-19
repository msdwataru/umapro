"""
競馬ラボ (keibalab.jp) からレース情報・出馬表・オッズを取得するクローラー。

Usage:
    # 日付指定でレース一覧・出馬表・単勝オッズを取得
    python -m uma.ingest.keibalab --date 20260614
    python -m uma.ingest.keibalab --date 20260614 --out csv   # CSV出力
    python -m uma.ingest.keibalab --race 202606140911          # 個別レース
"""
import argparse
import csv
import io
import logging
import re
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

KEIBALAB_BASE = "https://www.keibalab.jp"
# 各スレッドが自分の前リクエストから待機する間隔（スレッド間で独立）
THREAD_REQUEST_INTERVAL = 1.0
REQUEST_INTERVAL = THREAD_REQUEST_INTERVAL  # 後方互換

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

# 競馬ラボの venue コード → venue名マッピング
VENUE_MAP: dict[str, str] = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
    "05": "東京", "06": "中山", "07": "中京", "08": "京都",
    "09": "阪神", "10": "小倉",
}


@dataclass
class RaceMeta:
    race_id: str
    date_str: str          # YYYYMMDD
    venue_code: str
    venue_name: str
    race_number: int
    race_name: str
    race_class: str = ""
    track_type: str = ""   # 芝 / ダート / 障害
    distance_m: int | None = None
    weather: str = ""
    going: str = ""
    start_time: str = ""
    field_size: int = 0
    race_url: str = ""
    weight_type: str = ""         # 定量 / ハンデ / 馬齢 / 別定
    prize_money_1st: int | None = None  # 1着本賞金(万円)
    grade: str = ""               # GⅠ / GⅡ / GⅢ / J・GⅠ etc.


@dataclass
class HorseEntry:
    race_id: str
    finish_position: int | None     # None = 除外/取消/中止
    abnormal: str = ""              # 取消/除外/中止/失格
    bracket_number: int | None = None
    horse_number: int = 0
    horse_name: str = ""
    horse_id: str = ""              # keibalab horse code
    sex_age: str = ""
    weight_carried: float | None = None
    jockey_name: str = ""
    jockey_id: str = ""
    trainer_name: str = ""
    trainer_id: str = ""
    trainer_affiliation: str = ""   # 美 / 栗 / 地
    popularity: int | None = None
    win_odds: float | None = None
    finish_time: str = ""
    margin: str = ""
    corner_positions: str = ""
    last3f: float | None = None
    declared_weight_kg: int | None = None
    weight_diff: int | None = None


@dataclass
class OddsRecord:
    race_id: str
    odds_type: str       # tan / fuku / umaren / wide / sanpuku / santan
    horse_number: int | None = None
    combo: str = ""      # 複数頭の組み合わせ (e.g. "1-3")
    odds_min: float | None = None
    odds_max: float | None = None
    popularity: int | None = None


# ──────────────────────────────────────────
#  内部ヘルパー
# ──────────────────────────────────────────

# スレッドローカルなセッション + レート制限
_thread_local = threading.local()


def _get_session() -> requests.Session:
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update(HEADERS)
        _thread_local.session = s
        _thread_local.last_request = 0.0
    return _thread_local.session


def _get(url: str, params: dict | None = None) -> requests.Response:
    sess = _get_session()
    elapsed = time.time() - _thread_local.last_request
    if elapsed < THREAD_REQUEST_INTERVAL:
        time.sleep(THREAD_REQUEST_INTERVAL - elapsed)
    resp = sess.get(url, params=params, timeout=20)
    resp.raise_for_status()
    _thread_local.last_request = time.time()
    return resp


def _parse_race_id(race_id: str) -> tuple[str, str, int]:
    """race_id (12桁) → (date_str YYYYMMDD, venue_code, race_number)"""
    if len(race_id) != 12 or not race_id.isdigit():
        raise ValueError(f"Invalid race_id: {race_id}")
    date_str = race_id[:8]
    venue_code = race_id[8:10]
    race_number = int(race_id[10:12])
    return date_str, venue_code, race_number


def _extract_link_id(href: str | None, pattern: str) -> str:
    if not href:
        return ""
    m = re.search(pattern, href)
    return m.group(1) if m else ""


def _parse_weight(text: str) -> tuple[int | None, int | None]:
    """'520(＋4)' → (520, 4), '計不' → (None, None)"""
    text = text.replace("＋", "+").replace("－", "-").replace("−", "-")
    m = re.search(r"(\d+)\s*\(([+-]?\d+)\)", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    m2 = re.search(r"(\d+)", text)
    return (int(m2.group(1)), None) if m2 else (None, None)


# ──────────────────────────────────────────
#  日付ページ: レース一覧取得
# ──────────────────────────────────────────

def fetch_date_races(date_str: str) -> list[dict[str, Any]]:
    """
    日付ページ (e.g. '20260614') から全レース情報の一覧を返す。
    Returns: list of {race_id, venue_code, venue_name, race_number,
                       start_time, race_class, field_size}
    """
    url = f"{KEIBALAB_BASE}/db/race/{date_str}/"
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    races: list[dict[str, Any]] = []
    seen: set[str] = set()

    for table in soup.find_all("table"):
        # ヘッダー行から開催情報を取得
        header_row = table.find("tr")
        if not header_row:
            continue
        header_text = header_row.get_text(" ", strip=True)

        # 天候・馬場情報
        weather_m = re.search(r"天候：(\S+)", header_text)
        weather = weather_m.group(1) if weather_m else ""
        going_shiba_m = re.search(r"芝：(\S+)", header_text)
        going_shiba = going_shiba_m.group(1) if going_shiba_m else ""

        for row in table.find_all("tr")[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue
            link_a = row.find("a", href=re.compile(r"/db/race/\d{12}/"))
            if not link_a:
                continue
            href = link_a.get("href", "")
            m = re.search(r"/db/race/(\d{12})/", href)
            if not m:
                continue
            race_id = m.group(1)
            if race_id in seen:
                continue
            seen.add(race_id)

            date_s, venue_code, race_num = _parse_race_id(race_id)
            venue_name = VENUE_MAP.get(venue_code, venue_code)

            cell0_text = cells[0].get_text(strip=True)  # "1R09:55"
            time_m = re.search(r"(\d{2}:\d{2})", cell0_text)
            start_time = time_m.group(1) if time_m else ""

            cell1_text = cells[1].get_text(" ", strip=True) if len(cells) > 1 else ""
            # フィールドサイズ: "18頭" など
            fsize_m = re.search(r"(\d+)頭", cell1_text)
            field_size = int(fsize_m.group(1)) if fsize_m else 0

            # コース: "芝1600m" / "ダ1800m"
            track_m = re.search(r"(芝|ダ|障)(\d[\d,]+)m", cell1_text.replace(",", ""))
            if track_m:
                track_raw = track_m.group(1)
                track_type = "芝" if track_raw == "芝" else ("障害" if track_raw == "障" else "ダート")
                distance_m = int(track_m.group(2))
            else:
                track_type, distance_m = "", None

            races.append({
                "race_id": race_id,
                "date_str": date_s,
                "venue_code": venue_code,
                "venue_name": venue_name,
                "race_number": race_num,
                "start_time": start_time,
                "race_class": cell1_text,
                "track_type": track_type,
                "distance_m": distance_m,
                "field_size": field_size,
                "weather": weather,
                "going_shiba": going_shiba,
            })

    logger.info("Found %d races on %s", len(races), date_str)
    return races


# ──────────────────────────────────────────
#  個別レースページ: レース情報 + 出馬表/結果
# ──────────────────────────────────────────

def _parse_raceaboutbox(detail_div) -> dict:
    """
    raceaboutbox から separator="|" でパースして各フィールドを返す。
    Returns: {weather, going, track_type, distance_m, field_size, start_time,
              weight_type, prize_money_1st, grade, race_class}
    """
    detail_text = detail_div.get_text(separator="|", strip=True) if detail_div else ""
    parts = [p.strip() for p in detail_text.split("|") if p.strip()]

    WEATHER_SET = {"晴", "曇", "雨", "雪", "小雨", "小雪"}
    # 馬場状態: "稍" は "稍重" の省略形として扱う
    GOING_MAP = {"良": "良", "稍重": "稍重", "重": "重", "不良": "不良", "稍": "稍重"}

    weather, going = "", ""
    track_type, distance_m = "", None
    field_size = 0
    start_time = ""
    weight_type = ""
    prize_money_1st = None
    grade = ""
    race_class_parts: list[str] = []

    for i, p in enumerate(parts):
        # 天候
        if p in WEATHER_SET:
            weather = p
            continue
        # 馬場
        if p in GOING_MAP:
            going = GOING_MAP[p]
            # 「稍」の直後に「重」が来る場合も対応
            if going == "稍重" and i + 1 < len(parts) and parts[i + 1] == "重":
                going = "稍重"
            continue
        # コース・距離: "芝2200m" / "ダ1300m" / "障害3300m"
        track_m = re.search(r"(芝|ダート|ダ|障害|障)\s*(\d[\d,]+)\s*m", p)
        if track_m:
            raw = track_m.group(1)
            track_type = "芝" if raw == "芝" else ("障害" if raw in ("障害", "障") else "ダート")
            distance_m = int(track_m.group(2).replace(",", ""))
        # 出走頭数
        fsize_m = re.search(r"(\d+)\s*頭", p)
        if fsize_m:
            field_size = int(fsize_m.group(1))
        # 発走時刻
        time_m = re.search(r"(\d{2}:\d{2})\s*発走", p)
        if time_m:
            start_time = time_m.group(1)
        # 本賞金
        prize_m = re.search(r"本賞金\s*(\d+)\s*万", p)
        if prize_m:
            prize_money_1st = int(prize_m.group(1))
        # グレード: ＧⅠ / ＧⅡ / ＧⅢ (全角) or GⅠ etc.
        grade_m = re.search(r"(J・G[ⅠⅡⅢ]|[ＪJ]・Ｇ[ⅠⅡⅢ]|Ｇ[ⅠⅡⅢ]|G[ⅠⅡⅢ])", p)
        if grade_m:
            raw_g = grade_m.group(1)
            grade = raw_g.replace("Ｊ", "J").replace("Ｇ", "G")
        # 重量条件
        wt_m = re.search(r"(定量|ハンデ|馬齢|別定)", p)
        if wt_m:
            weight_type = wt_m.group(1)
            # クラス名: weight_type や条件記号を除いた残り
            cls_raw = re.sub(r"[（(【\[].+?[）)\]】]", "", p)
            cls_raw = cls_raw.replace(weight_type, "").strip()
            if cls_raw:
                race_class_parts.append(cls_raw)
        # クラス名候補: 数字・年齢・条件を含む
        elif re.search(r"(歳|未勝利|オープン|クラス|特別|Ｏ|OP)", p):
            cls_raw = re.sub(r"[（(【\[].+?[）)\]】]", "", p).strip()
            if cls_raw and not re.fullmatch(r"\d+R", cls_raw):
                race_class_parts.append(cls_raw)

    race_class = " ".join(race_class_parts).strip()

    return {
        "weather": weather,
        "going": going,
        "track_type": track_type,
        "distance_m": distance_m,
        "field_size": field_size,
        "start_time": start_time,
        "weight_type": weight_type,
        "prize_money_1st": prize_money_1st,
        "grade": grade,
        "race_class": race_class,
    }


def fetch_race_info(race_id: str) -> RaceMeta | None:
    """レースページのメタ情報（レース名・コース等）を取得する。"""
    url = f"{KEIBALAB_BASE}/db/race/{race_id}/"
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_race_info_from_soup(race_id, url, soup)


def _parse_race_info_from_soup(race_id: str, url: str, soup: BeautifulSoup) -> RaceMeta | None:
    """BeautifulSoup オブジェクトからレースメタ情報をパースする（単一リクエスト最適化用）。"""
    date_s, venue_code, race_num = _parse_race_id(race_id)
    venue_name = VENUE_MAP.get(venue_code, venue_code)

    # h1 からレース名取得
    h1 = soup.find("h1")
    race_name = h1.get_text(strip=True) if h1 else ""
    if not race_name:
        title_tag = soup.find("title")
        title_text = title_tag.get_text(strip=True) if title_tag else ""
        race_name_m = re.match(r"(.+?)【", title_text)
        race_name = race_name_m.group(1).strip() if race_name_m else ""

    # raceaboutbox パース
    detail_div = soup.find(class_=re.compile(r"raceabout|raceDetail|race-detail|raceInfo", re.I))
    parsed = _parse_raceaboutbox(detail_div)

    return RaceMeta(
        race_id=race_id,
        date_str=date_s,
        venue_code=venue_code,
        venue_name=venue_name,
        race_number=race_num,
        race_name=race_name,
        race_class=parsed["race_class"],
        track_type=parsed["track_type"],
        distance_m=parsed["distance_m"],
        weather=parsed["weather"],
        going=parsed["going"],
        start_time=parsed["start_time"],
        field_size=parsed["field_size"],
        race_url=url,
        weight_type=parsed["weight_type"],
        prize_money_1st=parsed["prize_money_1st"],
        grade=parsed["grade"],
    )


def fetch_race_full(race_id: str) -> tuple[RaceMeta | None, list[HorseEntry]]:
    """
    レースページから RaceMeta と HorseEntry リストを単一リクエストで取得する。
    ingest ジョブからはこちらを使う（HTTP リクエスト数を半減）。
    """
    url = f"{KEIBALAB_BASE}/db/race/{race_id}/"
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "lxml")
    meta = _parse_race_info_from_soup(race_id, url, soup)
    entries = _parse_entries_from_soup(race_id, soup)
    return meta, entries


def fetch_race_entries(race_id: str) -> list[HorseEntry]:
    """
    レースページから出走馬一覧（結果含む）をパースして返す。
    出走前なら finish_position=None、結果確定後は着順が入る。
    """
    url = f"{KEIBALAB_BASE}/db/race/{race_id}/"
    resp = _get(url)
    soup = BeautifulSoup(resp.text, "lxml")
    return _parse_entries_from_soup(race_id, soup)


def _parse_entries_from_soup(race_id: str, soup: BeautifulSoup) -> list[HorseEntry]:

    # 出走馬テーブルを探す（最初の大きなテーブル）
    entry_table = None
    for t in soup.find_all("table"):
        rows = t.find_all("tr")
        if len(rows) < 3:
            continue
        header = rows[0].get_text(" ", strip=True)
        if "馬名" in header or "馬番" in header:
            entry_table = t
            break

    if not entry_table:
        logger.warning("No entry table found for %s", race_id)
        return []

    entries: list[HorseEntry] = []
    rows = entry_table.find_all("tr")

    for row in rows[1:]:  # ヘッダースキップ
        cells = row.find_all(["td", "th"])
        if len(cells) < 5:
            continue

        # セル0: 着順
        pos_text = cells[0].get_text(strip=True)
        abnormal = ""
        finish_pos: int | None = None
        if pos_text.isdigit():
            finish_pos = int(pos_text)
        elif pos_text in ("取消", "除外", "中止", "失格", "再"):
            abnormal = pos_text
        elif pos_text == "":
            pass  # 出走前

        # セル1: 枠番（CSS class "wak{N}" から取得）
        bracket_num = None
        bracket_cell = cells[1]
        wak_m = re.search(r"wak(\d+)", " ".join(bracket_cell.get("class", [])))
        if wak_m:
            bracket_num = int(wak_m.group(1))
        else:
            bt = bracket_cell.get_text(strip=True)
            if bt.isdigit():
                bracket_num = int(bt)

        # セル2: 馬番
        horse_num_text = cells[2].get_text(strip=True)
        try:
            horse_num = int(horse_num_text)
        except ValueError:
            continue

        # セル3: 馬名 + horse_id
        horse_cell = cells[3]
        horse_a = horse_cell.find("a", href=re.compile(r"/db/horse/"))
        horse_name = horse_a.get_text(strip=True) if horse_a else horse_cell.get_text(strip=True)
        horse_id = _extract_link_id(horse_a.get("href") if horse_a else None, r"/db/horse/(\w+)/")

        # セル4: 性齢
        sex_age = cells[4].get_text(strip=True) if len(cells) > 4 else ""

        # セル5: 斤量
        weight_carried: float | None = None
        if len(cells) > 5:
            try:
                weight_carried = float(cells[5].get_text(strip=True))
            except ValueError:
                pass

        # セル6: 騎手
        jockey_cell = cells[6] if len(cells) > 6 else None
        jockey_name, jockey_id = "", ""
        if jockey_cell:
            jock_a = jockey_cell.find("a", href=re.compile(r"/db/jockey/"))
            jockey_name = jock_a.get_text(strip=True) if jock_a else jockey_cell.get_text(strip=True)
            jockey_id = _extract_link_id(jock_a.get("href") if jock_a else None, r"/db/jockey/(\w+)/")

        # セル7: 人気
        popularity: int | None = None
        if len(cells) > 7:
            try:
                popularity = int(cells[7].get_text(strip=True))
            except ValueError:
                pass

        # セル8: 単勝オッズ
        win_odds: float | None = None
        if len(cells) > 8:
            odds_text = cells[8].get_text(strip=True).replace(",", "")
            try:
                win_odds = float(odds_text)
            except ValueError:
                pass

        # セル9: タイム
        finish_time = cells[9].get_text(strip=True) if len(cells) > 9 else ""

        # セル10: 着差
        margin = cells[10].get_text(strip=True) if len(cells) > 10 else ""

        # セル11: コーナー通過順
        corner_pos = ""
        if len(cells) > 11:
            corner_pos = cells[11].get_text(strip=True)

        # セル12: 上り3F
        last3f: float | None = None
        if len(cells) > 12:
            try:
                last3f = float(cells[12].get_text(strip=True))
            except ValueError:
                pass

        # セル13: 調教師（[栗]安田翔伍 形式）
        trainer_cell = cells[13] if len(cells) > 13 else None
        trainer_name, trainer_id, trainer_affiliation = "", "", ""
        if trainer_cell:
            train_a = trainer_cell.find("a", href=re.compile(r"/db/trainer/"))
            trainer_raw = train_a.get_text(strip=True) if train_a else trainer_cell.get_text(strip=True)
            aff_m = re.match(r"^\[(.+?)\]", trainer_raw)
            trainer_affiliation = aff_m.group(1) if aff_m else ""
            trainer_name = re.sub(r"^\[.+?\]", "", trainer_raw).strip()
            trainer_id = _extract_link_id(train_a.get("href") if train_a else None, r"/db/trainer/(\w+)/")

        # セル14: 馬体重
        weight_kg, weight_diff = None, None
        if len(cells) > 14:
            weight_kg, weight_diff = _parse_weight(cells[14].get_text(strip=True))

        entries.append(HorseEntry(
            race_id=race_id,
            finish_position=finish_pos,
            abnormal=abnormal,
            bracket_number=bracket_num,
            horse_number=horse_num,
            horse_name=horse_name,
            horse_id=horse_id,
            sex_age=sex_age,
            weight_carried=weight_carried,
            jockey_name=jockey_name,
            jockey_id=jockey_id,
            trainer_name=trainer_name,
            trainer_id=trainer_id,
            trainer_affiliation=trainer_affiliation,
            popularity=popularity,
            win_odds=win_odds,
            finish_time=finish_time,
            margin=margin,
            corner_positions=corner_pos,
            last3f=last3f,
            declared_weight_kg=weight_kg,
            weight_diff=weight_diff,
        ))

    logger.info("Fetched %d entries for race %s", len(entries), race_id)
    return entries


# ──────────────────────────────────────────
#  オッズページ
# ──────────────────────────────────────────

ODDS_KIND = {
    "tan": "単勝/複勝",
    "umaren": "馬連",
    "wide": "ワイド",
    "sanpuku": "三連複",
    "santan": "三連単",
    "umatan": "馬単",
}


def fetch_odds(race_id: str, kind: str = "tan") -> list[OddsRecord]:
    """
    オッズページからオッズデータを取得する。
    kind: 'tan' | 'umaren' | 'wide' | 'sanpuku' | 'santan' | 'umatan'
    """
    url = f"{KEIBALAB_BASE}/db/race/{race_id}/odds.html"
    resp = _get(url, params={"kind": kind})
    soup = BeautifulSoup(resp.text, "lxml")

    records: list[OddsRecord] = []
    tables = soup.find_all("table")
    if not tables:
        logger.warning("No odds table found for %s kind=%s", race_id, kind)
        return []

    for table in tables:
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        header_cells = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]

        # ヘッダー行でカラム位置を特定
        header_texts = [c.get_text(strip=True) for c in rows[0].find_all(["th", "td"])]

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            row_texts = [c.get_text(strip=True) for c in cells]

            if kind == "tan":
                # keibalab列構成: [枠番, 馬番, 馬名, 単勝, 複勝min, '-', 複勝max, 人気]
                # (ヘッダー: 枠番 馬番 馬名 単勝 複勝 人気)
                try:
                    if len(row_texts) < 4:
                        continue
                    num_text = row_texts[1]
                    horse_num = int(num_text) if num_text.isdigit() else None
                    if horse_num is None:
                        continue

                    tan_text = row_texts[3].replace(",", "")
                    tan_val = float(tan_text) if tan_text and tan_text not in ("-", "") else None

                    # 複勝: 列4=min, 列5='-', 列6=max, 列7=人気
                    fuku_min, fuku_max = None, None
                    pop_val = None
                    if len(row_texts) >= 8:
                        try:
                            fuku_min = float(row_texts[4].replace(",", "")) if row_texts[4] not in ("-", "") else None
                            fuku_max = float(row_texts[6].replace(",", "")) if row_texts[6] not in ("-", "") else None
                            pop_val = int(row_texts[7]) if row_texts[7].isdigit() else None
                        except ValueError:
                            pass
                    elif len(row_texts) == 6:
                        # 単純な [枠, 馬番, 馬名, 単勝, 複勝, 人気] 形式
                        try:
                            pop_val = int(row_texts[5]) if row_texts[5].isdigit() else None
                        except ValueError:
                            pass

                    records.append(OddsRecord(
                        race_id=race_id,
                        odds_type="tan",
                        horse_number=horse_num,
                        combo=str(horse_num),
                        odds_min=tan_val,
                        popularity=pop_val,
                    ))
                    if fuku_min is not None:
                        records.append(OddsRecord(
                            race_id=race_id,
                            odds_type="fuku",
                            horse_number=horse_num,
                            combo=str(horse_num),
                            odds_min=fuku_min,
                            odds_max=fuku_max,
                        ))
                except (ValueError, IndexError):
                    continue
            else:
                # 馬連/ワイド/三連複/三連単: [人気, 組み合わせ, オッズ]
                try:
                    if len(row_texts) >= 3:
                        pop_text = row_texts[0]
                        combo_text = row_texts[1]
                        odds_text = row_texts[2].replace(",", "")
                        pop_val = int(pop_text) if pop_text.isdigit() else None
                        odds_val = float(odds_text) if odds_text and odds_text != "-" else None

                        if kind == "wide" and len(row_texts) >= 4:
                            min_text = row_texts[2].replace(",", "")
                            max_text = row_texts[3].replace(",", "")
                            records.append(OddsRecord(
                                race_id=race_id,
                                odds_type=kind,
                                combo=combo_text,
                                odds_min=float(min_text) if min_text and min_text != "-" else None,
                                odds_max=float(max_text) if max_text and max_text != "-" else None,
                                popularity=pop_val,
                            ))
                        else:
                            records.append(OddsRecord(
                                race_id=race_id,
                                odds_type=kind,
                                combo=combo_text,
                                odds_min=odds_val,
                                popularity=pop_val,
                            ))
                except (ValueError, IndexError):
                    continue
        break  # 最初のテーブルのみ使用

    logger.info("Fetched %d %s odds records for %s", len(records), kind, race_id)
    return records


def fetch_all_odds(race_id: str) -> dict[str, list[OddsRecord]]:
    """全種別のオッズをまとめて取得する。"""
    result: dict[str, list[OddsRecord]] = {}
    for kind in ODDS_KIND:
        try:
            records = fetch_odds(race_id, kind)
            if records:
                result[kind] = records
        except Exception as e:
            logger.warning("Failed to fetch %s odds for %s: %s", kind, race_id, e)
    return result


# ──────────────────────────────────────────
#  メイン処理
# ──────────────────────────────────────────

def scrape_date(date_str: str, out_format: str = "print") -> dict[str, Any]:
    """
    指定日の全レース情報・出馬表・単勝オッズを取得する。
    out_format: 'print' | 'csv' | 'dict'
    """
    races_meta = fetch_date_races(date_str)

    all_entries: list[HorseEntry] = []
    all_odds: list[OddsRecord] = []
    race_infos: list[RaceMeta] = []

    for race_summary in races_meta:
        race_id = race_summary["race_id"]
        logger.info("Processing race %s ...", race_id)
        try:
            info = fetch_race_info(race_id)
            if info:
                # date_page の情報で補完
                if not info.race_class:
                    info.race_class = race_summary.get("race_class", "")
                if not info.track_type:
                    info.track_type = race_summary.get("track_type", "")
                if not info.distance_m:
                    info.distance_m = race_summary.get("distance_m")
                race_infos.append(info)

            entries = fetch_race_entries(race_id)
            all_entries.extend(entries)

            odds = fetch_odds(race_id, "tan")
            all_odds.extend(odds)

        except Exception as e:
            logger.error("Error processing %s: %s", race_id, e)
            continue

    if out_format == "csv":
        _write_csv(f"{date_str}_races.csv", race_infos)
        _write_csv(f"{date_str}_entries.csv", all_entries)
        _write_csv(f"{date_str}_odds.csv", all_odds)
        print(f"Saved: {date_str}_races.csv, {date_str}_entries.csv, {date_str}_odds.csv")
    elif out_format == "print":
        print(f"\n=== {date_str} レース一覧 ({len(race_infos)}件) ===")
        for info in race_infos:
            print(f"  {info.race_id}  {info.venue_name}{info.race_number}R  {info.race_name or info.race_class}")
        print(f"\n=== 出馬/結果 ({len(all_entries)}頭) ===")
        if all_entries:
            _print_entries(all_entries[:20])
        print(f"\n=== 単勝オッズ ({len(all_odds)}件) ===")
        if all_odds:
            for o in all_odds[:10]:
                print(f"  {o.race_id}  {o.horse_number}番  {o.odds_min}")

    return {"races": race_infos, "entries": all_entries, "odds": all_odds}


def scrape_race(race_id: str, out_format: str = "print") -> dict[str, Any]:
    """個別レースの情報・出馬表・全オッズを取得する。"""
    info = fetch_race_info(race_id)
    entries = fetch_race_entries(race_id)
    tan_odds = fetch_odds(race_id, "tan")

    if out_format == "csv":
        prefix = race_id
        if info:
            _write_csv(f"{prefix}_info.csv", [info])
        _write_csv(f"{prefix}_entries.csv", entries)
        _write_csv(f"{prefix}_odds.csv", tan_odds)
        print(f"Saved: {prefix}_info.csv, {prefix}_entries.csv, {prefix}_odds.csv")
    elif out_format == "print":
        if info:
            print(f"\n=== {info.race_id} {info.venue_name}{info.race_number}R {info.race_name} ===")
            print(f"  {info.track_type} {info.distance_m}m  天候:{info.weather}  馬場:{info.going}")
        print(f"\n--- 出馬表/結果 ({len(entries)}頭) ---")
        _print_entries(entries)
        print(f"\n--- 単勝オッズ ({len(tan_odds)}件) ---")
        for o in sorted(tan_odds, key=lambda x: x.popularity or 99):
            print(f"  {o.horse_number}番  人気{o.popularity}  {o.odds_min}")

    return {"info": info, "entries": entries, "odds": tan_odds}


def _write_csv(filename: str, data: list) -> None:
    if not data:
        return
    rows = [asdict(d) if hasattr(d, "__dataclass_fields__") else d for d in data]
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)


def _print_entries(entries: list[HorseEntry]) -> None:
    fmt = "{:<5} {:<3} {:<3} {:<14} {:<6} {:<12} {:>5} {:>8} {:>7} {:>8}"
    print(fmt.format("着", "枠", "馬番", "馬名", "性齢", "騎手", "人気", "単勝", "タイム", "馬体重"))
    print("-" * 80)
    for e in entries:
        pos = str(e.finish_position) if e.finish_position else (e.abnormal or "-")
        wt = f"{e.declared_weight_kg}({e.weight_diff:+d})" if e.declared_weight_kg and e.weight_diff is not None else (str(e.declared_weight_kg) if e.declared_weight_kg else "-")
        print(fmt.format(
            pos, str(e.bracket_number or "-"), str(e.horse_number),
            (e.horse_name or "")[:14], (e.sex_age or "")[:6],
            (e.jockey_name or "")[:12], str(e.popularity or "-"),
            str(e.win_odds or "-"), (e.finish_time or "-")[:7], wt,
        ))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="競馬ラボ クローラー")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--date", metavar="YYYYMMDD", help="取得する日付 (例: 20260614)")
    group.add_argument("--race", metavar="RACE_ID", help="個別レースID 12桁 (例: 202606140911)")
    parser.add_argument("--out", choices=["print", "csv"], default="print", help="出力形式 (default: print)")
    args = parser.parse_args()

    if args.date:
        scrape_date(args.date, out_format=args.out)
    else:
        scrape_race(args.race, out_format=args.out)
