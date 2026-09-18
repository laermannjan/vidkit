# Repository Agent Guide

## Development Commands

```sh
mise run check      # lint, typecheck, test - everything CI runs
mise run fmt        # apply formatting
mise run test       # test suite alone
mise run lint       # lint and formatting check alone
mise run typecheck  # type check alone
```

`mise install` provides the tooling. `uv` owns the Python interpreter and
dependencies; `mise` owns everything that is not a Python package. `hk` runs the
fast checks on commit and is installed with `hk install`.

Fix the cause of a failing check, rather than skipping or disabling it.

## Code Architecture

vidkit downloads and processes video from embedded streams.

The **plan** is a text file: which streams, how to process them, what metadata
to write. Human readable, editable by hand.

**capture** helps you build one - browse a site, click the player to take its
stream, click or type the metadata. The plan is its only state, so it resumes.

**process** does what the plan says: download, sync and merge audio, re-mux,
tag, move into place. It resumes too - a failed step costs only itself.

### Where the code lives

- `src/vidkit/` - the package. Today this is the CLI entry point and nothing
  else; none of the above is built yet
- `tests/` - the test suite
- `xtasks/` - repo automation, invoked through `mise` tasks
- `.github/workflows/` - CI and release automation

## Development Guidelines

### Workflow

Issues and milestones are for planning ahead. A pull request is work in
progress.

Give a work package an issue when it is planned, or still only an idea, and
should not be lost. Give a larger effort being planned or brainstormed its own
milestone. Use milestones sparingly; an effort spanning two or three pull
requests does not need one. Work can also start ad-hoc.

Work happens in short-lived pull requests off `main`. Never push to `main`
directly. Keep a pull request as small in scope as possible and as large as
necessary.

Open the pull request as soon as the work is more than something tried quickly
on your own machine, and keep it in draft until it is ready for review. Start on
an issue with `gh issue develop <issue> --checkout`, which links the branch and
closes the issue when the pull request merges.

A spec belongs in the pull request body while the work is in progress, whether
it came out of the issue or out of doing the work. Keep the body current: when
the scope changes, change the title and the body with it. Before merging, clean
the body up so it describes what this pull request did. It becomes the squash
commit message, and feeds the changelog and any summary written from it.

Avoid committing files that hold plans, task specs, or other ephemeral prose.

Squash merge, so the pull request title becomes the commit subject. That is why
CI checks the title.

The title reaches the changelog verbatim through git-cliff. It MUST follow
conventional commit format; intermediate commit subjects SHOULD too.

`<type>[optional scope][optional !]: <description>`

- `feat:` new functionality
- `fix:` corrects the tool behaving wrongly. A repair to CI or to docs is `ci` or `docs`
- `perf:` faster or lighter
- `refactor:` internal restructuring
- `docs:` documentation, wherever it lives
- `test:` tests
- `style:` formatting
- `build:` packaging, dependencies, installation
- `ci:` automation
- `chore:` anything else, releases included
- `revert:` reverts an earlier change

Classify by what the change is. If two types fit, either is fine. `feat`, `fix`,
`perf`, `refactor`, `docs`, `test` and `revert` get their own changelog section;
everything else lands under Chore.

**Scopes** are optional: one word for the concept affected, reusing whatever is
already in the log - `plan`, `naming`, `sync`, `cache`, `capture`, `release`.

**Breaking changes** take a `!`, and the body says what to do instead.

**Descriptions** start lowercase, use imperative mood, and name what changed:

```
feat(sync): detect the offset from the shared jingle
feat(process): skip a failed video and report it at the end
fix(naming): keep the SxxExx anchor when the season is a year
perf(sync): correlate at full resolution via FFT instead of decimating
ci(release): tag the commit the release PR brings in
chore: release 2026.9.1
feat(plan)!: drop the id column
```

**The body** says why. For a fix, the trigger and the before and after. For a
feature, a short example. For a speed claim, the measurement.

### Releasing

A bot keeps a release PR up to date with the CalVer bump (`YYYY.M.PATCH`) and
the regenerated changelog. Merging that PR is the release: CI tags the merge
commit, which creates the GitHub Release.

`CHANGELOG.md` is generated. Never hand-edit it.

### Testing

Write tests where being wrong is silent: a plausible result that is quietly
incorrect.

### Documenting code

Do not document what the code does.

A comment stops someone undoing a non-obvious decision at that line:
`# ffmpeg's MP4 muxer truncates this to 8 bits`, beside the code that avoids it.

Do not leave standing claims about how the system behaves.

## Conduct

### Tone and language

When talking with a developer, write in Simplified Technical English (ASD-STE100):
short sentences, one idea in each, plain words, active voice.

A technical term has to earn its place against a plain phrase. Abbreviations and
acronyms have to earn more. Introduce or motivate a term the first time it carries
weight.

When explaining something larger - a concept, a design, a body of work - build it in
layers, so the reader could believe they would have arrived at it themselves. Say what
was chosen and what was rejected. Walk the chain: the problem, then the obvious first
attempt, then where it breaks or what it costs, then what that forces next.

When writing user-facing documentation, or longer prose that will persist somewhere,
follow "The Elements of Style".

Name a pull request or an issue by number and title. "#6, plan: read, write and
validate a plan file" rather than "#6" alone.

### Acting

Propose before anything outward-facing or hard to reverse: pushing, opening a pull
request, creating a repository, changing settings.

Verify instead of recalling. Read the file, run the command, check the API. Say
plainly what you did not verify.
