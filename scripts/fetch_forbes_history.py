"""Download every Forbes Global 2000 edition that still carries its own ten-year
financial history, so the time series can run back to fiscal 2001.

Usage: python scripts/fetch_forbes_history.py [first_year] [last_year] [outdir]
Default: 2011 2026 data/raw_history

Why this works
--------------
Each edition of the list ships ten years of revenue, profit and headcount for
the firms on that edition. The 2026 edition covers fiscal 2016-2025; the 2020
edition covers 2010-2019; the 2011 edition reaches back to 2001. Stitching the
editions together gives one long panel.

The join key is the Forbes company id inside `naturalId`
("fred/companies/F2K/2026/15317"). The id is stable across renames, so
Facebook (2011-2021) joins to Meta Platforms (2022+) and Royal Dutch Shell
joins to Shell Plc without any alias table.

The list started in 2011, so 2010 is the first year the API answers with a
full edition; editions before that are not useful.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")
URL = "https://www.forbes.com/forbesapi/org/global2000/{year}/position/true.json?limit=2000"


def main() -> None:
    first = int(sys.argv[1]) if len(sys.argv) > 1 else 2011
    last = int(sys.argv[2]) if len(sys.argv) > 2 else 2026
    outdir = Path(sys.argv[3] if len(sys.argv) > 3 else "data/raw_history")
    outdir.mkdir(parents=True, exist_ok=True)

    for year in range(first, last + 1):
        out = outdir / f"global2000_{year}_api.json"
        if out.exists() and out.stat().st_size > 1000:
            print(f"{year}: cached ({out.stat().st_size / 1e6:.1f} MB)")
            continue
        for attempt in range(3):
            try:
                r = requests.get(URL.format(year=year), headers={"User-Agent": UA}, timeout=180)
                r.raise_for_status()
                rows = r.json()["organizationList"]["organizationsLists"]
                if not rows:
                    print(f"{year}: no edition")
                    break
                out.write_bytes(r.content)
                print(f"{year}: {len(rows)} rows ({out.stat().st_size / 1e6:.1f} MB)")
                break
            except Exception as e:
                print(f"{year}: attempt {attempt + 1} failed: {e}")
                time.sleep(5)
        time.sleep(1)


if __name__ == "__main__":
    main()
