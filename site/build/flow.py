"""Build site/data/flow.js -> window.ATLAS.flow
Twenty-five years of the Forbes Global 2000 (fiscal 2001-2025) for the "25 years" page.

Every company on the 2026 list, with revenue, profit and headcount for each year from
data/global2000_2026_history_panel.csv, which scripts/build_history_panel.py stitches out of
every Forbes edition (2011-2026). Each edition carries ten years of financials, so the 2011
edition reaches back to fiscal 2001. The page works out ranks and shares itself, so every
number on screen traces back to a row of the panel.

The same data, as a standalone page, is built by interactive/build_flow_panel.py."""
import json, os, re
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
OUT = os.path.join(ROOT, 'site', 'data', 'flow.js')

# one hue per sector, as on the interactive pages
SECTOR_COLOURS = {
    'Financials': '#1B6CA8', 'Consumer & Retail': '#E07A4F', 'Energy & Utilities': '#2E8B74',
    'Technology': '#8A6FB0', 'Healthcare': '#E34948', 'Food & Agriculture': '#B8860B',
    'Industrials & Defense': '#6B7685', 'Construction & Real Estate': '#7FB3D9',
    'Materials & Chemicals': '#C08552', 'Business Services': '#1B9AAA', 'Telecom & Media': '#D96BA0',
    'Transport & Logistics': '#7A9A3E', 'Conglomerates': '#9AA5B1', 'Unclassified': '#B5BCC6',
}
METRICS = {'revenue': 'r', 'profits': 'p', 'employees': 'e'}


def key(name):
    return re.sub(r'[^a-z0-9]', '', str(name).lower())


listing = pd.read_csv(os.path.join(ROOT, 'data', 'global2000_2026.csv'), encoding='utf-8-sig', low_memory=False)
panel = pd.read_csv(os.path.join(ROOT, 'data', 'global2000_2026_history_panel.csv'), encoding='utf-8-sig', low_memory=False)
years = list(range(int(panel.approx_year.min()), int(panel.approx_year.max()) + 1))
blank = [None] * len(years)

series = {}
for metric, short in METRICS.items():
    w = panel[panel.metric == metric].pivot_table(index='company', columns='approx_year', values='value', aggfunc='first')
    w = w.reindex(columns=years)
    series[short] = {key(c): [None if pd.isna(v) else float(v) for v in vals] for c, vals in zip(w.index, w.values)}

desc = {}
biz_file = os.path.join(ROOT, 'article', 'data', 'business_ideas.csv')
if os.path.exists(biz_file):
    biz = pd.read_csv(biz_file, encoding='utf-8-sig')
    for name, text in zip(biz.company, biz.what_they_do):
        if not pd.isna(text):
            desc.setdefault(key(name), str(text).strip())

sectors = list(SECTOR_COLOURS)
rows = []
for _, r in listing.iterrows():
    k = key(r.company)
    rows.append(dict(n=r.company, c=r.country, s=sectors.index(r.sector), d=desc.get(k, ''),
                     r=series['r'].get(k, blank), p=series['p'].get(k, blank), e=series['e'].get(k, blank)))

ideas = {}
idea_file = os.path.join(ROOT, 'article', 'data', 'idea_sectors.csv')
if os.path.exists(idea_file):
    for _, r in pd.read_csv(idea_file, encoding='utf-8-sig').iterrows():
        ideas[r['sector']] = '' if pd.isna(r['the_idea']) else str(r['the_idea'])

payload = dict(years=years, sectors=sectors, colours=[SECTOR_COLOURS[s] for s in sectors],
               ideas=[ideas.get(s, '') for s in sectors], rows=rows)
with open(OUT, 'w', encoding='utf-8') as f:
    f.write('window.ATLAS = window.ATLAS || {}; window.ATLAS.flow = ' + json.dumps(payload, separators=(',', ':')) + ';\n')
print('wrote', OUT, f'{os.path.getsize(OUT) / 1e6:.2f} MB', f'years {years[0]}-{years[-1]}', len(rows), 'companies')
print('firms reporting revenue:', years[0], sum(r['r'][0] is not None for r in rows), '->',
      years[-1], sum(r['r'][-1] is not None for r in rows))
