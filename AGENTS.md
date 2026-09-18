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

### Planning and design

Put specs, plans and task breakdowns in the pull request body. Revise that body
as the scope changes, and again before merging, where it becomes the description
of the finished work.

Avoid committing files that hold plans, task specs, or other ephemeral prose.

Work coordinated across several pull requests gets its own issue, labelled
`tracking`. Write its body as prose: what is being built and what it covers,
without implementation detail. Follow that with the work broken into PR-sized
packages, nested where that helps - ordered for work that depends on what comes
before it, unordered for work that can run in parallel. Link each package to its
pull request and keep the technical detail in that body. The comments are the
discussion.

### Changes

- Short branches off `main`. Never push to `main` directly.
- Squash merge, so the PR title becomes the commit subject. CI checks the title.
- `mise run check` before pushing. `hk` runs the fast checks on commit.
- A PR that needs two changelog lines to describe is worth splitting in two.

**Title and body reach the changelog**, the title verbatim through git-cliff.
Before merging, reassess whether both still describe what the PR does.

The title MUST follow conventional commit format; intermediate commit subjects
SHOULD too.

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

### Working with agents

- Propose before anything outward-facing: pushing, opening a PR, creating a
  repository, changing settings.
- Verify. Read the file, run the command, check the API.
- Do not claim something works without having run it.
- Fix the cause of a failing check.
