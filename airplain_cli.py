# airplain_cli.py
from __future__ import annotations

import time

from flight_core import get_plane_list, get_latest_state

INTERVAL_SEC = 20
MAX_ITERATIONS = 10


def choose_index(max_index: int) -> int:
    while True:
        s = input(f"追跡したい飛行機の番号を入力してください (0〜{max_index}): ")
        try:
            idx = int(s)
        except ValueError:
            print("数字を入力してください。")
            continue
        if 0 <= idx <= max_index:
            return idx
        print("範囲外の番号です。")


def print_candidates_cli(planes: list[dict]) -> None:
    print(f"\n現在飛行中（callsignあり）の機体候補（最大 {len(planes)} 件）:")
    print("-" * 70)
    for idx, p in enumerate(planes):
        print(
            f"[{idx:2d}] CallSign: {p['callsign']:8s}  "
            f"国籍: {p['origin_country']:<15s}  "
            f"現在地: {p['rough_location']:<20s}  "
            f"{'地上' if p['on_ground'] else '飛行中'}"
        )
    print("-" * 70)


def print_flight_detail_cli(state: dict) -> None:
    print("\n=== 現在状態（OpenSky） ===")
    print(f"  CallSign      : {state['callsign']}")
    print(f"  ICAO24        : {state['icao24']}")
    print(f"  国籍          : {state['origin_country']}")
    print(f"  緯度          : {state['latitude']}")
    print(f"  経度          : {state['longitude']}")
    print(f"  現在どのあたり？: {state['location_text']}")
    print(f"  高度(m)       : {state['geo_altitude'] if state['geo_altitude'] is not None else state['baro_altitude']}")
    print(f"  速度(m/s)     : {state['velocity']}")
    print(f"  last_contact  : {state['last_contact']}")
    print(f"  コメント      : {state['comment_text']}")
    print("========================================")


def track_flight_cli(callsign: str) -> None:
    print(f"\n=== {callsign} の追跡を開始します（{INTERVAL_SEC}秒おき, 最大{MAX_ITERATIONS}回）===")
    for i in range(1, MAX_ITERATIONS + 1):
        print(f"\n--- 更新 {i}/{MAX_ITERATIONS} ---")
        state = get_latest_state(callsign)
        if state is None:
            print("見つかりません（到着済み・カバー外など）。")
        else:
            print_flight_detail_cli(state)

        if i < MAX_ITERATIONS:
            time.sleep(INTERVAL_SEC)


def main() -> None:
    planes = get_plane_list()
    if not planes:
        print("一覧を取得できませんでした。")
        return

    print_candidates_cli(planes)
    idx = choose_index(len(planes) - 1)
    selected = planes[idx]
    callsign = selected["callsign"]
    print(f"\n選択された機体: CallSign={callsign}, 国籍={selected['origin_country']}")
    track_flight_cli(callsign)


if __name__ == "__main__":
    main()
