"""The plan: which streams to fetch, how to process them, what metadata to write.

One file, TSV, one row per source URL, tab-delimited with no quoting. Every value has
its whitespace normalised, so none can hold a tab and splitting on tabs is exact. A
quoting dialect would undo that: a title with a quote character in it would come back
spelled differently from the one that went in.

Rows that agree on (show, season, day, number) are one video, and their sources become
its audio tracks. A group of one is a plain download.

The file is capture's only state. process never writes it.
"""

from __future__ import annotations

import os
import tempfile
import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from vidkit import languages

COLUMNS = (
    "show",
    "season",
    "day",
    "number",
    "title",
    "artist",
    "lang",
    "default",
    "url",
    "referer",
)

# What makes two rows one video.
IDENTITY_FIELDS = ("show", "season", "day", "number")
# Describe the video, so every source of it carries the same values.
ITEM_FIELDS = (*IDENTITY_FIELDS, "title", "artist")
# Describe one source, and are edited on their own.
SOURCE_FIELDS = ("lang", "default", "url", "referer")

# Written into the default column. Anything non-empty reads back the same way.
DEFAULT_MARK = "x"

_TEXT_FIELDS = tuple(name for name in COLUMNS if name != "default")

Identity = tuple[str, str, str, str]


class PlanError(ValueError):
    """The text is not a plan."""


def _normalise(value: str) -> str:
    # Composition as well as whitespace. "Café" and "Café" are one show to a
    # reader and to a filesystem, but two strings to casefold, so the spelling check
    # would never see them as the same and the plan would file two shows.
    return unicodedata.normalize("NFC", " ".join(value.split()))


@dataclass(frozen=True, slots=True)
class Source:
    """One row: one stream URL and everything said about it."""

    show: str = ""
    season: str = ""
    day: str = ""
    number: str = ""
    title: str = ""
    artist: str = ""
    lang: str = ""
    default: bool = False
    url: str = ""
    referer: str = ""

    def __post_init__(self) -> None:
        # Normalising on construction, rather than while parsing, is what holds the
        # file format up: no value can carry a tab or a newline, so a source written
        # out and read back is the same source.
        for name in _TEXT_FIELDS:
            object.__setattr__(self, name, _normalise(getattr(self, name)))

    @property
    def identity(self) -> Identity:
        return (self.show, self.season, self.day, self.number)


@dataclass(frozen=True, slots=True)
class Video:
    """One output file and the sources that feed it."""

    show: str
    season: str
    day: str
    number: str
    title: str
    artist: str
    sources: tuple[Source, ...]

    @property
    def identity(self) -> Identity:
        return (self.show, self.season, self.day, self.number)


@dataclass(frozen=True, slots=True)
class Plan:
    sources: tuple[Source, ...] = ()

    @property
    def videos(self) -> tuple[Video, ...]:
        """The sources grouped, in the order the plan first names each video."""
        videos = []
        for rows in _groups(self.sources).values():
            head = self.sources[rows[0]]
            videos.append(
                Video(
                    show=head.show,
                    season=head.season,
                    day=head.day,
                    number=head.number,
                    title=head.title,
                    artist=head.artist,
                    sources=tuple(self.sources[row] for row in rows),
                )
            )
        return tuple(videos)


def _groups(sources: Sequence[Source]) -> dict[Identity, list[int]]:
    """Row indices per video, first named first."""
    groups: dict[Identity, list[int]] = {}
    for row, source in enumerate(sources):
        groups.setdefault(source.identity, []).append(row)
    return groups


# --- the file ---------------------------------------------------------------------


def parse(text: str) -> Plan:
    # Only a truly empty line is skipped. A row whose every field is empty is nine
    # tabs, which a blank-line test that strips whitespace would throw away.
    lines = [(n, line) for n, line in enumerate(text.splitlines(), start=1) if line]
    if not lines:
        return Plan()
    header = [cell.strip().lower() for cell in lines[0][1].split("\t")]
    _check_header(header)
    sources = []
    for number, line in lines[1:]:
        cells = line.split("\t")
        if len(cells) != len(header):
            raise PlanError(
                f"line {number} has {len(cells)} fields where the header names {len(header)}"
            )
        values = dict(zip(header, cells, strict=True))
        marked = bool(values.pop("default").strip())
        sources.append(Source(default=marked, **values))
    return Plan(tuple(sources))


def format(plan: Plan) -> str:
    lines: list[str] = ["\t".join(COLUMNS)]
    lines += ["\t".join(_cell(source, name) for name in COLUMNS) for source in plan.sources]
    return "\n".join(lines) + "\n"


