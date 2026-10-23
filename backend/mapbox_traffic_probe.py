"""
Does Mapbox have traffic data for Karachi? Run this once before building on it.

    cd backend
    python mapbox_traffic_probe.py                # token from MAPBOX_ACCESS_TOKEN or .env
    python mapbox_traffic_probe.py --save         # also writes mapbox_probe_report.json

It checks three things on real Karachi corridors, with Dubai as a control city
that Mapbox lists as covered:

1. Live congestion: the driving-traffic route's per-segment congestion. Mostly
   "unknown" means Mapbox has no live feed for those roads.
2. Typical traffic: the same route departing tomorrow at 03:00 and at 08:30.
   Equal times mean there are no time-of-day speed profiles either.
3. Traffic tiles: the congestion lines the map overlay would draw.

It also asks the Valhalla server the app uses today, so you can see how far
the current (empty-road) ETAs are from Mapbox's. Uses about 20 Directions
requests and 5 tile requests, well inside Mapbox's free tier.
"""

import argparse
import gzip
import json
import math
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

MAPBOX = "https://api.mapbox.com"
VALHALLA = os.environ.get("MAP_ROUTING_URL", "https://valhalla1.openstreetmap.de").rstrip("/")
PKT = timezone(timedelta(hours=5))
GST = timezone(timedelta(hours=4))

# (name, city, timezone, [lng, lat] points in driving order)
CORRIDORS = [
    ("Saddar -> FAST NUCES", "Karachi", PKT, [(67.0295, 24.8586), (67.2646, 24.8569)]),
    ("Shahrah-e-Faisal: Karsaz -> FTC", "Karachi", PKT, [(67.0865, 24.8795), (67.0578, 24.8603)]),
    ("University Rd: Hasan Sq -> NIPA", "Karachi", PKT, [(67.0790, 24.9017), (67.0975, 24.9172)]),
    ("Control: Sheikh Zayed Rd, Dubai", "Dubai", GST, [(55.2744, 25.2048), (55.1390, 25.0805)]),
]
TILE_POINTS = [  # (label, lng, lat); zoom 13 tiles
    ("Saddar", 67.0295, 24.8586), ("Shahrah-e-Faisal", 67.0865, 24.8795),
    ("Gulshan / University Rd", 67.0900, 24.9100), ("FAST NUCES", 67.2646, 24.8569),
    ("Control: Dubai", 55.2744, 25.2048),
]
TILE_ZOOM = 13


def load_token(cli_token):
    if cli_token:
        return cli_token
    if os.environ.get("MAPBOX_ACCESS_TOKEN"):
        return os.environ["MAPBOX_ACCESS_TOKEN"]
    here = Path(__file__).resolve().parent
    for env in (here / ".env", here.parent / ".env"):
        if env.exists():
            for line in env.read_text(encoding="utf-8", errors="ignore").splitlines():
                key, _, value = line.partition("=")
                if key.strip() == "MAPBOX_ACCESS_TOKEN" and value.strip():
                    return value.strip().strip('"').strip("'")
    return None


def mapbox_get(url, token, params=None):
    """GET a Mapbox URL. Errors are reported without the token in them."""
    try:
        response = requests.get(url, params={**(params or {}), "access_token": token}, timeout=20)
    except requests.RequestException as exc:
        return None, f"network error ({type(exc).__name__})"
    if response.status_code != 200:
        try:
            message = response.json().get("message", "")
        except ValueError:
            message = response.text[:120]
        return None, f"HTTP {response.status_code} {message}".strip()
    return response, None


# ── Directions ──

