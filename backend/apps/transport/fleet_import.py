"""Bulk bus and driver import from a CSV file.

Each row is checked on its own. Valid rows are created, the rest are reported
back with their row number and a reason, so one bad line never blocks the file.

Duplicates are skipped, whether they clash with the database or with an earlier
row of the same file:
* bus:    same bus number (case, spaces and dashes ignored), or same GPS tracker token
* driver: same CNIC (digits only), or same license number (case, spaces and dashes ignored)

Driver logins are not imported: a CSV of passwords is a leak waiting to happen.
Admins add a login afterwards with Edit on the Drivers page.
"""
import csv
import io
import re

from django.db import transaction

from .models import Bus, Contractor, Driver

MAX_ROWS = 1000
MAX_CAPACITY = 100
FALSE_WORDS = {"0", "false", "no", "n", "inactive", "unavailable"}
BLANK_WORDS = {"", "n/a", "na", "-", "none"}

BUS_COLUMNS = ["bus_number", "capacity", "model", "tracker_token", "contractor", "is_active"]
DRIVER_COLUMNS = ["name", "cnic", "license_no", "phone", "address", "contractor", "is_available"]


def parse_csv(raw):
    """Rows of a CSV upload as dicts. Line 1 is the header, so data starts at row 2."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("The file is not UTF-8 text. Save it as 'CSV UTF-8' and try again.")
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except csv.Error as exc:
        raise ValueError(f"Could not read the CSV file: {exc}")
    if not reader.fieldnames:
        raise ValueError("The file is empty.")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"A file can have at most {MAX_ROWS} rows (this one has {len(rows)}).")
    return rows


def _alnum(value):
    """'ABC-123', 'abc 123' and 'ABC123' are the same bus number / license."""
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())


def _blank(value):
    return str(value or "").strip().lower() in BLANK_WORDS


def _clean_rows(rows, allowed):
    """Lower-case the headers, keep the allowed columns, report the rest."""
    ignored, cleaned = set(), []
    for raw in rows:
        row = {}
        for key, value in raw.items():
            key = str(key or "").strip().lower()
            if key in allowed:
                row[key] = value.strip() if isinstance(value, str) else ""
            elif key:
                ignored.add(key)
        cleaned.append(row)
    return cleaned, sorted(ignored)


def _contractor_lookup():
    contractors = {c.name.strip().lower(): c for c in Contractor.objects.all()}
    names = ", ".join(sorted(c.name for c in contractors.values())) or "none set up yet"

    def find(value):
        """(contractor or None, error or None). Blank means no contractor."""
        if _blank(value):
            return None, None
        found = contractors.get(str(value).strip().lower())
        if found is None:
            return None, f'Unknown contractor "{value}". Use one of: {names}.'
        return found, None

    return find


def _flag(value, default=True):
    return default if _blank(value) else str(value).strip().lower() not in FALSE_WORDS


def _report(created, skipped, invalid, ignored):
    return {"created": created, "skipped": skipped, "invalid": invalid, "ignored_columns": ignored}


# ── Buses ────────────────────────────────────────────────────────────────────

def import_buses(rows):
    rows, ignored = _clean_rows(rows, set(BUS_COLUMNS))
    find_contractor = _contractor_lookup()

    numbers, tokens = {}, {}
    for bus in Bus.objects.only("bus_number", "tracker_token"):
        label = f'existing bus "{bus.bus_number}"'
        numbers.setdefault(_alnum(bus.bus_number), label)
        if not _blank(bus.tracker_token):
            tokens.setdefault(bus.tracker_token.strip().lower(), label)

    to_create, skipped, invalid = [], [], []
    for row_no, row in enumerate(rows, start=2):
        if all(_blank(v) for v in row.values()):
            continue
        number = row.get("bus_number", "")
        entry = {"row": row_no, "name": number}

        if _blank(number):
            invalid.append({**entry, "reason": "Bus number is missing."})
            continue
        if len(number) > 20:
            invalid.append({**entry, "reason": "Bus number is longer than 20 characters."})
            continue
        try:
            capacity = int(float(row.get("capacity", "")))
        except ValueError:
            invalid.append({**entry, "reason": "Capacity is missing or not a number."})
            continue
        if not 1 <= capacity <= MAX_CAPACITY:
            invalid.append({**entry, "reason": f"Capacity must be between 1 and {MAX_CAPACITY}."})
            continue
        contractor, error = find_contractor(row.get("contractor"))
        if error:
            invalid.append({**entry, "reason": error})
            continue
        token = "" if _blank(row.get("tracker_token")) else row["tracker_token"][:50]

        key = _alnum(number)
        if key in numbers:
            skipped.append({**entry, "reason": f"Same bus number as {numbers[key]}."})
            continue
        if token and token.lower() in tokens:
            skipped.append({**entry, "reason": f"Same GPS tracker token as {tokens[token.lower()]}."})
            continue

        label = f'"{number}" (row {row_no} of this file)'
        numbers[key] = label
        if token:
            tokens[token.lower()] = label
        to_create.append(Bus(
            bus_number=number,
            capacity=capacity,
            model=(row.get("model") or "N/A")[:100],
            tracker_token=token or None,
            contractor=contractor,
            is_active=_flag(row.get("is_active")),
        ))

    with transaction.atomic():
        created = Bus.objects.bulk_create(to_create)
    return _report(
        [{"id": b.id, "name": b.bus_number} for b in created], skipped, invalid, ignored,
    )


# ── Drivers ──────────────────────────────────────────────────────────────────

def _format_cnic(value):
    """'4210112345671' or '42101-1234567-1' -> ('42101-1234567-1', None)."""
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) != 13:
        return None, "CNIC must have 13 digits (e.g. 42101-1234567-1)."
    return f"{digits[:5]}-{digits[5:12]}-{digits[12]}", None


def import_drivers(rows):
    rows, ignored = _clean_rows(rows, set(DRIVER_COLUMNS))
    find_contractor = _contractor_lookup()

    cnics, licenses = {}, {}
    for driver in Driver.objects.only("name", "cnic", "license_no"):
        label = f'existing driver "{driver.name}"'
        digits = re.sub(r"\D", "", driver.cnic or "")
        if digits:
            cnics.setdefault(digits, label)
        if not _blank(driver.license_no):
            licenses.setdefault(_alnum(driver.license_no), label)

    to_create, skipped, invalid = [], [], []
    for row_no, row in enumerate(rows, start=2):
        if all(_blank(v) for v in row.values()):
            continue
        name = row.get("name", "")
        entry = {"row": row_no, "name": name}

        if _blank(name):
            invalid.append({**entry, "reason": "Name is missing."})
            continue
        if len(name) > 150:
            invalid.append({**entry, "reason": "Name is longer than 150 characters."})
            continue
        cnic, error = _format_cnic(row.get("cnic"))
        if error:
            invalid.append({**entry, "reason": error})
            continue
        license_no = "" if _blank(row.get("license_no")) else row["license_no"]
        if len(license_no) > 30:
            invalid.append({**entry, "reason": "License number is longer than 30 characters."})
            continue
        contractor, error = find_contractor(row.get("contractor"))
        if error:
            invalid.append({**entry, "reason": error})
            continue

        cnic_key, license_key = re.sub(r"\D", "", cnic), _alnum(license_no)
        if cnic_key in cnics:
            skipped.append({**entry, "reason": f"Same CNIC as {cnics[cnic_key]}."})
            continue
        if license_key and license_key in licenses:
            skipped.append({**entry, "reason": f"Same license number as {licenses[license_key]}."})
            continue

        label = f'"{name}" (row {row_no} of this file)'
        cnics[cnic_key] = label
        if license_key:
            licenses[license_key] = label
        to_create.append(Driver(
            name=name,
            cnic=cnic,
            license_no=license_no or "N/A",
            phone=(row.get("phone") or "N/A")[:20],
            address=row.get("address") or "N/A",
            contractor=contractor,
            is_available=_flag(row.get("is_available")),
        ))

    with transaction.atomic():
        created = Driver.objects.bulk_create(to_create)
    return _report(
        [{"id": d.id, "name": d.name} for d in created], skipped, invalid, ignored,
    )
