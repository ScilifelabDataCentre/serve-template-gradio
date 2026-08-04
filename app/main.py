"""Toy Gradio app for the SciLifeLab Serve template.

Sequence composition explorer: paste a nucleotide sequence, get its base
composition and a sliding-window GC plot.

Keep the file name main.py. The Dockerfile runs `python main.py` and the
SciLifeLab Serve documentation uses the same convention for Gradio apps.

Deployment rules that this file must not break, see AGENTS.md:
  - bind to 0.0.0.0 in the container, via GRADIO_SERVER_NAME
  - listen on 7860, which is inside the 3000 to 9999 range Serve allows
  - no auth=, no login, no share=True
  - stateless: every visitor gets the app in its default state
"""

from __future__ import annotations

import os

import gradio as gr
import pandas as pd

from analysis import EXAMPLE_SEQUENCE, gc_windows, summarise

# Serve allows ports 3000-9999. 7860 is the Gradio default and what the docs
# tell you to type into the Port field of the app form.
DEFAULT_PORT = 7860

CSS = """
.gradio-container {font-family: Georgia, "Times New Roman", serif;}
#summary {background: #faf6ee; border: 1px solid #e0d6c2; border-radius: 8px; padding: 12px;}
"""


def analyse(raw: str, window: int):
    """Interface callback. Returns markdown, a composition frame and a GC frame."""
    result = summarise(raw)
    seq, length = result["sequence"], result["length"]

    if length == 0:
        empty = pd.DataFrame({"base": [], "count": []})
        return (
            "No nucleotides found. Paste a DNA or RNA sequence, FASTA headers are fine.",
            empty,
            pd.DataFrame({"position": [], "gc": []}),
        )

    note = ""
    if result["dropped"]:
        note = f"  \nIgnored {result['dropped']} unrecognised character(s)."

    summary = (
        f"**Length** {length} bp{note}  \n"
        f"**GC content** {result['gc'] * 100:.1f} %  \n"
        f"**Counts** "
        + ", ".join(f"{b} {n}" for b, n in result["counts"].items() if n)
    )

    composition = pd.DataFrame(
        {
            "base": list(result["counts"].keys()),
            "count": list(result["counts"].values()),
        }
    )

    points = gc_windows(seq, window)
    if points:
        gc_frame = pd.DataFrame(points, columns=["position", "gc"])
    else:
        summary += f"  \n_Sequence is shorter than the {window} bp window, no GC track._"
        gc_frame = pd.DataFrame({"position": [], "gc": []})

    return summary, composition, gc_frame


def build() -> gr.Blocks:
    """Build the interface. Importable, so tests can construct it without serving."""
    # Gradio 6 takes css in launch(), not in the Blocks constructor.
    with gr.Blocks(title="Sequence composition explorer") as demo:
        gr.Markdown(
            "# Sequence composition explorer\n"
            "A minimal demo app for the SciLifeLab Serve Gradio template. "
            "Replace it with your own app, keep the deployment contract."
        )

        with gr.Row():
            with gr.Column(scale=3):
                sequence = gr.Textbox(
                    label="Nucleotide sequence",
                    value=EXAMPLE_SEQUENCE,
                    lines=8,
                    max_lines=14,
                )
                window = gr.Slider(
                    label="GC window (bp)",
                    minimum=10,
                    maximum=150,
                    value=40,
                    step=10,
                )
                run = gr.Button("Analyse", variant="primary")
            with gr.Column(scale=2):
                summary = gr.Markdown(elem_id="summary")

        with gr.Row():
            composition = gr.BarPlot(
                x="base",
                y="count",
                title="Base composition",
                x_title="Base",
                y_title="Count",
            )
            gc_track = gr.LinePlot(
                x="position",
                y="gc",
                title="Sliding-window GC content",
                x_title="Position (bp)",
                y_title="GC fraction",
            )

        outputs = [summary, composition, gc_track]
        run.click(analyse, inputs=[sequence, window], outputs=outputs)
        # Populate on page load so a visitor sees a working app immediately.
        # This is also what keeps the app stateless: no server-side session.
        demo.load(analyse, inputs=[sequence, window], outputs=outputs)

    return demo


if __name__ == "__main__":
    demo = build()
    demo.queue(max_size=20).launch(
        css=CSS,
        # In the container GRADIO_SERVER_NAME is set to 0.0.0.0 by the
        # Dockerfile. Locally it falls back to localhost, which is what you
        # want on a laptop.
        server_name=os.environ.get("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.environ.get("GRADIO_SERVER_PORT", DEFAULT_PORT)),
        # Server-side rendering needs Node in the image. Off keeps the image
        # small and the startup predictable.
        ssr_mode=False,
        # Never enable these on Serve: share opens a public tunnel, and Serve
        # does not allow apps with their own user accounts or login.
        share=False,
    )