def directions(token, points, profile, depart_at=None):
    path = ";".join(f"{lng},{lat}" for lng, lat in points)
    params = {"overview": "full", "geometries": "geojson"}
    if profile == "driving-traffic":
        params["annotations"] = "congestion,duration"
    if depart_at:
        params["depart_at"] = depart_at
    response, error = mapbox_get(f"{MAPBOX}/directions/v5/mapbox/{profile}/{path}", token, params)
    if error:
        return {"error": error}
    body = response.json()
    if body.get("code") != "Ok" or not body.get("routes"):
        return {"error": body.get("message") or body.get("code")}
    route = body["routes"][0]
    result = {"minutes": route["duration"] / 60, "km": route["distance"] / 1000}
    if route.get("duration_typical") is not None:
        result["typical_minutes"] = route["duration_typical"] / 60
    if profile == "driving-traffic":
        mix = {}
        for leg in route["legs"]:
            for level in leg.get("annotation", {}).get("congestion", []):
                mix[level] = mix.get(level, 0) + 1
        total = sum(mix.values()) or 1
        result["congestion_mix"] = {level: round(100 * n / total) for level, n in sorted(mix.items())}
        result["known_pct"] = round(100 * (total - mix.get("unknown", 0)) / total) if mix else 0
    return result


def valhalla_minutes(points):
    """The drive time the app's current router gives (bus costing, no traffic)."""
    body = {
        "locations": [{"lon": lng, "lat": lat, "type": "break"} for lng, lat in points],
        "costing": "bus", "directions_type": "none",
    }
    try:
        response = requests.post(f"{VALHALLA}/route", json=body, timeout=20)
        response.raise_for_status()
        return response.json()["trip"]["summary"]["time"] / 60
    except (requests.RequestException, ValueError, KeyError):
        return None


# ── Traffic tiles (tiny protobuf reader, so no extra install) ──

def _varint(buf, i):
    shift = result = 0
    while True:
        byte = buf[i]
        i += 1
        result |= (byte & 0x7F) << shift
        if byte < 0x80:
            return result, i
        shift += 7


def _fields(buf):
    i = 0
    while i < len(buf):
        key, i = _varint(buf, i)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, i = _varint(buf, i)
        elif wire == 2:
            length, i = _varint(buf, i)
            value, i = buf[i:i + length], i + length
        elif wire == 1:
            value, i = None, i + 8
        elif wire == 5:
            value, i = None, i + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        yield number, value


def _packed(buf):
    values, i = [], 0
    while i < len(buf):
        value, i = _varint(buf, i)
        values.append(value)
    return values


