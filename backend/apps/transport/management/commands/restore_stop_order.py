"""
Put each route's stops back in the order of a source timetable file.

    python manage.py restore_stop_order "Claude outputs/fast_karachi_fall2026.json"          # show changes
    python manage.py restore_stop_order "Claude outputs/fast_karachi_fall2026.json" --apply  # save them

The file is the term's timetable: {"routes": [{"operator", "code", "stops": [{"order", "name"}]}]}.
A route matches by "<operator> <code>" (e.g. "Jadoon R-4"), a stop by its name
(case, spaces and punctuation ignored). Stops the file does not list keep their
current relative order after the listed ones; the campus stop stays last.
Changed routes lose their saved road line, which the background builder redraws.
"""

import json
import re

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.transport.models import Route, RouteStop
from apps.transport.road_lines import schedule_road_line_build


def _key(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


class Command(BaseCommand):
    help = "Restore route stop order from a timetable JSON file (dry run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--apply", action="store_true", help="Save the new order (default: only show it).")

    def handle(self, path, apply=False, **options):
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            raise CommandError(f"Cannot read {path}: {exc}")

        wanted = {}
        for route in data.get("routes", []):
            name = f'{route.get("operator", "")} {route.get("code", "")}'.strip()
            ordered = sorted(route.get("stops", []), key=lambda stop: stop.get("order", 0))
            wanted[_key(name)] = [_key(stop["name"]) for stop in ordered]

        changed = 0
        with transaction.atomic():
            for route in Route.objects.order_by("name"):
                source = wanted.get(_key(route.name))
                if source is None:
                    continue
                rows = list(RouteStop.objects.filter(route=route).select_related("stop").order_by("stop_order"))
                campus = [row for row in rows if row.stop.is_campus]
                pickups = [row for row in rows if not row.stop.is_campus]
                rank = {key: index for index, key in enumerate(source)}
                listed = sorted((row for row in pickups if _key(row.stop.name) in rank), key=lambda row: rank[_key(row.stop.name)])
                unlisted = [row for row in pickups if _key(row.stop.name) not in rank]
                new = listed + unlisted + campus
                if [row.id for row in new] == [row.id for row in rows]:
                    continue
                changed += 1
                self.stdout.write(f"\n{route.name}")
                self.stdout.write("  now: " + " > ".join(row.stop.name for row in rows))
                self.stdout.write("  new: " + " > ".join(row.stop.name for row in new))
                if unlisted:
                    self.stdout.write("  not in file (kept after listed stops): " + ", ".join(row.stop.name for row in unlisted))
                if not apply:
                    continue
                # Two steps: stop_order is unique per route.
                for offset, row in enumerate(new, start=1):
                    row.stop_order = 10000 + offset
                RouteStop.objects.bulk_update(new, ["stop_order"])
                for offset, row in enumerate(new, start=1):
                    row.stop_order = offset
                RouteStop.objects.bulk_update(new, ["stop_order"])
                Route.objects.filter(pk=route.pk).update(geometry=None, geometry_updated_at=None)
            if apply and changed:
                schedule_road_line_build()

        verb = "Reordered" if apply else "Would reorder"
        self.stdout.write(self.style.SUCCESS(f"\n{verb} {changed} route(s)."))
        if changed and not apply:
            self.stdout.write("Run again with --apply to save.")
