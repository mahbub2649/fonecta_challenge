#!/usr/bin/env python3
"""Build connect/views.json from analytics_daily.parquet, so the app itself needs no pandas.

    pip install pandas pyarrow && python3 tools/build_views.py

Holds each business's average daily search views over the last 90 days, and its views on each day of the previous
season (7 Nov 2025 to 6 Jan 2026). Only data up to the 3 Nov 2026 snapshot is used.
"""
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("CONNECT_DATA_DIR", ROOT.parent / "fonecta_data" / "FONECTA_CONNECT_SUGGESTS_2026"))


def main() -> None:
    frame = pd.read_parquet(DATA / "data" / "analytics_daily.parquet", columns=["date", "entity_id", "GOOGLE_SEARCH_VIEWS"])
    frame["date"] = frame["date"].astype(str).str[:10]
    recent = frame[frame["date"] >= "2026-08-05"].groupby("entity_id")["GOOGLE_SEARCH_VIEWS"].mean().round(1)
    season = frame[(frame["date"] >= "2025-11-07") & (frame["date"] <= "2026-01-06")]
    by_date = {}
    for eid, group in season.groupby("entity_id"):
        by_date[eid] = {d: int(v) for d, v in zip(group["date"], group["GOOGLE_SEARCH_VIEWS"]) if v == v}
    out = ROOT / "connect" / "views.json"
    out.write_text(json.dumps({"average": recent.to_dict(), "by_date": by_date}, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1e6:.1f} MB): {len(recent)} averages, {len(by_date)} businesses by date",
          file=sys.stderr)


if __name__ == "__main__":
    main()
