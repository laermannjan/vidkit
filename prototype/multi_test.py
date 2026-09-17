#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.47"]
# ///
"""Does picking work when a page has more than one video?

Case 1 (multi.html): each player in its own iframe. Frame identity is real evidence.
Case 2 (same.html):  two players sharing one frame. It is not. Must offer, not guess.
"""
import asyncio, sys, tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from capture import COLUMNS, PANEL_JS, Session, wire, load_plan, save_plan

SITE, ok = "http://127.0.0.1:8777", True
ADV, BIP = "img_bipbop_adv_example_fmp4", "bipbop_16x9"

def check(label, cond, detail=""):
    global ok; ok = ok and cond
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  {detail}" if detail else ""))

async def pick_player(page, scope, sel, s):
    await page.evaluate("window.vkArm('url')")
    await page.wait_for_timeout(250)
    await scope.locator(sel).first.hover()
    await scope.locator(sel).first.click()
    await page.wait_for_timeout(2200)

async def main():
    s = Session(Path("multi.toml"))
    with tempfile.TemporaryDirectory() as prof:
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(prof, headless=True)
            await ctx.add_init_script(f"window.__vk_cols = {COLUMNS!r};".replace("'", '"'))
            await ctx.add_init_script(PANEL_JS)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await wire(page, s)
            task = asyncio.create_task(s.classify(ctx))

            # ---- Case 1: separate iframes ----
            print("\ncase 1: two players, separate iframes")
            await page.goto(f"{SITE}/multi.html", wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            check("nothing bound before any pick", s.row.get("url") is None,
                  f"got {s.row.get('url')}")
            check("both players' streams noted separately", len(s.masters) >= 2,
                  f"{len(s.masters)} frames")

            await pick_player(page, page.frame_locator("#f1"), "#p", s)
            u1 = s.row.get("url") or ""
            check("picking player 1 bound player 1's stream", ADV in u1, u1[-46:])

            await pick_player(page, page.frame_locator("#f2"), "#p", s)
            u2 = s.row.get("url") or ""
            check("picking player 2 bound player 2's stream", BIP in u2, u2[-46:])
            check("the two picks gave different streams", u1 != u2 and bool(u1) and bool(u2))
            check("no choice needed - frame identity was enough", s.candidates == [])

            # ---- Case 2: one frame, two videos ----
            print("\ncase 2: two players sharing one frame")
            s.masters.clear(); s.candidates = []; s.row.pop("url", None); s.player_frame = None
            s.seen.clear()
            await page.goto(f"{SITE}/same.html", wait_until="domcontentloaded")
            await page.wait_for_timeout(2500)
            await pick_player(page, page, "#b1", s)
            check("ambiguity detected, nothing bound", s.row.get("url") is None,
                  f"got {s.row.get('url')}")
            check("both streams offered as a choice", len(s.candidates) == 2,
                  f"{len(s.candidates)} offered")

            if len(s.candidates) == 2:
                target = next(c for c in s.candidates if BIP in c)
                await s.choose(target)
                check("choosing by hand binds exactly that stream",
                      s.row.get("url") == target, (s.row.get("url") or "")[-46:])
                check("offer cleared after choosing", s.candidates == [])

            task.cancel(); await ctx.close()
    return 0 if ok else 1

sys.exit(asyncio.run(main()))
