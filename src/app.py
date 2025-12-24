# src/app.py
import json
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.error import HTTPError, URLError

OPENSKY_URL = "https://opensky-network.org/api/states/all"

# ===== 429 対策：TTL キャッシュ =====
CACHE_TTL_SEC = 30  # まずは30秒推奨（必要なら 15〜60 で調整）
_cached_states = None
_cached_at = 0.0

# ===== フォールバック：同梱スナップショット =====
SNAPSHOT_PATH = Path(__file__).with_name("opensky_states_snapshot.json")


def _load_snapshot():
    if SNAPSHOT_PATH.exists():
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return None


def _fetch_opensky_raw():
    req = Request(OPENSKY_URL, headers={"User-Agent": "air-traffic-tracker/0.1"})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def get_states_json():
    """
    OpenSky の /states/all を取得（TTL キャッシュ + フォールバック付き）
    """
    global _cached_states, _cached_at

    now = time.time()
    if _cached_states is not None and (now - _cached_at) < CACHE_TTL_SEC:
        return _cached_states, "cache"

    try:
        data = _fetch_opensky_raw()
        _cached_states = data
        _cached_at = now
        return data, "live"

    except HTTPError as e:
        # 429 や 5xx など
        snap = _load_snapshot()
        if snap is not None:
            return snap, f"snapshot(http:{e.code})"
        raise

    except (URLError, TimeoutError, Exception):
        snap = _load_snapshot()
        if snap is not None:
            return snap, "snapshot(error)"
        raise


def to_plane_list(data, limit=30):
    states = data.get("states") or []
    result = []
    for s in states:
        # [icao24, callsign, origin_country, time_position, last_contact, lon, lat, ...]
        callsign = (s[1] or "").strip()
        if not callsign:
            continue
        result.append({
            "icao24": s[0],
            "callsign": callsign,
            "origin_country": s[2],
            "time_position": s[3],
            "last_contact": s[4],
            "longitude": s[5],
            "latitude": s[6],
        })
        if len(result) >= limit:
            break
    return result


def find_by_icao24(data, icao24: str):
    icao24 = (icao24 or "").strip().lower()
    if not icao24:
        return None

    states = data.get("states") or []
    for s in states:
        if (s[0] or "").lower() == icao24:
            callsign = (s[1] or "").strip()
            return {
                "icao24": s[0],
                "callsign": callsign,
                "origin_country": s[2],
                "time_position": s[3],
                "last_contact": s[4],
                "longitude": s[5],
                "latitude": s[6],
                "baro_altitude": s[7],
                "on_ground": s[8],
                "velocity": s[9],
                "heading": s[10],
                "vertical_rate": s[11],
                "geo_altitude": s[13],
            }
    return None


def _resp(status, obj):
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json; charset=utf-8"},
        "body": json.dumps(obj, ensure_ascii=False),
    }


def lambda_handler(event, context):
    path = (event.get("path") or "").lower()
    qs = event.get("queryStringParameters") or {}

    try:
        data, source = get_states_json()

        # /planes
        if path.endswith("/planes"):
            planes = to_plane_list(data, limit=30)
            return _resp(200, {"source": source, "count": len(planes), "planes": planes})

        # /track?icao24=xxxx
        if path.endswith("/track"):
            icao24 = (qs.get("icao24") or "").strip()
            item = find_by_icao24(data, icao24)
            if item is None:
                return _resp(404, {"error": "not found", "icao24": icao24, "source": source})
            return _resp(200, {"source": source, **item})

        # それ以外
        return _resp(404, {"error": "unknown path", "path": path})

    except Exception as e:
        return _resp(500, {"error": str(e)})
