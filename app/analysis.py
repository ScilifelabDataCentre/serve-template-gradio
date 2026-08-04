"""Sequence analysis helpers for the demo app.

Deliberately free of any Gradio import so that tests stay fast and so that an
agent replacing the user interface does not have to untangle logic from layout.
Replace this file with your own analysis. Nothing in the deployment contract
depends on it.
"""

from __future__ import annotations

BASES = ("A", "C", "G", "T", "N")

# A short fragment with a visible GC-rich island in the middle, so the window
# plot shows something on first load.
EXAMPLE_SEQUENCE = (
    ">demo_fragment human-like, 300 bp\n"
    "ATTATTAAATTTAAGATTTATTAAAGGTTATTAAATTAGATTTAAGGTTAT\n"
    "TAAAGGTTATTAAATTAGATTTAAGGTTATTAAATTTAAGATTTATTAAAG\n"
    "GCGCCGGCGCGGCCGCGGGCCGCGCCGGGCCGCGGCGCCGGGCGCGCCGGC\n"
    "CGCGGCGCCGGGCGCGCCGGCCGCGGGCCGCGCCGGGCCGCGGCGCCGGGC\n"
    "TAAATTTAAGATTTATTAAAGGTTATTAAATTAGATTTAAGGTTATTAAAT\n"
    "TTAAGATTTATTAAAGGTTATTAAATTAGATTTAAGGTTATTAAATTTAAG\n"
)


def clean_sequence(raw: str) -> tuple[str, int]:
    """Normalise user input into a bare nucleotide string.

    Drops FASTA header lines, whitespace and digits, uppercases the rest, and
    reports how many characters were not recognised as nucleotides.
    """
    lines = [ln for ln in (raw or "").splitlines() if not ln.startswith(">")]
    body = "".join(lines).upper()
    kept, dropped = [], 0
    for char in body:
        if char in BASES:
            kept.append(char)
        elif char.isspace() or char.isdigit():
            continue
        else:
            dropped += 1
    return "".join(kept), dropped


def base_counts(seq: str) -> dict[str, int]:
    """Count each nucleotide, including bases that do not occur."""
    return {base: seq.count(base) for base in BASES}


def gc_fraction(seq: str) -> float:
    """GC content as a fraction of A, C, G and T. Returns 0.0 for empty input."""
    known = sum(seq.count(base) for base in ("A", "C", "G", "T"))
    if known == 0:
        return 0.0
    return (seq.count("G") + seq.count("C")) / known


def gc_windows(seq: str, window: int, step: int = 1) -> list[tuple[int, float]]:
    """GC fraction in a sliding window.

    Returns (midpoint position, fraction) pairs. An empty list means the
    sequence is shorter than one window, which the caller should handle.
    """
    if window <= 0 or len(seq) < window:
        return []
    points = []
    for start in range(0, len(seq) - window + 1, max(step, 1)):
        chunk = seq[start : start + window]
        points.append((start + window // 2, gc_fraction(chunk)))
    return points


def summarise(raw: str) -> dict[str, object]:
    """Everything the interface needs, in one call."""
    seq, dropped = clean_sequence(raw)
    return {
        "sequence": seq,
        "length": len(seq),
        "dropped": dropped,
        "gc": gc_fraction(seq),
        "counts": base_counts(seq),
    }
