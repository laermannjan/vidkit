#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["playwright>=1.47"]
# ///
"""Prototype of the vidkit capture panel.

A browser with a panel injected into every page. Click a field to arm it, then click
that text on the page. Click the video itself to bind its stream. Save, navigate to the
next page, keep going. Finish writes the plan.

The plan file is the state: it is loaded if it exists, and started empty if not.

    ./capture.py <plan.tsv> [url]

The browser profile persists in ./.profile, so a magic-link login survives between
runs. Navigate freely - the panel follows across sites.

Throwaway. Proves the mechanism, not the design.
"""

from __future__ import annotations

import argparse
import asyncio
import difflib
import re
import subprocess
import sys
from pathlib import Path

import csv
from playwright.async_api import async_playwright

COLUMNS = ["show", "season", "day", "number", "title", "artist", "lang", "url"]
ALL = set(COLUMNS)

# The file is the state. TSV, one row per source, tab-delimited with no quoting:
# every captured value has its whitespace normalised, so none can contain a tab.
FILE_COLUMNS = ["id", "show", "season", "day", "number", "title", "artist",
                "lang", "default", "url", "referer"]


def load_plan(path: Path) -> list[dict]:
    """Whatever is already there, or nothing if the file is absent or empty."""
    if not path.exists() or not path.stat().st_size:
        return []
    with path.open(newline="") as f:
        return [{k: v for k, v in r.items() if v}
                for r in csv.DictReader(f, delimiter="\t")]


