# flight_core.py
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict

import pandas as pd
import requests


# ================== 設定 ==================

MAX_LIST = 30

USE_OFFLINE = False        # True にするとローカル JSON から読み込む
SAVE_SNAPSHOT = False      # True にするとライブ取得時にスナップショット保存
OFFLINE_JSON_PATH = "opensky_states_snapshot.json"


# ================== スナップショット関連 ==================

def save_snapshot_to_file(data: dict, path: str = OFFLINE_JSON_PATH) -> None:
    """ /states/all の生 JSON をローカルファイルに保存 """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OFFLINE] スナップショットを {path} に保存しました。")


def load_snapshot_from_file(path: str = OFFLINE_JSON_PATH) -> Optional[dict]:
    """ ローカルのスナップショット JSON を読み込む """
    p = Path(path)
    if not p.exists():
        print(f"[OFFLINE] スナップショットファイルが見つかりません: {path}")
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ================== OpenSky データ取得 ==================

def _raw_states_json() -> Optional[dict]:
    """
    /states/all の JSON を返す。
    USE_OFFLINE=True のときはローカル JSON を使用。
    """
    if USE_OFFLINE:
        print("[OFFLINE] ローカルスナップショットから states を読み込みます...")
        return load_snapshot_from_file(OFFLINE_JSON_PATH)

    url = "https://opensky-network.org/api/states/all"
    print("[API] Fetching states from OpenSky...")

    try:
        resp = requests.get(url, timeout=15)
    except requests.exceptions.RequestException as e:
        print(f"[API] リクエストエラー: {e}")
        return None

    if resp.status_code == 429:
        print("[API] 429 Too Many Requests（無料枠などの制限の可能性）")
        return None

    try:
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"[API] HTTPエラー: {e}")
        return None

    data = resp.json()
    if SAVE_SNAPSHOT:
        save_snapshot_to_file(data, OFFLINE_JSON_PATH)
    return data


def fetch_opensky_states() -> pd.DataFrame:
    """OpenSky /states/all を叩いて、現在の航空機一覧を DataFrame として返す。"""
    data = _raw_states_json()
    if not data:
        return pd.DataFrame()

    states = data.get("states", []) or []
    if not states:
        print("[API] No states in response.")
        return pd.DataFrame()

    cols = [
        "icao24", "callsign", "origin_country", "time_position",
        "last_contact", "longitude", "latitude", "baro_altitude",
        "on_ground", "velocity", "heading", "vertical_rate",
        "sensors", "geo_altitude", "squawk", "spi", "position_source"
    ]
    df = pd.DataFrame(states, columns=cols)
    df["callsign_norm"] = df["callsign"].fillna("").str.strip().str.upper()
    return df


def select_candidates(df: pd.DataFrame, max_list: int = MAX_LIST) -> pd.DataFrame:
    """callsign のある機体だけに絞り、上位 max_list 件を候補として返す。"""
    df_valid = df[df["callsign_norm"] != ""].copy()
    df_valid = df_valid.sort_values("last_contact", ascending=False)
    return df_valid.head(max_list).reset_index(drop=True)


# ================== ざっくりエリア判定（小辞書） ==================

@dataclass
class RegionBox:
    name: str
    lat_min: float
    lat_max: float
    lon_min: float
    lon_max: float


REGION_BOXES: List[RegionBox] = [
    # 日本とその周辺
    RegionBox("日本付近", 20.0, 50.0, 120.0, 150.0),
    RegionBox("韓国付近", 33.0, 39.5, 124.0, 132.0),
    RegionBox("中国東部付近", 20.0, 42.0, 105.0, 125.0),

    # ヨーロッパ
    RegionBox("ドイツ付近", 47.0, 56.0, 5.0, 16.0),
    RegionBox("フランス付近", 42.0, 51.5, -5.0, 8.0),
    RegionBox("イギリス付近", 49.0, 61.0, -10.0, 2.0),
    RegionBox("ヨーロッパ西部付近", 35.0, 70.0, -10.0, 30.0),

    # 北米
    RegionBox("北米西海岸付近", 30.0, 55.0, -135.0, -110.0),
    RegionBox("北米中部付近", 30.0, 55.0, -110.0, -85.0),
    RegionBox("北米東海岸付近", 30.0, 50.0, -85.0, -60.0),

    # その他
    RegionBox("中東付近", 15.0, 40.0, 30.0, 60.0),
    RegionBox("東南アジア付近", -10.0, 25.0, 95.0, 130.0),
    RegionBox("オーストラリア付近", -45.0, -10.0, 110.0, 155.0),
]


