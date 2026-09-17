# vidkit - spec

Measured facts behind the rules are in FINDINGS.md.

## Purpose

Get course and lecture video off the web into a media library: capture the streams,
download them, merge per-language voice-overs into one multi-audio file, correct the
audio offset between them, tag, and file them under a correct path.

Site layouts are unpredictable. The automatic path will sometimes be wrong, so
correcting it must be cheap.

## Shape

Three phases, three different demands.

| phase | wants | is |
|---|---|---|
| capture | fast, forgiving, incremental | a browser with an injected panel |
| edit | ergonomic bulk change, restructuring | your tabular tool of choice |
| process | robust, unambiguous, dry-runnable | a batch pipeline |

Capture runs locally: it needs a real browser, your logins and your mouse. Process is
where the external binaries live. The plan file is the boundary.

## Plan file

**The file is the state.** `vidkit capture plan.tsv` loads whatever is there, or starts
empty if the file is absent or empty. No separate init, no append mode.

**Plans are temporary.** Capture, process, done - then delete it. Nothing is designed
around keeping one.

**The plan is read-only to `process`.** Only capture writes it. Process state lives in
the cache; see Process.

TSV, one file, one row per source URL. Tab-delimited with no quoting: capture
normalises whitespace on every value, so no field can contain a tab.

| column | notes |
|---|---|
| `show` | empty means standalone |
| `season` | year or ordinal |
| `day` | optional, day within a multi-day course |
| `number` | counting number, within the day when `day` is set |
| `title` | |
| `artist` | |
| `lang` | BCP 47; see Rules |
| `default` | marks the default audio track. Exactly one per video; zero means the first source, more than one is an error |
| `url` | the master playlist |
| `referer` | captured from the player's own request |

Video identity is `(show, season, day, number)`. Rows sharing it are one video and their
sources merge into its audio tracks. A group of one is a plain download.

Row identity is `(show, season, day, number, lang)`. Two rows of one video with the same
language are a duplicate. Nothing else is needed to identify a row, so there is no id
column: the tuple survives reordering and reformatting on its own.

`show`, `season`, `day`, `number`, `title`, `artist` describe the **video** and are
shared by all its language rows. `lang`, `url`, `referer`, `default` describe **one
source**. Editing an item-level field on one row means editing it on its siblings.

## Capture

`vidkit capture <plan.tsv> [url]`

A headed browser with a panel injected into every document, including cross-origin
embeds, surviving navigation between pages. The browser profile persists, so a
magic-link login is done once.

**Picking.** Clicking into a panel field arms it. Type and it is a text box; move onto
the page and hovering outlines elements with a preview of the text you would get.
Click to fill. Escape cancels. Arming `url` and clicking the player binds that video.

**Streams.** Every `.m3u8` / `.mpd` request is classified from the body the player
received - `#EXT-X-STREAM-INF` means master, `#EXTINF` means a variant. Masters are
recorded against the frame that requested them. Nothing binds until you pick a player.
Picking one binds the master that frame loaded; if that frame loaded several, the panel
offers the choice rather than guessing.

**Saving.** Four buttons say what the next row is, not what this one was:

| button | effect |
|---|---|
| add another language to it | keeps everything, clears `lang` and the video |
| start the next video | `number` + 1, clears the title |
| start a new day | `day` + 1, `number` back to 1 |
| start a different course | clears everything |

The plan is written to disk after every save, not at the end. A browser crash costs the
row in progress, never the ones already saved.

**Suggestions.** `show`, `title` and `artist` offer values already used in the plan,
fuzzy-matched. Matched characters are marked; characters that match only case-
insensitively are marked differently. Enter takes the top one.

**Plan view.** Two tabs: items grouped by course with their languages, and the file
tree that would be written with audio tracks per file. Clicking a language loads that
source into the form for repair; clicking x removes a video and all its languages.
Rows that fail validation are marked.

## Editing

