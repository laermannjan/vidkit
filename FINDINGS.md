# Measured behaviour

Facts established by testing, not inference. Kept out of SPEC.md so the spec stays a
description of what to build. Jellyfin results are from 12.1.0 in Docker, internet
metadata providers disabled, TV Shows library.

## Jellyfin metadata resolution

| Field | Source |
|---|---|
| Series name, season number, episode number | path and filename, always |
| Title | embedded tag, else the full filename stem |
| Overview | embedded tag |
| Premiere date, people, studio | NFO only |

- Embedded title and overview read identically from MKV and MP4.
- Embedded episode/season numbers ignored even with `EnableEmbeddedEpisodeInfos: true`.
  A tag claiming episode 99 lost to a path saying 3.
- With no tag and no NFO the title is the entire filename stem, not a parsed portion.

## Matroska tags must be untargeted

| Tag form | ffprobe key | Jellyfin |
|---|---|---|
| Targeted (`TargetTypeValue` 50/60/70) | `EPISODE/TITLE` | ignored |
| Untargeted (empty `<Targets>`) | `TITLE` | read |
| MP4 ItemList | `title` | read |

Jellyfin matches a plain `title`. Targeted tags get namespaced by ffprobe and never
match. Overview key: MKV `SYNOPSIS` or `DESCRIPTION`; MP4 `description`.

## Filename parsing beats folder naming

`Bar Course - 2026 - Alpha.mkv` in a `Season 2026/` folder resolved to **season 20,
episode 26** - the bare `2026` was parsed as `S20E26`.

`Show - S2026E03 - Title.mkv` in `Season 2026/` resolved correctly. Year-as-season
works, but only with an explicit `SxxExx` anchor.

## MP4 integer fields truncate to 8 bits

`season_number=2026` through ffmpeg produces a `tvsn` atom of `0x000000ea`, read back
as **234**. exiftool writes the full integer. Same defect class as the Garmin 255-track
overflow in split-audiobook.

## mkvmerge

```
mkvmerge -o out.mkv \
  --language 1:ger --track-name 1:Deutsch --default-track-flag 1:yes base.mkv \
  --no-video --audio-tracks 1 --sync 1:1500 \
  --language 1:eng --track-name 1:English --default-track-flag 1:no merge.mkv
```

- Track IDs are per input file. A video file's audio track is usually id 1, not 0.
  Targeting 0 silently applies options to the video track being dropped.
- Re-merging preserves existing track names, so track metadata never needs re-deriving.
- Languages: accepts BCP 47 2- and 3-letter codes, normalises to ISO 639-2/B
  (`de`→`ger`, `ja`→`jpn`, `zh`→`chi`). Rejects full words (`german`, `english`).

## Language tags

`mkvmerge --list-languages` prints every code it accepts - 8970 of them. That is the
authoritative source; there is no need to embed a list.

| input | result |
|---|---|
| `de`, `deu`, `ger`, `DE` | accepted, all stored as `language=ger`, `ietf=de` |
| `pt-BR`, `zh-Hans`, `es-419`, `de-Latn-DE` | accepted, subtag preserved |
| `nb` vs `no` | distinct (`nob` / `nor`) - collapsing them loses meaning |
| `pfe` | accepted, a real ISO 639-3 code |
| `pfe-dfasdf` | rejected |
| `xx`, `german`, `deutsch` | rejected |

So mkvmerge normalises 2/3-letter codes itself and keeps regional subtags. Only full
words need translating before they reach it.

Shape: a 2-3 letter primary subtag, then optionally a 4-letter script and a 2-letter or
3-digit region. BCP 47 also allows 5-8 character variant subtags, but they must be
IANA-registered - permitting them is what let `pfe-dfasdf` through a shape check.

## Line sizes

Measured on a real captured row:

| part | chars |
|---|---|
| full row | 228 |
| metadata only | 60 (81 aligned) |
| url + referer | 166 - 72% of the line |

## Tooling

- `#!/usr/bin/env -S mise x ffmpeg yt-dlp -- uv run --script` works from any directory,
  ~110ms warm, auto-installs a missing tool (verified with an uninstalled `dasel`).
- mise registry: no `mkvtoolnix`, `m4b-tool`, `mp4v2`. `exiftool` is conda-only.
- No Matroska muxer library exists in Rust or Go. `matroska` crate parses metadata only.
- No yt-dlp replacement exists in any compiled language; the Rust crates named for it
  shell out to the binary. In Python `yt_dlp` is importable with a real API.

## Defects in the current tools

1. `savid-retag` reads back 1 of `savid`'s 4 filename shapes. `Show - Title`,
   `Artist - Title` and `Title` are silently skipped as "unexpected format".
2. `mergid` guards a multi-stream base only in the `--lang-base` branch, not the
   auto-detect branch. Metadata then lands on the wrong tracks.
3. `mergid` auto-sync correlates the first 10s, documented as relying on a shared intro
   jingle. The actual problem is intros that differ in length.
4. `--download-archive archive.log` in `~/.config/yt-dlp/config` is CWD-relative, so the
   archive fragments per directory. No `archive.log` exists under `~`.
5. `mkvtoolnix`, `exiftool`, `m4b-tool`, `mp4v2` are brew-installed but absent from
   `[bootstrap.packages]`.
