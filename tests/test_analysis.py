"""Tests for the demo app's analysis helpers.

Replace these when you replace the app. Keep the file: an agent that can run
tests writes better code than one that cannot.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))

from analysis import (  # noqa: E402
    EXAMPLE_SEQUENCE,
    base_counts,
    clean_sequence,
    gc_fraction,
    gc_windows,
    summarise,
)


def test_clean_sequence_drops_fasta_header_and_whitespace():
    seq, dropped = clean_sequence(">header line\nAC GT\nacgt\n")
    assert seq == "ACGTACGT"
    assert dropped == 0


def test_clean_sequence_counts_unrecognised_characters():
    seq, dropped = clean_sequence("ACGT***123")
    assert seq == "ACGT"
    assert dropped == 3


def test_gc_fraction_basic():
    assert gc_fraction("GGCC") == 1.0
    assert gc_fraction("ATAT") == 0.0
    assert gc_fraction("ACGT") == 0.5


def test_gc_fraction_ignores_ambiguous_bases():
    assert gc_fraction("GCNN") == 1.0


def test_gc_fraction_of_empty_sequence_is_zero():
    assert gc_fraction("") == 0.0


def test_base_counts_includes_absent_bases():
    counts = base_counts("AAGG")
    assert counts["A"] == 2
    assert counts["G"] == 2
    assert counts["T"] == 0
    assert counts["N"] == 0


def test_gc_windows_shape():
    points = gc_windows("A" * 50 + "G" * 50, window=10)
    assert len(points) == 91
    positions = [p for p, _ in points]
    assert positions == sorted(positions)
    assert points[0][1] == 0.0
    assert points[-1][1] == 1.0


def test_gc_windows_returns_nothing_for_short_sequences():
    assert gc_windows("ACGT", window=40) == []


def test_summarise_on_the_bundled_example():
    result = summarise(EXAMPLE_SEQUENCE)
    assert result["length"] > 250
    assert result["dropped"] == 0
    assert 0.3 < result["gc"] < 0.6
    assert sum(result["counts"].values()) == result["length"]
