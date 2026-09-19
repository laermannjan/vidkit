import unicodedata

import pytest

from vidkit.languages import MkvmergeUnavailable
from vidkit.plan import (
    COLUMNS,
    Plan,
    PlanError,
    Severity,
    Source,
    format,
    parse,
    read,
    validate,
    write,
)


def source(**fields) -> Source:
    return Source(url="https://example.test/master.m3u8", referer="https://example.test/", **fields)


def only(tag: str) -> str | None:
    """A language check that needs no mkvmerge."""
    return None if tag in {"de", "en", "pt-BR"} else "not a language"


def problems(plan: Plan):
    return validate(plan, lang_problem=only)


# --- the file ---------------------------------------------------------------------


AWKWARD = Plan(
    (
        Source(
            series='The "Foo" Course',
            year="2026",
            number="0302",
            title="Foo, Bar & 'Baz' — 50% done",
            artist="Jane Roe",
            lang="pt-BR",
            default=True,
            url="https://example.test/m.m3u8?a=1&b=2",
            referer="https://example.test/",
        ),
        Source(),
        Source(title="standalone", url="https://example.test/s.m3u8"),
    )
)


def test_parse_undoes_format():
    assert parse(format(AWKWARD)) == AWKWARD


def test_format_undoes_parse():
    text = format(AWKWARD)
    assert format(parse(text)) == text


def test_an_empty_plan_still_names_its_columns():
    assert format(Plan()) == "\t".join(COLUMNS) + "\n"
    assert parse(format(Plan())) == Plan()


def test_values_lose_their_whitespace_on_the_way_in():
    assert Source(title="  Foo   Bar  ").title == "Foo Bar"


def test_a_tab_in_a_value_cannot_split_a_row():
    plan = Plan((Source(title="Foo\tBar", url="u"),))
    assert format(plan).count("\n") == 2
    assert parse(format(plan)) == plan
    assert plan.sources[0].title == "Foo Bar"


@pytest.mark.parametrize(
    ("typed", "stored"),
    [("3", "03"), ("03", "03"), ("0003", "03"), ("302", "0302"), ("0302", "0302"), ("", "")],
)
def test_zero_padding_is_not_information(typed, stored):
    assert Source(number=typed).number == stored


def test_a_number_that_is_not_a_count_is_left_alone():
    assert Source(number="pilot").number == "pilot"


def test_the_default_mark_survives_the_trip():
    plan = Plan((source(lang="de", default=True), source(lang="en")))
    read_back = parse(format(plan))
    assert [s.default for s in read_back.sources] == [True, False]


def test_columns_may_be_in_any_order_and_come_back_canonical():
    text = "url\tseries\tyear\tnumber\ttitle\tartist\tlang\tdefault\treferer\n"
    text += "u\tFoo\t2026\t1\tT\tA\tde\tx\tr\n"
    plan = parse(text)
    assert plan.sources[0].url == "u"
    assert plan.sources[0].default is True
    assert format(plan).splitlines()[0] == "\t".join(COLUMNS)


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("series\tyear\n", "missing"),
        ("\t".join((*COLUMNS, "extra")) + "\n", "unknown"),
        ("\t".join((*COLUMNS[:-1], "series")) + "\n", "twice"),
    ],
)
def test_a_header_that_is_not_the_plan_columns_is_refused(text, said):
    with pytest.raises(PlanError, match=said):
        parse(text)


def test_a_row_with_the_wrong_field_count_names_its_line():
    text = "\t".join(COLUMNS) + "\n" + "\t".join(["a"] * len(COLUMNS)) + "\n" + "a\tb\n"
    with pytest.raises(PlanError, match="line 3"):
        parse(text)


def test_blank_lines_are_not_rows():
    text = "\t".join(COLUMNS) + "\n\n" + "\t".join([""] * len(COLUMNS)) + "\n\n"
    assert len(parse(text).sources) == 1


def test_an_absent_or_empty_file_is_an_empty_plan(tmp_path):
    assert read(tmp_path / "nothing.tsv") == Plan()
    empty = tmp_path / "empty.tsv"
    empty.write_text("")
    assert read(empty) == Plan()


