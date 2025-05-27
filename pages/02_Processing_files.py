import streamlit as st
import json
import base64

from info import STAGE_INFO
from utils import (
    add_green_button_css, 
    format_initial_assistant_msg, 
    render_hypothesis_md
)
from assistants import create as get_assistants
from assistants import client

from instructions import processing_files_instruction, refinig_instructions

from schemas import response_format, hypotheses_schema

from openai.types.beta.threads.text_delta_block import TextDeltaBlock
from openai.types.beta.threads.runs.tool_calls_step_details import ToolCallsStepDetails
from openai.types.beta.threads.runs.code_interpreter_tool_call import (
    CodeInterpreterOutputImage,
    CodeInterpreterOutputLogs
    )

from openai.types.beta.assistant_stream_event import (
    ThreadRunStepCreated,
    ThreadRunStepDelta,
    ThreadRunStepCompleted,
    ThreadMessageCreated,
    ThreadMessageDelta,
)

ASSISTANTS = get_assistants()

print(st.session_state.app_state)

add_green_button_css()


processing_label = (
    "Start File Processing" if not st.session_state.processing_done else "🔄 Run processing again"
)

with st.sidebar:
    st.header("Processing options")
    st.markdown("You can re-run this stage if you upload new files or change the hypotheses.")
    processing_button = st.button(processing_label, key="process_files")

if st.session_state.processing_done:
    st.info("You can now proceed to the hypotheses refinement stage.")

if st.session_state.data_uploaded and st.session_state.hypotheses_uploaded:
    if not st.session_state.processing_done:
        st.markdown(STAGE_INFO["processing"])
    
else:
    st.info("Upload files to process them.")
    st.stop()

if st.session_state.processing_done:
    st.markdown("#### Data summary")
    # with st.expander("📊 Data summary", expanded=False):
    st.markdown(st.session_state.data_summary)
    st.markdown("----")
    st.markdown("#### Refined hypotheses")
    for hyp in st.session_state.updated_hypotheses["assistant_response"]:
        st.markdown(f"##### {hyp['title']}")
        st.markdown(f"{hyp['hypothesis_refined_with_data_text']}")
                             
        # st.markdown(r_hypothesis_md(hyp))


if processing_button:

    if not st.session_state.processing_done:
        thread = client.beta.threads.create()
        st.session_state.thread_id = thread.id

        for name, f in st.session_state.files.items():
            print(f"Uploading {name} …")
            file_obj = client.files.create(file=f, purpose="assistants")
            st.session_state.file_ids.append(file_obj.id)

    print(f"File IDs: {st.session_state.file_ids}")

    thread_id = st.session_state.thread_id

    print(f"Thread ID: {thread_id}")

    client.beta.threads.update(
        thread_id=thread_id,
        tool_resources={"code_interpreter": {"file_ids": st.session_state.file_ids}},
    )

    print(f"Files added to thread {thread_id}")

    container      = st.container()
    code_hdr_pl    = container.empty()
    code_pl        = container.empty()
    result_hdr_pl  = container.empty()
    result_pl      = container.empty()
    json_hdr_pl    = container.empty()
    json_pl        = container.empty()
    text_pl        = container.empty()

    assistant_items: list[dict] = []

    def ensure_slot(tp: str):
        if not assistant_items or assistant_items[-1]["type"] != tp:
            assistant_items.append({"type": tp, "content": ""})

    stream = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=ASSISTANTS["data_summary"].id,
        response_format=response_format,
        stream=True
    )

    for event in stream:
        # ---- code‑interpreter life‑cycle -----------------------------------
        if isinstance(event, ThreadRunStepCreated):
            if getattr(event.data.step_details, "tool_calls", None):
                ensure_slot("code_input")
                code_hdr_pl.markdown("**Running code ⏳ …**")

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
            if outputs:
                result_hdr_pl.markdown("#### Code‑interpreter output")
            for out in outputs:
                if isinstance(out, CodeInterpreterOutputLogs):
                    ensure_slot("code_output")
                    assistant_items[-1]["content"] += out.logs
                    result_pl.code(out.logs)
                elif isinstance(out, CodeInterpreterOutputImage):
                    fid  = out.image.file_id
                    data = client.files.content(fid).read()
                    b64  = base64.b64encode(data).decode()
                    html = f'<p align="center"><img src="data:image/png;base64,{b64}" width="600"></p>'
                    ensure_slot("image")
                    assistant_items[-1]["content"] += html
                    result_pl.markdown(html, unsafe_allow_html=True)

        # ---- assistant's JSON answer (delta‑streamed) ----------------------
        elif isinstance(event, ThreadMessageCreated):
            ensure_slot("json")               # we know the next message is JSON
            json_hdr_pl.markdown("#### Column summary (streaming)")

        elif isinstance(event, ThreadMessageDelta):
            blk = event.data.delta.content[0]
            if isinstance(blk, TextDeltaBlock):
                ensure_slot("json")
                assistant_items[-1]["content"] += blk.text.value
                # prettify incremental JSON (optional)
                json_pl.markdown(f"```json\n{assistant_items[-1]['content']}\n```")

    print(f"Assistant items: {assistant_items}")


    try:
        messages = client.beta.threads.messages.list(
            thread_id=thread_id, order="desc"
        ).data[0]

        print(f"Here sould be JSON conforming to the schema:\n\n{messages}")
        summary_dict = json.loads(messages.content[0].text.value)

    except Exception as e:
        st.error(f"❌ Could not parse JSON: {e}")

    st.session_state.data_summary = summary_dict

    st.session_state.processing_done = True

    # Refining prompt stage
    refine_prompt = (
        f"Data summary: {st.session_state.data_summary}\n\n"
        f"Hypotheses: {st.session_state.hypotheses}\n\n"
        f"{processing_files_instruction}\n")
    
    response = client.responses.create(
        model="gpt-4o",
        instructions=refinig_instructions,
        input=[{"role": "user", "content": refine_prompt}],
        tools=[{"type": "web_search_preview"}],
        text=hypotheses_schema,
    )

    print(f"Response output text: {response.output_text}")

    st.session_state.updated_hypotheses = json.loads(response.output_text)

    for hyp in st.session_state.updated_hypotheses["assistant_response"]:
        pretty_msg = format_initial_assistant_msg(hyp)
        hyp["chat_history"] = [{"role": "assistant", "content": pretty_msg}]
        hyp["final_hypothesis"] = []

    st.session_state.processing_done = True
    st.success("Processing complete!", icon="✅")

    st.rerun()

    # col_back, col_next = st.columns(2)
    # with col_next:
    #     if st.button("Next", key="next"):
    #         st.switch_page("pages/03_Hypotheses_manager.py")
    # with col_back:
    #     if st.button("Back", key="back"):
    #         st.switch_page("pages/01_Upload.py")

        