thread = client.beta.threads.create()
st.session_state.thread_id = thread.id

# Stream data summary creation
stream_data_summary(client)

st.session_state.processing_done = True

with st.expander("📊 Data summary", expanded=False):
    st.json(st.session_state.data_summary)

# Refining prompt stage
refine_prompt = (
    f"Data summary: {st.session_state.data_summary}\n\n"
    f"Hypotheses: {st.session_state.hypotheses}\n\n"
    f"{processing_files_instruction}\n"
)

response = client.responses.create(
    model="gpt-4o",
    instructions=refinig_instructions,
    input=[{"role": "user", "content": refine_prompt}],
    tools=[{"type": "web_search_preview"}],
    text=hypotheses_schema,
)

# The hypotheses are being updated here
st.session_state.updated_hypotheses = json.loads(response.output_text)

for hyp in st.session_state.updated_hypotheses["assistant_response"]:
    pretty_msg = format_initial_assistant_msg(hyp)
    hyp["chat_history"] = [{"role": "assistant", "content": pretty_msg}]
    hyp["final_hypothesis"] = []


st.session_state.processing_done = True
st.success("Processing complete!", icon="✅")
st.session_state.app_state = "hypotheses_manager"
st.rerun()