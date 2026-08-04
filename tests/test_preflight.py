"""Self-tests for the deployment contract checker.

Two jobs:

1. Assert that this repository passes its own preflight, with no failures.
2. Assert that the checks actually catch the mistakes they claim to catch, by
   running them against deliberately broken copies of the repository.

The second half matters more than it looks. A validator that passes everything
is worse than no validator, because it grants false confidence.
"""

import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import preflight  # noqa: E402

FAIL = preflight.FAIL


def levels(results, level):
    return [r for r in results if r.level == level]


def messages(results):
    return " | ".join(f"{r.level}:{r.message}" for r in results)


def test_this_repository_passes_its_own_contract():
    results = preflight.run(ROOT)
    failures = levels(results, FAIL)
    assert not failures, f"preflight failed on the template itself: {messages(failures)}"


def test_this_repository_passes_in_strict_mode():
    assert preflight.main(["--root", str(ROOT), "--strict"]) == 0


@pytest.fixture
def broken(tmp_path):
    """A writable copy of the repository that a test can damage."""
    target = tmp_path / "repo"
    shutil.copytree(
        ROOT,
        target,
        ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "tmp"),
    )
    return target


def assert_fails_with(root: Path, needle: str):
    results = preflight.run(root)
    failures = levels(results, FAIL)
    assert failures, f"expected a failure mentioning '{needle}', got none"
    assert any(needle in r.message for r in failures), (
        f"expected a failure mentioning '{needle}', got: {messages(failures)}"
    )


def test_catches_root_user(broken):
    path = broken / "Dockerfile"
    path.write_text(path.read_text().replace("USER $USER", "USER root"))
    assert_fails_with(broken, "root")


def test_catches_missing_user_instruction(broken):
    path = broken / "Dockerfile"
    path.write_text("\n".join(ln for ln in path.read_text().splitlines() if not ln.startswith("USER ")))
    assert_fails_with(broken, "USER")


def test_catches_wrong_uid(broken):
    path = broken / "Dockerfile"
    path.write_text(path.read_text().replace("-u 1000", "-u 1001"))
    assert_fails_with(broken, "UID 1000")


def test_catches_port_outside_the_serve_range(broken):
    path = broken / "Dockerfile"
    path.write_text(path.read_text().replace("EXPOSE 7860", "EXPOSE 80"))
    assert_fails_with(broken, "outside the range")


def test_catches_unpinned_base_image(broken):
    path = broken / "Dockerfile"
    path.write_text(path.read_text().replace("FROM python:3.12-slim", "FROM python:latest"))
    assert_fails_with(broken, "unpinned")


def test_catches_missing_server_name(broken):
    path = broken / "Dockerfile"
    path.write_text(path.read_text().replace("ENV GRADIO_SERVER_NAME=0.0.0.0", ""))
    assert_fails_with(broken, "GRADIO_SERVER_NAME")


def test_catches_renamed_entry_point(broken):
    (broken / "app" / "main.py").rename(broken / "app" / "server.py")
    assert_fails_with(broken, "app/main.py")


def test_catches_requirements_py_typo(broken):
    shutil.copy(broken / "app" / "requirements.txt", broken / "app" / "requirements.py")
    assert_fails_with(broken, "requirements.py")


def test_catches_auth_in_launch(broken):
    path = broken / "app" / "main.py"
    path.write_text(path.read_text().replace("share=False,", 'auth=("user", "pass"),'))
    assert_fails_with(broken, "auth")


def test_catches_share_true(broken):
    path = broken / "app" / "main.py"
    path.write_text(path.read_text().replace("share=False,", "share=True,"))
    assert_fails_with(broken, "share=True")


def test_catches_missing_amd64_platform_in_ci(broken):
    path = broken / ".github" / "workflows" / "docker-image-ghcr.yml"
    path.write_text(path.read_text().replace("platforms: linux/amd64", ""))
    assert_fails_with(broken, "linux/amd64")


def test_catches_latest_tag_in_ci(broken):
    path = broken / ".github" / "workflows" / "docker-image-ghcr.yml"
    path.write_text(path.read_text().replace("${{ env.IMAGE }}:${{ env.TAG }}", "${{ env.IMAGE }}:latest"))
    assert_fails_with(broken, "latest")


def test_catches_committed_secret(broken):
    (broken / "app" / "config.py").write_text('OPENAI_KEY = "sk-' + "a" * 40 + '"\n')
    assert_fails_with(broken, "OpenAI-style key")


def test_catches_committed_dotenv(broken):
    (broken / ".env").write_text("TOKEN=whatever\n")
    assert_fails_with(broken, ".env")


def test_catches_curl_healthcheck_on_slim_image(broken):
    # The shape the Serve Streamlit docs currently ship: curl against a slim
    # base image that has no curl. Docker honours the last HEALTHCHECK, so
    # appending one is enough to reproduce the mistake.
    path = broken / "Dockerfile"
    path.write_text(path.read_text() + "\nHEALTHCHECK CMD curl --fail http://localhost:7860/\n")
    assert_fails_with(broken, "curl")


def test_ignores_the_word_curl_in_a_comment(broken):
    # The template's own Dockerfile explains in a comment why curl is wrong.
    # A checker that cannot tell a comment from an instruction is a checker
    # people learn to ignore.
    path = broken / "Dockerfile"
    path.write_text(path.read_text() + "\n# never use curl in a HEALTHCHECK here\n")
    results = preflight.run(broken)
    assert not levels(results, FAIL), messages(results)
