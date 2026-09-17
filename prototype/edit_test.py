#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.47"]
# ///
"""Editing a captured source, and the file-tree view of the plan."""
import asyncio, sys, tempfile
from pathlib import Path
from playwright.async_api import async_playwright
from capture import COLUMNS, PANEL_JS, Session, wire, load_plan, save_plan, row_path

ok = True
def check(l, c, d=""):
    global ok; ok = ok and c
    print(f"  {'PASS' if c else 'FAIL'}  {l}" + (f"  {d}" if d else ""))

ROWS = [
 {"show":"Introduction to Foo","season":"2026","day":"1","number":"1",
  "title":"What Foo Is","lang":"de","url":"https://x/a.m3u8","referer":"https://site/"},
 {"show":"Introduction to Foo","season":"2026","day":"1","number":"1",
  "title":"What Foo Is","lang":"en","url":"https://x/b.m3u8","referer":"https://site/"},
 {"season":"2023","title":"A Talk About Bar","lang":"en","url":"https://x/c.m3u8"},
]

async def main():
    s = Session(Path("/dev/null")); s.rows = [dict(r) for r in ROWS]
    with tempfile.TemporaryDirectory() as prof:
        async with async_playwright() as pw:
            ctx = await pw.chromium.launch_persistent_context(prof, headless=True)
            await ctx.add_init_script(f"window.__vk_cols = {COLUMNS!r};".replace("'", '"'))
            await ctx.add_init_script(PANEL_JS)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            await wire(page, s)
            await page.goto("http://127.0.0.1:8777/day1.html", wait_until="domcontentloaded")
            await page.wait_for_timeout(600)

            async def val(n):
                return await page.evaluate(
                    """(n) => document.getElementById('__vk_host').shadowRoot
                         .querySelector(`input[data-f="${n}"]`).value""", n)
            async def shown(sel):
                return await page.evaluate(
                    """(s) => { const e = document.getElementById('__vk_host')
                        .shadowRoot.querySelector(s);
                        return e ? getComputedStyle(e).display !== 'none' : false; }""", sel)

            # --- editing loads a source back into the form ---
            await page.evaluate("window.vkEdit(1)")   # the English variant
            await page.wait_for_timeout(300)
            check("edit loaded the row", s.editing == 1, repr(s.editing))
            check("form shows that source's language", await val("lang") == "en",
                  repr(await val("lang")))
            check("form shows its title", await val("title") == "What Foo Is")
            check("form shows its url", await val("url") == "https://x/b.m3u8")
            check("referer came along too", s.referer == "https://site/", repr(s.referer))
            check("edit banner visible", await shown('#edbar'))
            check("save buttons hidden while editing", not await shown('#acts'))
            check("update buttons shown", await shown('#edacts'))

            # --- updating writes back in place, not as a new row ---
            await s.field("title", "What Foo Actually Is")
            await s.update()
            check("row count unchanged", len(s.rows) == 3, f"{len(s.rows)}")
            check("edit written back", s.rows[1]["title"] == "What Foo Actually Is")
            check("sibling language followed the item-level edit",
                  s.rows[0]["title"] == "What Foo Actually Is", s.rows[0]["title"])
            check("sibling kept its own language", s.rows[0]["lang"] == "de")
            check("sibling kept its own url", s.rows[0]["url"] == "https://x/a.m3u8")
            check("referer preserved through edit", s.rows[1].get("referer") == "https://site/")
            check("editing cleared", s.editing is None)
            check("save buttons back", await shown('#acts'))

            # --- cancel discards ---
            await page.evaluate("window.vkEdit(0)")
            await page.wait_for_timeout(250)
            await s.field("title", "scribble")
            await s.cancel()
            check("cancel discarded the change",
                  s.rows[0]["title"] == "What Foo Actually Is")
            check("cancel cleared editing", s.editing is None)

            # --- file view ---
            nodes = s.file_nodes()
            files = [n for n in nodes if n["kind"] == "file"]
            check("two languages make one file", len(files) == 2, f"{len(files)} files")
            foo = next(f for f in files if "Foo" in f["text"])
            check("filename uses the day-encoded episode",
                  "S2026E0101" in foo["text"], foo["text"])
            check("edited title reached the filename",
                  "What Foo Actually Is" in foo["text"], foo["text"])
            check("both audio tracks listed on that file",
                  [t["lang"] for t in foo["tracks"]] == ["de", "en"])
            check("first track marked default", foo["tracks"][0]["default"] is True)
            check("standalone uses the year layout",
                  any("A Talk About Bar (2023).mkv" == f["text"] for f in files))
            check("directories precede their files",
                  any(n["kind"] == "dir" and n["text"] == "Season 2026" for n in nodes))
            check("path matches the template",
                  row_path(s.rows[0]) ==
                  "Introduction to Foo/Season 2026/"
                  "Introduction to Foo - S2026E0101 - What Foo Actually Is.mkv",
                  row_path(s.rows[0]))

            # --- the file view renders and its track chips are clickable ---
            await page.evaluate("""() => document.getElementById('__vk_host')
                .shadowRoot.getElementById('tab_files').click()""")
            await page.wait_for_timeout(300)
            n = await page.evaluate("""() => document.getElementById('__vk_host')
                .shadowRoot.querySelectorAll('#plan .ffile').length""")
            check("file view rendered both files", n == 2, f"{n} rendered")

            await ctx.close()
    return 0 if ok else 1

sys.exit(asyncio.run(main()))
