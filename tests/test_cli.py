import pytest

from vidkit import __version__
from vidkit.cli import build_parser, main


def test_version_is_importable():
    assert __version__


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        build_parser().parse_args(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_bare_invocation_prints_help(capsys):
    assert main([]) == 0
    assert "vidkit" in capsys.readouterr().out