No vidkit command. The plan is a TSV; use `nu`, `visidata`, `miller`, `awk`, a
spreadsheet, or a text editor.

Note that BSD `column` (what macOS ships) collapses adjacent delimiters, so a row with
an empty field renders shifted and wrong. Use a tool that respects empty fields -
`visidata`, `miller`, `nu`, or an `awk` one-liner.

Editing is for **repair**: change a value, delete a row. Creation is capture's job -
you cannot type a stream URL you do not have.

## Commands

| command | arguments | exit |
|---|---|---|
| `vidkit capture` | `<plan.tsv> [url]` | 0 |
| `vidkit process` | `<plan.tsv> [--dry-run]` | 0 all written, 1 any failed or plan invalid |
| `vidkit doctor` | | 0 all tools present and roots configured, 1 anything missing |

## Validation

Not a command. `process` validates the whole plan before it touches the network, and
reports every problem found rather than the first.

The point is not input hygiene - it is that a forty-video plan runs for hours, and you
must not learn at hour three that row 12 has a language mkvmerge will reject. A good
error message at the moment of failure does not buy that, because the time is already
spent.

One function, used three ways: `process` runs it up front, `--dry-run` is its on-demand
form, and capture runs it to mark bad rows in the plan view.

The checks come from failures actually hit; the error/warning split is a first pass.

| check | severity |
|---|---|
| `lang` not accepted by `mkvmerge --list-languages` | error |
| row has no `url` | error |
| two videos resolve to the same output path | error |
| rows of one video disagree on an item-level field | error |
| two rows of one video share a `lang` | error |
| a video has no `default`, or more than one | warning - first source wins |
| `show` differs from another only by case or whitespace | warning - a typo splitting a group |
| `referer` absent | warning - the download may be refused |

Errors stop the run before anything is fetched. Warnings print and the run continues.

## Process

`vidkit process <plan.tsv> [--dry-run]`

Per video - a group of rows sharing `(show, season, day, number)`:

- Every source is fetched, using its `referer`.
- With more than one source, their audio is aligned before merging.
- The result is one MKV: video from the source with the longest preamble, one audio
  track per source, each carrying its language and a track name, with `default` set.
- Untargeted Matroska tags are written.
- It lands at its output path, and never appears there in a partial state.
- What happened is reported: each video, its sources, the offsets applied, the output
  path, and the reason for anything skipped.

`--dry-run` produces that report without touching the network or the disk.

The video comes from the **longest** preamble so every other audio track shifts forward
and nothing is trimmed. Choosing a shorter source as the base would need a negative
`--sync`, which cuts the head off the other tracks. This is independent of `default`,
which says which audio plays, not where the video comes from.

### State

State is derived, never recorded. **A file at its final name is complete.** Nothing is
written at its final name until it is finished: write `X.part`, then rename. `os.replace`
is atomic within a filesystem, so existence is proof. No status field, no sidecar, no
lock file, no column in the plan.

```
~/.cache/vidkit/
  src/<url-hash>/source.mkv      yt-dlp writes .part itself and resumes it
  src/<url-hash>/audio-8k.raw    mono PCM for correlation
  item/<item-hash>/offsets.json
  item/<item-hash>/merged.mkv
```

| key | derived from |
|---|---|
| `url-hash` | the source URL. It identifies the bytes |
| `item-hash` | the source keys in order, plus `lang`, `default` and the offsets. Everything that changes the muxed bytes |

Title, artist and overview are deliberately **not** in `item-hash`. Tags are applied by
`mkvpropedit` after the mux, so correcting a title is a re-tag - never a re-download,
never a remux. The expensive line is drawn at the download; a remux is a copy with no
re-encode.

The destination is written the same way: copy the merged file to `<dest>.part`, tag it,
rename. On APFS that copy is a copy-on-write clone and near free.

A resumed run starts at the first missing file. A second run of a finished plan does
nothing but verify and report. That is what makes the pipeline idempotent, and it falls
out of the rename rule rather than being built on top of it.

