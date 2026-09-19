"""Whether a language tag is one mkvmerge will take.

mkvmerge is the authority. vidkit embeds no list of codes and adds no rule of its
own, so a tag is valid here exactly when the muxer that has to write it says so.
"""

from __future__ import annotations

import os
import subprocess
from functools import cache

MKVMERGE = "mkvmerge"

# mkvmerge has no "validate this tag" command, but it parses --default-language before
# it looks for input files, so a run with a destination and no input judges the tag and
# reads nothing. --list-languages is not a substitute: it prints the bibliographic
# ISO 639-2/B code only, so deu, fra, nld, ces and the other terminological codes are
# missing from it while mkvmerge accepts them all.
_PROBE = ("-o", os.devnull, "--default-language")

# Both outcomes exit 2 and write to stdout, so only the message tells them apart.
_PARSED = "No source files were given"
_INVALID = "is not a valid IETF BCP 47"
_REASON = "Additional information from the parser:"

# mkvmerge translates its messages, and the messages above are what this reads.
_ENGLISH = {"LC_ALL": "C", "LANG": "C", "LANGUAGE": ""}


class MkvmergeUnavailable(RuntimeError):
    """mkvmerge could not be asked, so no tag can be judged."""


@cache
def tag_problem(tag: str) -> str | None:
    """What mkvmerge objects to in `tag`, or None when it accepts it."""
    # The tag goes to mkvmerge as its own argument, and mkvmerge has no --opt=value
    # form to pin it down as a value. A tag starting with '-' would be read as an
    # option; one starting with '@' as an options file, which mkvmerge would open and
    # obey. Neither can be a language tag, so neither is handed over.
    if tag.startswith(("-", "@")):
        return "a language tag cannot start with '-' or '@'"
    return _verdict(tag, _probe(tag))


def _verdict(tag: str, output: str) -> str | None:
    if _PARSED in output:
        return None
    if _INVALID in output:
        _, _, reason = output.partition(_REASON)
        return reason.strip() or "not a language tag"
    raise MkvmergeUnavailable(f"mkvmerge said something unexpected about {tag!r}: {output.strip()}")


def _probe(tag: str) -> str:
    try:
        done = subprocess.run(
            [MKVMERGE, *_PROBE, tag],
            capture_output=True,
            text=True,
            timeout=20,
            env={**os.environ, **_ENGLISH},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise MkvmergeUnavailable(f"could not run {MKVMERGE}: {exc}") from exc
    return done.stdout
