# hypotheses_refinement.py
'''Streamlit page 03 – Chat-based refinement of hypotheses'''

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import streamlit as st

from assistants import client
from instructions import refining_chat_response_instructions
from schemas import hyp_refining_chat_response_schema
from utils import add_green_button_css, format_initial_assistant_msg  # type: ignore

# ──────────────────────────  Globals  ──────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

SOULLESS_CSS = '''
<style>
    html, body, [class*="css"]  { font-family: Arial, sans-serif; }
</style>
'''

# ───────────────────────  Session helpers  ─────────────────────
def _init_session_state() -> None:
    defaults = {
        'selected_hypothesis':       0,
        'all_hypotheses_accepted':   False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

# ─────────────────────────  UI helpers  ────────────────────────
def add_global_style() -> None:
    st.markdown(SOULLESS_CSS, unsafe_allow_html=True)
    add_green_button_css()

def sidebar_hypotheses(hypotheses: List[Dict[str, Any]]) -> None:
    '''Render collapsible list of hypotheses and handle “Edit” clicks.'''
    sel_idx = st.session_state.selected_hypothesis

    st.header('Refined hypotheses')
    for idx, hyp in enumerate(hypotheses):
        label = (f':heavy_check_mark: {hyp["title"]}'
                 if hyp.get('final_hypothesis') else hyp['title'])

        with st.expander(label, expanded=(idx == sel_idx)):
            quote = (hyp['final_hypothesis']
                     if hyp.get('final_hypothesis')
                     else hyp['hypothesis_refined_with_data_text'])
            st.markdown(f'> {quote}')

            if st.button('Edit', key=f'select_{idx}'):
                st.session_state.selected_hypothesis = idx
                st.rerun()

def display_chat_history(chat: List[Dict[str, str]]) -> None:
    for msg in chat:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])

def refine_hypothesis(sel_hyp: Dict[str, Any], user_prompt: str) -> None:
    '''Call GPT to generate assistant response & updated hypothesis text.'''
    sel_hyp.setdefault('chat_history', []).append(
        {'role': 'user', 'content': user_prompt},
    )

    # Strip potential assistant-specific keys for model input
    history_for_model = [
        {k: v for k, v in m.items() if k != 'refined_hypothesis_text'}
        for m in sel_hyp['chat_history']
    ]

    with st.spinner('Thinking …'):
        rsp = client.responses.create(
            model='gpt-4o',
            instructions=refining_chat_response_instructions,
            input=[{
                'role': 'user',
                'content': f'Here is the summary of the data: {st.session_state.data_summary}',
            }] + history_for_model,
            tools=[{'type': 'web_search_preview'}],
            text=hyp_refining_chat_response_schema,
        )

    data = json.loads(rsp.output_text)

    sel_hyp['chat_history'].append(
        {'role': 'assistant',
         'content': data['assistant_response'],
         'refined_hypothesis_text': data['refined_hypothesis_text'],
         }
    )

def accept_current(sel_hyp: Dict[str, Any]) -> None:
    if not sel_hyp.get('chat_history'):
        st.warning('Nothing to accept yet.')
        return

    last_refined = sel_hyp['chat_history'][-1].get('refined_hypothesis_text')
    sel_hyp['final_hypothesis'] = last_refined or sel_hyp.get('refined_hypothesis_text')


# ─────────────────────────  Main page  ─────────────────────────
def main() -> None:                               # noqa: C901 – manageablef
    _init_session_state()
    add_global_style()

    # ── Check prerequisites ────────────────────────────────────────────
    upd = st.session_state.get('updated_hypotheses', {})
    if not upd.get('assistant_response'):
        st.warning('Please run the processing stage first.')
        st.stop()

    hypotheses: List[Dict[str, Any]] = upd['assistant_response']

    # Guard selected_hypothesis index
    st.session_state.selected_hypothesis = min(
        st.session_state.selected_hypothesis, len(hypotheses) - 1,
    )
    sel_idx = st.session_state.selected_hypothesis
    sel_hyp = hypotheses[sel_idx]

    # if st.session_state.get('all_hypotheses_accepted'):
        # st.rerun()

    if not all(isinstance(h.get('chat_history'), list) and h['chat_history']
               for h in hypotheses):
        st.warning('⚠️  At least one hypothesis is missing chat history.')

    # ── Layout: sidebar & main canvas ─────────────────────────────────
    with st.sidebar:
        sidebar_hypotheses(hypotheses)

    st.subheader(f'Discussion: {sel_hyp["title"]}')
    display_chat_history(sel_hyp.get('chat_history', []))

    # ── Chat input ────────────────────────────────────────────────────
    prompt = st.chat_input('Refine this hypothesis further …',
                           key=f'chat_input_{sel_idx}')
    if prompt:
        # Reset final result if user reopens discussion
        sel_hyp.pop('final_hypothesis', None)
        refine_hypothesis(sel_hyp, prompt)
        st.rerun()

    # ── Sidebar actions (accept, next stage) ─────────────────────────
    with st.sidebar:
        st.header('Actions')
        st.write('Accept the refined hypothesis or discuss it further.')

        accept_clicked = st.button(
            'Keep the refined hypothesis',
            key='accept',
            disabled=bool(sel_hyp.get('final_hypothesis')),
        )
        if accept_clicked:
            accept_current(sel_hyp)
            # Only check after accepting a hypothesis
            if all(h.get('final_hypothesis') for h in hypotheses):
                st.session_state.all_hypotheses_accepted = True
                st.info('All hypotheses are accepted. You can now proceed to the **PLAN MANAGEMENT** stage.')
            st.rerun()          # ← now it executes at top level, so it works

        if st.session_state.get('all_hypotheses_accepted'):
            if st.button('NEXT STAGE', key='next'):
                st.session_state.selected_hypothesis = 0
                st.switch_page('pages/04_Plan_manager.py')

if __name__ == '__main__':
    main()
