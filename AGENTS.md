# SciLifeLab Serve: rules for this repository

You are helping build a **Gradio** app that will be hosted on **SciLifeLab Serve**.

The rules below are platform requirements, not preferences. Breaking one produces
an app that builds and runs perfectly on a laptop and then fails on Serve, which
is the single most common support request the Serve team receives. Do not relax
them because they seem unnecessary, and do not "simplify" them away.

If the user asks for something that conflicts with a rule, say so and propose an
alternative rather than silently breaking the rule.

## Hard invariants

1. **Port 7860.** `EXPOSE 7860` in the Dockerfile, and the server must listen on
   it. Serve permits ports 3000 to 9999 only.
2. **Bind to all interfaces in the container.** `ENV GRADIO_SERVER_NAME=0.0.0.0`.
   A server bound to 127.0.0.1 is unreachable on Serve.
3. **Run as non-root, UID 1000.** `RUN useradd -m -u 1000 $USER` and a final
   `USER $USER` before `CMD`. Not root, and not any other UID.
4. **Entry point is `app/main.py`**, copied into `WORKDIR`. Keep the file name.
   The Serve documentation and the official example app both use `main.py`.
5. **Build for `linux/amd64`.** Serve runs amd64 nodes. On Apple Silicon you
   must pass `--platform linux/amd64` or the image will not start.
6. **Every published image needs a unique tag. Never `latest`.** Once a tag has
   been deployed, Serve will not fetch a new build under the same tag, and the
   app will silently keep serving the old version. CI handles this for you with
   a timestamp plus short SHA.
7. **The image must stay public and available forever.** Serve re-pulls it on a
   schedule. Deleting or privating the image takes the app down.
8. **`app/requirements.txt`, pinned with `==`.** Not `requirements.py`, not
   unpinned ranges.
9. **No user accounts.** No `launch(auth=...)`, no login screen, no registration,
   no user database. Serve does not permit apps that manage their own users.
10. **Stateless.** Every new visitor must get the app in its default state. Do
    not keep per-user state on the server between visits.
11. **No database service.** There is none to attach. If you need persistence,
    it is SQLite on a mounted project volume, and never for personal data.
12. **No sensitive or personal data, ever.** This includes patient data, human
    subject data and anything re-identifiable. If the task requires it, stop and
    tell the user that Serve is the wrong host.
13. **Uploads.** 100 MB limit per file. Set `GRADIO_TEMP_DIR` inside the user's
    home if the app accepts files, and clean up: Gradio uploads break once temp
    files pass 5 GB.
14. **Never commit a secret.** Code and image are public, so a committed key is
    public the moment it is pushed. There are no runtime secrets to configure.
15. **`share=False`.** Never open a Gradio tunnel from a hosted app.

## Before you tell the user you are done

```bash
python scripts/preflight.py     # must exit 0
pytest -q                       # must pass
```

`preflight.py` is the contract in executable form. If it fails, fix the code it
points at. **Do not edit the checks to make them pass.** If you believe a check
is wrong, say so in your reply and leave it alone.

## Local development

```bash
pip install -r app/requirements.txt
python app/main.py               # http://127.0.0.1:7860
```

The container sets `GRADIO_SERVER_NAME=0.0.0.0`; locally the app falls back to
127.0.0.1, which is intentional.

## Everything else lives in the documentation

Form fields, permission levels, hardware requests, storage mount paths, DOIs,
the FAQ. Do not copy these pages into this repository, they change more often
than the rules above.

- Gradio guide: <https://serve.scilifelab.se/docs/application-hosting/gradio/>
- Custom app requirements, the source of the UID 1000 and port range rules:
  <https://serve.scilifelab.se/docs/application-hosting/other/>
- Raw Markdown of any docs page: append `_source/` to its URL, for example
  <https://serve.scilifelab.se/docs/application-hosting/gradio/_source/>

**This file is the authoritative statement of the rules for now.** A single
consolidated contract page on the Serve docs is planned but does not exist yet,
so do not try to fetch `/docs/deployment-contract/`. When it ships, the fifteen
rules above become a pointer to it.

If you cannot fetch a URL because your environment has no network access, the
fifteen rules above are sufficient to produce a working deployment. Say that you
could not fetch the page rather than guessing at its contents.

## Known platform quirks worth remembering

- Gradio apps have a **known bug with `Private` and `Project` permissions** on
  Serve. Use `Public` or `Link` while developing.
- Serve app logs are kept for 24 hours, for debugging only. Do not add user
  tracking, and do not log user input.
- App creation itself is a web form. There is no API to deploy, so the last step
  is always a human pasting values from `DEPLOY.md` into the Serve interface.
