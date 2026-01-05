# src/app.py
import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

OPENSKY_URL = "https://opensky-network.org/api/states/all"

BASE_DIR = Path(__file__).resolve().parent
SNAPSHOT_PATH = BASE_DIR / "opensky_states_snapshot.json"
INDEX_PATH = BASE_DIR / "static" / "index.html"

# JSON用
def _resp_json(status: int, obj) -> dict:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Cache-Control": "no-store",
            "Access-Control-Allow-Origin": "https://d1nej4xkg5qji4.cloudfront.net",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type"
        },
        "body": json.dumps(obj, ensure_ascii=False),
    }

# HTML用
def _resp_html(status: int, html: str) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "text/html; charset=utf-8", 
                    "Cache-Control": "no-store",
                    "Access-Control-Allow-Origin": "https://d1nej4xkg5qji4.cloudfront.net",
                    "Access-Control-Allow-Methods": "GET,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type"
        },
        "body": html,
    }

# snapshotからデータ取得
def load_snapshot() -> dict:
    if SNAPSHOT_PATH.exists():
        return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    return {"time": None, "states": []}

# OpenSkyからデータ取得
def fetch_opensky_or_snapshot(timeout_sec: int = 12) -> tuple[dict, str]:
    # 戻り値: (data, source)  source = "live" or "snapshot"

    if os.getenv("FORCE_SNAPSHOT") == "1":
        return load_snapshot(), "snapshot"

    try:
        req = Request(OPENSKY_URL, headers={"User-Agent": "air-traffic-tracker/0.1"})
        with urlopen(req, timeout=timeout_sec) as r:
            raw = r.read().decode("utf-8")
            data = json.loads(raw)
            return data, "live"
        
    except Exception as e:
        print(f"[WARN] OpenSky failed -> snapshot fallback: {type(e).__name__}: {e}")
        return load_snapshot(), "snapshot"

# states配列をlistに変換
def to_plane_list(data: dict, limit: int = 200) -> list[dict]:
    states = data.get("states") or []
    result = []
    for s in states:
        # [icao24, callsign, origin_country, time_position, last_contact, lon, lat, baro_altitude, on_ground, velocity, heading, vertical_rate, ...]
        callsign = (s[1] or "").strip()
        if not callsign:
            continue

        result.append(
            {
                "icao24": s[0],
                "callsign": callsign,
                "origin_country": s[2],
                "time_position": s[3],
                "last_contact": s[4],
                "longitude": s[5],
                "latitude": s[6],
                "baro_altitude": s[7],
                "geo_altitude": s[13],
                "on_ground": bool(s[8]) if s[8] is not None else None,
                "velocity": s[9],
                "heading": s[10],
                "vertical_rate": s[11],
            }
        )
        if len(result) >= limit:
            break
    return result


def find_by_icao24(data: dict, icao24: str) -> dict | None:
    target = (icao24 or "").strip().lower()
    if not target:
        return None

    states = data.get("states") or []
    for s in states:
        if (s[0] or "").lower() == target:
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
                "on_ground": bool(s[8]) if s[8] is not None else None,
                "velocity": s[9],
                "heading": s[10],
                "vertical_rate": s[11],
            }
    return None


def lambda_handler(event, context):
    method = (event.get("requestContext", {}).get("http", {}).get("method")
              or event.get("httpMethod") or "GET")

    # CORS preflight
    if method == "OPTIONS":
        return {
            "statusCode": 204,
            "headers": {
                "Access-Control-Allow-Origin": "https://d1nej4xkg5qji4.cloudfront.net",
                "Access-Control-Allow-Methods": "GET,OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type",
                "Cache-Control": "no-store",
            },
            "body": "",
        }
    try:
        path = event.get("path") or event.get("rawPath") or "/"
        qs = event.get("queryStringParameters") or {}

        # ルートはUI（static/index.html）を返す
        if path == "/":
            if INDEX_PATH.exists():
                return _resp_html(200, INDEX_PATH.read_text(encoding="utf-8"))
            return _resp_html(200, "<h1>Flight Tracker</h1><p>static/index.html not found</p>")

        # planes / track は OpenSky or snapshot
        data, source = fetch_opensky_or_snapshot()

        if path == "/planes":
            planes = to_plane_list(data, limit=200)
            return _resp_json(200, {"source": source, "count": len(planes), "planes": planes})

        if path == "/track":
            icao24 = qs.get("icao24")
            hit = find_by_icao24(data, icao24)
            if not hit:
                return _resp_json(404, {"source": source, "error": "not found", "icao24": icao24})
            return _resp_json(200, {"source": source, **hit})

        return _resp_json(404, {"error": "not found", "path": path})

    except Exception as e:
        # Internal server error
        return _resp_json(500, {"error": str(e), "event_path": (event.get("path") or event.get("rawPath"))})
