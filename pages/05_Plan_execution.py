# analysis_execution.py
'''Streamlit page 04 – Execute analysis plans generated for each hypothesis'''

from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple

import streamlit as st
from openai.types.beta.assistant_stream_event import (
    ThreadRunStepCreated,
    ThreadRunStepDelta,
    ThreadRunStepCompleted,
    ThreadMessageCreated,
    ThreadMessageDelta,
)
from openai.types.beta.threads.text_delta_block import TextDeltaBlock
from openai.types.beta.threads.runs.code_interpreter_tool_call import (
    CodeInterpreterOutputImage,
    CodeInterpreterOutputLogs,
)

from assistants import client, create as get_assistants
from instructions import (
    step_execution_instructions,
    step_execution_chat_instructions,
)
from utils import (
    add_green_button_css,
    ensure_execution_keys,
    safe_load_plan,
    IMG_DIR,
)

# ──────────────────────────  Globals  ──────────────────────────
ASSISTANTS = get_assistants()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SOULLESS_CSS = '''
<style>
    html, body, [class*="css"]  { font-family: Arial, sans-serif; }
</style>
'''

# ───────────────────────  Session helpers  ─────────────────────
def _init_session_state() -> None:
    defaults: Dict[str, Any] = {
        'current_exec_idx': 0,
        'all_plans_executed': False,
        'analysis_running': False,
        'images': [],
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

    # Guarantee we have a thread & an images list
    st.session_state.setdefault('thread_id',
                                client.beta.threads.create().id)
    st.session_state.setdefault('images', [])

# ─────────────────────────  UI helpers  ────────────────────────
def add_global_style() -> None:
    st.markdown(SOULLESS_CSS, unsafe_allow_html=True)
    add_green_button_css()

def sidebar_hypotheses(hyps: List[Dict[str, Any]]) -> None:
    '''List accepted hypotheses and allow switching which plan to run.'''
    cur = st.session_state.current_exec_idx
    st.header('Accepted hypotheses')
    for idx, h in enumerate(hyps):
        label = (f':heavy_check_mark: Hypothesis {idx+1}'
                 if h.get('analysis_executed') else f'Hypothesis {idx+1}')
        with st.expander(label, expanded=(idx == cur)):
            st.markdown(h['final_hypothesis'], unsafe_allow_html=True)
            if st.button('Work on this analysis', key=f'select_exec_{idx}'):
                st.session_state.current_exec_idx = idx
                st.rerun()

def show_transcript(chat: List[Dict[str, Any]]) -> None:
    '''Render previous code / images / markdown from plan_execution_chat_history.'''
    for msg in chat:
        with st.chat_message(msg['role']):
            if msg['role'] == 'assistant':
                for item in msg['items']:
                    if item['type'] == 'code_input':
                        st.code(item['content'], language='python')
                    elif item['type'] == 'code_output':
                        st.code(item['content'], language='text')
                    elif item['type'] == 'image':
                        for html in item['content']:
                            st.markdown(html, unsafe_allow_html=True)
                    elif item['type'] == 'text':
                        st.markdown(item['content'], unsafe_allow_html=True)
            else:
                st.markdown(msg['content'], unsafe_allow_html=True)

def stream_assistant(
    hypo_obj: Dict[str, Any],
    plan_dict: Dict[str, Any],
    user_prompt: str | None,
) -> None:
    '''
    Run the analysis or a chat refinement and stream results to the UI,
    updating `hypo_obj['plan_execution_chat_history']`.
    '''
    thread_id = st.session_state.thread_id

    # Inform the thread of the plan (or user prompt)
    if user_prompt:
        hypo_obj['plan_execution_chat_history'].append(
            {'role': 'user', 'content': user_prompt},
        )
        client.beta.threads.messages.create(
            thread_id=thread_id, role='user', content=user_prompt,
        )
        assistant_id = ASSISTANTS['analysis_chat'].id
        instructions = step_execution_chat_instructions
    else:
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role='user',
            content=f'\n\nThe analysis plan:\n{json.dumps(plan_dict, indent=2)}',
        )
        assistant_id = ASSISTANTS['analysis'].id
        instructions = step_execution_instructions

    st.session_state.analysis_running = True
    banner = st.empty()
    
    banner.info('Running analysis ⏳ …')

    # Live placeholders
    container      = st.container()
    code_hdr_pl    = container.empty()
    code_pl        = container.empty()
    result_hdr_pl  = container.empty()
    result_pl      = container.empty()
    text_pl        = container.empty()

    assistant_items: List[Dict[str, Any]] = []

    def ensure_slot(tp: str) -> None:
        if not assistant_items or assistant_items[-1]['type'] != tp:
            assistant_items.append({'type': tp,
                                    'content': '' if tp != 'image' else []})

    # ----- start streaming --------------------------------------------------
    stream = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id,
        instructions=instructions,
        tool_choice={'type': 'code_interpreter'},
        stream=True,
    )

    for event in stream:
        if isinstance(event, ThreadRunStepCreated):
            if getattr(event.data.step_details, 'tool_calls', None):
                ensure_slot('code_input')
                code_hdr_pl.markdown('**Writing code ⏳ …**')

        elif isinstance(event, ThreadRunStepDelta):
            tc = getattr(event.data.delta.step_details, 'tool_calls', None)
            if tc and tc[0].code_interpreter:
                delta = tc[0].code_interpreter.input or ''
                if delta:
                    ensure_slot('code_input')
                    assistant_items[-1]['content'] += delta
                    code_pl.code(assistant_items[-1]['content'],
                                 language='python')

        elif isinstance(event, ThreadRunStepCompleted):
            tc = getattr(event.data.step_details, 'tool_calls', None)
            if not tc:
                continue
            outputs = tc[0].code_interpreter.outputs or []
            if outputs:
                result_hdr_pl.markdown('#### Results')
            for out in outputs:
                if isinstance(out, CodeInterpreterOutputLogs):
                    ensure_slot('code_output')
                    assistant_items[-1]['content'] += out.logs
                    result_pl.code(out.logs)

                elif isinstance(out, CodeInterpreterOutputImage):
                    fid  = out.image.file_id
                    data = client.files.content(fid).read()
                    img_path = IMG_DIR / f'{fid}.png'
                    img_path.write_bytes(data)

                    html = (
                        '<p align="center">'
                        f'<img src="data:image/png;base64,'
                        f'{base64.b64encode(data).decode()}" width="600"></p>'
                    )
                    st.session_state.images.append(
                        {'image_path': img_path, 'file_id': fid, 'html': html},
                    )
                    ensure_slot('image')
                    assistant_items[-1]['content'].append(html)
                    assistant_items[-1]['file_id']   = fid
                    assistant_items[-1]['image_path'] = str(img_path)
                    result_pl.markdown(html, unsafe_allow_html=True)

        elif isinstance(event, ThreadMessageCreated):
            ensure_slot('text')

        elif isinstance(event, ThreadMessageDelta):
            blk = event.data.delta.content[0]
            if isinstance(blk, TextDeltaBlock):
                ensure_slot('text')
                assistant_items[-1]['content'] += blk.text.value
                text_pl.markdown(assistant_items[-1]['content'],
                                 unsafe_allow_html=True)

    # Upload all collected images back to the thread
    for img in st.session_state.images:
        file = client.files.create(
            file=open(img['image_path'], 'rb'),
            purpose='vision',
        )
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role='user',
            content=[{'type': 'image_file',
                      'image_file': {'file_id': file.id}}],
        )

    hypo_obj['plan_execution_chat_history'].append(
        {'role': 'assistant', 'items': assistant_items},
    )
    hypo_obj['analysis_executed'] = True
    st.session_state.analysis_running = False
    banner.success('Analysis finished ✅')
    st.rerun()

