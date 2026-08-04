#!/usr/bin/env python3
"""SciLifeLab Serve preflight check.

The deployment contract, expressed as assertions. Every check here corresponds
to a rule in AGENTS.md, and almost every one corresponds to a way that an app
can build perfectly on a laptop and then fail on Serve.

Standard library only, no Docker required, runs in well under a second.

    python scripts/preflight.py            # human readable
    python scripts/preflight.py --strict   # warnings also fail
    python scripts/preflight.py --json     # machine readable, for CI

Exit codes: 0 all good, 1 at least one failure (or a warning under --strict).

If a check fires, fix the code it points at. Do not edit the check.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# The contract, as constants. Change these when porting to another framework.
# --------------------------------------------------------------------------
FRAMEWORK = "gradio"
EXPECTED_PORT = 7860
SERVE_PORT_MIN, SERVE_PORT_MAX = 3000, 9999
REQUIRED_UID = 1000
ENTRY_POINT = "app/main.py"
REQUIREMENTS = "app/requirements.txt"
UPLOAD_LIMIT_MB = 100

PASS, WARN, FAIL = "pass", "warn", "fail"

SECRET_PATTERNS = {
    "GitHub token": r"gh[pousr]_[A-Za-z0-9]{30,}",
    "OpenAI-style key": r"sk-[A-Za-z0-9]{24,}",
    "AWS access key": r"AKIA[0-9A-Z]{16}",
    "private key block": r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    "hardcoded password": r"(?i)\b(password|passwd|secret|api_key)\s*=\s*[\"'][^\"'\s]{8,}[\"']",
}

SCAN_SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", "tmp", ".pytest_cache"}
SCAN_SUFFIXES = {".py", ".txt", ".md", ".yml", ".yaml", ".json", ".sh", ".cfg", ".toml", ""}


@dataclass
class Result:
    level: str
    group: str
    message: str
    hint: str = ""


def dockerfile_instructions(text: str) -> list[str]:
    """Dockerfile instructions with comments dropped and continuations joined.

    Checks run against this rather than the raw text, so that a comment
    explaining a rule is never mistaken for a violation of it.
    """
    instructions: list[str] = []
    buffer = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        buffer += line
        if buffer.endswith("\\"):
            buffer = buffer[:-1].rstrip() + " "
            continue
        instructions.append(buffer)
        buffer = ""
    if buffer:
        instructions.append(buffer)
    return instructions


@dataclass
class Context:
    root: Path
    dockerfile: str = ""
    entry: str = ""
    requirements: str = ""
    workflows: dict[str, str] = field(default_factory=dict)

    @property
    def docker(self) -> str:
        """The Dockerfile as executable instructions only, one per line."""
        return "\n".join(dockerfile_instructions(self.dockerfile))

    @classmethod
    def load(cls, root: Path) -> "Context":
        def read(rel: str) -> str:
            path = root / rel
            return path.read_text(encoding="utf-8") if path.is_file() else ""

        workflows = {}
        wf_dir = root / ".github" / "workflows"
        if wf_dir.is_dir():
            for path in sorted(wf_dir.glob("*.y*ml")):
                workflows[path.name] = path.read_text(encoding="utf-8")

        return cls(
            root=root,
            dockerfile=read("Dockerfile"),
            entry=read(ENTRY_POINT),
            requirements=read(REQUIREMENTS),
            workflows=workflows,
        )


# --------------------------------------------------------------------------
# Checks. Each returns a list of Results.
# --------------------------------------------------------------------------


def check_layout(ctx: Context) -> list[Result]:
    out = []
    required = ["Dockerfile", ENTRY_POINT, REQUIREMENTS, "AGENTS.md", "DEPLOY.md"]
    for rel in required:
        if (ctx.root / rel).is_file():
            out.append(Result(PASS, "layout", f"{rel} present"))
        else:
            out.append(
                Result(
                    FAIL,
                    "layout",
                    f"{rel} is missing",
                    "Serve needs the entry point at this exact path. Do not rename it.",
                )
            )

    # The Serve Streamlit docs show "requirements.py" in their file tree. It is a
    # typo there, and agents copy file trees literally, so guard against it.
    stray = ctx.root / "app" / "requirements.py"
    if stray.is_file():
        out.append(
            Result(
                FAIL,
                "layout",
                "found app/requirements.py",
                "The file must be requirements.txt. requirements.py installs nothing.",
            )
        )
    return out


def check_base_image(ctx: Context) -> list[Result]:
    match = re.search(r"^\s*FROM\s+(\S+)", ctx.docker, re.M)
    if not match:
        return [Result(FAIL, "container", "no FROM instruction in the Dockerfile")]
    image = match.group(1)
    if image.endswith(":latest") or ":" not in image.split("/")[-1]:
        return [
            Result(
                FAIL,
                "container",
                f"base image is unpinned: {image}",
                "Pin a version, for example python:3.12-slim. Never :latest.",
            )
        ]
    return [Result(PASS, "container", f"base image pinned: {image}")]


def check_non_root_uid(ctx: Context) -> list[Result]:
    out = []
    if re.search(rf"useradd[^\n]*-u\s+{REQUIRED_UID}\b", ctx.docker):
        out.append(Result(PASS, "container", f"creates a user with UID {REQUIRED_UID}"))
    else:
        out.append(
            Result(
                FAIL,
                "container",
                f"no user created with UID {REQUIRED_UID}",
                f"Serve requires it: RUN useradd -m -u {REQUIRED_UID} $USER",
            )
        )

    users = re.findall(r"^\s*USER\s+(\S+)", ctx.docker, re.M)
    if not users:
        out.append(
            Result(
                FAIL,
                "container",
                "no USER instruction, so the container runs as root",
                "Add USER $USER after the COPY and chown steps.",
            )
        )
        return out

    last = users[-1]
    resolved = last
    var = re.fullmatch(r"\$\{?(\w+)\}?", last)
    if var:
        env = re.search(rf"^\s*ENV\s+{var.group(1)}=(\S+)", ctx.docker, re.M)
        resolved = env.group(1) if env else last

    if resolved in {"root", "0"}:
        out.append(
            Result(
                FAIL,
                "container",
                f"the last USER instruction resolves to {resolved}",
                "The container must not run as root on Serve.",
            )
        )
    else:
        out.append(Result(PASS, "container", f"runs as non-root user ({resolved})"))
    return out


def check_port(ctx: Context) -> list[Result]:
    out = []
    exposed = [int(p) for p in re.findall(r"^\s*EXPOSE\s+(\d+)", ctx.docker, re.M)]
    if not exposed:
        return [
            Result(
                FAIL,
                "network",
                "no EXPOSE instruction",
                f"Add EXPOSE {EXPECTED_PORT} so the port is documented in the image.",
            )
        ]
    for port in exposed:
        if not SERVE_PORT_MIN <= port <= SERVE_PORT_MAX:
            out.append(
                Result(
                    FAIL,
                    "network",
                    f"port {port} is outside the range Serve allows",
                    f"Serve permits {SERVE_PORT_MIN} to {SERVE_PORT_MAX} only.",
                )
            )
        elif port != EXPECTED_PORT:
            out.append(
                Result(
                    WARN,
                    "network",
                    f"port {port} is allowed but is not the Gradio default",
                    f"The docs and DEPLOY.md assume {EXPECTED_PORT}. Update DEPLOY.md if this is deliberate.",
                )
            )
        else:
            out.append(Result(PASS, "network", f"exposes port {port}"))

    if re.search(r"GRADIO_SERVER_NAME\s*=?\s*[\"']?0\.0\.0\.0", ctx.docker):
        out.append(Result(PASS, "network", "binds 0.0.0.0 via GRADIO_SERVER_NAME"))
    else:
        out.append(
            Result(
                FAIL,
                "network",
                "GRADIO_SERVER_NAME is not set to 0.0.0.0 in the Dockerfile",
                "An app bound to 127.0.0.1 is unreachable on Serve.",
            )
        )
    return out


def check_entry_point(ctx: Context) -> list[Result]:
    out = []
    name = Path(ENTRY_POINT).name
    if re.search(rf"^\s*(CMD|ENTRYPOINT)\b.*{re.escape(name)}", ctx.docker, re.M):
        out.append(Result(PASS, "container", f"CMD runs {name}"))
    else:
        out.append(
            Result(
                FAIL,
                "container",
                f"no CMD or ENTRYPOINT that runs {name}",
                f'Use CMD ["python", "{name}"].',
            )
        )

    if re.search(rf"^\s*COPY\b.*{re.escape(name)}", ctx.docker, re.M):
        out.append(Result(PASS, "container", f"{name} is copied into the image"))
    else:
        out.append(
            Result(
                FAIL,
                "container",
                f"{name} is never COPYed into the image",
                "The image will start and immediately fail to find the app.",
            )
        )

    # The Serve Streamlit docs ship a HEALTHCHECK that calls curl on a slim base
    # image, which can only ever fail. Make sure the template never regresses
    # into that shape. Look at the instruction itself, not at comments about it.
    healthchecks = [ln for ln in ctx.docker.splitlines() if ln.startswith("HEALTHCHECK")]
    slim_base = re.search(r"^\s*FROM\s+\S*(slim|alpine)", ctx.docker, re.M)
    installs_curl = re.search(r"apt-get install[^\n]*\bcurl\b", ctx.docker)
    for line in healthchecks:
        if "curl" in line and slim_base and not installs_curl:
            out.append(
                Result(
                    FAIL,
                    "container",
                    "HEALTHCHECK calls curl on a slim base image",
                    "Slim images ship no curl, so the healthcheck can only fail. "
                    'Use CMD python -c "..." instead.',
                )
            )
    if healthchecks and not any(r.level == FAIL and "HEALTHCHECK" in r.message for r in out):
        out.append(Result(PASS, "container", "HEALTHCHECK uses a tool the image actually has"))
    return out


def check_requirements(ctx: Context) -> list[Result]:
    if not ctx.requirements.strip():
        return [Result(FAIL, "dependencies", f"{REQUIREMENTS} is empty or missing")]
    unpinned = []
    for line in ctx.requirements.splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        if "==" not in line:
            unpinned.append(line)
    if unpinned:
        return [
            Result(
                WARN,
                "dependencies",
                "unpinned dependencies: " + ", ".join(unpinned),
                "Pin with == so the build is reproducible when Serve re-pulls the image.",
            )
        ]
    pinned = [
        ln.split("#")[0].strip()
        for ln in ctx.requirements.splitlines()
        if "==" in ln.split("#")[0]
    ]
    return [Result(PASS, "dependencies", f"all {len(pinned)} dependencies pinned with ==")]


def check_app_code(ctx: Context) -> list[Result]:
    """Inspect the entry point through its syntax tree.

    Parsing rather than grepping matters here: a docstring that says "never use
    share=True" is not a violation, and a validator that cannot tell the
    difference trains people to ignore it.
    """
    out: list[Result] = []
    if not ctx.entry:
        return [Result(FAIL, "app", f"cannot read {ENTRY_POINT}")]

    try:
        tree = ast.parse(ctx.entry, filename=ENTRY_POINT)
    except SyntaxError as exc:
        return [
            Result(
                FAIL,
                "app",
                f"{ENTRY_POINT} does not parse: line {exc.lineno}, {exc.msg}",
                "The image would build and then crash on start.",
            )
        ]

    keywords: dict[str, list[ast.keyword]] = {}
    called_attrs: set[str] = set()
    imported: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg:
                    keywords.setdefault(kw.arg, []).append(kw)
            if isinstance(node.func, ast.Attribute):
                called_attrs.add(node.func.attr)
        elif isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    if "auth" in keywords:
        out.append(
            Result(
                FAIL,
                "app",
                "a call passes auth=",
                "Serve does not allow apps with their own login or user accounts.",
            )
        )
    else:
        out.append(Result(PASS, "app", "no login or user accounts"))

    share_true = any(
        isinstance(kw.value, ast.Constant) and kw.value.value is True for kw in keywords.get("share", [])
    )
    if share_true:
        out.append(
            Result(
                FAIL,
                "app",
                "a call passes share=True",
                "That opens a public Gradio tunnel. Never do this from a hosted app.",
            )
        )
    else:
        out.append(Result(PASS, "app", "no public Gradio tunnel"))

    upload_widgets = {"File", "Files", "UploadButton", "Image", "Audio", "Video", "Model3D"}
    accepts_uploads = bool(upload_widgets & called_attrs)
    has_temp_dir = "GRADIO_TEMP_DIR" in ctx.docker
    if accepts_uploads and not has_temp_dir:
        out.append(
            Result(
                WARN,
                "app",
                "the app accepts files but GRADIO_TEMP_DIR is not set in the Dockerfile",
                f"Set it inside the user's home. The upload limit on Serve is {UPLOAD_LIMIT_MB} MB, "
                "and Gradio uploads break once temp files pass 5 GB.",
            )
        )
    elif accepts_uploads:
        out.append(Result(PASS, "app", "upload-capable, and GRADIO_TEMP_DIR is set"))

    if "sqlite3" in imported:
        out.append(
            Result(
                WARN,
                "app",
                "sqlite3 is imported",
                "Allowed only on a mounted project volume, and never for personal data. "
                "The app must still return to its default state for each new visitor.",
            )
        )
    return out


def check_ci(ctx: Context) -> list[Result]:
    out = []
    if not ctx.workflows:
        return [
            Result(
                WARN,
                "ci",
                "no GitHub Actions workflows found",
                "Without CI you must build and push amd64 images by hand, with a unique tag every time.",
            )
        ]

    build = {name: body for name, body in ctx.workflows.items() if "build-push-action" in body}
    if not build:
        out.append(Result(WARN, "ci", "no workflow builds and pushes an image"))
        return out
    if not any(re.search(r"push:\s*true", body) for body in build.values()):
        out.append(
            Result(
                WARN,
                "ci",
                "no workflow pushes an image to a registry",
                "Serve pulls the image from a public registry, so something has to publish it.",
            )
        )

    for name, body in build.items():
        if re.search(r"platforms:\s*.*linux/amd64", body):
            out.append(Result(PASS, "ci", f"{name} builds linux/amd64"))
        else:
            out.append(
                Result(
                    FAIL,
                    "ci",
                    f"{name} does not declare platforms: linux/amd64",
                    "It works on GitHub's amd64 runners today by luck, not by contract.",
                )
            )

        if not re.search(r"push:\s*true", body):
            # A build-only job (preflight) does not publish, so tag discipline
            # does not apply to it.
            continue

        tag_lines = re.findall(r"^\s*tags:.*$|^\s{6,}\S*:.*$", body, re.M)
        if any(":latest" in ln for ln in tag_lines) or re.search(r"tags:\s*\S+:latest", body):
            out.append(
                Result(
                    FAIL,
                    "ci",
                    f"{name} publishes a :latest tag",
                    "Serve will not re-pull an already-deployed tag. Every version needs a unique one.",
                )
            )
        elif re.search(r"date -u \+%Y%m%d|github\.sha|metadata-action", body):
            out.append(Result(PASS, "ci", f"{name} generates a unique tag per build"))
        else:
            out.append(
                Result(
                    WARN,
                    "ci",
                    f"{name} tagging strategy is unclear",
                    "Derive the tag from a timestamp or the commit SHA.",
                )
            )
    return out


def check_secrets(ctx: Context) -> list[Result]:
    out = []
    if (ctx.root / ".env").is_file():
        out.append(
            Result(
                FAIL,
                "secrets",
                ".env is present in the repository",
                "Code on Serve is public, so anything committed here is published.",
            )
        )

    hits = []
    for path in ctx.root.rglob("*"):
        if not path.is_file():
            continue
        # Filter on the path *relative to the repository root*. Matching against
        # absolute parts means a repository checked out under, say, /tmp/build
        # silently skips every file.
        rel = path.relative_to(ctx.root)
        if any(part in SCAN_SKIP_DIRS for part in rel.parts):
            continue
        if path.suffix not in SCAN_SUFFIXES:
            continue
        if rel == Path("scripts") / Path(__file__).name:
            continue  # this file contains the patterns themselves
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            match = re.search(pattern, text)
            if match:
                hits.append(f"{label} in {rel} (line {text[:match.start()].count(chr(10)) + 1})")

    if hits:
        out.extend(
            Result(
                FAIL,
                "secrets",
                hit,
                "Rotate the credential, then remove it from the history. Serve requires public code.",
            )
            for hit in hits
        )
    else:
        out.append(Result(PASS, "secrets", "no credential-shaped strings found"))
    return out


CHECKS = (
    check_layout,
    check_base_image,
    check_non_root_uid,
    check_port,
    check_entry_point,
    check_requirements,
    check_app_code,
    check_ci,
    check_secrets,
)

GROUP_ORDER = ("layout", "container", "network", "dependencies", "app", "ci", "secrets")


# --------------------------------------------------------------------------
# Runner and output
# --------------------------------------------------------------------------


def run(root: Path) -> list[Result]:
    ctx = Context.load(root)
    results: list[Result] = []
    for check in CHECKS:
        results.extend(check(ctx))
    return results


def render(results: list[Result], root: Path, colour: bool) -> str:
    marks = {PASS: "ok  ", WARN: "warn", FAIL: "FAIL"}
    if colour:
        marks = {PASS: "\033[32mok\033[0m  ", WARN: "\033[33mwarn\033[0m", FAIL: "\033[31mFAIL\033[0m"}

    lines = [f"SciLifeLab Serve preflight  ({FRAMEWORK})", f"repo: {root}", ""]
    for group in GROUP_ORDER:
        items = [r for r in results if r.group == group]
        if not items:
            continue
        lines.append(f"  {group}")
        for item in items:
            lines.append(f"    {marks[item.level]}  {item.message}")
            if item.hint and item.level != PASS:
                lines.append(f"          {item.hint}")
        lines.append("")

    counts = {level: sum(1 for r in results if r.level == level) for level in (PASS, WARN, FAIL)}
    lines.append(f"{counts[PASS]} passed, {counts[WARN]} warning(s), {counts[FAIL]} failed")
    if counts[FAIL]:
        lines.append("")
        lines.append("Fix the failures above. They are platform requirements, not suggestions.")
        lines.append("Do not edit the checks in scripts/preflight.py to make them pass.")
    else:
        lines.append("")
        lines.append("Preflight OK. Push to main, let CI publish the image, then copy the")
        lines.append("values from DEPLOY.md into the SciLifeLab Serve app form.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check this repository against the SciLifeLab Serve deployment contract.")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    parser.add_argument("--root", default=None, help="repository root (default: parent of this script)")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent.parent
    results = run(root)

    failed = [r for r in results if r.level == FAIL]
    warned = [r for r in results if r.level == WARN]

    if args.json:
        print(
            json.dumps(
                {
                    "framework": FRAMEWORK,
                    "root": str(root),
                    "ok": not failed and not (args.strict and warned),
                    "results": [vars(r) for r in results],
                },
                indent=2,
            )
        )
    else:
        print(render(results, root, colour=sys.stdout.isatty()))

    return 1 if failed or (args.strict and warned) else 0


if __name__ == "__main__":
    raise SystemExit(main())
