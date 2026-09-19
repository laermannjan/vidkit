import shutil

import pytest

from vidkit.languages import MkvmergeUnavailable, _verdict, tag_problem

# What mkvmerge v98 writes to stdout. Both outcomes exit 2, so only the text tells
# them apart, and these strings are the whole of what the module reads.
ACCEPTED = "mkvmerge v98.0 ('Chonks') 64-bit\nError: No source files were given.\n"
REFUSED = (
    "mkvmerge v98.0 ('Chonks') 64-bit\n"
    "Error: 'xx' is not a valid IETF BCP 47/RFC 5646 language tag in "
    "'--default-language xx'. Additional information from the parser: The value 'xx' "
    "is not a valid ISO 639 language code.\n"
)

needs_mkvmerge = pytest.mark.skipif(
    shutil.which("mkvmerge") is None, reason="mkvmerge is not installed"
)


def test_no_source_files_means_the_tag_parsed():
    assert _verdict("de", ACCEPTED) is None


def test_a_refusal_carries_the_parser_reason():
    assert _verdict("xx", REFUSED) == "The value 'xx' is not a valid ISO 639 language code."


def test_output_it_cannot_read_is_not_silently_an_answer():
    with pytest.raises(MkvmergeUnavailable):
        _verdict("de", "mkvmerge: command not found")


@pytest.mark.parametrize("tag", ["-o", "@options.json"])
def test_a_tag_mkvmerge_would_read_as_an_argument_is_never_handed_over(tag):
    # '@file' makes mkvmerge open that file and obey the options in it, so a tag
    # shaped like one must not reach the command line at all.
    assert tag_problem(tag) is not None


@needs_mkvmerge
@pytest.mark.parametrize("tag", ["de", "deu", "ger", "en", "pt-BR", "zh-Hans", "es-419", "und"])
def test_mkvmerge_takes_these(tag):
    # deu, fra, nld and the other terminological codes are the reason this asks
    # mkvmerge to parse the tag: --list-languages does not print them.
    assert tag_problem(tag) is None


@needs_mkvmerge
@pytest.mark.parametrize("tag", ["german", "deutsch", "xx", "pfe-dfasdf"])
def test_mkvmerge_refuses_these(tag):
    assert tag_problem(tag) is not None
