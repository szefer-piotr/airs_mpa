# streamlit_chat_app.py
"""
Streamlit app that lets a user upload a file and chat with an LLM.  
It uses the provided `get_llm_response` helper, supports code‑interpreter
executions inside an OpenAI container, and keeps the full conversation in
`st.session_state`.

Requirements:
    pip install streamlit openai asyncio
    export OPENAI_API_KEY="..."
Run with:
    streamlit run streamlit_chat_app.py
"""

from __future__ import annotations

import openai
import pandas as pd
from dotenv import load_dotenv
from pathlib import Path
from typing import AsyncGenerator, Dict, List
from streamlit.runtime.uploaded_file_manager import UploadedFile
# from openai.containers import Container

import io
import streamlit as st
from openai import OpenAI

###############################################################################
# 🧠  LLM HELPER – directly copied from the userʼs code so the app is self‑contained
###############################################################################

load_dotenv()  # load environment variables from .env file

client: OpenAI = OpenAI()  # uses $OPENAI_API_KEY automatically OPENAI_API_KEY

# Create a container for code‑interpreter runs ONCE at start‑up
def _create_container(client: OpenAI,
                      file_ids: List[str],
                      name: str = "user-container"):
    container = client.containers.create(
        name=name,
        file_ids=file_ids
        )
    # Print message to confirm container creation
    
    print(f"Created container {container.id} for code interpreter runs.")
    # print(f"Container details: {container.to_dict()}")

    return container


def _create_code_interpreter_tool(container):
    if container == "auto":
        # Use the default container for code interpreter
        user_container = {"type": "code_interpreter", "container": "auto"}
    else:
        user_container = {"type": "code_interpreter", "container": container.id}
    
    print(f"Created code interpreter tool with container: {user_container}")

    return user_container


def _create_web_search_tool():
    return {"type": "web_search_preview"}


def _get_uploaded_csv_file_id(
                client: OpenAI,
                uploaded_file: UploadedFile
            ):
    """Upload the CSV file to OpenAI and store the file ID in session state."""

    print(f"Uploading file {uploaded_file.name} to OpenAI... of type {uploaded_file.type}")
    
    if uploaded_file.type == "text/csv":
        
        df = pd.read_csv(uploaded_file)
    
        csv_file = io.BytesIO()    
        df.to_csv(csv_file, index=False)
        csv_file.seek(0)  # Reset file pointer to the beginning

        openai_file = client.files.create(
            file=csv_file,
            purpose="user_data",
        )

        return(openai_file.id)
    
    else:
        raise ValueError("Uploaded file is not a CSV file.")
        


