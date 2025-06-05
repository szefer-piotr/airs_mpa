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
import pandas as pd

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
    all_hypotheses_accepted = False,
    all_plans_generated = False,
    all_plans_executed = False,
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
    data_mannually_updated=False
)


def init_state() -> None:
    """Ensure every expected key exists in `st.session_state`."""
    for k, v in DEFAULT_STATE.items():
        st.session_state.setdefault(k, v)


def show_data_summary(summary: dict) -> None:
    """
    Render the `summary` dict returned by your analysis pipeline
    in a compact, user-friendly table.

    Parameters
    ----------
    summary : dict
        A dict with the shape
        {
            "columns": {
                <col_name>: {
                    "column_name": str,
                    "description": str,
                    "type": str,
                    "unique_value_count": int,
                },
                ...
            }
        }
    """
    # -------------------- 1. Flatten --------------------
    df = (
        pd.DataFrame(summary["columns"])   # keys become columns
        .T                                 # flip so each col is a row
        .rename_axis("Column")             # index label
        .reset_index()                     #  ➜ ordinary column
        .loc[:, ["Column", "description", "type", "unique_value_count"]]
        .rename(
            columns={
                "description": "Description",
                "type": "Type",
                "unique_value_count": "Unique values",
            }
        )
    )

    # -------------------- 2. Display --------------------
    st.dataframe(
        df,
        use_container_width=True,          # stretch to sidebar/main width
        hide_index=True,
        height=min(400, 38 * len(df) + 38) # auto-shrink if few rows
    )


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


def extract_json_fragment(text: str) -> Optional[str]:
    m = JSON_RE.search(text)
    return m.group(0) if m else None



def _mk_fallback_plan(text: str) -> Dict[str, Any]:
    """Convert a loose Markdown plan → canonical dict."""
    lines   = [ln.strip() for ln in text.splitlines() if ln.strip()]
    title   = lines[0].lstrip("# ") if lines else "Analysis Plan"
    steps   = []
    for ln in lines[1:]:
        m = STEP_RE.match(ln)
        if m:
            steps.append({"step": m.group(1).strip()})
    if not steps:  # fall back to one‑chunk step
        steps = [{"step": text.strip()}]
    return {"analyses": [{"title": title, "steps": steps}]}



def safe_load_plan(raw: Any) -> Optional[Dict[str, Any]]:
    """Return plan dict from dict / JSON / python literal / markdown."""
    if isinstance(raw, dict):
        return raw
    if not raw:  # empty / None
        return None

    if isinstance(raw, str):
        txt = raw.strip()
        if txt.startswith("```"):
            txt = txt.lstrip("` pythonjson").rstrip("`").strip()

        # 1️⃣ json.loads with double quotes
        try:
            return json.loads(txt)
        except json.JSONDecodeError:
            # 2️⃣ ast.literal_eval for single‑quoted dicts
            try:
                obj = ast.literal_eval(txt)
                if isinstance(obj, dict):
                    return obj
            except Exception:
                pass
            # 3️⃣ fragment inside markdown
            frag = extract_json_fragment(txt)
            if frag:
                try:
                    return json.loads(frag)
                except json.JSONDecodeError:
                    pass
            # 4️⃣ fallback – build from markdown bullets
            return _mk_fallback_plan(txt)
    return None



def ensure_execution_keys(h):
    h.setdefault("plan_execution_chat_history", [])
    return h

IMG_DIR = Path("images"); IMG_DIR.mkdir(exist_ok=True)
JSON_RE  = re.compile(r"\{[\s\S]*?\}")
STEP_RE  = re.compile(r"^(?:\d+\.\s+|[-*+]\s+)(.+)")


# def replace_file_ids_with_html(text: str) -> str:
#     """
#     Scans the given text for file IDs of the form "file-<alphanumeric>"
#     and replaces each occurrence with an <img> tag whose source is the
#     corresponding base64‐encoded image bytes stored in st.session_state.images.

#     Assumes:
#     - st.session_state.images is a list of dicts, each with keys:
#         - "fid": the file ID string (e.g., "file-KsuFnyXE1Upst5o1GAHGip")
#         - "img_bytes": raw bytes of a PNG or JPG image
#     - If a matched file ID has no entry in st.session_state.images, it is left unchanged.

#     Returns:
#         The input text with every recognized file ID replaced by centered <img> HTML.
#     """
#     # Prebuild a lookup from fid → base64‐encoded HTML snippet
#     fid_to_html = {}
#     for img_dict in st.session_state.images:
#         fid = img_dict.get("fid")
#         img_bytes = img_dict.get("img_bytes")
#         if fid and img_bytes:
#             b64 = base64.b64encode(img_bytes).decode("utf-8")
#             img_html = f'<p align="center"><img src="data:image/png;base64,{b64}" width="600"></p>'
#             fid_to_html[fid] = img_html

#     # Define a regex to find substrings like "file-<alphanumeric>"
#     pattern = re.compile(r"\bfile-[A-Za-z0-9]+\b")

#     # Replacement function: if we have HTML for this fid, return it; else, leave unchanged
#     def _replace_match(match: re.Match) -> str:
#         fid = match.group(0)
#         return fid_to_html.get(fid, fid)

#     # Substitute all occurrences in the text
#     replaced_text = pattern.sub(_replace_match, text)
#     return replaced_text

def replace_file_ids_with_html(text: str) -> str:
    """
    Replace every `file-<alphanumeric>` token in *text* with an <img> tag whose
    bytes live in st.session_state.images.  
    Surrounding back-ticks or quote marks are removed as part of the match, so
    they never appear in the output.
    """
    # Pre-compute fid → HTML snippet
    fid_to_html = {}
    for img in st.session_state.images:
        fid, img_bytes = img.get("fid"), img.get("img_bytes")
        if fid and img_bytes:
            b64 = base64.b64encode(img_bytes).decode("utf-8")
            fid_to_html[fid] = (
                f'<p align="center"><img src="data:image/png;base64,{b64}" '
                f'width="600"></p>'
            )

    # ── regex ──────────────────────────────────────────────────────────────
    # 1. (?<!\w)  ensures we’re not in the middle of a word
    # 2. [`'\"“”‘’]? optionally captures a single surrounding mark
    # 3. (file-[A-Za-z0-9]+) captures the raw fid (no punctuation)
    # 4. same optional mark on the right
    # 5. (?!\w)   ensures we end on a word boundary, too
    pattern = re.compile(
        r"(?<!\w)(?:[`'\"“”‘’])?"
        r"(file-[A-Za-z0-9]+)"
        r"(?:[`'\"“”‘’])?(?!\w)"
    )

    def _replace(match: re.Match) -> str:
        fid = match.group(1)  # clean fid, guaranteed no punctuation
        return fid_to_html.get(fid, fid)  # keep raw fid if we have no image

    return pattern.sub(_replace, text)