def rough_location_from_latlon(lat: float, lon: float, origin_country: Optional[str] = None) -> str:
    """Nominatim を使わず緯度経度から大ざっぱな現在地テキストを返す。"""
    if pd.isna(lat) or pd.isna(lon):
        return "位置不明"

    lat = float(lat)
    lon = float(lon)

    for box in REGION_BOXES:
        if box.lat_min <= lat <= box.lat_max and box.lon_min <= lon <= box.lon_max:
            return box.name

    # ざっくり海判定
    if lon < -140 or lon > 160:
        return "北太平洋上空" if lat >= 0 else "南太平洋上空"
    if -140 <= lon < -30:
        return "北アメリカ大陸付近" if lat >= 0 else "南アメリカ大陸付近"
    if -30 <= lon < 60:
        return "ヨーロッパ〜北アフリカ付近" if lat >= 0 else "南アフリカ付近"
    if 60 <= lon <= 150:
        return "アジア大陸付近" if lat >= 0 else "インド洋〜オセアニア付近"

    if origin_country:
        return f"{origin_country} 付近"

    return f"緯度 {lat:.1f}°, 経度 {lon:.1f}° 付近"


# ================== コメント生成 ==================

def make_simple_comment(alt: Optional[float], vel: Optional[float], vert_rate: Optional[float]) -> str:
    if alt is None or pd.isna(alt):
        return "高度情報がないため、詳しい景色は推定できません。"

    alt_ft = float(alt) * 3.28084
    if alt_ft < 1000:
        return "滑走路付近か、離着陸の直前・直後の高度かもしれません。"
    elif alt_ft < 10000:
        return "まだ上昇中で、地形や街並みがかなりはっきり見えていそうです。"
    elif alt_ft < 25000:
        return "雲の合間から、地上の街や山が時々見えるような高度を飛行中だと思われます。"
    else:
        return "雲の上を巡航中で、窓の外は青い空と雲のじゅうたんが広がっていそうです。"


def ts_to_str(ts) -> str:
    if pd.isna(ts) or ts is None:
        return "N/A"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return str(ts)


# ================== 外部から使う関数（CLI/API共通） ==================

def get_plane_list() -> List[Dict]:
    """一覧表示用のデータ（dictの配列）を返す。"""
    df = fetch_opensky_states()
    if df.empty:
        return []

    cands = select_candidates(df, MAX_LIST)
    result: List[Dict] = []

    for _, row in cands.iterrows():
        lat = row["latitude"]
        lon = row["longitude"]
        origin = row["origin_country"]
        loc = rough_location_from_latlon(lat, lon, origin_country=origin)

        result.append({
            "callsign": row["callsign_norm"],
            "origin_country": origin,
            "icao24": row["icao24"],
            "latitude": lat,
            "longitude": lon,
            "on_ground": bool(row["on_ground"]),
            "rough_location": loc,
            "last_contact": ts_to_str(row["last_contact"]),
        })

    return result


def get_latest_state(callsign: str) -> Optional[Dict]:
    """callsign の最新状態を1件だけ返す。見つからなければ None。"""
    callsign_norm = (callsign or "").strip().upper()
    if not callsign_norm:
        return None

    df = fetch_opensky_states()
    if df.empty:
        return None

    df_target = df[df["callsign_norm"] == callsign_norm]
    if df_target.empty:
        return None

    row = df_target.iloc[0]

    lat = row["latitude"]
    lon = row["longitude"]
    origin = row["origin_country"]

    baro_alt = row["baro_altitude"]
    geo_alt = row["geo_altitude"]
    alt_use = geo_alt if pd.notna(geo_alt) else baro_alt

    vel = row["velocity"]
    vert_rate = row["vertical_rate"]

    loc_text = rough_location_from_latlon(lat, lon, origin_country=origin)
    comment_text = make_simple_comment(alt_use, vel, vert_rate)

    return {
        "callsign": row["callsign_norm"],
        "icao24": row["icao24"],
        "origin_country": origin,
        "latitude": lat,
        "longitude": lon,
        "baro_altitude": baro_alt,
        "geo_altitude": geo_alt,
        "velocity": vel,
        "heading": row["heading"],
        "vertical_rate": vert_rate,
        "on_ground": bool(row["on_ground"]),
        "time_position": ts_to_str(row["time_position"]),
        "last_contact": ts_to_str(row["last_contact"]),
        "location_text": loc_text,
        "comment_text": comment_text,
    }
