# src/app.py
import json
from urllib.request import urlopen, Request
from urllib.parse import urlencode

OPENSKY_STATES_URL = "https://opensky-network.org/api/states/all"
MAX_LIST = 30

# ---- ざっくりエリア判定（最小） ----
REGION_BOXES = [
    ("日本付近", 20.0, 50.0, 120.0, 150.0),
    ("韓国付近", 33.0, 39.5, 124.0, 132.0),
    ("中国東部付近", 20.0, 42.0, 105.0, 125.0),
    ("ドイツ付近", 47.0, 56.0, 5.0, 16.0),
    ("フランス付近", 42.0, 51.5, -5.0, 8.0),
    ("イギリス付近", 49.0, 61.0, -10.0, 2.0),
    ("ヨーロッパ西部付近", 35.0, 70.0, -10.0, 30.0),
    ("北米西海岸付近", 30.0, 55.0, -135.0, -110.0),
    ("北米中部付近", 30.0, 55.0, -110.0, -85.0),
    ("北米東海岸付近", 30.0, 50.0, -85.0, -60.0),
    ("中東付近", 15.0, 40.0, 30.0, 60.0),
    ("東南アジア付近", -10.0, 25.0, 95.0, 130.0),
    ("オーストラリア付近", -45.0, -10.0, 110.0, 155.0),
]

def rough_location(lat, lon, origin_country=None):
    if lat is None or lon is None:
        return "位置不明"
    try:
        lat = float(lat); lon = float(lon)
    except Exception:
        return "位置不明"

    for name, lat_min, lat_max, lon_min, lon_max in REGION_BOXES:
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return name

    if origin_country:
        return f"{origin_country} 付近"
    return f"緯度 {lat:.1f}°, 経度 {lon:.1f}° 付近"

def make_simple_comment(alt_m, vel, vert_rate):
    if alt_m is None:
        return "高度情報がないため、詳しい景色は推定できません。"
    try:
        alt_ft = float(alt_m) * 3.28084
    except Exception:
        return "高度情報がないため、詳しい景色は推定できません。"

    if alt_ft < 1000:
        return "滑走路付近か、離着陸の直前・直後の高度かもしれません。"
    elif alt_ft < 10000:
        return "まだ上昇中で、地形や街並みがかなりはっきり見えていそうです。"
    elif alt_ft < 25000:
        return "雲の合間から、地上の街や山が時々見えるような高度を飛行中だと思われます。"
    else:
        return "雲の上を巡航中で、窓の外は青い空と雲のじゅうたんが広がっていそうです。"

def fetch_opensky_states_all():
    req = Request(OPENSKY_STATES_URL, headers={"User-Agent": "air-traffic-tracker/0.1"})
    with urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))

def response(status, body_obj):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json; charset=utf-8",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body_obj, ensure_ascii=False),
    }

def lambda_handler(event, context):
    path = event.get("rawPath") or event.get("path") or "/"
    q = event.get("queryStringParameters") or {}
    # /planes : 候補一覧
    if path == "/" or path == "/planes":
        try:
            data = fetch_opensky_states_all()
            states = data.get("states") or []
            result = []
            for s in states:
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
                    "on_ground": bool(s[8]),
                    "rough_location": rough_location(s[6], s[5], origin_country=s[2]),
                })
                if len(result) >= MAX_LIST:
                    break
            return response(200, result)
        except Exception as e:
            return response(500, {"message": "Internal server error", "error": str(e)})

    # /track?icao24=xxxx : 1機だけ詳細
    if path == "/track":
        icao24 = (q.get("icao24") or "").strip().lower()
        if not icao24:
            return response(400, {"error": "icao24 is required. e.g. /track?icao24=4952ca"})
        try:
            data = fetch_opensky_states_all()
            states = data.get("states") or []
            for s in states:
                if (s[0] or "").lower() != icao24:
                    continue

                callsign = (s[1] or "").strip()
                origin = s[2]
                lon = s[5]; lat = s[6]
                baro_alt = s[7]
                on_ground = bool(s[8])
                vel = s[9]
                heading = s[10]
                vert_rate = s[11]
                geo_alt = s[13]
                alt_use = geo_alt if geo_alt is not None else baro_alt

                return response(200, {
                    "icao24": s[0],
                    "callsign": callsign,
                    "origin_country": origin,
                    "longitude": lon,
                    "latitude": lat,
                    "baro_altitude": baro_alt,
                    "geo_altitude": geo_alt,
                    "velocity": vel,
                    "heading": heading,
                    "vertical_rate": vert_rate,
                    "on_ground": on_ground,
                    "time_position": s[3],
                    "last_contact": s[4],
                    "location_text": rough_location(lat, lon, origin_country=origin),
                    "comment_text": make_simple_comment(alt_use, vel, vert_rate),
                })

            return response(404, {"error": "not found", "icao24": icao24})
        except Exception as e:
            return response(500, {"message": "Internal server error", "error": str(e)})

    return response(404, {"error": "not found", "path": path})
