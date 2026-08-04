#!/usr/bin/env python3
"""Check that the invariants baked into this template still appear in the docs.

SciLifeLab Serve is in beta and the documentation says so. Rather than hoping
this template stays correct, assert it: fetch the canonical pages and look for
the strings this repository depends on.

    python scripts/docs_drift.py
    python scripts/docs_drift.py --report drift.md

Exit codes: 0 nothing moved, 1 at least one invariant is missing or a page could
not be fetched.

Once the Serve docs expose Markdown twins (planned, see the project document),
switch SOURCES to the .md URLs and drop the HTML unwrapping entirely.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "serve-template-gradio docs-drift check (+https://serve.scilifelab.se/docs/)"
TIMEOUT = 20

# Page -> strings that must still be present. Keep this list short: only the
# things that break a deployment when they change.
SOURCES: dict[str, list[str]] = {
    "https://serve.scilifelab.se/docs/application-hosting/gradio/_source/": [
        "7860",
        "useradd -m -u 1000",
        "GRADIO_SERVER_NAME",
        "linux/amd64",
        "unique image tag",
        "100MB",
    ],
    "https://serve.scilifelab.se/docs/application-hosting/other/_source/": [
        "3000",
        "9999",
        "user id 1000",
    ],
}


def fetch(url: str, attempts: int = 3) -> str:
    """Fetch a page, retrying so that a transient blip is not reported as drift."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                raw = response.read().decode("utf-8", errors="replace")
            break
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            if attempt == attempts:
                raise
            time.sleep(2 * attempt)
    # django-wiki wraps the raw Markdown in site HTML. Strip tags crudely: we
    # only ever test for the presence of short literal strings.
    text = re.sub(r"<script.*?</script>", " ", raw, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", default=None, help="write a Markdown report to this path")
    args = parser.parse_args(argv)

    problems: list[str] = []
    lines: list[str] = ["# Docs drift report", ""]

    for url, expected in SOURCES.items():
        lines.append(f"## {url}")
        try:
            text = fetch(url)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            problems.append(f"could not fetch {url}: {exc}")
            lines.extend([f"- could not fetch the page: `{exc}`", ""])
            continue

        for needle in expected:
            if needle in text:
                lines.append(f"- found `{needle}`")
            else:
                problems.append(f"{url}: `{needle}` no longer appears")
                lines.append(f"- **MISSING** `{needle}`")
        lines.append("")

    if problems:
        lines.extend(
            [
                "## What to do",
                "",
                "One of the values this template hard-codes has changed, or a page moved.",
                "Re-read the page, update `AGENTS.md`, `Dockerfile`, `DEPLOY.md` and",
                "`scripts/preflight.py` together, then close this issue.",
                "",
            ]
        )

    report = "\n".join(lines)
    if args.report:
        Path(args.report).write_text(report, encoding="utf-8")
    print(report)

    if problems:
        print("\nDrift detected:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1

    print("No drift. Every invariant is still documented.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
