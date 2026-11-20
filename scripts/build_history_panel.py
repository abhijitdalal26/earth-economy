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
back out of whichever editions they appeared on. Each edition carries up to
ten years of figures, newest first:

    fiscal year = edition year - 1 - index in the edition's list

Editions are worked through newest first, and each older edition only adds
the years the newer ones do not have. Three things keep the joins honest:

1. Alignment. Some editions put a trailing-twelve-month figure first for some
   firms, which pushes every year in that firm's list one slot along (about
   150-270 firms in the 2012, 2013 and 2015 editions). Before an older
   edition is used, its list is lined up against the years already in the
   panel: shifts of -1, 0 and +1 year are tried and the one with the most
   identical values wins (no identical values: no shift).
2. Level. Forbes changed definitions between editions (in 2015 it dropped
   excise taxes from oil companies' revenue, for example), so the same year
   can be ~10% apart in two editions. Each older edition is scaled to the
   panel by the median ratio over the years both cover, so a definition
   change does not show up as a jump. Profit takes the revenue scale.
   An edition that needs a scale outside 0.5-2 is not used for that firm.
3. Renamed companies. A firm that changed its Forbes id (Google became
   Alphabet) is joined to its old id through PREDECESSORS below, a reviewed
   list. Mergers and spin-offs are not joined: their history would show
   growth that came from buying or losing a business.

`source_edition`, `shift` and `scale` record where each number came from
and what was done to it.

Known limits
------------
- Values are only as consistent as Forbes' own restatements; scaling fixes
  levels, not one-off errors inside a single edition.
- A company only has history back to the first edition it appeared on, and
  only if Forbes gave it figures for the years before that.
- The list itself starts in 2011, so nothing before fiscal 2001 exists.
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data/raw_history"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data/global2000_2026_history_panel.csv"

FIRST_EDITION = 2011
LIST_YEAR = 2026
EARLIEST_YEAR = 2001
LATEST_YEAR = 2025
# The 2019 edition carries two-year lists laid out differently from every other edition:
# 1,801 of the 1,850 firms it shares with 2018 match it at no shift at all.
SKIP_EDITIONS = {2019}

FIELDS = {
    "revenue": "revenueList",
    "profits": "profitList",
    "employees": "employeesList",
}
UNITS = {"revenue": "USD millions", "profits": "USD millions", "employees": "employees"}

# 2026 company id -> the Forbes id it had before. Found by identical revenue and profit
# under two ids, or by name, and checked by hand: renames and new holding companies only.
PREDECESSORS = {
    "103537": "1821",   # Alphabet <- Google (holding company, 2015)
    "90907": "4166",    # Swiss Re <- Swiss Re Group
    "102024": "241",    # American Airlines Group <- AMR (out of bankruptcy, 2013)
    "102734": "3151",   # Eversource Energy <- Northeast Utilities (rename, 2015)
    "103706": "1117",   # Cosmo Energy Holdings <- Cosmo Oil (holding company, 2015)
    "118449": "5693",   # Hainan Airlines Holding <- Hainan Airlines
    "118494": "3091",   # Nippon Express Holdings <- Nippon Express (holding company, 2022)
    "105176": "3112",   # Nishi-Nippon Financial Holdings <- Nishi-Nippon City Bank (2016)
    "125239": "3893",   # Shizuoka Financial Group <- Shizuoka Bank (holding company, 2022)
    "102822": "4376",   # Tokyu Fudosan Holdings <- Tokyu Land (holding company, 2013)
}

SHIFTS = (0, -1, 1)
SAME = 0.002          # values within 0.2% count as identical
SCALE_OK = (0.5, 2.0)


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


def by_year(row: dict, field: str, edition: int, shift: int) -> dict[int, float]:
    out = {}
    for i, value in enumerate(row.get(field) or []):
        if value is not None:
            out[edition - 1 - i + shift] = float(value)
    return out


def identical(a: dict[int, float], seen: dict[int, list[float]]) -> int:
    """Years where a value in `a` equals one any newer edition reported for that year."""
    return sum(1 for y, v in a.items() if v and any(w and abs(v / w - 1) < SAME for w in seen.get(y, ())))


def scale_to(panel: dict[int, float], new: dict[int, float]) -> float | None:
    """Median of panel / new over the years both have (positive values only)."""
    ratios = [panel[y] / v for y, v in new.items() if y in panel and v > 0 and panel[y] > 0]
    return statistics.median(ratios) if ratios else None


def stitch(rows: list[tuple[int, dict]]) -> tuple[dict, dict]:
    """rows: (edition, row) for one company, newest edition first.
    Returns panel[metric][year] = value and meta[metric][year] = (edition, shift, scale)."""
    panel = {m: {} for m in FIELDS}
    meta = {m: {} for m in FIELDS}
    seen = {m: {} for m in FIELDS}     # raw values, lined up, from every edition used so far
    for n, (edition, row) in enumerate(rows):
        if n == 0:
            shift, scales = 0, {m: 1.0 for m in FIELDS}
        else:
            # 1. alignment: the shift with the most identical values (revenue, then profit)
            def hits(s):
                return (identical(by_year(row, "revenueList", edition, s), seen["revenue"]),
                        identical(by_year(row, "profitList", edition, s), seen["profits"]))
            score = {s: hits(s) for s in SHIFTS}
            shift = max(SHIFTS, key=lambda s: (score[s], s == 0))
            if score[shift] == (0, 0):
                shift = 0
            # 2. level: scale each metric to what the panel already holds
            rev = scale_to(panel["revenue"], by_year(row, "revenueList", edition, shift))
            emp = scale_to(panel["employees"], by_year(row, "employeesList", edition, shift))
            scales = {"revenue": rev, "profits": rev, "employees": emp}
            if rev is not None and not (SCALE_OK[0] <= rev <= SCALE_OK[1]):
                continue          # too far from the panel to trust: skip this edition for this firm
        for metric, field in FIELDS.items():
            k = scales[metric] if scales[metric] is not None else 1.0
            if metric == "employees" and not (SCALE_OK[0] <= k <= SCALE_OK[1]):
                k = 1.0
            for year, value in by_year(row, field, edition, shift).items():
                seen[metric].setdefault(year, []).append(value)
                if EARLIEST_YEAR <= year <= LATEST_YEAR and year not in panel[metric]:
                    panel[metric][year] = value * k
                    meta[metric][year] = (edition, shift, round(k, 4))
    return panel, meta


def main() -> None:
    editions = {}
    for year in range(FIRST_EDITION, LIST_YEAR + 1):
        if year in SKIP_EDITIONS:
            continue
        rows = load_edition(year)
        if rows:
            editions[year] = {company_id(r): r for r in rows if company_id(r)}
    if not editions:
        raise SystemExit(f"no editions found in {RAW}")
    print(f"editions: {sorted(editions)} (skipped {sorted(SKIP_EDITIONS)})")

    current = editions[LIST_YEAR]
    print(f"universe: {len(current)} companies on the {LIST_YEAR} list")

    records = []
    shifted = scaled = 0
    for cid, row in current.items():
        ids = [cid] + ([PREDECESSORS[cid]] if cid in PREDECESSORS else [])
        rows = []
        for year in sorted(editions, reverse=True):          # newest first
            hit = next((editions[year][i] for i in ids if i in editions[year]), None)
            if hit:
                rows.append((year, hit))
        panel, meta = stitch(rows)
        for metric in FIELDS:
            for fy in sorted(panel[metric]):
                edition, shift, k = meta[metric][fy]
                shifted += metric == "revenue" and shift != 0
                scaled += metric == "revenue" and abs(k - 1) > 0.01
                records.append({
                    "company": row["organizationName"],
                    "forbes_id": cid,
                    "country": row.get("country"),
                    "industry": row.get("industry"),
                    "metric": metric,
                    "approx_year": fy,
                    "value": panel[metric][fy],
                    "unit": UNITS[metric],
                    "source_edition": edition,
                    "shift": shift,
                    "scale": k,
                })

    df = pd.DataFrame(records)
    df = df.sort_values(["company", "metric", "approx_year"]).reset_index(drop=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"wrote {OUT}  shape={df.shape}")
    print(f"revenue values moved a year to line up: {shifted}; rescaled by more than 1%: {scaled}")

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
    firsts = rev.groupby("company").approx_year.min()
    print(f"earliest year any company reports: {int(firsts.min())}, "
          f"latest first year: {int(firsts.max())}")
    for name in ("Alphabet", "American Airlines Group", "Swiss Re"):
        if name in firsts.index:
            print(f"  {name}: revenue from {int(firsts[name])}")


if __name__ == "__main__":
    main()
