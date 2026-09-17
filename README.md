# vidkit

Gets course and lecture video off the web into a media library: captures the streams,
downloads them, merges per-language voice-overs into one multi-audio file, corrects the
audio offset, tags, and files them.

## Where to start

| file | what it is |
|---|---|
| `SPEC.md` | what to build. Read first |
| `FINDINGS.md` | facts established by testing, not inference. Read before changing anything it covers |
| `prototype/` | a working capture panel. Reference implementation, not production code |

Build order is in `SPEC.md`. **Process first** - capture is built and proven, process is
unverified and holds every remaining unknown.

## The prototype

Proves the capture design works. 79 checks across four suites:

```
prototype/run-tests.sh
```

It serves its own fixtures, so no setup. Needs `uv`; the scripts declare their own
dependencies and fetch a browser on first run (~90 MB).

To use it against a real page:

```
prototype/capture.py plan.tsv https://example.com/course
```

The plan file is the state - loaded if it exists, started empty if not.

**What it is not:** a CLI, packaged, or structured for reuse. It is one script and one
injected panel, kept deliberately close to the thing it proves. Port it in PR 7; do not
extend it in place.

## What is not built

Everything in `SPEC.md` under Process. Nothing has ever been run against a real
download, so these are all open:

- whether the captured `referer` is enough, or cookies are needed too
- whether sync works on real dubs, and what window and search range they need
- whether the output displays the way the file-tree view claims

`SPEC.md` marks the process design decisions that were deliberately left open.
