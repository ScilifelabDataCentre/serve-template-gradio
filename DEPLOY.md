# Deploying this app on SciLifeLab Serve

There is no API to deploy an app. The last step is always a human filling in a
web form, so this file exists to make that step mechanical. Everything before it
is automated.

## 1. Publish the image

Push to `main`. The `Publish image to GHCR` workflow builds for `linux/amd64`,
tags the image with a timestamp plus short SHA, and prints the full reference in
the run summary.

**The first time only:** make the package public, or Serve cannot pull it.
Repository, then Packages, then your package, then Package settings, then Change
visibility, then Public.

If you would rather build by hand:

```bash
TAG=$(date -u +%Y%m%d-%H%M%S)
docker build --platform linux/amd64 -t ghcr.io/<owner>/<repo>:$TAG .
docker push ghcr.io/<owner>/<repo>:$TAG
```

Never reuse a tag. Serve will not re-pull one it has already deployed, and your
app will keep serving the old build with no error anywhere.

## 2. Fill in the Serve form

Log in at <https://serve.scilifelab.se>, open or create a project, then click
**Create** on the **Gradio app** card.

| Field | Value | Why |
|---|---|---|
| **Subdomain** | your choice, for example `sequence-explorer` | Becomes `<subdomain>.serve.scilifelab.se`. Left empty, Serve generates one |
| **Mount path** | `None` | This app stores nothing. Pick a mount path only if your app reads or writes files that must survive a restart, and configure it first under project Settings, then Storage |
| **Hardware** | default | 2 vCPU and 4 GB RAM. Email serve@scilifelab.se with a motivation if you need up to 12 vCPU and 48 GB |
| **Port** | `7860` | What the Dockerfile exposes. Serve allows 3000 to 9999 |
| **Image** | `ghcr.io/<owner>/<repo>:<tag>` | Copy it from the CI run summary. Must be public |
| **Title** | your app's display name | Shown on the public Apps page |
| **Description** | two or three sentences | Functions as the abstract for the app |
| **Subjects and keywords** | pick a few | Used for discovery |
| **Permissions** | `Public` or `Link` or `Private` or `Project`| `Link` is the right choice while a paper is under review |
| **Creators** | you, and co-authors | ORCID lookup fills the details in |
| **Language of the application interface** | usually English | |
| **Funding sources** | funder and grant number | |
| **Source code URL** | this repository, or a DOI | Serve requires the code to be public |

Submit. The status goes from Pending to Running, and the app may take another
minute or two to answer after that.

## 3. Updating the app

1. Push your change to `main`.
2. Wait for CI, copy the new image reference from the run summary.
3. On Serve: app **Settings**, replace the tag in the **Image** field, **Update**.

Changing the tag is the whole mechanism. If the app looks unchanged after an
update, the tag was almost certainly reused.

## 4. Before you make it public

- [ ] `python scripts/preflight.py` exits 0
- [ ] No credentials anywhere in the repository or its history. The code is public
- [ ] No sensitive, personal or re-identifiable data in the app or in any bundled file
- [ ] The app returns to its default state for a new visitor
- [ ] The GHCR package is public, and you intend to leave it public. Serve re-pulls
      the image on a schedule, and a deleted or private image takes the app down
- [ ] A `LICENSE` that permits others to reuse the code

Public apps receive a DOI. See <https://serve.scilifelab.se/docs/doi/>.
