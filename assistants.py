from dotenv import load_dotenv
import os
import streamlit as st
from openai import OpenAI
from instructions import (
    data_summary_instructions, step_execution_assistant_instructions,
    step_execution_chat_assistant_instructions, report_generation_instructions
)

load_dotenv()
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key)  # pick up key from env

def create() -> dict:
    if "assistants" not in st.session_state:
        st.session_state.assistants = {
            "data_summary": client.beta.assistants.create(
                name="Data summariser",
                model="gpt-4o-2024-08-06",
                instructions=data_summary_instructions,
                temperature=0,
                tools=[{"type":"code_interpreter"}],
            ),
            "analysis": client.beta.assistants.create(
                name="Analysis",
                model="gpt-4o",
                instructions=step_execution_assistant_instructions,
                tools=[{"type":"code_interpreter"}],
                temperature=0,
            ),
            "analysis_chat": client.beta.assistants.create(
                name="Analysis chat",
                model="gpt-4o",
                instructions=step_execution_chat_assistant_instructions,
                tools=[{"type":"code_interpreter"}],
                temperature=0,
            ),
            "report": client.beta.assistants.create(
                name="Report builder",
                model="gpt-4.1",
                instructions=report_generation_instructions,
                temperature=0,
                tools=[{"type":"code_interpreter"}],
            ),
        }
    return st.session_state.assistants