def congestion_in_tile(data):
    """{congestion level: feature count} across every layer of a vector tile."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    counts = {}
    for number, layer in _fields(data):
        if number != 3:
            continue
        keys, values, features = [], [], []
        for field, value in _fields(layer):
            if field == 3:
                keys.append(value.decode("utf-8", "replace"))
            elif field == 4:
                text = next((v for f, v in _fields(value) if f == 1), b"")
                values.append(text.decode("utf-8", "replace") if isinstance(text, bytes) else str(text))
            elif field == 2:
                features.append(value)
        for feature in features:
            tags = next((_packed(v) for f, v in _fields(feature) if f == 2), [])
            tag_map = {keys[k]: values[v] for k, v in zip(tags[::2], tags[1::2]) if k < len(keys) and v < len(values)}
            level = tag_map.get("congestion", "other")
            counts[level] = counts.get(level, 0) + 1
    return counts


def tile_xy(lng, lat, zoom):
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def traffic_tile(token, lng, lat):
    x, y = tile_xy(lng, lat, TILE_ZOOM)
    url = f"{MAPBOX}/v4/mapbox.mapbox-traffic-v1/{TILE_ZOOM}/{x}/{y}.vector.pbf"
    response, error = mapbox_get(url, token)
    if error:
        return {"error": error}
    try:
        return {"counts": congestion_in_tile(response.content), "bytes": len(response.content)}
    except (ValueError, IndexError, OSError) as exc:
        return {"error": f"could not read tile ({exc})"}


# ── Report ──

def fmt(value):
    return "-" if value is None else f"{value:.0f} min"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--token", help="Mapbox token (default: MAPBOX_ACCESS_TOKEN or .env)")
    parser.add_argument("--save", action="store_true", help="also write mapbox_probe_report.json")
    args = parser.parse_args()
    token = load_token(args.token)
    if not token:
        sys.exit("No Mapbox token. Set MAPBOX_ACCESS_TOKEN, add it to .env, or pass --token.")

    report = {"run_at": datetime.now(PKT).isoformat(timespec="minutes"), "corridors": [], "tiles": []}
    print(f"Mapbox traffic probe, {report['run_at']} Karachi time\n")

    for name, city, tz, points in CORRIDORS:
        tomorrow = (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")
        row = {
            "name": name, "city": city,
            "now": directions(token, points, "driving-traffic"),
            "night_0300": directions(token, points, "driving-traffic", f"{tomorrow}T03:00"),
            "rush_0830": directions(token, points, "driving-traffic", f"{tomorrow}T08:30"),
            "mapbox_driving": directions(token, points, "driving"),
            "valhalla_minutes": valhalla_minutes(points) if city == "Karachi" else None,
        }
        report["corridors"].append(row)
        now = row["now"]
        print(name)
        if "error" in now:
            print(f"  driving-traffic failed: {now['error']}\n")
            continue
        print(f"  App today (Valhalla, no traffic): {fmt(row['valhalla_minutes'])}")
        print(f"  Mapbox driving (no live traffic): {fmt(row['mapbox_driving'].get('minutes'))}")
        print(f"  Mapbox with traffic, now:         {fmt(now['minutes'])}  (typical for now: {fmt(now.get('typical_minutes'))})")
        print(f"  Tomorrow 03:00 vs 08:30:          {fmt(row['night_0300'].get('minutes'))} vs {fmt(row['rush_0830'].get('minutes'))}")
        print(f"  Segments with known congestion:   {now['known_pct']}%  {now['congestion_mix']}\n")
        time.sleep(1)  # the public Valhalla server asks for about one request a second

    print(f"Traffic tiles (zoom {TILE_ZOOM})")
    for label, lng, lat in TILE_POINTS:
        tile = traffic_tile(token, lng, lat)
        report["tiles"].append({"label": label, **tile})
        detail = tile.get("error") or (f"{sum(tile['counts'].values())} congestion lines {tile['counts']}" if tile["counts"] else "no traffic lines")
        print(f"  {label:<24} {detail}")

    print("\nVerdict for Karachi")
    karachi = [row for row in report["corridors"] if row["city"] == "Karachi" and "error" not in row["now"]]
    control = next((row for row in report["corridors"] if row["city"] == "Dubai" and "error" not in row["now"]), None)
    if not karachi:
        print("  No Karachi route came back. Check the token's scopes and the errors above.")
    else:
        known = sum(row["now"]["known_pct"] for row in karachi) / len(karachi)
        swings = [
            (row["rush_0830"]["minutes"] - row["night_0300"]["minutes"]) / row["night_0300"]["minutes"]
            for row in karachi if "minutes" in row["rush_0830"] and row["night_0300"].get("minutes")
        ]
        swing = max(swings) if swings else 0.0
        low = min(swings) if swings else 0.0
        # A real rush hour makes every corridor slower at 08:30 than at 03:00, and by more than rounding.
        pattern = "rush-hour pattern present" if swings and low > 0 and swing >= 0.10 else "no reliable rush-hour pattern"
        tiles_with_lines = sum(1 for tile in report["tiles"][:-1] if tile.get("counts"))
        print(f"  Live congestion on {known:.0f}% of route segments "
              f"({'usable' if known >= 50 else 'patchy' if known >= 15 else 'effectively none'}).")
        print(f"  Rush hour (08:30) vs night (03:00): {low * 100:+.0f}% to {swing * 100:+.0f}% across corridors ({pattern}).")
        print(f"  Traffic tiles with lines: {tiles_with_lines} of {len(TILE_POINTS) - 1}.")
        if control:
            print(f"  Dubai control: {control['now']['known_pct']}% known, so a low Karachi figure means "
                  f"{'missing Karachi data, not a broken setup' if control['now']['known_pct'] >= 50 else 'the setup itself may be wrong; check the control too'}.")
        report["verdict"] = {"karachi_known_pct": round(known), "karachi_rush_swing_pct": [round(low * 100), round(swing * 100)], "karachi_tiles_with_lines": tiles_with_lines}
        print("  Run it again at rush hour (8-9am or 5-7pm) too: a night run can look quieter than it is.")

    if args.save:
        out = Path(__file__).resolve().parent / "mapbox_probe_report.json"
        out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
