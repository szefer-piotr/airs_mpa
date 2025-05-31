'''Streamlit page 02 – File processing & hypothesis refinement'''

from __future__ import annotations

import base64
import json
import logging
from typing import Any, Dict

import streamlit as st

from info import STAGE_INFO
from utils import (
    add_green_button_css,
    format_initial_assistant_msg,
    show_data_summary,
)
from assistants import create as get_assistants
from assistants import client
from instructions import processing_files_instruction, refinig_instructions
from schemas import response_format, hypotheses_schema
from openai.types.beta.threads.text_delta_block import TextDeltaBlock
from openai.types.beta.threads.runs.code_interpreter_tool_call import (
    CodeInterpreterOutputImage,
    CodeInterpreterOutputLogs,
)
from openai.types.beta.assistant_stream_event import (
    ThreadRunStepCreated,
    ThreadRunStepDelta,
    ThreadRunStepCompleted,
    ThreadMessageCreated,
    ThreadMessageDelta,
)

# ──────────────────────────  Globals  ──────────────────────────
ASSISTANTS = get_assistants()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# ───────────────────────  Styling helpers  ─────────────────────
def add_global_style() -> None:
    '''Inject CSS so the whole app uses a proudly soulless font.'''
    st.markdown(
        '''
        <style>
            html, body, [class*="css"]  {
                font-family: Arial, sans-serif;
            }
        </style>
        ''',
        unsafe_allow_html=True,
    )

