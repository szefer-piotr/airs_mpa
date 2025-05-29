import streamlit as st
import json

from assistants import client
from instructions import (
    refining_chat_response_instructions
)

from utils import add_green_button_css
from schemas import hyp_refining_chat_response_schema

add_green_button_css()



### Page logic
if st.session_state.updated_hypotheses.get("assistant_response", None) is None:
    st.warning("Please run the processing stage first.")
    st.stop()

hypotheses = st.session_state.updated_hypotheses["assistant_response"]

all_have_history = all(
    isinstance(h.get("chat_history"), list) and len(h["chat_history"]) > 0
    for h in hypotheses
)

if all(h.get("final_hypothesis", False) for h in st.session_state.updated_hypotheses["assistant_response"]):
    st.session_state.all_hypotheses_accepted = True
    st.info("All hypotheses are accepted. Yu can now proceed to the PLAN MANAGMENT stage.")


if not all_have_history:
    st.markdown("⚠️ At least one hypothesis is missing chat history")

if all_have_history:
    # ── SIDEBAR: list of hypotheses --------------------------------------------
    
    # ── MAIN CANVAS: chat & accept button -------------------------------------
    sel_idx = st.session_state.selected_hypothesis
    sel_hyp = st.session_state.updated_hypotheses["assistant_response"][sel_idx]
    
    with st.sidebar:
        st.header("Refined hypotheses")

        for idx, hyp in enumerate(st.session_state.updated_hypotheses["assistant_response"]):

            print((idx, sel_idx, hyp["title"]))
            # with st.expander(hyp["title"], expanded = (idx == sel_idx)):

            hypo_label = f":heavy_check_mark: {hyp['title']}" if bool(hyp["final_hypothesis"]) else hyp["title"]

            with st.expander(label = hypo_label, expanded = (idx == sel_idx)):
                
                if hyp["final_hypothesis"]:
                    st.markdown(f"> {hyp['final_hypothesis']}")

                else:
                    st.markdown(f"> {hyp['hypothesis_refined_with_data_text']}")
                
                if st.button("Edit", key=f"select_{idx}"):
                    st.session_state.selected_hypothesis = idx
                    st.rerun()

    st.subheader(f"Discussion: {sel_hyp['title']}")

    # display chat history
    for msg in sel_hyp["chat_history"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # chat input
    user_prompt = st.chat_input("Refine this hypothesis further …", key=f"chat_input_{sel_idx}")

    if user_prompt:
        # Restart the final hypothesis when user adds prompts to already refined hypothesis
        print(f"User prompt: ")
        if sel_hyp.get("final_hypothesis", None) is not None:
            sel_hyp["final_hypothesis"] = []

        sel_hyp["chat_history"].append({"role": "user", "content": user_prompt})

        response_input_history = [{
            k: v for k, v in d.items() if k != "refined_hypothesis_text"} for d in sel_hyp["chat_history"]
            ]

        with st.spinner("Thinking …"):
            response = client.responses.create(
                model="gpt-4o",
                instructions=refining_chat_response_instructions,
                input= [{
                    "role": "user", 
                    "content": f"Here is the summary of the data: {st.session_state.data_summary}"
                }] + response_input_history,
                tools=[{"type": "web_search_preview"}],
                text = hyp_refining_chat_response_schema,
            )
        
        response_json = json.loads(response.output_text)

        # print(f"\n\nTHE RESPONSE JSON:\n\n{response_json}")

        sel_hyp["chat_history"].append(
            {"role": "assistant", 
             "content": response_json["assistant_response"],
             "refined_hypothesis_text": response_json["refined_hypothesis_text"]}
        )
        st.rerun()

    # ACCEPT BUTTON
    acc_disabled = bool(sel_hyp["final_hypothesis"])
    
    with st.sidebar:
        st.header("Actions")
        st.write("Accept the refined hypothesis or discuss it further.")
        if st.button("Keep the refined hypothesis", key="accept"):
            if len(sel_hyp["chat_history"]) > 1:
                sel_hyp["final_hypothesis"] = sel_hyp["chat_history"][-1]["refined_hypothesis_text"]
                st.rerun()
            else:
                sel_hyp["final_hypothesis"] = sel_hyp["refined_hypothesis_text"]
            st.success("Hypothesis accepted!")
            st.rerun()
        if all(h.get("final_hypothesis", False) for h in st.session_state.updated_hypotheses["assistant_response"]):
            with st.sidebar:
                if st.button("NEXT STAGE", key="next"):
                    st.session_state.selected_hypothesis = 0
                    st.switch_page("pages/04_Plan_manager.py")

# ── AUTO‑ADVANCE -----------------------------------------------------------

    # col_back, col_next = st.columns(2)
    # with col_next:
    #     if st.button("Next", key="next"):
    #         st.switch_page("pages/04_Plan_manager.py")
    # with col_back:
    #     if st.button("Back", key="back"):
    #         st.switch_page("pages/02_Processing_files.py")