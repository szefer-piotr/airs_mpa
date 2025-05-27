import streamlit as st
import json

from openai import OpenAI
from assistants import client

from instructions import (
    analyses_step_generation_instructions,
    analyses_step_chat_instructions
)

from utils import add_green_button_css

add_green_button_css()

from schemas import plan_generation_response_schema

# STAGE 3 ANALYSIS PLAN MANAGER

def pretty_markdown_plan(raw_json: str) -> str:
    """Convert the assistant‑returned JSON (analyses → steps) into Markdown."""
    try:
        data = json.loads(raw_json)
        md_blocks = []
        for ana in data.get("analyses", []):
            md_blocks.append(f"### {ana['title']}\n")
            for idx, step in enumerate(ana["steps"], 1):
                md_blocks.append(f"{idx}. {step['step']}")
            md_blocks.append("\n")
        return "\n".join(md_blocks)
    except Exception:
        # fall back to raw text if parsing fails
        return raw_json



def ensure_plan_keys(h):
    h.setdefault("analysis_plan_chat_history", [])
    h.setdefault("analysis_plan", "")
    h.setdefault("analysis_plan_accepted", False)
    return h


# ── PAGE SETUP ---------------------------------------------------------------

# Which hypothesis is in focus?
current = st.session_state.get("current_hypothesis_idx", 0)

hypo_obj = ensure_plan_keys(
    st.session_state.updated_hypotheses["assistant_response"][current]
)

with st.sidebar:
    st.header("Accepted hypotheses")
    for idx, h in enumerate(st.session_state.updated_hypotheses["assistant_response"]):
        label = f":heavy_check_mark: Hypothesis {idx+1}" if h["analysis_plan_accepted"] else f"Hypothesis {idx+1}" 
        title = label
        with st.expander(title, expanded=(current == idx)):
            st.markdown(h["final_hypothesis"], unsafe_allow_html=True)
            if st.button("✏️ Work on this", key=f"select_hypo_{idx}"):
                st.session_state["current_hypothesis_idx"] = idx
                st.rerun()


all_ready = all(
    h.get("analysis_plan") and h.get("analysis_plan_accepted")
    for h in st.session_state.updated_hypotheses["assistant_response"]
)

if all_ready:
    st.info("Yu can now proceed to the PLAN EXECUTION stage.")


st.subheader(f"Analysis Plan Manager: Hypothesis {current+1}")
st.markdown(hypo_obj["final_hypothesis"], unsafe_allow_html=True)

# Plan generation / chat
chat_hist = hypo_obj["analysis_plan_chat_history"]

with st.sidebar:
    st.header("Actions")
    # button_label = "Generate plan" if not hypo_obj["analysis_plan_accepted"] else "Generate new plan"
    button_label = "Generate plan" if not chat_hist else "Re-generate plan"
    if st.button(button_label, key="generate_plan"):
        prompt = (
            f"Here is the data summary: {st.session_state.data_summary}\n\n"
            f"Here is the hypothesis: {hypo_obj['final_hypothesis']}"
        )

        prompt_str = "".join(prompt)

        chat_hist.append({"role": "user", "content": prompt_str})

        with st.spinner("Generating …"):
            resp = client.responses.create(
                model="gpt-4o",
                temperature=0,
                instructions=analyses_step_generation_instructions,
                input=prompt_str,
                stream=False,
                tools=[{"type": "web_search_preview"}],
                text=plan_generation_response_schema,
                store=False,
            )

        # print(f"\n\nResponse from the plan generation response:\n\n{resp}")

        chat_hist.append({"role": "assistant", "content": resp.output_text})

        st.rerun()

if not hypo_obj["analysis_plan_accepted"]:
    
    # Show existing chat
    for m in chat_hist[1:]:
        with st.chat_message(m["role"]):
            if m["role"] == "assistant":
                st.markdown(
                    json.loads(m["content"])["assistant_response"], 
                    unsafe_allow_html=True
                )
            elif m["role"] == "user":
                st.write(m["content"])

    user_msg = st.chat_input("Refine this analysis plan …")

    if user_msg:
        chat_hist.append({"role": "user", "content": user_msg})
        
        with st.spinner("Thinking …"):
            resp = client.responses.create(
                model="gpt-4o",
                temperature=0,
                instructions=analyses_step_chat_instructions,
                input=chat_hist,
                stream=False,
                tools=[{"type": "web_search_preview"}],
                text=plan_generation_response_schema,
                store=False,
            )
        chat_hist.append({"role": "assistant", "content": resp.output_text})
        st.rerun()

    if chat_hist:
        with st.sidebar:
            if st.button("Accept this plan", key="accept_plan"):
                hypo_obj["analysis_plan"] = chat_hist[-1]["content"]
                hypo_obj["analysis_plan_accepted"] = True
                st.rerun()

if hypo_obj["analysis_plan_accepted"]:

    raw_plan = hypo_obj["analysis_plan"]
    plan_json = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
    st.markdown(plan_json["assistant_response"], unsafe_allow_html=True)

    with st.sidebar:
        if st.button("Edit plan", key="edit_plan"):
            hypo_obj["analysis_plan_accepted"] = False
            st.rerun()

    # col_back, col_next = st.columns(2)
    # with col_next:
    #     if st.button("Next", key="next"):
    #         st.switch_page("pages/05_Plan_execution.py")
    # with col_back:
    #     if st.button("Back", key="back"):
    #         st.switch_page("pages/03_Hypotheses_manager.py")