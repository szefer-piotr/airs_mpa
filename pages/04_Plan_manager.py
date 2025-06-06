# pages/04_Plan_manager.py
# ───────────────────────────────────────────────────────────────────────────
"""Stage 4 – Analysis-plan manager."""

from __future__ import annotations

# ── std-lib ────────────────────────────────────────────────────────────────
import json
import logging
from typing import Dict, List

# ── 3rd-party ──────────────────────────────────────────────────────────────
import streamlit as st

# ── app modules ────────────────────────────────────────────────────────────
from assistants import client
from instructions import (
    analyses_step_generation_instructions,
    analyses_step_chat_instructions,
)
from schemas import plan_generation_response_schema
from utils import (
    init_state,
    add_green_button_css,
    add_modern_font_css,
)

# ───────────────────────── logging ────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ═══════════════════════════  Styling helpers  ════════════════════════════
def add_sidebar_button_styles() -> None:
    """Transparent sidebar buttons; the *primary* one (NEXT) is green."""
    st.markdown(
        """
        <style>
            /* default: outline buttons in the sidebar */
            div[data-testid="stSidebar"] button {
                background: transparent !important;
                color: var(--text-color) !important;
                border: 1px solid var(--text-color) !important;
            }
            /* the one we mark as 'primary' (NEXT) */
            div[data-testid="stSidebar"] button[data-baseweb="button-primary"] {
                background: #00A86B !important;
                color: #fff !important;
                border: none !important;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )



# ═══════════════════════════  Helper functions  ═══════════════════════════
def pretty_markdown_plan(raw_json: str) -> str:
    """Convert the assistant-returned plan JSON to readable Markdown."""
    try:
        data = json.loads(raw_json)
        md = []
        for ana in data.get("analyses", []):
            md.append(f"### {ana['title']}\n")
            for idx, step in enumerate(ana["steps"], 1):
                md.append(f"{idx}. {step['step']}")
            md.append("")                               # blank line
        return "\n".join(md)
    except Exception:                                  # noqa: BLE001
        return raw_json                                # fallback


def ensure_plan_keys(h: Dict) -> Dict:
    """Guarantee all plan-related keys exist for a hypothesis dict."""
    h.setdefault("analysis_plan_chat_history", [])
    h.setdefault("analysis_plan", "")
    h.setdefault("analysis_plan_accepted", False)
    return h


def _init_session_state() -> None:
    """Add any keys this page expects."""
    defaults = {
        "current_hypothesis_idx": 0,
        "all_plans_generated":    False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

# ═══════════════════════════  Main page  ══════════════════════════════════
def main() -> None:
    # ── page config & CSS ────────────────────────────────────────────────
    init_state()                # MUST be first Streamlit call
    add_green_button_css()
    add_modern_font_css()
    add_sidebar_button_styles()
    _init_session_state()

    # ── pick the hypothesis in focus ─────────────────────────────────────
    current = st.session_state["current_hypothesis_idx"]
    hyps    = st.session_state.updated_hypotheses["assistant_response"]
    hypo    = ensure_plan_keys(hyps[current])

    # ══════════════════════  SIDEBAR  ════════════════════════════════════
    with st.sidebar:
        st.header("Accepted hypotheses")
        for idx, h in enumerate(hyps):
            label = (
                f":heavy_check_mark: Hypothesis {idx+1}"
                if h.get("analysis_plan_accepted")
                else f"Hypothesis {idx+1}"
            )
            with st.expander(label, expanded=(idx == current)):
                st.markdown(h["final_hypothesis"], unsafe_allow_html=True)
                if st.button("Work on this plan", key=f"select_h_{idx}"):
                    st.session_state["current_hypothesis_idx"] = idx
                    st.rerun()

    # ── main header ──────────────────────────────────────────────────────
    st.subheader(f"Analysis-Plan Manager – Hypothesis {current+1}")
    st.markdown(hypo["final_hypothesis"], unsafe_allow_html=True)

    # ══════════════════════  SIDEBAR ACTIONS  ════════════════════════════
    with st.sidebar:
        st.header("Actions")

        hist: List[Dict] = hypo["analysis_plan_chat_history"]
        gen_label = "Generate plan" if not hist else "Re-generate plan"
        if st.button(gen_label, key="generate_plan"):
            prompt = (
                f"Data summary: {st.session_state.data_summary}\n\n"
                f"Hypothesis: {hypo['final_hypothesis']}"
            )
            hist.append({"role": "user", "content": prompt})

            with st.spinner("Generating …"):
                resp = client.responses.create(
                    model="gpt-4o",
                    temperature=0,
                    instructions=analyses_step_generation_instructions,
                    input=prompt,
                    text=plan_generation_response_schema,
                    tools=[{"type": "web_search_preview"}],
                    stream=False,
                    store=False,
                )

            hist.append({"role": "assistant", "content": resp.output_text})
            st.rerun()

    # ══════════════════════  CHAT / EDIT LOOP  ════════════════════════════
    if not hypo["analysis_plan_accepted"]:
        # ─ existing chat messages ─
        for m in hist[1:]:
            with st.chat_message(m["role"]):
                if m["role"] == "assistant":
                    st.markdown(
                        pretty_markdown_plan(json.loads(m["content"])["assistant_response"]),
                        unsafe_allow_html=True,
                    )
                else:
                    st.write(m["content"])

        # ─ user reply box ─
        user_msg = st.chat_input("Refine this analysis plan …")
        if user_msg:
            hist.append({"role": "user", "content": user_msg})
            with st.spinner("Thinking …"):
                resp = client.responses.create(
                    model="gpt-4o",
                    temperature=0,
                    instructions=analyses_step_chat_instructions,
                    input=hist,
                    text=plan_generation_response_schema,
                    tools=[{"type": "web_search_preview"}],
                    stream=False,
                    store=False,
                )
            hist.append({"role": "assistant", "content": resp.output_text})
            st.rerun()

        # ─ accept button ─
        if hist:
            with st.sidebar:
                if st.button("Accept this plan", key="accept_plan"):
                    hypo["analysis_plan"]          = hist[-1]["content"]
                    hypo["analysis_plan_accepted"] = True

                    # ▶︎ NEW: check all hypotheses and set the flag
                    all_ready = all(
                        h.get("analysis_plan") and h.get("analysis_plan_accepted")
                        for h in st.session_state.updated_hypotheses["assistant_response"]
                    )
                    if all_ready:
                        st.session_state.all_plans_generated = True

                    st.rerun()

    # ══════════════════════  ACCEPTED PLAN VIEW  ══════════════════════════
    if hypo["analysis_plan_accepted"]:
        raw   = hypo["analysis_plan"]
        md    = pretty_markdown_plan(raw if isinstance(raw, str) else json.dumps(raw))
        st.markdown(md, unsafe_allow_html=True)

        with st.sidebar:
            if st.button("Edit plan"):
                hypo["analysis_plan_accepted"] = False
                st.rerun()

            all_ready = all(
                h.get("analysis_plan") and h.get("analysis_plan_accepted")
                for h in hyps
            )
            if all_ready and st.button("NEXT STAGE", type="primary"):
                st.switch_page("pages/05_Plan_execution.py")

# ───────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    main()
