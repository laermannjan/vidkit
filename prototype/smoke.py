#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.47"]
# ///
"""Drives the panel headlessly: picking, save modes, the plan view, navigation."""
import asyncio, sys, tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from capture import COLUMNS, PANEL_JS, Session, wire, load_plan, save_plan

SITE, ok = "http://127.0.0.1:8777", True

def check(label, cond, detail=""):
    global ok; ok = ok and cond
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  {detail}" if detail else ""))

async def val(page, name):
    return await page.evaluate(
        """(n) => document.getElementById('__vk_host')
             .shadowRoot.querySelector(`input[data-f="${n}"]`).value""", name)

async def focus_field(page, name):
    """Click into the panel input, the way a user arms a field now."""
    await page.evaluate(
        """(n) => document.getElementById('__vk_host')
             .shadowRoot.querySelector(`input[data-f="${n}"]`).focus()""", name)

async def pick(page, scope, field, sel):
    await focus_field(page, field)          # focusing is what arms it
    await page.wait_for_timeout(250)
    await scope.locator(sel).first.hover()
    await scope.locator(sel).first.click()
    await page.wait_for_timeout(400)

async def main():
    out = Path("smoke-plan.tsv"); out.unlink(missing_ok=True)
    s = Session(out)
    with tempfile.TemporaryDirectory() as prof:
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(prof, headless=True)
            await ctx.add_init_script(f"window.__vk_cols = {COLUMNS!r};".replace("'", '"'))
            await ctx.add_init_script(PANEL_JS)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await wire(page, s)
            task = asyncio.create_task(s.classify(ctx))

            await page.goto(f"{SITE}/day1.html", wait_until="domcontentloaded")
            await page.wait_for_timeout(600)
            check("panel injected", await page.evaluate(
                "!!document.getElementById('__vk_host')?.shadowRoot?.getElementById('fields')"))
            frames = [f for f in page.frames if "8778" in f.url]
            check("injected into cross-origin embed", bool(frames) and
                  await frames[0].evaluate("!!window.__vk_injected"))

            # --- focus is what arms a field; no arm button exists ---
            await focus_field(page, "artist")
            await page.wait_for_timeout(250)
            check("focusing a field arms it", s.armed == "artist", repr(s.armed))
            await focus_field(page, "title")
            await page.wait_for_timeout(250)
            check("focusing another field moves the arm", s.armed == "title", repr(s.armed))

            # --- picking ---
            await pick(page, page.frame_locator("iframe"), "artist", "#cap")
            check("field stays armed after a pick (it is still focused)",
                  s.armed == "artist", repr(s.armed))
            check("picked text inside the embed",
                  await val(page, "artist") == "Recorded by Jane Roe")
            await pick(page, page, "title", ".lt")
            check("picked text in the page", await val(page, "title") == "What Foo Is")

            await pick(page, page.frame_locator("iframe"), "url", "#p")
            await page.wait_for_timeout(2600)
            check("clicking the video bound its stream", s.row.get("url") is not None)
            check("master kept, variant rejected",
                  "master.m3u8" in (s.row.get("url") or ""))

            for k, v in [("show", "Introduction to Foo"), ("season", "2026"),
                         ("day", "1"), ("number", "1"), ("lang", "de")]:
                await s.field(k, v)

            # --- save mode: another language ---
            await s.save("language")
            check("row 1 saved", len(s.rows) == 1)
            check("language mode held number", s.row.get("number") == "1")
            check("language mode held title", s.row.get("title") == "What Foo Is")
            check("language mode cleared lang", "lang" not in s.row)
            check("language mode cleared the video", "url" not in s.row)

            await s.field("lang", "en")
            await pick(page, page.frame_locator("iframe"), "url", "#p")
            await page.wait_for_timeout(2600)
            check("second language bound a stream", s.row.get("url") is not None)

            # --- save mode: next video ---
            await s.save("video")
            check("row 2 saved", len(s.rows) == 2)
            check("video mode bumped number", s.row.get("number") == "2",
                  repr(s.row.get("number")))
            check("video mode cleared title", "title" not in s.row)
            check("video mode kept lang", s.row.get("lang") == "en")

            # --- the plan view groups variants under one video ---
            nodes = s.plan_nodes()
            items = [n for n in nodes if n["kind"] == "item"]
            check("two languages collapse to one video in the plan", len(items) == 1,
                  f"{len(items)} items")
            check("plan lists both languages",
                  [l["lang"] for l in items[0]["langs"]] == ["de", "en"],
                  str([l["lang"] for l in items[0]["langs"]]))
            check("plan labels it D1E1", items[0]["num"] == "D1E1", items[0]["num"])
            check("plan shows the course as a group",
                  any(n["kind"] == "group" and "Introduction to Foo" in n["text"]
                      for n in nodes))

            # --- navigation, then save mode: new day ---
            await page.click("a"); await page.wait_for_url("**/day2.html")
            await page.wait_for_timeout(700)
            check("panel survived navigation", await page.evaluate(
                "!!document.getElementById('__vk_host')?.shadowRoot?.getElementById('fields')"))
            check("kept fields survived navigation",
                  await val(page, "show") == "Introduction to Foo")

            await pick(page, page, "title", ".lt")
            await pick(page, page.frame_locator("iframe"), "url", "#p")
            await page.wait_for_timeout(2600)
            check("stream captured on the next page", s.row.get("url") is not None)
            await s.save("day")
            check("row 3 saved", len(s.rows) == 3)
            check("day mode bumped the day", s.row.get("day") == "2", repr(s.row.get("day")))
            check("day mode reset numbering", s.row.get("number") == "1",
                  repr(s.row.get("number")))

            # --- removing an item takes all its languages ---
            key = items[0]["key"]
            await s.delete(key)
            check("removing a video removed both its languages", len(s.rows) == 1,
                  f"{len(s.rows)} rows left")

            await s.finish(); task.cancel(); await ctx.close()

    save_plan(out, s.rows)
    check("plan round-trips through TSV", len(load_plan(out)) == 1)
    check("ids were assigned", all(r.get("id") for r in load_plan(out)))
    return 0 if ok else 1

sys.exit(asyncio.run(main()))
