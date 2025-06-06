# pages/02_Processing_files.py
# ───────────────────────────────────────────────────────────────────────────
"""Streamlit page 02 – File processing & hypothesis refinement."""

from __future__ import annotations

# ── std-lib ────────────────────────────────────────────────────────────────
import base64
import json
import logging
from typing import Any, Dict, List

# ── 3rd-party ──────────────────────────────────────────────────────────────
import streamlit as st

import time
from openai.types.beta.threads.runs.code_interpreter_tool_call import (
    CodeInterpreterOutputImage,
    CodeInterpreterOutputLogs,
)

# ── app modules ────────────────────────────────────────────────────────────
from info import STAGE_INFO
from utils import (
    init_state,
    add_green_button_css,
    add_modern_font_css,
    format_initial_assistant_msg,
    show_data_summary,
)
from assistants import create as get_assistants
from assistants import client
from instructions import processing_files_instruction, refinig_instructions
from schemas import response_format, hypotheses_schema

# ─────────────────────────── Globals & logging ────────────────────────────
ASSISTANTS = get_assistants()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ═══════════════════════════ Session bootstrap ════════════════════════════
def _init_session_state() -> None:
    """Ensure all custom session keys are present exactly once."""
    defaults: Dict[str, Any] = {
        # processing status
        "processing_done":     False,
        "need_refinement":     False,
        "edit_mode":           False,
        # uploads
        "data_uploaded":       False,
        "hypotheses_uploaded": False,
        "file_ids":            [],
        # OpenAI artefacts
        "thread_id":           None,
        # results
        "data_summary":        {},
        "hypotheses":          [],
        "updated_hypotheses":  {},
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

# ═══════════════════════════ OpenAI helpers ════════════════════════════════
def refine_hypotheses() -> None:
    """Use GPT-4o to refine hypotheses against the current data summary."""
    prompt = (
        f"Data summary: {st.session_state.data_summary}\n\n"
        f"Hypotheses: {st.session_state.hypotheses}\n\n"
        f"{processing_files_instruction}\n"
    )

    rsp = client.responses.create(
        model="gpt-4o",
        instructions=refinig_instructions,
        input=[{"role": "user", "content": prompt}],
        tools=[{"type": "web_search_preview"}],
        text=hypotheses_schema,
    )

    st.session_state.updated_hypotheses = json.loads(rsp.output_text)
    for hyp in st.session_state.updated_hypotheses["assistant_response"]:
        hyp["chat_history"]     = [
            {"role": "assistant", "content": format_initial_assistant_msg(hyp)}
        ]
        hyp["final_hypothesis"] = []

    st.success("Hypotheses refined!", icon="✅")


def generate_data_summary() -> None:
    """Run the assistant once, show a spinner, then display the final JSON."""
    if not st.session_state.thread_id:
        st.session_state.thread_id = client.beta.threads.create().id

    # ─ upload any new files ─
    if not st.session_state.file_ids:
        for name, file_obj in st.session_state.files.items():
            logger.info("Uploading %s …", name)
            fid = client.files.create(file=file_obj, purpose="assistants").id
            st.session_state.file_ids.append(fid)

    client.beta.threads.update(
        thread_id=st.session_state.thread_id,
        tool_resources={"code_interpreter": {"file_ids": st.session_state.file_ids}},
    )

    # ─────────── run assistant (non-stream) ───────────
    with st.spinner("Running data-summary assistant…"):
        run = client.beta.threads.runs.create(
            thread_id=st.session_state.thread_id,
            assistant_id=ASSISTANTS["data_summary"].id,
            response_format=response_format,
        )

        # poll until complete
        while run.status not in {"completed", "failed", "cancelled", "expired"}:
            time.sleep(1.0)
            run = client.beta.threads.runs.retrieve(
                thread_id=st.session_state.thread_id, run_id=run.id
            )

    if run.status != "completed":
        st.error(f"❌ Run ended with status: **{run.status}**")
        return

    # ─────────── fetch last message & parse JSON ───────────
    try:
        msg = client.beta.threads.messages.list(
            thread_id=st.session_state.thread_id, order="desc"
        ).data[0]

        st.session_state.data_summary  = json.loads(msg.content[0].text.value)
        st.session_state.need_refinement = True
        st.session_state.processing_done = True
        st.success("Data summary ready!", icon="✅")

    except Exception as exc:  # noqa: BLE001
        st.error(f"❌ Could not parse JSON: {exc}")
        raise


# ═══════════════════════════ Metadata editor ══════════════════════════════
def edit_data_summary() -> None:
    """Interactive form to tweak column descriptions / types."""
    st.subheader("Edit column metadata")

    defaults  = {"int", "float", "str", "bool", "datetime",
                 "list", "dict", "NoneType", "category"}
    existing  = {meta.get("type", "str")
                 for meta in st.session_state.data_summary["columns"].values()}
    py_types  = tuple(sorted(defaults | existing))

    with st.form("edit_metadata", clear_on_submit=False):
        for col, meta in st.session_state.data_summary["columns"].items():
            desc_col, type_col = st.columns([3, 1])

            with desc_col:
                st.text_area(
                    f"{col} description",
                    value=meta["description"],
                    key=f"desc_{col}",
                    height=80,
                )

            with type_col:
                cur = meta.get("type", "str")
                st.selectbox(
                    f"{col} type",
                    options=py_types,
                    index=py_types.index(cur) if cur in py_types else py_types.index("str"),
                    key=f"type_{col}",
                )

        save_col, cancel_col = st.columns(2)
        save   = save_col.form_submit_button("💾 Save",   type="primary")
        cancel = cancel_col.form_submit_button("❌ Cancel")

    if save:
        for col in st.session_state.data_summary["columns"]:
            meta                    = st.session_state.data_summary["columns"][col]
            meta["description"]     = st.session_state[f"desc_{col}"]
            meta["type"]            = st.session_state[f"type_{col}"]

        st.session_state.edit_mode       = False
        st.session_state.need_refinement = True
        st.success("Column metadata updated!")
        st.rerun()

    elif cancel:
        for col in st.session_state.data_summary["columns"]:
            st.session_state.pop(f"desc_{col}", None)
            st.session_state.pop(f"type_{col}", None)
        st.session_state.edit_mode = False
        st.info("No changes saved.")
        st.rerun()


def add_sidebar_button_styles() -> None:
    """Make every sidebar button transparent except NEXT STAGE (green)."""
    st.markdown(
        """
        <style>
            /* All sidebar buttons… */
            div[data-testid="stSidebar"] button {
                background: transparent !important;
                color: var(--text-color) !important;
                border: 1px solid var(--text-color) !important;
            }
            /* …except the one we mark as 'primary' (NEXT STAGE).           */
            div[data-testid="stSidebar"] button[data-baseweb="button-primary"] {
                background: #00A86B !important;  /* pleasant green */
                color: #fff !important;
                border: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ═══════════════════════════ Main page ════════════════════════════════════
def main() -> None:  # noqa: C901 – single entry-point, clear sections
    # ── page init & styling ──────────────────────────────────────────────
    init_state()              # must be *first* Streamlit call
    add_green_button_css()
    add_modern_font_css() 
    _init_session_state()
    add_sidebar_button_styles()  

    # ── upfront guard ────────────────────────────────────────────────────
    if not (st.session_state.data_uploaded and st.session_state.hypotheses_uploaded):
        st.warning("Upload files first to process them.")
        st.stop()

    if not st.session_state.processing_done:
        st.markdown(STAGE_INFO["processing"])
    else:
        st.info("You can now proceed to the hypotheses refinement stage.")

    # ── sidebar actions ─────────────────────────────────────────────────
    # ─ sidebar buttons ─
    with st.sidebar:
        st.header("Actions")

        # 1️⃣ edit (transparent)
        st.button("✏️ Manually edit data summary",
                disabled=not bool(st.session_state.data_summary))

        # 2️⃣ processing (transparent)
        processing_label = (
            "Start File Processing"
            if not st.session_state.processing_done
            else "Run processing again"
        )
        processing_click = st.button(processing_label)

        # 3️⃣ NEXT STAGE (the *only* green one)
        if st.session_state.processing_done:
            if st.button("NEXT STAGE", type="primary"):
                st.switch_page("pages/03_Hypotheses_manager.py")

    # ── edit mode ───────────────────────────────────────────────────────
    if st.session_state.edit_mode:
        edit_data_summary()

    # ── processing / re-processing ──────────────────────────────────────
    if processing_click:
        st.session_state.processing_done = False
        generate_data_summary()
        st.rerun()

    # ── refinement if flagged ───────────────────────────────────────────
    if st.session_state.need_refinement and st.session_state.data_summary:
        refine_hypotheses()
        st.session_state.need_refinement = False

    # ── show results ────────────────────────────────────────────────────
    if st.session_state.processing_done:
        st.markdown("#### Data summary")
        show_data_summary(st.session_state.data_summary)

        st.divider()
        st.markdown("#### Refined hypotheses")
        for hyp in st.session_state.updated_hypotheses.get("assistant_response", []):
            st.markdown(f"##### {hyp['title']}")
            st.markdown(hyp["hypothesis_refined_with_data_text"])


if __name__ == "__main__":
    main()
