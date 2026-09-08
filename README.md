# SciLifeLab Serve Gradio Template

A starter repository for building a Gradio app and deploying it to [SciLifeLab Serve](https://serve.scilifelab.se).

It includes:

* a small working Gradio app
* a Dockerfile configured for SciLifeLab Serve
* preflight checks for common deployment problems
* GitHub Actions for testing and publishing container images
* a deployment guide in [`DEPLOY.md`](DEPLOY.md)

> **Status:** Prototype for internal review. Not yet published under `ScilifelabDataCentre`.

## Quick start

### 1. Create a repository

Use this repository as a GitHub template, or open:

```text
https://github.com/ScilifelabDataCentre/serve-template-gradio/generate
```

### 2. Run the app locally

```bash
pip install -r app/requirements.txt
python app/main.py
```

Open:

```text
http://127.0.0.1:7860
```

If you do not have Docker installed, you can use a GitHub Codespace. The included devcontainer provides Python and Docker.

### 3. Replace the demo app

Edit the files under `app/` to build your own application.

Keep these deployment requirements unchanged unless the SciLifeLab Serve documentation says otherwise:

* keep `app/main.py` as the application entry point
* run the container as UID `1000`
* use a port between `3000` and `9999`
* bind Gradio to `0.0.0.0`
* pin Python dependencies with `==`
* use a unique container image tag for each build
* do not use `latest`

Then run:

```bash
python scripts/preflight.py
pytest -q
```

### 4. Deploy

Push to `main`.

GitHub Actions will:

1. run the checks and tests
2. build a `linux/amd64` container image
3. publish the image to GitHub Container Registry (GHCR)
4. print the image reference in the workflow summary

Use [`DEPLOY.md`](DEPLOY.md) to fill in the SciLifeLab Serve deployment form.

## Repository structure

| Path                                      | Purpose                                                          |
| ----------------------------------------- | ---------------------------------------------------------------- |
| `app/main.py`                             | Gradio application entry point                                   |
| `app/analysis.py`                         | Application logic kept separate from the interface               |
| `app/requirements.txt`                    | Python dependencies                                              |
| `Dockerfile`                              | Container configuration for SciLifeLab Serve                     |
| `scripts/preflight.py`                    | Checks the repository for common deployment problems             |
| `scripts/docs_drift.py`                   | Checks whether important Serve documentation values have changed |
| `.github/workflows/preflight.yml`         | Runs checks, tests, container build, and smoke test              |
| `.github/workflows/docker-image-ghcr.yml` | Builds and publishes uniquely tagged images to GHCR              |
| `.github/workflows/docs-drift.yml`        | Runs a monthly documentation check                               |
| `.devcontainer/`                          | Development container for GitHub Codespaces                      |
| `AGENTS.md`                               | Repository rules for coding tools and automated assistants       |
| `CLAUDE.md`                               | Pointer to `AGENTS.md`                                           |
| `.github/copilot-instructions.md`         | Pointer to `AGENTS.md` for GitHub Copilot                        |
| `DEPLOY.md`                               | Step-by-step SciLifeLab Serve deployment settings                |
| `tests/`                                  | Tests for the demo app and preflight checks                      |

## Demo app

The included demo is a sequence composition explorer.

Paste a nucleotide sequence, with or without a FASTA header, to view:

* sequence length
* GC content
* base composition
* sliding-window GC content

The demo is intentionally small and has no model or large data dependency, so it is easy to replace with your own application.

## Preflight checks

Run:

```bash
python scripts/preflight.py
```

For stricter checks, including warnings:

```bash
python scripts/preflight.py --strict
```

The preflight script checks areas such as:

* required repository files
* Docker image and user configuration
* exposed port and Gradio host binding
* pinned Python dependencies
* unsafe or unsupported Gradio settings
* container image platform and tag rules
* accidentally committed secrets or `.env` files

A successful run ends with:

```text
Preflight OK.
```

## Full local validation

Before deploying, you can run the same basic checks locally:

```bash
python scripts/preflight.py --strict
pytest -q
docker build --platform linux/amd64 -t trial:local .
docker run --rm -p 7860:7860 trial:local
```

Then open:

```text
http://127.0.0.1:7860
```

## Important Serve requirements

A few deployment rules are easy to miss:

* the container must not run as root
* the application must use an allowed Serve port
* Gradio must listen on `0.0.0.0`
* container images must target `linux/amd64`
* reusing an image tag can cause Serve to keep running an older image
* applications that handle sensitive data or require user accounts may need a different hosting solution

See the current SciLifeLab Serve documentation before changing these assumptions.

## Licence

MIT. See [`LICENSE`](LICENSE).

## Help

* SciLifeLab Serve documentation: https://serve.scilifelab.se/docs/
* Gradio on SciLifeLab Serve: https://serve.scilifelab.se/docs/application-hosting/gradio/
* Serve support: [serve@scilifelab.se](mailto:serve@scilifelab.se)
