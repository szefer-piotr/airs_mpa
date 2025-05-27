import streamlit as st
import json
from assistants import client
from pathlib import Path
import re
import base64

from typing import Any, Dict, List, Optional
import ast
from openai import OpenAI

from openai.types.beta.assistant_stream_event import (
    ThreadRunStepCreated,
    ThreadRunStepDelta,
    ThreadRunStepCompleted,
    ThreadMessageCreated,
    ThreadMessageDelta
)

from openai.types.beta.threads.text_delta_block import TextDeltaBlock
# from openai.types.beta.threads.runs.tool_calls_step_details import ToolCallsStepDetails
from openai.types.beta.threads.runs.code_interpreter_tool_call import (
    CodeInterpreterOutputImage,
    CodeInterpreterOutputLogs
    )

from assistants import create as get_assistants
from instructions import (
    step_execution_instructions,
    step_execution_chat_instructions
)

from utils import add_green_button_css

add_green_button_css()

ASSISTANTS = get_assistants()

IMG_DIR = Path("images"); IMG_DIR.mkdir(exist_ok=True)
JSON_RE  = re.compile(r"\{[\s\S]*?\}")
STEP_RE  = re.compile(r"^(?:\d+\.\s+|[-*+]\s+)(.+)")



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


st.title("Analysis Plan Execution")

# ------------------------------------------------------------------
# Sidebar – hypotheses
# ------------------------------------------------------------------
# Which hypothesis are we executing?
current = st.session_state.get("current_exec_idx", 0)


with st.sidebar:
    st.header("Accepted hypotheses")
    for idx, h in enumerate(st.session_state.updated_hypotheses["assistant_response"]):
        title = f"Hypothesis {idx+1}"
        with st.expander(title, expanded=(idx==current)):
            st.markdown(h["final_hypothesis"], unsafe_allow_html=True)
            if st.button("▶️ Run / review", key=f"select_exec_{idx}"):
                st.session_state["current_exec_idx"] = idx
                st.rerun()


hypo_obj = ensure_execution_keys(
    st.session_state.updated_hypotheses["assistant_response"][current])

plan_dict = safe_load_plan(hypo_obj["analysis_plan"])

if not plan_dict:
    st.error("❌ Could not parse analysis plan JSON. Please regenerate the plan in the previous stage or ask the assistant to output valid JSON.")

# print(f"\n\nPLAN DICT\n\n:{plan_dict}")

st.markdown(plan_dict['assistant_response'])
st.markdown(plan_dict['current_plan_execution'])

# Normalise stored plan to dict for future safety
if isinstance(hypo_obj["analysis_plan"], str):
    hypo_obj["analysis_plan"] = plan_dict


print(f"THREAD??: {st.session_state.thread_id}")

