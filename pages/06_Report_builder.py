# report_builder.py
'''Streamlit page 05 – Build and refine the final scientific report'''

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any, Dict, List

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
from instructions import report_generation_instructions, report_chat_instructions
from utils import add_green_button_css, IMG_DIR, replace_file_ids_with_html

# ──────────────────────────  Globals  ──────────────────────────
ASSISTANTS = get_assistants()
SOULLESS_CSS = '''
<style>
    html, body, [class*="css"]  { font-family: Arial, sans-serif; }
</style>
'''
TOOLS = [{'type': 'web_search_preview'}]

# ───────────────────────  Session helpers  ─────────────────────
def _init_session_state() -> None:
    defaults: Dict[str, Any] = {
        'report_generated':      False,
        'final_report':          [],
        'report_chat_history':   [],
        'images':                [],
        'thread_id':             client.beta.threads.create().id,
        'report_running':        False,
    }
    for k, v in defaults.items():
        st.session_state.setdefault(k, v)

# ────────────────────────  Styling  ───────────────────────────
def add_global_style() -> None:
    st.markdown(SOULLESS_CSS, unsafe_allow_html=True)
    add_green_button_css()


def preview(fid: str, width: int = 600):
    from io import BytesIO, BufferedReader
    import base64, streamlit as st
    raw: bytes = client.files.content(fid).read()
    st.image(raw, width=width)

# ──────────────────────  Utility funcs  ───────────────────────
def replace_image_paths_with_html(text: str,
                                  img_dir: Path | None = None,
                                  width: int = 600) -> str:
    pattern = re.compile(r'[\w./\\-]+(?:\.png|\.jpg|\.jpeg|\.gif)',
                         re.IGNORECASE)

    def _to_html(match):
        path_str = match.group(0)
        try:
            img_path = Path(path_str)
            if img_dir and not img_path.is_absolute():
                img_path = img_dir / path_str
            if not img_path.exists():
                return f'[Image not found: {img_path}]'
            b64 = base64.b64encode(img_path.read_bytes()).decode()
            return (f'<p align="center"><img src="data:image/png;base64,{b64}" '
                    f'width="{width}"></p>')
        except Exception as exc:                  # noqa: BLE001
            return f'[Error loading image: {exc}]'

    return pattern.sub(_to_html, text)


# def build_report_prompt() -> List[str]:
#     prompt_parts: List[str] = []
#     for hyp in st.session_state.updated_hypotheses['assistant_response']:
#         prompt_parts.append(hyp['title'])
#         for msg in hyp['plan_execution_chat_history']:
#             print(f"Processing message: {msg}")
#             if 'items' in msg:
#                 for item in msg['items']:
#                     if item['type'] == 'image':
#                         prompt_parts.append(item['content'][0])
#                         # prompt_parts.append(str(item['image_path']))
#                     else:
#                         prompt_parts.append(item['content'])
#             elif 'content' in msg:
#                 prompt_parts.append(msg['content'])
#         print(f"Prompt parts: {type(prompt_parts)}, {len(prompt_parts)}")
#     return "\n\n".join(prompt_parts)


def build_report_prompt() -> str:
    """Build the single markdown prompt sent to the report-generator.
    
    * Includes every refined hypothesis and its execution history.
    * If the user has already chatted with the assistant about the report,
      that dialogue is appended under a separate header.
    """
    prompt_parts: list[str] = []

    # ── 1. Hypotheses & execution logs ─────────────────────────────
    for hyp in st.session_state.updated_hypotheses["assistant_response"]:
        prompt_parts.append(hyp["title"])

        for msg in hyp["plan_execution_chat_history"]:
            if "items" in msg:                             # assistant/user log
                for item in msg["items"]:
                    if item["type"] == "image":
                        prompt_parts.append(item["content"][0])
                    else:
                        prompt_parts.append(item["content"])
            elif "content" in msg:                         # plain text log
                prompt_parts.append(msg["content"])

    # ── 2. Optional follow-up chat ────────────────────────────────
    chat_history = st.session_state.get("report_chat_history", [])
    if chat_history:                                       # only if not empty
        prompt_parts.append("\n\n--- Discussion history ---\n")
        for chat in chat_history:
            role = chat["role"].capitalize()               # User / Assistant

            if role == "Assistant":
                # assistant messages are chunked into `items`
                for item in chat["items"]:
                    if item["type"] == "image":
                        prompt_parts.append("[assistant posted an image]")
                    else:
                        prompt_parts.append(item["content"])
            else:  # user message
                prompt_parts.append(f"User: {chat['content']}")

    # ── 3. Flatten everything into one markdown string ────────────
    return "\n\n".join(prompt_parts)


def display_report() -> None:
    md = st.session_state.final_report[0]
    st.markdown(replace_file_ids_with_html(md),
                unsafe_allow_html=True)

    st.download_button('⬇️ Download report (Markdown)',
                       md,
                       file_name='scientific_report.md',
                       mime='text/markdown')

