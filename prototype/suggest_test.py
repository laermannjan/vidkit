#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.47"]
# ///
"""Typo-resistant suggestions drawn from values already in the plan."""
import asyncio, sys, tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from capture import COLUMNS, PANEL_JS, Session, wire, load_plan, save_plan

ok = True
def check(l, c, d=""):
    global ok; ok = ok and c
    print(f"  {'PASS' if c else 'FAIL'}  {l}" + (f"  {d}" if d else ""))

async def main():
    s = Session(Path("/dev/null"))
    # Pretend these were captured earlier in the session.
    s.rows = [{"artist": "Johannes Müller", "show": "Introduction to Foo"},
              {"artist": "Jane Roe", "show": "Introduction to Foo"}]
    with tempfile.TemporaryDirectory() as prof:
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(prof, headless=True)
            await ctx.add_init_script(f"window.__vk_cols = {COLUMNS!r};".replace("'", '"'))
            await ctx.add_init_script(PANEL_JS)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await wire(page, s)
            await page.goto("http://127.0.0.1:8777/day1.html", wait_until="domcontentloaded")
            await page.wait_for_timeout(600)

            async def sugs():
                return await page.evaluate("""() => [...document.getElementById('__vk_host')
                    .shadowRoot.querySelectorAll('.sug[data-for="artist"] .s')]
                    .map(b => ({text: b.dataset.v,
                                bold: [...b.querySelectorAll('em')].map(e => e.textContent),
                                cased: [...b.querySelectorAll('u')].map(e => e.textContent)}))""")

            await page.evaluate("""() => document.getElementById('__vk_host')
                .shadowRoot.querySelector('input[data-f="artist"]').focus()""")
            await page.wait_for_timeout(300)
            check("focusing an empty field lists what you already used",
                  len(await sugs()) == 2, f"{len(await sugs())} shown")

            await s.field("artist", "Johanes Muller")   # two typos
            await page.wait_for_timeout(300)
            got = await sugs()
            check("a typo still finds the right value",
                  bool(got) and got[0]["text"] == "Johannes Müller",
                  got[0]["text"] if got else "nothing")
            check("matching characters are marked",
                  bool(got) and "".join(got[0]["bold"]) and
                  len("".join(got[0]["bold"])) >= 8,
                  f"bold: {''.join(got[0]['bold'])!r}" if got else "")
            check("non-matching characters are not marked",
                  bool(got) and "".join(got[0]["bold"]) != got[0]["text"],
                  f"bold: {''.join(got[0]['bold'])!r}" if got else "")

            await page.evaluate("""() => document.getElementById('__vk_host')
                .shadowRoot.querySelector('.sug[data-for="artist"] .s').click()""")
            await page.wait_for_timeout(300)
            check("clicking a suggestion fixes the field",
                  s.row.get("artist") == "Johannes Müller", repr(s.row.get("artist")))

            await s.field("artist", "Jan")
            await page.wait_for_timeout(300)
            await page.evaluate("""() => {
                const i = document.getElementById('__vk_host').shadowRoot
                            .querySelector('input[data-f="artist"]');
                i.focus();
                i.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true}));
            }""")
            await page.wait_for_timeout(300)
            check("enter accepts the top suggestion",
                  s.row.get("artist") == "Jane Roe", repr(s.row.get("artist")))

            # case-only difference must be visible, not silently treated as a match
            await s.field("artist", "johannes müller")
            await page.wait_for_timeout(300)
            got = await sugs()
            check("case-only mismatch is marked separately",
                  bool(got) and got[0]["cased"] == ["J", "M"],
                  f"cased={got[0]['cased'] if got else None}")
            check("the rest still counts as matched",
                  bool(got) and "".join(got[0]["bold"]) == "ohannes üller",
                  f"bold={''.join(got[0]['bold']) if got else None!r}")

            await s.field("artist", "Johannes Müller ")
            await page.wait_for_timeout(300)
            got = await sugs()
            check("an exact match shows no case marks",
                  bool(got) and got[0]["cased"] == [], str(got[0]["cased"] if got else None))

            await s.field("artist", "zzzzzz")
            await page.wait_for_timeout(300)
            check("nothing offered when nothing is close", len(await sugs()) == 0)

            await ctx.close()
    return 0 if ok else 1

sys.exit(asyncio.run(main()))