# Previous transcript ------------------------------------------------
for msg in hypo_obj["plan_execution_chat_history"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant":
            for item in msg["items"]:
                if item["type"] == "code_input":
                    st.code(item["content"], language="python")
                elif item["type"] == "code_output":
                    st.code(item["content"], language="text")
                elif item["type"] == "image":
                    for html in item["content"]:
                        st.markdown(html, unsafe_allow_html=True)
                elif item["type"] == "text":
                    st.markdown(item["content"], unsafe_allow_html=True)
        else:
            st.markdown(msg["content"], unsafe_allow_html=True)

# Prompt & run button ------------------------------------------------
user_prompt = st.chat_input(
    "Discuss the plan or ask to run specific steps …",
    key="exec_chat_input",
)

run_label = (
    f"▶ Run analysis {current + 1}" if not hypo_obj["plan_execution_chat_history"] else f"Run analysis again {current}"
)
with st.sidebar:
    st.header("Actions")
    run_label = "Run analysis" if not hypo_obj.get("plan_executed", None) else "Run analysis again"
    run_analysis = st.button(run_label, key=f"run_analysis_btn{current}")



if run_analysis or user_prompt:
    
    hypo_obj["plan_executed"] = True

    # Choose assistant instructions
    client.beta.threads.messages.create(
        thread_id=st.session_state.thread_id,
        role="user",
        content=f"\n\nThe analysis plan:\n{json.dumps(plan_dict, indent=2)}",
    )

    # Live placeholders
    container      = st.container()
    code_hdr_pl    = container.empty()
    code_pl        = container.empty()
    result_hdr_pl  = container.empty()
    result_pl      = container.empty()
    text_pl        = container.empty()

    assistant_items: List[Dict[str, Any]] = []

    def ensure_slot(tp: str):
        if not assistant_items or assistant_items[-1]["type"] != tp:
            assistant_items.append({"type": tp, "content": "" if tp != "image" else []})

    if run_analysis:
        # Runs the initial analysis with specific instructions.
        stream = client.beta.threads.runs.create(
            thread_id    = st.session_state.thread_id,
            assistant_id = ASSISTANTS["analysis"].id,
            instructions = step_execution_instructions,
            tool_choice  = {"type": "code_interpreter"},
            stream       = True,
        )

    elif user_prompt:
        # Responds to user, focuses on refining parts of the plan.
        hypo_obj["plan_execution_chat_history"].append(
            {"role": "user", "content": user_prompt}
        )

        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=user_prompt,
        )

        stream = client.beta.threads.runs.create(
            thread_id    = st.session_state.thread_id,
            assistant_id = ASSISTANTS["analysis_chat"].id,
            instructions = step_execution_chat_instructions,
            tool_choice  = {"type": "code_interpreter"},
            stream       = True,
        )


    for event in stream:
        if isinstance(event, ThreadRunStepCreated):
            if getattr(event.data.step_details, "tool_calls", None):
                ensure_slot("code_input")
                code_hdr_pl.markdown("**Writing code ⏳ …**")

        elif isinstance(event, ThreadRunStepDelta):
            tc = getattr(event.data.delta.step_details, "tool_calls", None)
            if tc and tc[0].code_interpreter:
                delta = tc[0].code_interpreter.input or ""
                if delta:
                    ensure_slot("code_input")
                    assistant_items[-1]["content"] += delta
                    code_pl.code(assistant_items[-1]["content"], language="python")

        elif isinstance(event, ThreadRunStepCompleted):
            tc = getattr(event.data.step_details, "tool_calls", None)
            if not tc:
                continue
            outputs = tc[0].code_interpreter.outputs or []
            if not outputs:
                continue
            result_hdr_pl.markdown("#### Results")
            for out in outputs:
                if isinstance(out, CodeInterpreterOutputLogs):
                    ensure_slot("code_output")
                    assistant_items[-1]["content"] += out.logs
                    result_pl.code(out.logs)
                
                elif isinstance(out, CodeInterpreterOutputImage):
                    fid  = out.image.file_id
                    data = client.files.content(fid).read()
                    img_path = IMG_DIR / f"{fid}.png"
                    img_path.write_bytes(data)

                    print(f"Image: {out.image.file_id} at {IMG_DIR / f'{fid}.png'} added to the thread {st.session_state.thread_id}.")

                    b64 = base64.b64encode(data).decode()
                    html = (
                        f'<p align="center"><img src="data:image/png;base64,{b64}" '
                        f'width="600"></p>'
                    )

                    # After saving the image data, add it to the thread
                    st.session_state.images.append(
                        {"image_path": img_path, 
                            "file_id": fid, 
                            "html": html}
                        )

                    ensure_slot("image")
                    assistant_items[-1]["content"].append(html)                        
                    assistant_items[-1]["file_id"] = fid
                    assistant_items[-1]["image_path"] = str(img_path)

                    print(f"\n\nASSISTANT ITEM [-1]:\n\n{assistant_items}")

                    result_pl.markdown(html, unsafe_allow_html=True)

        elif isinstance(event, ThreadMessageCreated):
            ensure_slot("text")

        elif isinstance(event, ThreadMessageDelta):
            blk = event.data.delta.content[0]
            if isinstance(blk, TextDeltaBlock):
                ensure_slot("text")
                assistant_items[-1]["content"] += blk.text.value
                text_pl.markdown(assistant_items[-1]["content"], unsafe_allow_html=True)

    # After the run ends add the images to the thread
    for img in st.session_state["images"]:
        file = client.files.create(
                        file=open(img["image_path"], "rb"),
                        purpose="vision"
                    )

        client.beta.threads.messages.create(
            thread_id=st.session_state.thread_id,
            role="user",
            content=[{"type": "image_file","image_file": {"file_id": file.id}}]
        )

    hypo_obj["plan_execution_chat_history"].append(
        {"role": "assistant", "items": assistant_items}
    )

    hypo_obj["analysis_executed"] = True

    st.rerun()

with st.sidebar:
    generate_report_button = st.button("Generate final report")
    if generate_report_button:
        st.switch_page("pages/06_Report_builder.py")

# if all(
#     h.get("analysis_plan") and h.get("analysis_plan_accepted")
#     for h in st.session_state.updated_hypotheses["assistant_response"]
# )