def read(path: Path) -> Plan:
    """Whatever is in the file. An absent or empty one is an empty plan."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Plan()
    except UnicodeDecodeError as exc:
        raise PlanError(f"{path} is not utf-8: {exc}") from exc
    return parse(text)


def write(path: Path, plan: Plan) -> None:
    # Never in place. The plan is capture's only state, and truncating it to rewrite it
    # means a crash between the first byte and the last leaves nothing to resume from.
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as file:
            file.write(format(plan))
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _check_header(header: Sequence[str]) -> None:
    if len(set(header)) != len(header):
        raise PlanError("the header names a column twice")
    missing = [name for name in COLUMNS if name not in header]
    unknown = [name for name in header if name not in COLUMNS]
    if not missing and not unknown:
        return
    said = []
    if missing:
        said.append("missing " + ", ".join(missing))
    if unknown:
        said.append("unknown " + ", ".join(unknown))
    raise PlanError("the header does not name the plan columns: " + "; ".join(said))


def _cell(source: Source, name: str) -> str:
    if name == "default":
        return DEFAULT_MARK if source.default else ""
    return getattr(source, name)


# --- validation -------------------------------------------------------------------


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Problem:
    severity: Severity
    message: str
    # Indices into Plan.sources, not line numbers: a plan may hold blank lines.
    rows: tuple[int, ...] = ()


LangProblem = Callable[[str], str | None]

_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1}


def validate(plan: Plan, *, lang_problem: LangProblem = languages.tag_problem) -> list[Problem]:
    """Every problem in the plan, errors before warnings.

    Every problem, not the first: a forty-video plan runs for hours and must not stop
    at hour three on a language mkvmerge would have refused in the first second.
    """
    problems = [
        *_language_problems(plan, lang_problem),
        *_row_problems(plan),
        *_video_problems(plan),
        *_show_problems(plan),
    ]
    return sorted(problems, key=lambda problem: _ORDER[problem.severity])


def _language_problems(plan: Plan, lang_problem: LangProblem) -> list[Problem]:
    # One question per distinct tag: mkvmerge is a subprocess, and a plan repeats a
    # handful of languages across all its rows.
    tags: dict[str, list[int]] = {}
    for row, source in enumerate(plan.sources):
        if source.lang:
            tags.setdefault(source.lang, []).append(row)
    problems = []
    for tag, rows in tags.items():
        try:
            why = lang_problem(tag)
        except languages.MkvmergeUnavailable as exc:
            # capture validates on every edit, so a missing mkvmerge has to arrive as a
            # problem in the list rather than as a traceback out of it.
            everywhere = tuple(sorted(row for where in tags.values() for row in where))
            return [
                *problems,
                Problem(Severity.ERROR, f"no language could be checked: {exc}", everywhere),
            ]
        if why is not None:
            problems.append(
                Problem(
                    Severity.ERROR,
                    f"mkvmerge will not take the language {tag!r}: {why}",
                    tuple(rows),
                )
            )
    return problems


def _row_problems(plan: Plan) -> list[Problem]:
    problems = []
    for row, source in enumerate(plan.sources):
        if not source.url:
            problems.append(Problem(Severity.ERROR, "the row has no url", (row,)))
        if not source.referer:
            problems.append(
                Problem(Severity.WARNING, "no referer; the download may be refused", (row,))
            )
    return problems


def _video_problems(plan: Plan) -> list[Problem]:
    problems = []
    for identity, rows in _groups(plan.sources).items():
        label = _label(identity)
        sources = [plan.sources[row] for row in rows]
        problems += _disagreements(label, rows, sources)
        problems += _duplicate_languages(label, rows, sources)
        problems += _default_problems(label, rows, sources)
    return problems


def _disagreements(label: str, rows: list[int], sources: list[Source]) -> list[Problem]:
    problems = []
    # The identity fields are what grouped these rows, so only the rest can differ.
    for name in (name for name in ITEM_FIELDS if name not in IDENTITY_FIELDS):
        spellings = {getattr(source, name) for source in sources}
        if len(spellings) > 1:
            said = ", ".join(repr(value) for value in sorted(spellings))
            problems.append(
                Problem(
                    Severity.ERROR,
                    f"the sources of {label} disagree on {name}: {said}",
                    tuple(rows),
                )
            )
    return problems


def _duplicate_languages(label: str, rows: list[int], sources: list[Source]) -> list[Problem]:
    tags: dict[str, list[int]] = {}
    for row, source in zip(rows, sources, strict=True):
        tags.setdefault(source.lang.casefold(), []).append(row)
    problems = []
    for tag, where in tags.items():
        if len(where) > 1:
            what = f"the language {tag!r}" if tag else "no language"
            problems.append(
                Problem(
                    Severity.ERROR,
                    f"{len(where)} sources of {label} share {what}",
                    tuple(where),
                )
            )
    return problems


def _default_problems(label: str, rows: list[int], sources: list[Source]) -> list[Problem]:
    marked = [row for row, source in zip(rows, sources, strict=True) if source.default]
    if len(marked) > 1:
        return [
            Problem(
                Severity.WARNING,
                f"{len(marked)} sources of {label} are marked default; the first is used",
                tuple(marked),
            )
        ]
    # A lone source is the default whether or not it says so. Warning there would put
    # a line on every video of a single-language plan and teach the reader to skip them.
    if not marked and len(sources) > 1:
        return [
            Problem(
                Severity.WARNING,
                f"no source of {label} is marked default; the first is used",
                tuple(rows),
            )
        ]
    return []


def _show_problems(plan: Plan) -> list[Problem]:
    # Whitespace variants cannot reach this far, since every value is normalised on
    # construction. Only case can still split one show in two.
    shows: dict[str, dict[str, list[int]]] = {}
    for row, source in enumerate(plan.sources):
        if source.show:
            shows.setdefault(source.show.casefold(), {}).setdefault(source.show, []).append(row)
    problems = []
    for spellings in shows.values():
        if len(spellings) > 1:
            rows = sorted(row for where in spellings.values() for row in where)
            said = ", ".join(repr(value) for value in sorted(spellings))
            problems.append(
                Problem(
                    Severity.WARNING,
                    f"one show is spelled {len(spellings)} ways and files as "
                    f"{len(spellings)} shows: {said}",
                    tuple(rows),
                )
            )
    return problems


def _label(identity: Identity) -> str:
    show, season, day, number = identity
    said = [show or "(standalone)"]
    if season:
        said.append(f"S{season}")
    if day:
        said.append(f"D{day}")
    if number:
        said.append(f"E{number}")
    return " ".join(said)
