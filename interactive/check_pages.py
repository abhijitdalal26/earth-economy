"""Render the interactive pages in a headless browser and report any console
errors, plus write a screenshot of each page.

Run from the repo root:
    python interactive/check_pages.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
PAGES = ["index.html", "ideas.html", "flow.html"]
OUT = Path(r"C:\Users\abhijit\AppData\Local\Temp\opencode")


def main() -> int:
    bad = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for page in PAGES:
            ctx = browser.new_context(viewport={"width": 1280, "height": 1600})
            tab = ctx.new_page()
            errors: list[str] = []
            tab.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
            tab.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            url = (ROOT / "interactive" / page).as_uri()
            tab.goto(url)
            tab.wait_for_timeout(1200)
            # exercise the controls: change year, measure, and filter
            if page == "index.html":
                tab.fill("#year", "4")
                tab.dispatch_event("#year", "input")
                tab.wait_for_timeout(400)
                tab.click("#metricBtns button[data-m='p']")
                tab.wait_for_timeout(400)
                tab.click("#topBtns button[data-n='50']")
                tab.wait_for_timeout(600)
                tab.click("#year")
                tab.fill("#year", "9")
                tab.dispatch_event("#year", "input")
                tab.wait_for_timeout(800)
            elif page == "ideas.html":
                tab.click("#metricBtns button[data-m='p']")
                tab.wait_for_timeout(500)
                tab.click("#baseBtns button[data-b='4']")
                tab.wait_for_timeout(500)
                tab.click("#minBtns button[data-min='20']")
                tab.wait_for_timeout(700)
                tab.click("#univBtns button[data-u='all']")
                tab.wait_for_timeout(700)
            else:
                tab.click("#metricBtns button[data-m='p']")
                tab.wait_for_timeout(500)
                tab.click("#colourBtns button[data-c='growth']")
                tab.wait_for_timeout(500)
                tab.click("#cutoffBtns button[data-n='100']")
                tab.wait_for_timeout(700)
                tab.click("#colourBtns button[data-c='sector']")
                tab.wait_for_timeout(500)
                tab.click("#flowLegend button")
                tab.wait_for_timeout(500)
            shot = OUT / ("shot_" + page.replace(".html", ".png"))
            tab.screenshot(path=str(shot), full_page=True)
            print(f"{page}: {len(errors)} console error(s)")
            for e in errors[:10]:
                print("   ", e)
                bad += 1
            print("   screenshot:", shot)
            ctx.close()
        browser.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