def render_chat_history() -> None:
    for msg in st.session_state.report_chat_history:
        with st.chat_message(msg['role']):
            if msg['role'] == 'assistant':
                for item in msg['items']:
                    tp = item['type']
                    if tp == 'code_input':
                        st.code(item['content'], language='python')
                    elif tp == 'code_output':
                        st.code(item['content'], language='text')
                    elif tp == 'image':
                        for html in item['content']:
                            st.markdown(replace_file_ids_with_html(html), unsafe_allow_html=True)
                    elif tp == 'text':
                        st.markdown(item['content'], unsafe_allow_html=True)
            else:
                st.markdown(msg['content'], unsafe_allow_html=True)


# ─────────────────────  Assistant streaming  ──────────────────
def stream_report_chat(user_prompt: str) -> None:
    thread_id = st.session_state.thread_id
    st.session_state.report_chat_history.append(
        {'role': 'user', 'content': user_prompt},
    )
    client.beta.threads.messages.create(thread_id=thread_id,
                                        role='user',
                                        content=user_prompt)

    banner = st.empty()
    banner.info('Assistant is thinking ⏳ …')

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

    stream = client.beta.threads.runs.create(
        thread_id    = thread_id,
        assistant_id = ASSISTANTS['report_chat'].id,
        instructions = report_chat_instructions,
        tool_choice  = {'type': 'code_interpreter'},
        stream       = True,
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
                
                # elif isinstance(out, CodeInterpreterOutputImage):
                #     fid  = out.image.file_id
                #     data = client.files.content(fid).read()
                #     img_path = IMG_DIR / f'{fid}.png'
                #     img_path.write_bytes(data)
                #     html = (
                #         '<p align="center">'
                #         f'<img src="data:image/png;base64,'
                #         f'{base64.b64encode(data).decode()}" width="600"></p>'
                #     )
                #     assistant_items[-1]['content'].append(html)
                #     result_pl.markdown(html, unsafe_allow_html=True)
                
                # elif isinstance(out, CodeInterpreterOutputImage):
                #     ensure_slot("image")                      # <<< NEW
                #     fid  = out.image.file_id
                #     data = client.files.content(fid).read()
                #     img_path = IMG_DIR / f"{fid}.png"
                #     img_path.write_bytes(data)

                #     html = (
                #         "<p align='center'>"
                #         f"<img src='data:image/png;base64,"
                #         f"{base64.b64encode(data).decode()}' width='600'></p>"
                #     )
                #     assistant_items[-1]["content"].append(html)
                #     result_pl.markdown(html, unsafe_allow_html=True)

                elif isinstance(out, CodeInterpreterOutputImage):
                    fid = out.image.file_id          
                    st.session_state.images.append(
                        {"fid": fid, "caption": f"Figure {len(st.session_state.images)+1}",
                         "img_bytes": client.files.content(fid).read()}
                    )

                    print(f'\n\nImage file ID:\n\n{fid}')

                    img_bytes = client.files.content(fid).read()
                    b64 = base64.b64encode(img_bytes).decode()
                    html = f'<p align="center"><img src="data:image/png;base64,{b64}" width="600"></p>'
                    ensure_slot("image")
                    assistant_items[-1]["content"].append(fid)
                    
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

    st.session_state.report_chat_history.append(
        {'role': 'assistant', 'items': assistant_items},
    )
    banner.success('Assistant response finished ✅')
    st.rerun()

# ─────────────────────────  Main page  ─────────────────────────
def main() -> None:                              # noqa: C901 – large but clear
    _init_session_state()
    add_global_style()

    st.title('📄 Report builder')

    # print(f"\n\nImages saved\n\n{st.session_state.get('images', [])}")

    # for img in st.session_state.get("images", []):
    #     if isinstance(img, dict) and "fid" in img:
    #         preview(img["fid"])

    # ---------- Sidebar --------------------------------------------------
    with st.sidebar:
        st.header('Refined initial hypotheses')
        for i, hyp in enumerate(
                st.session_state.updated_hypotheses['assistant_response'], 1):
            st.markdown(f'**H{i}.** {hyp["title"]}')

        st.divider()
        st.header('Actions')

        gen_clicked = st.button(
            '📝 Generate full report',
            # disabled=st.session_state.report_running,
        )
        
        if st.session_state.get("report_generated", False):
            reset_clicked = st.button('Start new session')
            # ---------- Reset session -------------------------------------------
            if reset_clicked:
                st.session_state.clear()
                st.switch_page('pages/01_Upload.py')
                st.rerun()

    # ---------- Generate report -----------------------------------------
    if gen_clicked:
        st.session_state.report_running = True
        banner = st.empty()
        banner.info('Synthesising report – this may take a minute …')

        full_prompt: str = build_report_prompt()

        rsp = client.responses.create(
            model='gpt-4.1',
            instructions=report_generation_instructions,
            input=full_prompt,
            tools=TOOLS,
        )

        st.session_state.final_report = [rsp.output_text]
        st.session_state.report_generated = True
        st.session_state.report_running = False
        banner.success('Report generated ✅')
        st.rerun()

    

    # ---------- Show report & chat --------------------------------------
    if st.session_state.report_generated:
        display_report()
        st.divider()
        st.subheader('💬 Discuss & refine the report')

        render_chat_history()

        prompt = st.chat_input('Ask for corrections, extra analyses, images …',
                               key='report_chat_input')
        if prompt:
            stream_report_chat(prompt)

if __name__ == '__main__':
    main()
