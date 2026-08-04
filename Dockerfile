# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# SciLifeLab Serve compatible image for a Gradio app.
#
# Every rule below is a platform requirement, not a style preference. If you
# change one, the app will very likely build locally and then fail on Serve.
# See AGENTS.md for the full list and scripts/preflight.py for the checks.
#
# Build for amd64, always:
#   docker build --platform linux/amd64 -t my-app:$(date -u +%Y%m%d-%H%M%S) .
# ---------------------------------------------------------------------------

# Pin the base image to a minor version. Never use :latest, here or anywhere.
FROM python:3.12-slim

# Serve requires the container to run as a non-root user with UID 1000.
ENV USER=serveuser
ENV HOME=/home/$USER
RUN useradd -m -u 1000 $USER

# The working directory is where your entry point has to live.
WORKDIR $HOME/app

# Dependencies first, so this layer stays cached while you iterate on the app.
# No build-essential needed: gradio and pandas ship prebuilt wheels, and the
# smaller image pulls faster when Serve re-fetches it.
COPY app/requirements.txt $HOME/app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Application code. Add a COPY line for every new file your app needs.
COPY app/main.py $HOME/app/main.py
COPY app/analysis.py $HOME/app/analysis.py

# If your app accepts file uploads, Gradio needs a writable temp directory
# inside the user's home. The upload limit on Serve is 100 MB, and Gradio
# uploads start failing once temp files exceed 5 GB, so clean up after use.
ENV GRADIO_TEMP_DIR=$HOME/app/tmp
RUN mkdir -p $GRADIO_TEMP_DIR && chown -R $USER:$USER $HOME

# Do not phone home from a research platform.
ENV GRADIO_ANALYTICS_ENABLED=False

# Everything after this line runs as UID 1000.
USER $USER

# Serve allows ports 3000-9999 only. 7860 is the Gradio default and the value
# you type into the Port field of the Serve app form.
EXPOSE 7860
ENV GRADIO_SERVER_NAME=0.0.0.0
ENV GRADIO_SERVER_PORT=7860

# Healthcheck in Python, not curl: slim base images ship no curl, so a
# curl-based HEALTHCHECK can only ever fail. Useful for `docker run` locally.
HEALTHCHECK --interval=30s --timeout=5s --start-period=45s --retries=3 \
    CMD python -c "import urllib.request as u, sys; sys.exit(0 if u.urlopen('http://127.0.0.1:7860/', timeout=4).status == 200 else 1)"

CMD ["python", "main.py"]