def get_llm_response(
    client: OpenAI,
    model: str,
    prompt: str,
    instructions: str,
    tools: List[Dict[str, str]],
    context: str = "",
    stream: bool = False,
    temperature: float = 0,
):
    """Wrapper around `client.responses.create` that yields final content."""
    
    try:
        response = client.responses.create(
            model=model,
            tools=tools,
            instructions=instructions,
            input=[
                {"role": "system", "content": context},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            stream=stream,
        )

         # NOTE: streaming support left as an exercise – default is single final chunk
        content = response.output_text
        if content is not None:
            return content
    except openai.BadRequestError as e:
        error_message = str(e)
        # Or, if you want the dict:
        error_data = getattr(e, 'response', None)
        # Check for specific error message
        if "Container is expired" in error_message:
            print("Container expired! Re-create or refresh the container before retrying.")
        # (Optional) Add your recovery logic here, e.g., re-create the container
        else:
            print(f"BadRequestError: {error_message}")
        # Handle other 400 errors
    except Exception as e:
        # Catch-all for other exceptions
        print(f"An unexpected error occurred: {e}")

###############################################################################
# 🎛️  Streamlit UI helpers
###############################################################################

st.set_page_config(
    page_title="Chat with your Data – powered by OpenAI",
    page_icon="💬",
    layout="wide",
)

# Initialise session state on first load ------------------------------------------------
if "messages" not in st.session_state:
    # Each entry: {"role": "user"|"assistant", "content": str}
    st.session_state.messages: List[Dict[str, str]] = []

if "uploaded_file" not in st.session_state:
    st.session_state.uploaded_file: Path | None = None

if "container" not in st.session_state:
    st.session_state.container: str | None = None  # Container for code interpreter runs

if "tools" not in st.session_state:
    st.session_state.tools: List[Dict[str, str]] = []  # Tools for LLM calls

if "file_ids" not in st.session_state:
    st.session_state["file_ids"] = []  # Store file IDs for uploaded files

###############################################################################
# 🔄  Sidebar – settings & upload
###############################################################################
with st.sidebar:
    st.header("Settings")

    model: str = st.text_input("Model", value="gpt-4o-mini")
    temperature: float = st.slider("Temperature", 0.0, 1.0, 0.0, 0.05)
    st.divider()

    uploaded_file = st.file_uploader("Upload a file to give the LLM extra context")
    
    if uploaded_file:
        st.session_state.uploaded_file = uploaded_file
        st.success(f"**{st.session_state.uploaded_file.name}** successfully uploaded. It will be included as context in your next message.")
        # When files are uploaded create a container for code interpreter runs
        


###############################################################################
# 💬  Main area – chat transcript and input box
###############################################################################

st.title("💬 Chat with an LLM over your data")

# Display the existing conversation -----------------------------------------
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"], unsafe_allow_html=True)

# Input box -------------------------------------------------------------------
user_prompt: str | None = st.chat_input("Ask me anything…")

if user_prompt:
    if st.session_state.uploaded_file is None:
        st.error("Please upload a file first to give the LLM extra context.")
        st.stop()

    else:
        if st.session_state.container is None:
            
            # Create a container for code interpreter runs
            # Use the uploaded file to create the container
            print("Creating container for code interpreter runs with uploaded file.")
            st.session_state.container = _create_container(
                client=client,
                file_ids=[_get_uploaded_csv_file_id(client, st.session_state.uploaded_file)],
                name="user-container")
            st.session_state.tools = [
                _create_web_search_tool(),
                _create_code_interpreter_tool(container=st.session_state.container if st.session_state.uploaded_file else "auto")
            ]
     
    # 1️⃣  Echo the user message in the chat transcript
    st.session_state.messages.append({"role": "user", "content": user_prompt})
    
    with st.chat_message("user"):
        st.markdown(user_prompt)

    # 2️⃣  Build context: file preview + last N assistant messages -------------
    # context_chunks: List[str] = []

    # # (a) Include a small preview of the uploaded file so the model sees it
    # if st.session_state.uploaded_file is not None:
    #     # file_bytes: bytes = st.session_state.uploaded_file.read()
    #     context_chunks.append(
    #         f"The user uploaded a file named **{st.session_state.uploaded_file.name}**.\n"
    #     )
    #     # Reset file pointer so the user can download it later if desired
    #     st.session_state.uploaded_file.seek(0)

    # (b) Include the last assistant response to keep short‑term memory
    # recent_assistant_msgs = [m["content"] for m in st.session_state.messages if m["role"] == "assistant"]
    recent_chat_msgs = [m["content"] for m in st.session_state.messages]
    # if recent_assistant_msgs:
    #     context_chunks.append("Previous assistant reply: " + recent_assistant_msgs[-1])

    history: str = "\n\n".join(recent_chat_msgs)

    # 3️⃣  Call the LLM ---------------------------------------------------------
    def _ask_llm() -> str:
        response_text = ""
        for chunk in get_llm_response(
            client=client,
            model=model,
            prompt=user_prompt,
            instructions="You are a helpful assistant that answers the user based on the available context.",
            tools=st.session_state.tools,
            context=history,
            stream=False,
            temperature=temperature,
        ):
            response_text += chunk
        return response_text.strip()

    with st.spinner("Thinking …"):
        assistant_reply: str = _ask_llm()

    # 4️⃣  Show assistant reply and append to session state --------------------
    with st.chat_message("assistant"):
        st.markdown(assistant_reply, unsafe_allow_html=True)

    st.session_state.messages.append({"role": "assistant", "content": assistant_reply})

###############################################################################
# 📌  Footer – credits
###############################################################################

st.caption("Built with 🧡 using Streamlit & OpenAI")