def save_plan(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, FILE_COLUMNS, delimiter="\t", extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def next_id(rows: list[dict]) -> str:
    """Unique within the plan, never reused - including ids loaded from disk."""
    used = {r.get("id", "") for r in rows}
    n = 1
    while (i := f"s{n}") in used:
        n += 1
    return i

# Output naming. Only place the layout is defined - a proper template mechanism is
# still a spec question, but changing it here changes it everywhere.
PATH_SERIES = "{show}/Season {season}/{show} - S{season}E{ep} - {title}.mkv"
PATH_STANDALONE = "{title} ({season})/{title} ({season}).mkv"


def episode_token(day: str, number: str) -> str:
    """Day-encoded episodes render as four digits, plain ones as two."""
    d, n = (day or "").strip(), (number or "").strip()
    if d.isdigit() and n.isdigit():
        return f"{int(d):02d}{int(n):02d}"
    return f"{int(n):02d}" if n.isdigit() else (n or "??")


def row_path(r: dict) -> str:
    f = {k: (r.get(k) or "").strip() for k in
         ("show", "season", "day", "number", "title")}
    f["title"] = f["title"] or "(untitled)"
    f["ep"] = episode_token(f["day"], f["number"])
    f["season"] = f["season"] or "?"
    tpl = PATH_SERIES if f["show"] else PATH_STANDALONE
    return tpl.format(**f)

# mkvmerge takes BCP 47 and normalises 2/3-letter codes itself (de, deu, ger, DE all
# land on the same track language), and keeps regional subtags like pt-BR. It rejects
# words outright, so only those need translating.
LANG_ALIASES = {
    "german": "de", "deutsch": "de", "english": "en", "englisch": "en",
    "french": "fr", "französisch": "fr", "francais": "fr", "français": "fr",
    "spanish": "es", "spanisch": "es", "espanol": "es", "español": "es",
    "italian": "it", "italienisch": "it", "italiano": "it",
    "portuguese": "pt", "dutch": "nl", "nederlands": "nl", "polish": "pl",
    "russian": "ru", "japanese": "ja", "chinese": "zh", "korean": "ko",
}
# Free-text fields that repeat across rows. A typo in one of these silently splits
# a group in two, so offering what you already used is the cheapest guard there is.
SUGGEST_FIELDS = {"show", "title", "artist"}

# These describe the video, so every language variant of it shares them. Editing one
# variant's title must move its siblings too, or the group splits into two files.
ITEM_FIELDS = {"show", "season", "day", "number", "title", "artist"}
# These describe one audio source and are edited on their own.
SOURCE_FIELDS = {"lang", "url", "name", "referer"}

# Offered as suggestions; anything valid may still be typed.
LANG_SUGGEST = ["de", "en", "fr", "es", "it", "pt", "nl", "pl", "ru", "ja", "zh", "ko"]

# Primary subtag: 2-3 letters. Then optional script (4 letters) and/or region
# (2 letters or 3 digits). Variants are legal BCP 47 but must be IANA-registered,
# and we will never use one - allowing them is what let "pfe-dfasdf" through.
LANG_SHAPE = re.compile(
    r"^(?P<primary>[A-Za-z]{2,3})"
    r"(-(?P<script>[A-Za-z]{4}))?"
    r"(-(?P<region>[A-Za-z]{2}|[0-9]{3}))?$"
)

_CODES: set[str] | None = None


def language_codes() -> set[str]:
    """Every code mkvmerge knows, from mkvmerge itself. Empty if it is not installed,
    in which case only the shape is checked."""
    global _CODES
    if _CODES is None:
        _CODES = set()
        try:
            out = subprocess.run(["mkvmerge", "--list-languages"],
                                 capture_output=True, text=True, timeout=20).stdout
            for line in out.splitlines():
                parts = [c.strip() for c in line.split("|")]
                if len(parts) >= 4:
                    _CODES.update(c.lower() for c in parts[1:4] if c)
        except Exception:
            pass
    return _CODES


def lang_problem(v: str) -> str | None:
    if not v:
        return None
    m = LANG_SHAPE.match(v)
    if not m:
        return "not a language tag - try de, en, pt-BR, zh-Hans"
    codes = language_codes()
    if codes and m["primary"].lower() not in codes:
        return f"'{m['primary']}' is not a known language code"
    return None

# What each save button means. You say what the next row IS, rather than deriving it
# from per-field sticky flags.
MODES = {
    # same video, different audio track
    "language": {"keep": ALL - {"lang", "url"}},
    # next lecture in the same day
    "video":    {"keep": {"show", "season", "day", "artist", "lang"}, "bump": "number"},
    # next day of the same course, numbering restarts
    "day":      {"keep": {"show", "season", "artist", "lang"}, "bump": "day",
                 "set": {"number": "1"}},
    # unrelated course
    "show":     {"keep": set()},
}

PANEL_JS = Path(__file__).with_name("panel.js").read_text()


def screen_size(default=(1920, 1200)) -> tuple[int, int]:
    """Logical desktop size, so the browser opens at a usable size.

    Chromium ignores --start-maximized on macOS, so the window has to be sized
    explicitly or you get 800x600.
    """
    if sys.platform != "darwin":
        return default
    try:
        out = subprocess.run(["system_profiler", "SPDisplaysDataType"],
                             capture_output=True, text=True, timeout=8).stdout
        # "UI Looks like" is the logical size; "Resolution" is the physical one.
        m = re.search(r"UI Looks like:\s*(\d+)\s*x\s*(\d+)", out) \
            or re.search(r"Resolution:\s*(\d+)\s*x\s*(\d+)", out)
        if m:
            return int(m[1]), int(m[2])
    except Exception:
        pass
    return default


def is_master(text: str) -> bool:
    """HLS manifests self-identify: a master lists variants, a media playlist lists
    segments. See FINDINGS.md."""
    return "#EXT-X-STREAM-INF" in text


class Session:
    def __init__(self, out: Path, debug: bool = False):
        self.out = out
        self.debug = debug
        self.pages: list = []
        self.armed: str | None = None
        self.row: dict[str, str] = {}
        self.referer: str | None = None
        self.player_frame: str | None = None
        # Every master seen, keyed by the frame that asked for it. Players fetch
        # their master on load, long before you click, so this has to be a memory
        # rather than a live capture window.
        self.masters: dict[str, list[tuple[str, str | None]]] = {}
        self.candidates: list[str] = []
        self.editing: int | None = None
        self.rows: list[dict] = []
        self.done = asyncio.Event()
        # Keyed by (frame, url): the same stream seen in a different frame or on a
        # later page is a different association and must be evaluated again.
        self.seen: set[tuple[str, str]] = set()
        self.queue: asyncio.Queue = asyncio.Queue()

    # --- called from the page -------------------------------------------------
    async def ready(self):
        """Panel booted - after first load, and again after every navigation."""
        await self.paint()

    async def arm(self, field: str):
        self.armed = field
        await self.paint()

    async def bind(self, url: str, referer: str | None, why: str):
        self.row["url"], self.referer = url, referer
        self.candidates = []
        print(f"  ~ bound ({why}): {url[:80]}")
        await self.paint()

    async def offer(self, frame_url: str):
        """More than one stream from the picked player. Ask rather than guess."""
        self.candidates = [u for u, _ in self.masters.get(frame_url, [])]
        self.row.pop("url", None)
        print(f"  ? {len(self.candidates)} streams from this player - choose one in the panel")
        await self.paint()

    async def choose(self, url: str):
        for cands in self.masters.values():
            for u, ref in cands:
                if u == url:
                    await self.bind(u, ref, "chosen by hand")
                    return

    @staticmethod
    def _segments(typed: str, cand: str, sm: difflib.SequenceMatcher) -> list[dict]:
        """Label every character of the candidate: matched exactly, matched but with
        different case, or not matched. Lets a capitalisation slip be visible."""
        lt, lc = typed.lower(), cand.lower()
        # Some characters change length when lowercased; without a 1:1 index map the
        # per-character comparison would be wrong, so fall back to "matched".
        exactable = len(lt) == len(typed) and len(lc) == len(cand)
        marks = ["none"] * len(cand)
        for b in sm.get_matching_blocks():
            for k in range(b.size):
                ti, ci = b.a + k, b.b + k
                if ci >= len(cand):
                    continue
                marks[ci] = ("exact" if not exactable or typed[ti] == cand[ci]
                             else "case")
        segs: list[dict] = []
        for ch, kind in zip(cand, marks):
            if segs and segs[-1]["kind"] == kind:
                segs[-1]["text"] += ch
            else:
                segs.append({"text": ch, "kind": kind})
        return segs

    def suggestions(self, field: str | None, typed: str) -> list[dict]:
        """Values already used for this field, fuzzy-ranked against what is typed.

        Returns the match positions too, so the panel can show *why* something
        matched rather than just that it did.
        """
        if field not in SUGGEST_FIELDS:
            return []
        pool = {r[field] for r in self.rows if r.get(field)} - {typed}
        if not pool:
            return []
        t = typed.strip().lower()
        out = []
        for cand in pool:
            if not t:
                out.append({"text": cand, "score": 0.0,
                            "segs": [{"text": cand, "kind": "none"}]})
                continue
            sm = difflib.SequenceMatcher(None, t, cand.lower())
            score = sm.ratio()
            if t in cand.lower():          # a clean substring beats a fuzzy ratio
                score = max(score, 0.92)
            if score >= 0.45:
                segs = self._segments(typed.strip(), cand, sm)
                out.append({"text": cand, "score": score, "segs": segs,
                            "caseOff": any(g["kind"] == "case" for g in segs)})
        out.sort(key=lambda x: (-x["score"], x["text"].lower()))
        return out[:6]

    async def edit(self, idx: int):
        """Load a captured source back into the form."""
        if not 0 <= idx < len(self.rows):
            return
        r = self.rows[idx]
        self.editing = idx
        self.row = {k: v for k, v in r.items() if k != "referer"}
        self.referer = r.get("referer")
        print(f"  editing: {r.get('title', '(untitled)')} [{r.get('lang', '?')}]")
        await self.paint()

    async def update(self):
        """Write the form back over the source being edited.

        Item-level fields propagate to the other languages of the same video; source
        -level ones stay put.
        """
        if self.editing is None:
            return
        was = self._key(self.rows[self.editing])
        siblings = [i for i, r in enumerate(self.rows) if self._key(r) == was]
        new = {k: v for k, v in self.row.items() if v}
        if self.referer:
            new["referer"] = self.referer

        for i in siblings:
            if i == self.editing:
                self.rows[i] = new
            else:
                self.rows[i] = ({k: v for k, v in self.rows[i].items()
                                 if k not in ITEM_FIELDS}
                                | {k: v for k, v in new.items() if k in ITEM_FIELDS})
        moved = len(siblings) - 1
        print(f"  ~ updated: {self.row.get('title', '(untitled)')}"
              + (f" (+{moved} other language{'s' if moved > 1 else ''})" if moved else ""))
        self.editing = None
        self.row = {}
        self.referer = self.player_frame = None
        await self.paint()

    async def cancel(self):
        self.editing = None
        self.row = {}
        self.referer = self.player_frame = None
        await self.paint()

    async def pick(self, text: str | None, meta: dict | None = None):
        """An element was clicked while a field was armed. None means cancelled.

        The field stays armed afterwards because it is still focused; escape or
        moving to another field is what disarms.
        """
        if not self.armed:
            return
        field, meta = self.armed, (meta or {})
        if field == "url" and meta.get("player"):
            # Scope to this player's frame so a page with several videos cannot hand
            # us the wrong stream.
            self.player_frame = frame = meta.get("frame")
            known = self.masters.get(frame, [])
            self.row.pop("url", None)
            self.candidates = []
            if len(known) == 1:
                await self.bind(*known[0], "loaded by the player you picked")
            elif len(known) > 1:
                await self.offer(frame)
            else:
                # Nothing from this frame yet: the replayed click should trigger it,
                # and only a stream from this frame will be accepted.
                print("  player picked - waiting for a stream from this player")
                if not meta.get("ownFrame"):
                    print("  ! this player shares a frame with the page; if several "
                          "videos live here, you will be offered a choice")
        elif text:
            self.row[field] = text
            print(f"  {field} = {text!r}")
        await self.paint()

    async def accept(self, field: str, value: str):
        """A suggestion was clicked."""
        self.row[field] = value
        await self.paint()

    async def field(self, name: str, value: str):
        if name == "lang" and (code := LANG_ALIASES.get(value.strip().lower())):
            value = code                      # "deutsch" -> "de", before it reaches the mux
            self.row[name] = value
            await self.paint()
            return
        self.row[name] = value
        if name in SUGGEST_FIELDS:
            await self.paint()

    async def clear(self):
        self.row = {}
        self.referer = self.player_frame = None
        self.seen.clear()
        await self.paint()

    async def save(self, mode: str = "video"):
        if not self.row.get("url"):
            print("  ! no video selected - arm url and click the video, or paste one in")
            return
        self.rows.append({"id": next_id(self.rows)}
                         | {k: v for k, v in self.row.items() if v}
                         | ({"referer": self.referer} if self.referer else {}))
        spec = MODES[mode]
        print(f"  + saved: {self.row.get('title', '(untitled)')} "
              f"[{self.row.get('lang', '?')}] -> {mode}")

        nxt = {k: v for k, v in self.row.items() if k in spec["keep"] and v}
        if (f := spec.get("bump")) and (v := self.row.get(f, "")).isdigit():
            nxt[f] = str(int(v) + 1)
        nxt |= spec.get("set", {})
        self.row = nxt
        self.referer = self.player_frame = None
        self.masters.clear()
        self.candidates = []
        self.seen.clear()
        await self.paint()

    async def delete(self, key: str):
        before = len(self.rows)
        self.rows = [r for r in self.rows if self._key(r) != key]
        print(f"  - removed {before - len(self.rows)} row(s)")
        await self.paint()

    @staticmethod
    def _key(r: dict) -> str:
        return "|".join(r.get(f, "") for f in ("show", "season", "day", "number", "title"))

    def plan_nodes(self) -> list[dict]:
        """The plan as it stands, grouped so variants sit under one video."""
        items, order = {}, []
        for i, r in enumerate(self.rows):
            k = (r.get("show", ""), r.get("season", "")), self._key(r)
            if k not in items:
                items[k] = (r, [])
                order.append(k)
            items[k][1].append({"lang": r.get("lang") or "?", "idx": i})
        out, last = [], None
        for k in order:
            (show, season), key = k
            if (show, season) != last:
                last = (show, season)
                label = show or "(standalone)"
                out.append({"kind": "group",
                            "text": label + (f" · S{season}" if season else "")})
            r, langs = items[k]
            day, num = r.get("day", ""), r.get("number", "")
            out.append({"kind": "item",
                        "num": (f"D{day}E{num}" if day else f"E{num}") if num else "—",
                        "title": r.get("title", "") or "(untitled)",
                        "langs": langs, "key": key})
        return out

    def file_nodes(self) -> list[dict]:
        """The tree that would be written, with what the paths cannot show."""
        files: dict[str, list[tuple[int, dict]]] = {}
        for i, r in enumerate(self.rows):
            files.setdefault(row_path(r), []).append((i, r))
        out, shown = [], []
        for path in sorted(files):
            parts = path.split("/")
            for d in range(len(parts) - 1):
                if shown[d:d + 1] != [parts[d]]:
                    shown = parts[:d + 1]
                    out.append({"kind": "dir", "depth": d, "text": parts[d]})
            tracks = [{"lang": r.get("lang") or "?", "idx": i,
                       "default": n == 0, "name": r.get("name", "")}
                      for n, (i, r) in enumerate(files[path])]
            out.append({"kind": "file", "depth": len(parts) - 1,
                        "text": parts[-1], "tracks": tracks})
        return out

    async def finish(self):
        self.done.set()

    # --- internal -------------------------------------------------------------
    async def paint(self):
        state = {
            "row": self.row, "armed": self.armed,
            "plan": self.plan_nodes(),
            "files": self.file_nodes(),
            "editing": self.editing,
            "langProblem": lang_problem(self.row.get("lang", "").strip()),
            "langSuggest": LANG_SUGGEST,
            "suggest": self.suggestions(self.armed, self.row.get(self.armed or "", "")),
            "url": self.row.get("url"),
            "candidates": self.candidates,

        }
        for p in list(self.pages):
            try:
                await p.evaluate("(s) => window.__vk && window.__vk.paint(s)", state)
            except Exception:
                pass  # navigating; the panel re-injects and calls vkReady again
            for f in p.frames:
                try:
                    await f.evaluate("(on) => window.__vk_setArmed && window.__vk_setArmed(on)",
                                     self.armed)
                except Exception:
                    pass

    MANIFEST_TYPES = ("mpegurl", "dash+xml", "vnd.apple")

    def on_response(self, resp):
        """Queue anything that looks like a manifest.

        We keep the Response object rather than the URL: re-fetching loses the
        player's headers, and CDNs that check referer or a token answer a re-fetch
        with a 403 page that parses as 'not a playlist'.
        """
        url = resp.url
        base = url.split("?")[0]
        ct = (resp.headers.get("content-type") or "").lower()
        why = ("extension" if base.endswith((".m3u8", ".mpd"))
               else f"type {ct[:36]}" if any(t in ct for t in self.MANIFEST_TYPES)
               else None)
        if not why:
            return
        try:
            frame_url = resp.frame.url
        except Exception:
            frame_url = ""
        key = (frame_url, base)
        if key in self.seen:
            return
        self.seen.add(key)
        if self.debug:
            print(f"  [dbg] candidate ({why}): {url[:110]}")
        self.queue.put_nowait((resp, url, resp.request.headers.get("referer"), frame_url))

    async def _body(self, ctx, resp, url):
        """The body the player got, falling back to a replay with its own headers."""
        try:
            return await resp.text(), "player response"
        except Exception:
            pass
        try:
            hdrs = {k: v for k, v in resp.request.headers.items()
                    if k.lower() in ("referer", "origin", "user-agent", "cookie")}
            r = await ctx.request.get(url, headers=hdrs)
            return await r.text(), f"replay {r.status}"
        except Exception as e:
            return None, f"failed {type(e).__name__}"

    async def classify(self, ctx):
        while True:
            resp, url, referer, frame_url = await self.queue.get()
            body, how = await self._body(ctx, resp, url)
            if body is None:
                if self.debug:
                    print(f"  [dbg] -> {how}: {url[:90]}")
                continue
            if is_master(body):
                kind = "master"
            elif "#EXTINF" in body:
                kind = "media"
            else:
                kind = "not a playlist"
            if self.debug:
                head = " ".join(body[:70].split())
                print(f"  [dbg] -> {kind} via {how}: {url[:80]}")
                if kind == "not a playlist":
                    print(f"  [dbg]    body starts: {head!r}")
            if ".mpd" in url or kind == "master":
                seen = self.masters.setdefault(frame_url, [])
                if url not in [u for u, _ in seen]:
                    seen.append((url, referer))
                if self.debug:
                    print(f"  [dbg] master noted for frame {frame_url[:60]}")
                # Only bind if this frame is the player you actually picked, and it is
                # the only thing that frame has asked for. Never guess.
                if frame_url == self.player_frame:
                    if len(seen) == 1:
                        await self.bind(url, referer, "loaded by the player you picked")
                    else:
                        await self.offer(frame_url)


async def wire(page, s: Session):
    """Attach the panel and its callbacks to a page (including popups)."""
    s.pages.append(page)
    for name, fn in [("vkReady", s.ready), ("vkArm", s.arm),
                     ("vkPick", s.pick), ("vkChoose", s.choose), ("vkField", s.field),
                     ("vkAccept", s.accept), ("vkSave", s.save), ("vkClear", s.clear),
                     ("vkEdit", s.edit), ("vkUpdate", s.update), ("vkCancel", s.cancel),
                     ("vkDelete", s.delete), ("vkFinish", s.finish)]:
        await page.expose_function(name, fn)
    page.on("response", s.on_response)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", type=Path, help="the plan file - loaded if it exists")
    ap.add_argument("url", nargs="?")
    ap.add_argument("--profile", type=Path, default=Path(__file__).with_name(".profile"))
    ap.add_argument("--debug", action="store_true",
                    help="log every manifest candidate, CSP headers, and frame injection")
    args = ap.parse_args()

    s = Session(args.plan, debug=args.debug)
    s.rows = load_plan(args.plan)
    if s.rows:
        print(f"loaded {len(s.rows)} existing source(s) from {args.plan}")
    async with async_playwright() as pw:
        # Persistent profile so a magic-link login is done once, not every run.
        w, h = screen_size()
        ctx = await pw.chromium.launch_persistent_context(
            # no_viewport, not viewport=None: in Python the latter is
            # indistinguishable from "unset" and you get a fixed 1280x720 page.
            str(args.profile), headless=False, no_viewport=True,
            args=[f"--window-size={w},{h - 60}", "--window-position=0,0"],
        )
        await ctx.add_init_script(f"window.__vk_cols = {COLUMNS!r};".replace("'", '"'))
        await ctx.add_init_script(PANEL_JS)

        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await wire(page, s)
        ctx.on("page", lambda p: asyncio.create_task(wire(p, s)))

        task = asyncio.create_task(s.classify(ctx))
        print(f"opening {args.url}\nnavigate freely; click finish in the panel when done\n")
        resp = await page.goto(args.url, wait_until="domcontentloaded")
        if args.debug:
            csp = (resp.headers.get("content-security-policy") if resp else None)
            print(f"  [dbg] CSP: {csp[:160] if csp else 'none'}")
            await page.wait_for_timeout(1200)
            for f in page.frames:
                got = await f.evaluate("!!window.__vk_injected").__await__() \
                      if False else await f.evaluate("!!window.__vk_injected")
                print(f"  [dbg] injected={got}  {f.url[:80]}")
        await s.done.wait()
        task.cancel()
        await ctx.close()

    if not s.rows:
        print("nothing saved")
        return 1
    save_plan(args.plan, s.rows)
    print(f"\nwrote {len(s.rows)} source(s) to {args.plan}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
