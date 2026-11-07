#!/usr/bin/env python3
"""Replace the public holidays in the package's calendar with live data from Nager.Date, and report what we learned.

    python3 tools/live_calendar.py

Writes connect/live_calendar.csv, which the app reads instead of data/calendar_special_days.csv. Nager only has public
holidays, so eves, in-between days, observances and commercial days stay from the package. If this can't reach the API,
the last saved file stays as it is. The app falls back to the package's file if there's no saved one.
"""
import csv
import json
import sys
import urllib.request
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from connect import config  # noqa: E402

API = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country}"
OUT = ROOT / "connect" / "live_calendar.csv"
LAST_DAY = "2027-01-06"
SEASON = ("2026-11-07", LAST_DAY)


def fetch() -> dict:
    live = {}
    for country in ("FI", "SE", "NO"):
        for year in (2024, 2025, 2026, 2027):
            request = urllib.request.Request(API.format(year=year, country=country), headers={"User-Agent": "connect-suggests-hackathon/1.0"})
            with urllib.request.urlopen(request, timeout=30) as response:
                for holiday in json.loads(response.read().decode()):
                    if holiday["date"] <= LAST_DAY:
                        live[(country, holiday["date"])] = holiday
    return live


def main() -> None:
    with (config.DATA_DIR / "data" / "calendar_special_days.csv").open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    package = {(r["country"], r["date"]): r for r in rows}
    live = fetch()
    fetched = date.today().isoformat()

    only_live = sorted(k for k in live if k not in package)
    official = {k for k, r in package.items() if r["official_public_holiday"] == "1"}
    missing = sorted(official - set(live))
    renamed = [k for k in live if k in package and package[k]["name_local"].lower() != live[k]["localName"].lower()]
    disagree = sorted(k for k in live if k in package and k not in official)
    season = [k for k in package if SEASON[0] <= k[1] <= SEASON[1]]
    gaps = {}
    for key in season:
        if key not in live:
            gaps[package[key]["day_type"]] = gaps.get(package[key]["day_type"], 0) + 1

    print(f"Live public-holiday dates to {LAST_DAY}: {len(live)}")
    print(f"Dates only in the live source: {len(only_live)} {only_live[:6]}")
    print(f"Package's official holidays missing from the live source: {len(missing)} {missing[:6]}")
    print(f"Names that differ: {len(renamed)}, for example {[(package[k]['name_local'], live[k]['localName']) for k in sorted(renamed)[:3]]}")
    print(f"Live says public, package says not official: {len(disagree)}, for example {[package[k]['name_local'] for k in disagree[:3]]}")
    print(f"This season's special-day rows: {len(season)}, covered by the live source: {sum(k in live for k in season)}, not covered: {gaps}")
    if only_live:
        sys.exit("The live source has dates we have no day key for. Keeping the saved file.")

    with OUT.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]) + ["source"])
        writer.writeheader()
        for row in rows:
            key = (row["country"], row["date"])
            if key in live:
                writer.writerow({**row, "name_local": live[key]["localName"], "source": f"Nager.Date {fetched}"})
            else:
                writer.writerow({**row, "source": "challenge package"})
    print(f"Wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