# ──────────────────────  Session bootstrap  ────────────────────
def _init_session_state() -> None:
    defaults = {
        'processing_done':     False,
        'data_uploaded':       False,
        'hypotheses_uploaded': False,
        'file_ids':            [],
        'thread_id':           None,
        'data_summary':        {},
        'hypotheses':          [],
        'updated_hypotheses':  {},
        'edit_mode':           False,
        'need_refinement':     False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

# ───────────────────────  OpenAI helpers  ──────────────────────
def refine_hypotheses() -> None:
    '''Use GPT-4o to refine hypotheses against the current data-summary.'''
    prompt = (
        f'Data summary: {st.session_state.data_summary}\n\n'
        f'Hypotheses: {st.session_state.hypotheses}\n\n'
        f'{processing_files_instruction}\n'
    )

    rsp = client.responses.create(
        model='gpt-4o',
        instructions=refinig_instructions,
        input=[{'role': 'user', 'content': prompt}],
        tools=[{'type': 'web_search_preview'}],
        text=hypotheses_schema,
    )

    st.session_state.updated_hypotheses = json.loads(rsp.output_text)
    for hyp in st.session_state.updated_hypotheses['assistant_response']:
        hyp['chat_history']   = [{'role': 'assistant',
                                  'content': format_initial_assistant_msg(hyp)}]
        hyp['final_hypothesis'] = []

    st.success('Hypotheses refined!', icon='✅')

def generate_data_summary() -> None:
    '''Run the assistant to create a data summary for uploaded files.'''
    if not st.session_state.thread_id:
        st.session_state.thread_id = client.beta.threads.create().id

    if not st.session_state.file_ids:            # upload any new files
        for name, file_obj in st.session_state.files.items():
            logger.info('Uploading %s …', name)
            fid = client.files.create(file=file_obj,
                                      purpose='assistants').id
            st.session_state.file_ids.append(fid)

    client.beta.threads.update(
        thread_id=st.session_state.thread_id,
        tool_resources={'code_interpreter':
                        {'file_ids': st.session_state.file_ids}},
    )

    # ---------------- stream assistant output -----------------
    container       = st.container()
    code_hdr_pl     = container.empty()
    code_pl         = container.empty()
    result_hdr_pl   = container.empty()
    result_pl       = container.empty()
    json_hdr_pl     = container.empty()
    json_pl         = container.empty()
    assistant_items: list[Dict[str, str]] = []

    def ensure_slot(tp: str) -> None:
        if not assistant_items or assistant_items[-1]['type'] != tp:
            assistant_items.append({'type': tp, 'content': ''})

    stream = client.beta.threads.runs.create(
        thread_id=st.session_state.thread_id,
        assistant_id=ASSISTANTS['data_summary'].id,
        response_format=response_format,
        stream=True,
    )

    for event in stream:
        # --- code-interpreter lifecycle ----------------------------------
        if isinstance(event, ThreadRunStepCreated):
            if getattr(event.data.step_details, 'tool_calls', None):
                ensure_slot('code_input')
                code_hdr_pl.markdown('**Running code ⏳ …**')

        elif isinstance(event, ThreadRunStepDelta):
            tc = getattr(event.data.delta.step_details, 'tool_calls', None)
            if tc and tc[0].code_interpreter and tc[0].code_interpreter.input:
                ensure_slot('code_input')
                assistant_items[-1]['content'] += tc[0].code_interpreter.input
                code_pl.code(assistant_items[-1]['content'], language='python')

        elif isinstance(event, ThreadRunStepCompleted):
            tc = getattr(event.data.step_details, 'tool_calls', None)
            if not tc:
                continue
            outputs = tc[0].code_interpreter.outputs or []
            if outputs:
                result_hdr_pl.markdown('#### Code-interpreter output')
            for out in outputs:
                if isinstance(out, CodeInterpreterOutputLogs):
                    ensure_slot('code_output')
                    assistant_items[-1]['content'] += out.logs
                    result_pl.code(out.logs)
                elif isinstance(out, CodeInterpreterOutputImage):
                    fid  = out.image.file_id
                    data = client.files.content(fid).read()
                    html = (
                        '<p align="center">'
                        f'<img src="data:image/png;base64,'
                        f'{base64.b64encode(data).decode()}" width="600"></p>'
                    )
                    ensure_slot('image')
                    assistant_items[-1]['content'] += html
                    result_pl.markdown(html, unsafe_allow_html=True)

        # --- assistant JSON (delta-streamed) -----------------------------
        elif isinstance(event, ThreadMessageCreated):
            ensure_slot('json')
            json_hdr_pl.markdown('#### Column summary (streaming)')

        elif isinstance(event, ThreadMessageDelta):
            blk = event.data.delta.content[0]
            if isinstance(blk, TextDeltaBlock):
                ensure_slot('json')
                assistant_items[-1]['content'] += blk.text.value
                json_pl.markdown(f'```json\n{assistant_items[-1]["content"]}\n```',
                                 unsafe_allow_html=True)

    # ------------- parse final JSON from last assistant message ----------
    try:
        msg = client.beta.threads.messages.list(
            thread_id=st.session_state.thread_id,
            order='desc',
        ).data[0]

        st.session_state.data_summary = json.loads(msg.content[0].text.value)
        st.session_state.need_refinement = True
        st.session_state.processing_done = True
        st.success('Data summary ready!', icon='✅')

    except Exception as exc:                     # noqa: BLE001
        st.error(f'❌ Could not parse JSON: {exc}')
        raise

# ─────────────────────  Metadata editor  ──────────────────────
def edit_data_summary() -> None:
    st.subheader('Edit column metadata')

    defaults = {'int', 'float', 'str', 'bool', 'datetime',
                'list', 'dict', 'NoneType', 'category'}

    existing = {meta.get('type', 'str')
                for meta in st.session_state.data_summary['columns'].values()}

    py_types = tuple(sorted(defaults | existing))

    with st.form('edit_metadata', clear_on_submit=False):
        for col, meta in st.session_state.data_summary['columns'].items():
            desc_col, type_col = st.columns([3, 1])

            with desc_col:
                st.text_area(f'{col} description',
                             value=meta['description'],
                             key=f'desc_{col}',
                             height=80)

            with type_col:
                cur = meta.get('type', 'str')
                st.selectbox(f'{col} type',
                             options=py_types,
                             index=py_types.index(cur)
                             if cur in py_types else py_types.index('str'),
                             key=f'type_{col}')

        save, cancel = st.columns(2)
        save_clicked   = save.form_submit_button('💾 Save',   type='primary')
        cancel_clicked = cancel.form_submit_button('❌ Cancel')

    if save_clicked:
        for col in st.session_state.data_summary['columns']:
            st.session_state.data_summary['columns'][col]['description'] \
                = st.session_state[f'desc_{col}']
            st.session_state.data_summary['columns'][col]['type'] \
                = st.session_state[f'type_{col}']

        st.session_state.edit_mode = False
        st.session_state.need_refinement = True
        st.success('Column metadata updated!')
        st.rerun()

    elif cancel_clicked:
        for col in st.session_state.data_summary['columns']:
            st.session_state.pop(f'desc_{col}',  None)
            st.session_state.pop(f'type_{col}',  None)
        st.session_state.edit_mode = False
        st.info('No changes saved.')
        st.rerun()

# ─────────────────────────  Main page  ─────────────────────────
def main() -> None:                              # noqa: C901 – big but clear
    _init_session_state()
    add_green_button_css()
    add_global_style()

    if not (st.session_state.data_uploaded and st.session_state.hypotheses_uploaded):
        st.warning('Upload files first to process them.')
        st.stop()

    if not st.session_state.processing_done:
        st.markdown(STAGE_INFO['processing'])
    else:
        st.info('You can now proceed to the hypotheses refinement stage.')

    # ──────────── sidebar ────────────
    with st.sidebar:
        st.header('Actions')

        # 1️⃣ Button to edit data summary
        can_edit      = bool(st.session_state.data_summary)
        edit_clicked  = st.button(
            '✏️ Manually edit data summary',
            key='update_data_summary',
            disabled=not can_edit,
        )
        if edit_clicked:
            st.session_state.edit_mode = True
            st.rerun()

        # 2️⃣ Button to (re)run processing
        processing_label = (
            'Start File Processing'
            if not st.session_state.processing_done
            else 'Run processing again'
        )
        processing_click = st.button(processing_label, key='process_files')

        # 3️⃣ Move on to next stage
        if st.session_state.processing_done:
            if st.button('NEXT STAGE', key='next_stage'):
                st.switch_page('pages/03_Hypotheses_manager.py')

    # ------------------ edit mode -----------------------------
    if st.session_state.edit_mode:
        edit_data_summary()

    # ------------------ processing/reprocessing --------------
    if processing_click:
        st.session_state.processing_done = False
        generate_data_summary()
        st.rerun()

    # ------------------ refinement if flagged ----------------
    if st.session_state.need_refinement and st.session_state.data_summary:
        refine_hypotheses()
        st.session_state.need_refinement = False

    # ------------------ show results -------------------------
    if st.session_state.processing_done:
        st.markdown('#### Data summary')
        show_data_summary(st.session_state.data_summary)

        st.divider()
        st.markdown('#### Refined hypotheses')
        for hyp in st.session_state.updated_hypotheses.get('assistant_response', []):
            st.markdown(f'##### {hyp["title"]}')
            st.markdown(hyp['hypothesis_refined_with_data_text'])

if __name__ == '__main__':
    main()