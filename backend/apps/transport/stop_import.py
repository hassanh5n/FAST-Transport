"""Bulk stop import from a CSV or JSON file.

Only columns that exist on the Stop table are used; anything else is ignored
and reported. A row is skipped when a stop with the same name (case/space
insensitive) or within DUPLICATE_RADIUS_M of it already exists, either in the
database or earlier in the same file. Addresses are filled in afterwards by the
admin UI (one reverse-geocode per second), so new stops start with "N/A".
"""
import csv
import io
import json
import math
from decimal import Decimal

from django.db import transaction

from .models import Stop

MAX_ROWS = 1000
DUPLICATE_RADIUS_M = 25
ALLOWED_COLUMNS = {
    "name", "latitude", "longitude", "address",
    "is_active", "location_accuracy_m", "provider_place_id",
}
FALSE_WORDS = {"0", "false", "no", "n", "inactive"}


def _norm_name(name):
    return " ".join(str(name).lower().split())


def _distance_m(lat1, lng1, lat2, lng2):
    # ponytail: equirectangular approximation, accurate to well under 1 m at a 25 m radius.
    rad = math.pi / 180
    x = (lng2 - lng1) * rad * math.cos((lat1 + lat2) * rad / 2)
    y = (lat2 - lat1) * rad
    return 6371000 * math.hypot(x, y)


def parse_file(filename, raw):
    """Return (rows, first_row_number). Raises ValueError with a readable message."""
    text = raw.decode("utf-8-sig")
    if filename.lower().endswith(".json"):
        data = json.loads(text)
        if isinstance(data, dict):
            data = data.get("stops")
        if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
            raise ValueError('JSON must be a list of stops, or {"stops": [...]}.')
        return data, 1
    try:
        return list(csv.DictReader(io.StringIO(text))), 2  # line 1 is the header
    except csv.Error as exc:
        raise ValueError(f"Could not read the CSV file: {exc}")


def _clean_row(raw, ignored):
    row = {}
    for key, value in raw.items():
        key = str(key or "").strip().lower()
        if key in ALLOWED_COLUMNS:
            row[key] = value.strip() if isinstance(value, str) else value
        elif key:
            ignored.add(key)
    return row


def _build_stop(row):
    """Return (Stop, None) or (None, reason) for a non-blank row."""
    name = str(row.get("name") or "").strip()
    if not name:
        return None, "Name is missing."
    if len(name) > 100:
        return None, "Name is longer than 100 characters."
    try:
        lat = float(row.get("latitude"))
        lng = float(row.get("longitude"))
    except (TypeError, ValueError):
        return None, "Latitude/longitude is missing or not a number."
    if not (math.isfinite(lat) and math.isfinite(lng)) or not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None, "Latitude/longitude is out of range."
    if lat == 0 and lng == 0:
        return None, "0,0 is not a valid stop location."

    accuracy = row.get("location_accuracy_m")
    if accuracy in (None, ""):
        accuracy = None
    else:
        try:
            accuracy = int(float(accuracy))
            if accuracy < 0:
                raise ValueError
        except (TypeError, ValueError):
            return None, "location_accuracy_m must be a positive whole number."

    active = row.get("is_active")
    is_active = True if active in (None, "") else str(active).strip().lower() not in FALSE_WORDS

    return Stop(
        name=name,
        latitude=Decimal(str(round(lat, 6))),
        longitude=Decimal(str(round(lng, 6))),
        address=str(row.get("address") or "").strip() or "N/A",
        is_active=is_active,
        location_source="import",
        location_accuracy_m=accuracy,
        provider_place_id=str(row.get("provider_place_id") or "").strip()[:255],
    ), None


def import_stops(rows, first_row=1):
    """Create every valid, non-duplicate stop. Returns a report dict."""
    if len(rows) > MAX_ROWS:
        raise ValueError(f"A file can have at most {MAX_ROWS} rows (this one has {len(rows)}).")

    # Known stops (database first, then rows accepted from this file) for duplicate checks.
    known_names = {}
    known_points = []
    for stop in Stop.objects.only("name", "latitude", "longitude"):
        label = f'existing stop "{stop.name}"'
        known_names.setdefault(_norm_name(stop.name), label)
        known_points.append((float(stop.latitude), float(stop.longitude), label))

    ignored, to_create, skipped, invalid = set(), [], [], []
    for index, raw in enumerate(rows):
        row_no = first_row + index
        row = _clean_row(raw, ignored)
        if all(value in (None, "") for value in row.values()):
            continue  # blank row
        stop, reason = _build_stop(row)
        if stop is None:
            invalid.append({"row": row_no, "name": str(row.get("name") or ""), "reason": reason})
            continue

        lat, lng = float(stop.latitude), float(stop.longitude)
        name_key = _norm_name(stop.name)
        if name_key in known_names:
            reason = f"Same name as {known_names[name_key]}."
        else:
            near = next(
                ((d, label) for plat, plng, label in known_points
                 if (d := _distance_m(lat, lng, plat, plng)) <= DUPLICATE_RADIUS_M),
                None,
            )
            reason = f"Only {near[0]:.0f} m from {near[1]}." if near else None
        if reason:
            skipped.append({"row": row_no, "name": stop.name, "reason": reason})
            continue

        label = f'"{stop.name}" (row {row_no} of this file)'
        known_names[name_key] = label
        known_points.append((lat, lng, label))
        to_create.append(stop)

    with transaction.atomic():
        created = Stop.objects.bulk_create(to_create)

    return {
        "created": [
            {"id": s.id, "name": s.name, "address": s.address,
             "latitude": float(s.latitude), "longitude": float(s.longitude)}
            for s in created
        ],
        "skipped": skipped,
        "invalid": invalid,
        "ignored_columns": sorted(ignored),
    }