def test_write_then_read(tmp_path):
    path = tmp_path / "plan.tsv"
    write(path, AWKWARD)
    assert read(path) == AWKWARD


def test_write_replaces_the_file_and_leaves_nothing_behind(tmp_path):
    path = tmp_path / "plan.tsv"
    path.write_text("stale\n")
    write(path, AWKWARD)
    assert read(path) == AWKWARD
    assert [p.name for p in tmp_path.iterdir()] == ["plan.tsv"]


def test_a_file_that_is_not_utf_8_is_a_plan_error(tmp_path):
    path = tmp_path / "plan.tsv"
    path.write_bytes("series\n".encode("latin-1") + b"\xe9\n")
    with pytest.raises(PlanError, match="utf-8"):
        read(path)


def test_the_same_name_composed_two_ways_is_one_series():
    composed = unicodedata.normalize("NFC", "Café")
    decomposed = unicodedata.normalize("NFD", "Café")
    assert composed != decomposed
    assert Source(series=decomposed).series == composed
    plan = Plan(
        (
            source(series=composed, year="2026", number="1", lang="de"),
            source(series=decomposed, year="2026", number="2", lang="de"),
        )
    )
    assert {video.series for video in plan.videos} == {composed}
    assert problems(plan) == []


# --- grouping ---------------------------------------------------------------------


def test_rows_sharing_an_identity_are_one_video():
    plan = Plan(
        (
            source(series="Foo", year="2026", number="1", title="One", lang="de"),
            source(series="Foo", year="2026", number="2", title="Two", lang="de"),
            source(series="Foo", year="2026", number="1", title="One", lang="en"),
        )
    )
    videos = plan.videos
    assert len(videos) == 2
    assert [len(video.sources) for video in videos] == [2, 1]
    assert [s.lang for s in videos[0].sources] == ["de", "en"]
    assert videos[0].title == "One"


def test_a_number_written_two_ways_is_one_video():
    plan = Plan(
        (
            source(series="Foo", year="2026", number="3", lang="de"),
            source(series="Foo", year="2026", number="03", lang="en"),
        )
    )
    assert len(plan.videos) == 1


def test_an_item_field_is_not_part_of_the_identity():
    # Two rows that name one video stay one video even when a shared field was edited
    # on one row only. That edit is a problem, not a split.
    plan = Plan(
        (
            source(series="Foo", year="2026", number="1", title="One", lang="de"),
            source(series="Foo", year="2026", number="1", title="Uno", lang="en"),
        )
    )
    assert len(plan.videos) == 1


def test_two_standalone_videos_are_not_one():
    # Nothing but the title tells these apart, and nothing but the title has to:
    # they file as "Talk One (2023)" and "Talk Two (2023)".
    plan = Plan(
        (
            source(year="2023", title="Talk One", lang="de"),
            source(year="2023", title="Talk Two", lang="de"),
        )
    )
    assert len(plan.videos) == 2
    assert problems(plan) == []


def test_one_standalone_video_in_two_languages_is_one_video():
    plan = Plan(
        (
            source(year="2023", title="A Talk About Bar", lang="de", default=True),
            source(year="2023", title="A Talk About Bar", lang="en"),
        )
    )
    assert len(plan.videos) == 1
    assert problems(plan) == []


def test_the_same_talk_in_two_years_is_two_videos():
    plan = Plan(
        (
            source(year="2024", title="Keynote", lang="de"),
            source(year="2025", title="Keynote", lang="de"),
        )
    )
    assert len(plan.videos) == 2


# --- validation -------------------------------------------------------------------


def test_a_clean_plan_has_nothing_to_say():
    assert problems(Plan((source(series="Foo", year="2026", number="1", lang="de"),))) == []


def test_a_language_mkvmerge_refuses_is_an_error():
    found = problems(Plan((source(lang="klingon"),)))
    assert [p.severity for p in found] == [Severity.ERROR]
    assert "klingon" in found[0].message


