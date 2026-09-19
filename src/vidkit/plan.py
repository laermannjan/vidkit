"""The plan: which streams to fetch, how to process them, what metadata to write.

One file, TSV, one row per source URL, tab-delimited with no quoting. Every value has
its whitespace normalised, so none can hold a tab and splitting on tabs is exact. A
quoting dialect would undo that: a title with a quote character in it would come back
spelled differently from the one that went in.

Rows that name the same video are one video, and their sources become its audio tracks.
A group of one is a plain download. What names a video is what its output path is built
from: a series by (series, year, number), a standalone item by its year and title.

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
    "series",
    "year",
    "number",
    "title",
    "artist",
    "lang",
    "default",
    "url",
    "referer",
)

# Describe the video, so every source of it carries the same values.
ITEM_FIELDS = ("series", "year", "number", "title", "artist")
# Describe one source, and are edited on their own.
SOURCE_FIELDS = ("lang", "default", "url", "referer")

# A video is one output file, so what tells two videos apart is what their paths are
# built from, and nothing else. An empty series is a standalone item, filed as
# "Title (year)", so its title identifies it where a series uses its number.
SERIES_IDENTITY = ("series", "year", "number")
STANDALONE_IDENTITY = ("series", "year", "title")

# Written into the default column. Anything non-empty reads back the same way.
DEFAULT_MARK = "x"

_TEXT_FIELDS = tuple(name for name in COLUMNS if name != "default")

Identity = tuple[str, ...]


class PlanError(ValueError):
    """The text is not a plan."""


def _normalise(value: str) -> str:
    # Composition as well as whitespace. "Café" and "Café" are one series to a reader
    # and to a filesystem, but two strings to casefold, so the spelling check would
    # never see them as the same and the plan would file two series.
    return unicodedata.normalize("NFC", " ".join(value.split()))


def _pad(value: str) -> str:
    # Zero padding is not information: 3, 03 and 0003 are one video, and left as typed
    # they would be three of them with nothing said about it. Padded rather than
    # stripped bare, so a number written as {ddnn} still reads as a day and a counter.
    # ASCII digits only. str.isdigit() is true for the superscripts and the circled
    # forms, which int() then refuses, and true for the other decimal scripts, which
    # int() accepts and would quietly rewrite as ASCII. Neither is a counting number
    # anyone typed on purpose, so both are left exactly as written.
    if not (value.isascii() and value.isdigit()):
        return value
    number = int(value)
    return f"{number:04d}" if number >= 100 else f"{number:02d}"


@dataclass(frozen=True, slots=True)
class Source:
    """One row: one stream URL and everything said about it."""

    series: str = ""
    year: str = ""
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
        object.__setattr__(self, "number", _pad(self.number))

    @property
    def identity(self) -> Identity:
        return tuple(getattr(self, name) for name in _identity_fields(self.series))


@dataclass(frozen=True, slots=True)
class Video:
    """One output file and the sources that feed it."""

    series: str
    year: str
    number: str
    title: str
    artist: str
    sources: tuple[Source, ...]

    @property
    def identity(self) -> Identity:
        return tuple(getattr(self, name) for name in _identity_fields(self.series))


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
                    series=head.series,
                    year=head.year,
                    number=head.number,
                    title=head.title,
                    artist=head.artist,
                    sources=tuple(self.sources[row] for row in rows),
                )
            )
        return tuple(videos)


def _identity_fields(series: str) -> tuple[str, ...]:
    return SERIES_IDENTITY if series else STANDALONE_IDENTITY


def _groups(sources: Sequence[Source]) -> dict[Identity, list[int]]:
    """Row indices per video, first named first."""
    groups: dict[Identity, list[int]] = {}
    for row, source in enumerate(sources):
        groups.setdefault(source.identity, []).append(row)
    return groups


# --- the file ---------------------------------------------------------------------


def parse(text: str) -> Plan:
    # A byte order mark survives utf-8 decoding and would otherwise ride into the first
    # header name, so the header reads as unknown and the column it names as missing.
    text = text.removeprefix("\ufeff")
    # Only a truly empty line is skipped. A row whose every field is empty is eight
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
            said = f"line {number} has {len(cells)} fields where the header names {len(header)}"
            if len(cells) < len(header):
                # Loud and recoverable beats padding the row out: a tab deleted between
                # two values would shift every value after it into the wrong column, and
                # padding the tail would accept that silently.
                said += (
                    "; an editor that trims trailing whitespace drops the tab "
                    "of an empty last column"
                )
            raise PlanError(said)
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
            file.flush()
            os.fsync(file.fileno())
        _carry_mode(path, temporary)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _carry_mode(path: Path, temporary: str) -> None:
    # mkstemp creates 0600 and os.replace carries the temporary file's mode onto the
    # plan, so saving would narrow a file the user had made readable by anyone else.
    try:
        os.chmod(temporary, path.stat().st_mode & 0o777)
    except FileNotFoundError:
        umask = os.umask(0)
        os.umask(umask)
        os.chmod(temporary, 0o666 & ~umask)


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
        *_series_problems(plan),
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
    for rows in _groups(plan.sources).values():
        sources = [plan.sources[row] for row in rows]
        label = _label(sources[0])
        problems += _unidentified(label, rows, sources)
        problems += _disagreements(label, rows, sources)
        problems += _duplicate_languages(label, rows, sources)
        problems += _default_problems(label, rows, sources)
    return problems


def _unidentified(label: str, rows: list[int], sources: list[Source]) -> list[Problem]:
    # The field a video is told apart by has to be there. Without it every half-filled
    # row in the plan shares one identity and they merge into a single video with one
    # audio track each, which is the failure the identity rule exists to prevent - and
    # the same missing field is what leaves the video with no path to be written to.
    head = sources[0]
    if head.series and not head.number:
        said = f"{label} has no number, so it cannot be told from another video of the series"
    elif not head.series and not head.title:
        # No label here: it would render as "(untitled)" and say the same thing twice.
        said = "a standalone video has no title, so it cannot be told from another"
    else:
        return []
    return [Problem(Severity.ERROR, said, tuple(rows))]


def _disagreements(label: str, rows: list[int], sources: list[Source]) -> list[Problem]:
    problems = []
    # The identity fields are what grouped these rows, so only the rest can differ.
    identity = _identity_fields(sources[0].series)
    for name in (name for name in ITEM_FIELDS if name not in identity):
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


def _series_problems(plan: Plan) -> list[Problem]:
    # Whitespace and composition variants cannot reach this far, since every value is
    # normalised on construction. Only case can still split one series in two.
    names: dict[str, dict[str, list[int]]] = {}
    for row, source in enumerate(plan.sources):
        if not source.series:
            continue
        spellings = names.setdefault(source.series.casefold(), {})
        spellings.setdefault(source.series, []).append(row)
    problems = []
    for spellings in names.values():
        if len(spellings) > 1:
            rows = sorted(row for where in spellings.values() for row in where)
            said = ", ".join(repr(value) for value in sorted(spellings))
            problems.append(
                Problem(
                    Severity.WARNING,
                    f"one series is spelled {len(spellings)} ways and files as "
                    f"{len(spellings)} series: {said}",
                    tuple(rows),
                )
            )
    return problems


def _label(source: Source) -> str:
    title = source.title or "(untitled)"
    if not source.series:
        return f"{title} ({source.year})" if source.year else title
    said = [source.series]
    if source.year:
        said.append(f"S{source.year}")
    if source.number:
        said.append(f"E{source.number}")
    return " ".join(said)
