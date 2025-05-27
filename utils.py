"""
utils.py  ·  Shared constants, schemas and helper functions
==========================================================

All pages in the multipage Streamlit app should import *only* from this file.
Nothing here creates network connections or writes to disk, so it is safe to
`import utils` at the top of every page without side-effects.
"""
from __future__ import annotations

import ast
import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st
from pydantic import BaseModel


# ────────────────────────────────────────────────────────────────────────────
# REGEXES for plan-parsing helpers
# ────────────────────────────────────────────────────────────────────────────
JSON_RE = re.compile(r"\{[\s\S]*?\}")
STEP_RE = re.compile(r"^(?:\d+\.\s+|[-*+]\s+)(.+)")


# ────────────────────────────────────────────────────────────────────────────
# HELPER FUNCTIONS (UI renderers & plan parsing)
# ────────────────────────────────────────────────────────────────────────────
def render_hypothesis_md(hyp: Dict[str, Any]) -> str:
    """Return a Markdown block summarising one hypothesis object."""
    md: List[str] = [f"### {hyp['title']}"]
    if hyp.get("hypothesis_refined_with_data_text"):
        md.append(f"{hyp['hypothesis_refined_with_data_text']}")
    if hyp.get("final_hypothesis"):
        md.append("\n **Accepted version:**\n")
        md.append(f"{hyp['final_hypothesis']}")
    return "\n".join(md)


def format_initial_assistant_msg(hyp: Dict[str, Any]) -> str:
    """Seed message shown in chat after initial refinement."""
    return (
        f"**Refined hypothesis:** {hyp['title']}\n\n"
        f"{hyp['hypothesis_refined_with_data_text']}"
    )


def update_csv_key():
    st.session_state.uploader_csv_key += 1

def update_txt_key():
    st.session_state.uploader_txt_key += 1

# ---- Plan-text → dict helpers ------------------------------------------------
def extract_json_fragment(text: str) -> Optional[str]:
    m = JSON_RE.search(text)
    return m.group(0) if m else None


def _mk_fallback_plan(text: str) -> Dict[str, Any]:
    """If no valid JSON, derive a very rough plan from markdown bullets."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title = lines[0].lstrip("# ") if lines else "Analysis Plan"
    steps = []
    for ln in lines[1:]:
        m = STEP_RE.match(ln)
        if m:
            steps.append({"step": m.group(1).strip()})
    if not steps:
        steps = [{"step": text.strip()}]
    return {"analyses": [{"title": title, "steps": steps}]}


def safe_load_plan(raw: Any) -> Optional[Dict[str, Any]]:
    """
    Robustly turn user/assistant output into a plan dict.
    Accepts true dict, JSON string, python-literal string or markdown list.
    """
    if isinstance(raw, dict):
        return raw
    if not raw:
        return None

    if isinstance(raw, str):
        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.lstrip("` pythonjson").rstrip("`").strip()

        # 1️⃣ JSON with double quotes
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            # 2️⃣ python literal with single quotes
            try:
                obj = ast.literal_eval(txt)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
            # 3️⃣ JSON fragment inside markdown
            frag = extract_json_fragment(txt)
            if frag:
                try:
                    return json.loads(frag)
                except json.JSONDecodeError:
                    pass
            # 4️⃣ fallback: build from bullet list
            return _mk_fallback_plan(txt)
    return None


# ────────────────────────────────────────────────────────────────────────────
# UI UTILITIES
# ────────────────────────────────────────────────────────────────────────────
def add_green_button_css() -> None:
    """Global CSS so *enabled* buttons are green; disabled are grey."""
    st.markdown(
        """
        <style>
        div.stButton > button:enabled {
            background-color:#28a745 !important; color:white !important;
        }
        div.stButton > button:disabled {
            background-color:#d0d0d0 !important; color:#808080 !important;
            cursor:not-allowed !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ────────────────────────────────────────────────────────────────────────────
# SESSION-STATE MANAGEMENT
# ────────────────────────────────────────────────────────────────────────────
DEFAULT_STATE: Dict[str, Any] = dict(
    # workflow flags
    app_state="upload",
    data_uploaded=False,
    hypotheses_uploaded=False,
    processing_done=False,
    # user files & OpenAI artefacts
    files={},               # {filename: BytesIO}
    file_ids=[],            # IDs returned by client.files.create
    thread_id="",
    images=[],              # list[{"image_path":Path,"file_id":str,"html":str}]
    # data & hypothesis content
    hypotheses="",          # raw txt from upload
    data_summary="",        # dict from DataSummary assistant
    updated_hypotheses={},  # refined list incl. chat logs
    # navigation helpers
    selected_hypothesis=0,
    current_hypothesis_idx=0,
    current_exec_idx=0,
    # downstream
    approved_hypotheses=[],
    report_generated=False,
    final_report=[],
    uploader_csv_key = 0,
    uploader_txt_key = 0,
)


def init_state() -> None:
    """Ensure every expected key exists in `st.session_state`."""
    for k, v in DEFAULT_STATE.items():
        st.session_state.setdefault(k, v)


# ────────────────────────────────────────────────────────────────────────────
# IMAGE EMBEDDER (re-used by report page)
# ────────────────────────────────────────────────────────────────────────────
def embed_local_images(markdown: str, img_dir: Path | str = "images", width: int = 600) -> str:
    """
    Replace bare image file paths in a markdown string with inlined base64 HTML.
    Useful when piping Code-Interpreter PNGs into the final report.
    """
    img_dir = Path(img_dir)

    def _replace(match: re.Match) -> str:
        path_str = match.group(0)
        p = Path(path_str)
        if not p.is_absolute():
            p = img_dir / p
        if not p.exists():
            return f"[Image not found: {p}]"
        data = p.read_bytes()
        b64 = base64.b64encode(data).decode()
        return (
            f'<p align="center"><img src="data:image/png;base64,{b64}" '
            f'width="{width}"></p>'
        )

    return re.sub(r'[\w./\\-]+(?:\.png|\.jpg|\.jpeg|\.gif)', _replace, markdown)