The cache is a cache: safe to delete at any time, never required for correctness.

### Decided

| question | answer |
|---|---|
| Does a failed video abort the run? | No. Skipped, reported at the end, exit 1 |
| Are downloads cached? Keyed how? | Yes, by URL hash, under `~/.cache/vidkit` |
| Is an interrupted download resumed? | Yes. yt-dlp's `.part` already does it |
| One video at a time, or several? | One. yt-dlp already parallelises fragments and mkvmerge does no re-encoding. Add `--jobs` only after measuring that the link is not saturated |
| Where does intermediate state live, and who cleans it up? | The cache. Nobody has to; it is safe to delete |

## Sync detection

Each source is internally consistent: its preamble sits in both its video and its audio,
so a source never drifts against itself. Sources differ only in how long that preamble
runs before the lecture starts, and they share a jingle at that point - the same fixed
marker in both, like a clapperboard.

So two sources are related by exactly one constant offset. Cross-correlation finds it:
sliding one signal against the other locks onto the jingle wherever it sits, so a
differing preamble is handled by the method rather than defeating it.

Both signals are mono PCM at 8 kHz, extracted with `ffmpeg -ar 8000 -ac 1 -f s16le`.
Mono because the jingle starts at the same instant in both channels. 8 kHz because the
onset of a jingle does not live in the high frequencies. That makes the arrays small
enough for a full-precision FFT correlation in numpy: no value is skipped, and
resolution is 0.125 ms rather than the prototype's 10 ms.

What must hold:

- The window must be long enough that the jingle falls inside it in **both** files.
- The search range must cover the largest difference in preamble length. **Unmeasured.**
  The prototype used +/-5 s, which was a guess. If real preambles differ by 40 s, a
  +/-5 s search returns a confident-looking wrong answer.
- A weak correlation peak refuses the video. Never applied silently.

Not supported, and refused rather than guessed at:

- sources with no shared jingle
- sources paced differently, so that no single offset exists
- a cut or ad break present in one source and not the other

## Output layout

Roots come from `~/.config/vidkit/config.toml`, overridable per run:

```toml
series_root     = "/Volumes/media/Shows"
standalone_root = "/Volumes/media/Films"
```

`doctor` reports them when unset. `process --dry-run` cannot print a tree without them.

```
Introduction to Foo/Season 2026/Introduction to Foo - S2026E0101 - What Foo Is.mkv
A Talk About Bar (2023)/A Talk About Bar (2023).mkv
```

Container is MKV. Series and standalone items go to separate roots. Artist is carried
in tags, not in filenames.

`day` and `number` derive the episode token: four digits when `day` is set (`E0302`),
two when it is not (`E03`). The sort integer is `day*100 + number`.

## Rules

1. Filenames carry an explicit `S{season}E{episode}` anchor. Without it a bare year in
   the name is misparsed as a season/episode pair.
2. Matroska tags are written **untargeted**. Targeted tags are namespaced by ffprobe
   and ignored by the media server.
3. Metadata never goes through ffmpeg's MP4 muxer - it truncates integers to 8 bits.
4. mkvmerge track IDs are per input file, not global.
5. Series, season and episode come from the path. Tags carry title and overview.
6. `lang` is BCP 47: a 2-3 letter primary subtag known to `mkvmerge --list-languages`,
   optionally a 4-letter script and a 2-letter or 3-digit region. Common words are
   translated to codes on entry; anything else is rejected before it can reach the mux.
7. Sync is one constant offset, found by correlating a shared jingle. A weak peak
   refuses the video rather than emitting a silently wrong merge.
8. A stream binds to a video only on evidence: the frame that requested it, or a
   deliberate choice. Never proximity, never recency.
9. A file at its final name is complete. Nothing is written at its final name until it
   is finished.
10. Tags are applied after the mux, not during it. A metadata fix must never cost a
    download or a remux.

