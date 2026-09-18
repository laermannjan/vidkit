# vidkit

vidkit downloads and processes video from embedded streams.

The **plan** is a text file: which streams, how to process them, what metadata to
write. Human readable, editable by hand.

**capture** helps you build one - browse a site, click the player to take its
stream, click or type the metadata. The plan is its only state, so it resumes.

**process** does what the plan says: download, sync and merge audio, re-mux, tag,
move into place. It resumes too - a failed step costs only itself.

## Install

```sh
uv tool install git+https://github.com/laermannjan/vidkit
```

Needs `ffmpeg`, `mkvmerge` and `mkvpropedit` on `PATH`. `vidkit doctor` names what is
missing and how to install it.

## State

Nothing is built yet beyond the CLI entry point, and nothing has ever run against a real
download. The work is tracked in the [MVP milestone](https://github.com/laermannjan/vidkit/milestone/1).

`prototype/` is a working capture panel that proves the design: a browser with an
injected panel, stream classification, and plan read/write. 79 checks across four suites:

```sh
prototype/run-tests.sh
```

It serves its own fixtures, so no setup is needed. It is not a CLI, not packaged, and
its plan format is a generation behind the one the milestone describes. It gets ported,
not extended.

## Contributing

`AGENTS.md` covers how work is done here.
