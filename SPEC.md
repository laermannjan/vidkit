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
where the external binaries live and is the half worth containerising. The plan file is
the boundary.

## Plan file

**The file is the state.** `vidkit capture plan.tsv` loads whatever is there, or starts
empty if the file is absent or empty. No separate init, no append mode.

**Plans are temporary.** Capture, process, done - then delete it. Nothing is designed
around keeping one.

TSV, one file, one row per source URL. Tab-delimited with no quoting: capture
normalises whitespace on every value, so no field can contain a tab.

| column | notes |
|---|---|
| `id` | stable row identity, survives reordering and reformatting. Opaque, unique within a plan, never reused |
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

Item identity is `(show, season, day, number)`. Rows sharing it are one video and their
sources merge into its audio tracks. A group of one is a plain download.

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

**Suggestions.** `show`, `title` and `artist` offer values already used in the plan,
fuzzy-matched. Matched characters are marked; characters that match only case-
insensitively are marked differently. Enter takes the top one.

**Plan view.** Two tabs: items grouped by course with their languages, and the file
tree that would be written with audio tracks per file. Clicking a language loads that
source into the form for repair; clicking × removes a video and all its languages.

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
| `vidkit check` | `<plan.tsv>` | 0 clean, 1 problems found |
| `vidkit process` | `<plan.tsv> [--dry-run]` | 0 all written, 1 any failed |
| `vidkit doctor` | | 0 all tools present, 1 any missing |

## check

Runs before processing and on demand. Reports every problem found, not the first.
The checks come from failures actually hit; the error/warning split is a first pass.

| check | severity |
|---|---|
| `lang` not accepted by `mkvmerge --list-languages` | error |
| row has no `url` | error |
| two videos resolve to the same output path | error |
| `id` missing or duplicated | error |
| rows of one video disagree on an item-level field | error |
| a video has no `default`, or more than one | warning - first source wins |
| `show` differs from another only by case or whitespace | warning - a typo splitting a group |
| `referer` absent | warning - the download may be refused |

## Process

Not built, and not thought through. What follows is what must be true, not how.

Per video - a group of rows sharing `(show, season, day, number)`:

- Every source is fetched, using its `referer`.
- With more than one source, their audio is aligned before merging.
- The result is one MKV: video from the first source, one audio track per source, each
  carrying its language and a track name, with `default` set.
- Untargeted Matroska tags are written.
- It lands at its output path, and never appears there in a partial state.
- What happened is reported: each video, its sources, the offsets applied, the output
  path, and the reason for anything skipped.

`--dry-run` produces that report without touching the network or the disk.

Deliberately not decided:

| question |
|---|
| Does a failed video abort the run, or get skipped and reported at the end? |
| Are downloads cached? Keyed how? Does a re-run refetch? |
| Is an interrupted download resumed or discarded? |
| One video at a time, or several in parallel? |
| Where does intermediate state live, and who cleans it up? |

## Sync detection

Language variants share a jingle near the start - the same fixed marker in both, like a
clapperboard. What varies is how much precedes it. Cross-correlation finds it: sliding
one signal against the other locks onto the jingle wherever it sits, so a differing
lead-in is handled by the method rather than defeating it.

What must hold:

- The window must be long enough that the jingle falls inside it in **both** files.
- The search range must cover the largest difference in lead-in.
- Precision must not be traded away to make the search affordable. The current
  implementation samples every tenth value at 10 ms steps - a speed workaround in pure
  Python, not a decision.
- A weak correlation peak is reported as low confidence, never applied silently.

The existing implementation uses a 10 s window and a ±5 s range. Whether that is enough
depends on how long lead-ins actually run, which nobody has measured. Measure before
choosing numbers.

Unproven idea: correlate a second window from the middle of the file as a consistency
check. If it disagrees with the first, the two are not related by a single constant
offset - a case probably worth refusing rather than merging.
## Output layout

```
Introduction to Foo/Season 2026/Introduction to Foo - S2026E0101 - What Foo Is.mkv
A Talk About Bar (2023)/A Talk About Bar (2023).mkv
```

Container is MKV. Series and standalone items go to separate output roots. Artist is
carried in tags, not in filenames.

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
7. Sync samples several windows across the file, reports the median, and refuses with a
   warning when they disagree - rather than emitting a silently wrong merge.
8. A stream binds to a video only on evidence: the frame that requested it, or a
   deliberate choice. Never proximity, never recency.

## External tools

| tool | source | used for |
|---|---|---|
| yt-dlp | python import | download |
| ffmpeg / ffprobe | mise | probing, PCM extraction |
| mkvmerge / mkvpropedit | brew - not in the mise registry | mux, tags, language validation |

Checked for at startup; missing ones are named along with how to install them. No
re-exec, no auto-install, no assumption that mise is present.

## Build order

**Process first.** Capture is built and proven; process is unverified and holds every
remaining unknown - whether the captured referer is enough, whether sync works on real
dubs, whether the output displays correctly. Plans can be hand-written, so process does
not need capture to exist.

Each step is a PR worth a changelog line, and leaves the tool working.

| # | change | done when |
|---|---|---|
| 1 | plan read/write, `check` | a hand-written plan is parsed and every problem in the check table is reported, with the right exit code |
| 2 | `doctor`, path resolution, `process --dry-run` | a hand-written plan prints its output tree and intended actions; no network, no writes |
| 3 | download one source | a single-source plan fetches to the cache, resumes on re-run, leaves nothing behind on failure |
| 4 | single-source video end to end | that plan produces a tagged MKV at the correct path |
| 5 | merge, assuming zero offset | a two-source video becomes one MKV with two named audio tracks and the right default |
| 6 | sync detection | a synthetic pair with a known offset is measured within tolerance; a mismatched pair warns instead of merging |
| 7 | capture, ported from `prototype/` | a captured plan passes `check` and processes without hand editing |

## Testing

Test where being wrong is silent. Every defect found while prototyping was a plausible
design that failed quietly, never a crash:

- a stream bound to the wrong video because capture deduplicated too aggressively
- a field that could never be re-armed because focus and state disagreed
- an edit that split one video into two files because item and source fields were conflated
- aligned columns that could not be parsed back, silently merging two values

So: the naming round trip (`parse(format(x)) == x`), sync against a known offset, the
check rules, and grouping - that rows sharing an identity produce exactly one output.

Things that fail loudly - a missing binary, a malformed URL, mkvmerge rejecting an
argument - do not need tests.

## Open questions

| # | Question |
|---|---|
| 1 | Cookies are not captured. Needed for session-gated CDNs? |
| 2 | Naming template is a constant in the source. Worth exposing? |
| 3 | Is a container for `process` worth it, given capture stays local? |
| 4 | Language for the real implementation. Python assumed |

## State

Built and tested (79 checks, `prototype/`): the capture panel, picking, stream
classification and binding, save modes, suggestions, plan and file-tree views,
in-panel editing, TSV plan read/write with generated ids, loading an existing plan.

Not built: everything in Process. Never tested against a real download - whether the
captured referer is sufficient, whether sync works on real dubs, whether the output
displays as the file-tree view claims.