## External tools

| tool | source | used for |
|---|---|---|
| yt-dlp | python import | download |
| ffmpeg / ffprobe | mise | probing, PCM extraction |
| mkvmerge / mkvpropedit | brew - not in the mise registry | mux, tags, language validation |

Checked for at startup; missing ones are named along with how to install them, per
platform. No re-exec, no auto-install, no assumption that mise is present.

## Build order

**Process first.** Capture is built and proven; process is unverified and holds every
remaining unknown - whether the captured referer is enough, whether sync works on real
dubs, whether the output displays correctly. Plans can be hand-written, so process does
not need capture to exist.

Each step is a PR worth a changelog line, and leaves the tool working.

| # | change | done when |
|---|---|---|
| 1 | plan read/write, validation | a hand-written plan is parsed and every problem in the validation table is reported, with the right exit code |
| 2 | `doctor`, path resolution, `process --dry-run` | a hand-written plan prints its output tree and intended actions; no network, no writes |
| 3 | download one source | a single-source plan fetches to the cache, resumes on re-run, leaves nothing behind on failure |
| 4 | single-source video end to end | that plan produces a tagged MKV at the correct path |
| 5 | merge, assuming zero offset | a two-source video becomes one MKV with two named audio tracks and the right default |
| 6 | sync detection | a synthetic pair with a known offset is measured within tolerance; a mismatched pair refuses instead of merging |
| 7 | capture, ported from `prototype/` | a captured plan processes without hand editing |

Steps 1 and 2 need no external binaries and no network. That is where the test suite
gets built.

## Testing

Test where being wrong is silent. Every defect found while prototyping was a plausible
design that failed quietly, never a crash:

- a stream bound to the wrong video because capture deduplicated too aggressively
- a field that could never be re-armed because focus and state disagreed
- an edit that split one video into two files because item and source fields were conflated
- aligned columns that could not be parsed back, silently merging two values

So: the naming round trip (`parse(format(x)) == x`), sync against a known offset, the
validation rules, grouping - that rows sharing an identity produce exactly one output -
and cache-key derivation, that an irrelevant edit does not invalidate a download.

Things that fail loudly - a missing binary, a malformed URL, mkvmerge rejecting an
argument - do not need tests.

`mkvmerge --list-languages` sits behind one function so tests can inject a fake and CI
needs no mkvtoolnix.

## Open questions

Both are measurements, not design work, and neither needs any vidkit code to exist.

| # | question | why it matters |
|---|---|---|
| 1 | Does a captured `url` + `referer` still download an hour later? | If the CDN wants a short-lived token, a plan captured on Monday cannot be processed on Tuesday, and the capture/process boundary does not hold. A cookie column fixes an extra credential; nothing fixes an expiring one |
| 2 | How far apart are real preambles? | Sets the correlation search range. Too narrow and sync returns a confident wrong answer |

Settled, recorded so they stop being reopened:

| question | answer |
|---|---|
| Naming template exposed? | No. The `SxxExx` anchor is load-bearing (FINDINGS); a free-form template invites configuring the library into misparsing. Add a named layout if a second one is ever needed |
| Container for `process`? | No. Capture needs your real profile and your logins, so it stays local, and there is no process-only half left to containerise. Keep the code container-ready anyway: no browser in the process path, all paths from config |
| Language? | Python 3.12+. `yt_dlp` is importable with a real API and has no compiled-language equivalent, no Matroska muxer exists outside mkvmerge, and capture is Playwright |
| Cookies captured? | Not yet. Open question 1 decides |

## State

Built and tested (79 checks, `prototype/`): the capture panel, picking, stream
classification and binding, save modes, suggestions, plan and file-tree views,
in-panel editing, TSV plan read/write, loading an existing plan.

Not built: everything in Process. Never tested against a real download - whether the
captured referer is sufficient, whether sync works on real dubs, whether the output
displays as the file-tree view claims.