# ─────────────────────────  Main page  ─────────────────────────
def main() -> None:                              # noqa: C901 – big but clear
    _init_session_state()
    add_global_style()

    hyps = st.session_state.updated_hypotheses['assistant_response']
    cur  = st.session_state.current_exec_idx
    hypo_obj = ensure_execution_keys(hyps[cur])
    plan_dict = safe_load_plan(hypo_obj['analysis_plan'])

    st.title('Analysis plan execution')

    # ---------- banners --------------------------------------------------
    if st.session_state.analysis_running:
        st.info('Analysis is running …')


    if hypo_obj.get('accept_analysis_execution'):
        st.info('This analysis execution has been accepted. You may still re-run or discuss it.')

    # ---------- sidebar (hypothesis list + actions) ----------------------
    with st.sidebar:
        sidebar_hypotheses(hyps)

    if not plan_dict:
        st.error('❌ Could not parse analysis-plan JSON. Regenerate it in the previous stage.')
        st.stop()

    # ---------- show plan summary ---------------------------------------
    st.markdown(plan_dict['assistant_response'])
    st.markdown(plan_dict['current_plan_execution'])

    # Transcript of previous exchanges
    show_transcript(hypo_obj['plan_execution_chat_history'])

    # ---------- user interaction ----------------------------------------
    prompt = st.chat_input('Discuss the plan or ask to run specific steps …',
                           key='exec_chat_input')

    with st.sidebar:
        st.header('Actions')
        run_clicked = st.button(
            'Run analysis' if not hypo_obj.get('analysis_executed')
            else 'Run analysis again',
            key=f'run_analysis_btn_{cur}',
            disabled=st.session_state.analysis_running,
        )
        if hypo_obj.get('analysis_executed'):
            done_clicked = st.button('Done', key=f'done_btn_{cur}')
            if done_clicked:
                hypo_obj['accept_analysis_execution'] = True
                st.rerun()

    # ---------- handle run / chat ---------------------------------------
    if run_clicked or prompt:
        hypo_obj['plan_executed'] = True
        stream_assistant(hypo_obj, plan_dict, prompt)
    
        if all(h.get('analysis_executed') for h in hyps):
            st.session_state.all_plans_executed = True
            st.success('All plans have been executed. You can proceed to report generation.')
            st.rerun()

    # ---------- next stage button ---------------------------------------
    with st.sidebar:
        if st.session_state.get('all_plans_executed'):
            if st.button('NEXT → Report builder'):
                st.switch_page('pages/06_Report_builder.py')

if __name__ == '__main__':
    main()