def test_one_bad_language_on_many_rows_is_one_problem():
    plan = Plan(
        (
            source(series="A", number="1", lang="klingon"),
            source(series="B", number="1", lang="klingon"),
        )
    )
    found = [p for p in problems(plan) if "klingon" in p.message]
    assert len(found) == 1
    assert found[0].rows == (0, 1)


def test_a_row_with_no_url_is_an_error():
    plan = Plan((Source(series="Foo", number="1", lang="de", referer="r"),))
    assert [(p.severity, p.rows) for p in problems(plan)] == [(Severity.ERROR, (0,))]


def test_sources_of_one_video_that_disagree_are_an_error():
    plan = Plan(
        (
            source(series="Foo", year="2026", number="1", title="One", lang="de"),
            source(series="Foo", year="2026", number="1", title="Uno", lang="en"),
        )
    )
    found = [p for p in problems(plan) if "title" in p.message]
    assert [p.severity for p in found] == [Severity.ERROR]
    assert found[0].rows == (0, 1)


def test_two_sources_of_one_video_in_one_language_are_an_error():
    plan = Plan(
        (
            source(series="Foo", year="2026", number="1", lang="de"),
            source(series="Foo", year="2026", number="1", lang="DE"),
        )
    )
    found = [p for p in problems(plan) if "share" in p.message]
    assert [p.severity for p in found] == [Severity.ERROR]
    assert found[0].rows == (0, 1)


def test_two_sources_of_one_video_with_no_language_are_an_error():
    plan = Plan(
        (
            source(series="Foo", year="2026", number="1"),
            source(series="Foo", year="2026", number="1"),
        )
    )
    assert any(p.severity is Severity.ERROR and "no language" in p.message for p in problems(plan))


def test_a_video_with_two_defaults_warns():
    plan = Plan(
        (
            source(series="Foo", number="1", lang="de", default=True),
            source(series="Foo", number="1", lang="en", default=True),
        )
    )
    found = [p for p in problems(plan) if "default" in p.message]
    assert [p.severity for p in found] == [Severity.WARNING]
    assert found[0].rows == (0, 1)


def test_a_video_with_no_default_warns_only_when_there_is_a_choice():
    lone = Plan((source(series="Foo", number="1", lang="de"),))
    assert [p for p in problems(lone) if "default" in p.message] == []
    pair = Plan(
        (
            source(series="Foo", number="1", lang="de"),
            source(series="Foo", number="1", lang="en"),
        )
    )
    assert [p.severity for p in problems(pair) if "default" in p.message] == [Severity.WARNING]


def test_a_series_spelled_two_ways_warns():
    plan = Plan(
        (
            source(series="Foo Course", number="1", lang="de"),
            source(series="foo course", number="2", lang="de"),
        )
    )
    found = [p for p in problems(plan) if "spelled" in p.message]
    assert [p.severity for p in found] == [Severity.WARNING]
    assert found[0].rows == (0, 1)


def test_a_missing_referer_warns():
    plan = Plan((Source(series="Foo", number="1", lang="de", url="u"),))
    assert [(p.severity, p.rows) for p in problems(plan)] == [(Severity.WARNING, (0,))]


def test_a_missing_mkvmerge_is_a_problem_rather_than_a_traceback():
    def absent(tag: str) -> str | None:
        raise MkvmergeUnavailable("could not run mkvmerge")

    plan = Plan((Source(series="Foo", number="1", lang="de", referer="r"),))
    found = validate(plan, lang_problem=absent)
    assert [p.message for p in found if "no language could be checked" in p.message]
    # The rest of the plan is still reported, which is the point of the function.
    assert [p.message for p in found if "no url" in p.message]


def test_every_problem_is_reported_and_errors_come_first():
    plan = Plan(
        (
            Source(series="Foo", number="1", lang="klingon"),
            Source(series="foo", number="2", lang="de", url="u"),
        )
    )
    found = problems(plan)
    severities = [p.severity for p in found]
    assert severities == sorted(severities, key=lambda s: s is Severity.WARNING)
    assert severities.count(Severity.ERROR) == 2  # the language, and the row with no url
    assert severities.count(Severity.WARNING) == 3  # the series spelling, and two referers
