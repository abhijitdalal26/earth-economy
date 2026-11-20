"""Stitch every Forbes Global 2000 edition into one long history panel.

Usage: python scripts/build_history_panel.py [rawdir] [outcsv]
Default: data/raw_history  data/global2000_2026_history_panel.csv

Input : data/raw_history/global2000_<year>_api.json for every edition fetched
Output: data/global2000_2026_history_panel.csv
        long format: one row per company, metric and fiscal year

The panel
---------
Only the 2,000 companies on the 2026 list are kept, so every line in the
"one picture" chart is a firm that survived to 2026. Their history is read
back out of whichever editions they appeared on:

    fiscal year = edition year - 1 - index in the edition's list

When two editions report the same fiscal year for the same company, the
newest edition wins: Forbes restates old figures (currency, restatements,
fiscal-year shifts) and the most recent edition is the one that matches the
figures the rest of this project uses. `source_edition` records where each
number came from, so any value can be traced back to the edition it was read
from.

Known limits
------------
- Forbes restates between editions. A year read from an older edition can
  differ from the same year in a newer one (median gap around 7% for 2015).
- A company only has history back to the first edition it appeared on, and
  only if Forbes gave it figures for the years before that.
- The list itself starts in 2011, so nothing before fiscal 2001 exists.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/raw_history"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data/global2000_2026_history_panel.csv"

FIRST_EDITION = 2011
LIST_YEAR = 2026
EARLIEST_YEAR = 2001
LATEST_YEAR = 2025

FIELDS = {
    "revenue": "revenueList",
    "profits": "profitList",
    "employees": "employeesList",
}
UNITS = {"revenue": "USD millions", "profits": "USD millions", "employees": "employees"}


def company_id(row: dict) -> str | None:
    """The stable Forbes company id, e.g. fred/companies/F2K/2026/15317 -> 15317."""
    tail = (row.get("naturalId") or "").rsplit("/", 1)[-1]
    return tail if tail.isdigit() else None


def load_edition(year: int) -> list[dict]:
    path = RAW / f"global2000_{year}_api.json"
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload["organizationList"]["organizationsLists"]


def main() -> None:
    editions = {}
    for year in range(FIRST_EDITION, LIST_YEAR + 1):
        rows = load_edition(year)
        if rows:
            editions[year] = rows
    if not editions:
        raise SystemExit(f"no editions found in {RAW}")
    print(f"editions: {sorted(editions)}")

    current = editions[LIST_YEAR]
    names = {company_id(r): r for r in current}
    universe = {cid for cid in names if cid}
    print(f"universe: {len(universe)} companies on the {LIST_YEAR} list")

    # panel[company id][metric][fiscal year] = (value, edition)
    panel: dict[str, dict[str, dict[int, tuple[float, int]]]] = defaultdict(
        lambda: defaultdict(dict))
    for year in sorted(editions, reverse=True):          # newest first, so it wins
        for row in editions[year]:
            cid = company_id(row)
            if cid not in universe:
                continue
            for metric, field in FIELDS.items():
                for i, value in enumerate(row.get(field) or []):
                    if value is None:
                        continue
                    fy = year - 1 - i
                    if not (EARLIEST_YEAR <= fy <= LATEST_YEAR):
                        continue
                    if fy not in panel[cid][metric]:
                        panel[cid][metric][fy] = (float(value), year)

    records = []
    for cid, row in names.items():
        if cid not in universe:
            continue
        for metric in FIELDS:
            for fy, (value, edition) in sorted(panel[cid][metric].items()):
                records.append({
                    "company": row["organizationName"],
                    "forbes_id": cid,
                    "country": row.get("country"),
                    "industry": row.get("industry"),
                    "metric": metric,
                    "approx_year": fy,
                    "value": value,
                    "unit": UNITS[metric],
                    "source_edition": edition,
                })

    df = pd.DataFrame(records)
    df = df.sort_values(["company", "metric", "approx_year"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"wrote {OUT}  shape={df.shape}")

    # ---- coverage -------------------------------------------------------
    print("\ncoverage by fiscal year (firms reporting, of the 2,000):")
    print(f"{'year':>6} {'revenue':>8} {'profit':>8} {'employees':>10}")
    rev = df[df.metric == "revenue"]
    pro = df[df.metric == "profits"]
    emp = df[df.metric == "employees"]
    for fy in range(EARLIEST_YEAR, LATEST_YEAR + 1):
        print(f"{fy:>6} {int((rev.approx_year == fy).sum()):>8} "
              f"{int((pro.approx_year == fy).sum()):>8} {int((emp.approx_year == fy).sum()):>10}")

    # ---- integrity ------------------------------------------------------
    listing = pd.read_csv(ROOT / f"data/global2000_{LIST_YEAR}.csv",
                          encoding="utf-8-sig", low_memory=False)
    last = rev[rev.approx_year == LATEST_YEAR].set_index("company")["value"]
    listed = listing.set_index("company")["revenue_musd"]
    common = last.index.intersection(listed.index)
    gap = ((last[common] - listed[common]).abs() / listed[common].replace(0, pd.NA)).dropna()
    print(f"\n{LATEST_YEAR} revenue vs the list's own figure: {len(gap)} firms, "
          f"median gap {gap.median() * 100:.3f}%, exact {int((gap < 0.001).sum())}/{len(gap)}")

    pre = rev[rev.approx_year < 2016].groupby("company").size()
    print(f"companies with pre-2016 revenue: {len(pre)} of {listing.shape[0]}")
    firsts = rev.groupby("company").approx_year.min()
    print(f"earliest year any company reports: {int(firsts.min())}, "
          f"latest first year: {int(firsts.max())}")
    editions_used = rev.groupby("approx_year").source_edition.agg(
        lambda s: sorted(set(s))[0] if len(set(s)) == 1 else f"{len(set(s))} editions")
    print("\nwhich edition supplies each year (revenue):")
    for fy in range(EARLIEST_YEAR, LATEST_YEAR + 1):
        used = rev[rev.approx_year == fy].source_edition
        print(f"  {fy}: {dict(sorted(used.value_counts().items()))}")


if __name__ == "__main__":
    main()
