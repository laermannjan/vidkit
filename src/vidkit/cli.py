"""Command line entry point.

Commands are added as the build order in SPEC.md reaches them. Today only
`--version` exists, so the packaging and the release machinery have something
real to prove themselves against.
"""

from __future__ import annotations

import argparse

from vidkit import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vidkit", description=__doc__)
    parser.add_argument("--version", action="version", version=f"vidkit {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
