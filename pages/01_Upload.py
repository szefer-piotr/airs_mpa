# pages/01_📂_Upload.py

from __future__ import annotations

import pandas as pd
import streamlit as st
from utils import init_state, add_green_button_css, update_csv_key, update_txt_key, DEFAULT_STATE
from info import STAGE_INFO
import pandas as pd
import copy

# Initialise session state
init_state()
add_green_button_css()

def reset_state():
    st.session_state.clear()
    st.session_state.update(copy.deepcopy(DEFAULT_STATE))
    st.rerun()

@st.dialog("Confirm delete")
def confirm_delete():
        st.warning("This will delete all uploaded files and analyses.")
        col1, col2 = st.columns(2)
        if col1.button("✅  Yes, delete everything"):
            reset_state()
        if col2.button("❌  Cancel"):
            st.rerun()


if st.session_state.data_uploaded and st.session_state.hypotheses_uploaded:
    st.info("You can now proceed to the **Processing** stage.")
    # main sidebar
    with st.sidebar:
        st.header("Actions")
        if st.button("Next", key="next"):
            st.switch_page("pages/02_Processing_files.py")
        if st.button("Remove all files"):
            confirm_delete()

# Instructions
if st.session_state.app_state == "upload":
    st.markdown(STAGE_INFO["upload"])




# ── upload controls ────────────────────────────────────────────────────────
col_csv, col_txt = st.columns(2)

with col_csv:
    csv_up = st.file_uploader("Add CSV", type="csv", key=f"csv_up_{st.session_state.uploader_csv_key}")
    if csv_up:
        if st.button("UPLOAD", key=f"upload_csv_{st.session_state.uploader_csv_key}"):
            st.session_state.files[csv_up.name] = csv_up
            st.success(f"Saved **{csv_up.name}**")
            st.session_state.data_uploaded = True
            update_csv_key()
            st.rerun()
        

with col_txt:
    txt_up = st.file_uploader("Add TXT", type="txt", key=f"txt_up_{st.session_state.uploader_txt_key}")
    if txt_up:
        if st.button("UPLOAD", key=f"upload_txt_{st.session_state.uploader_txt_key}"):
            st.session_state.hypotheses = txt_up
            st.success(f"Saved **{txt_up.name}**")
            st.session_state.hypotheses_uploaded = True
            update_txt_key()
            st.rerun()

# ── show existing uploads ──────────────────────────────────────────────────
if st.session_state.files:
    st.markdown("#### Files in current session")
    for fname, uf in st.session_state.files.items():
        # with st.expander(fname, expanded=False):

        st.markdown(f"##### Filename: **{fname}**")
        st.markdown(f"Size: **{uf.size / 1024:.2f} KB**")
        st.markdown(f"Type: **{uf.type}**")
        st.markdown("---")

        ext = fname.split(".")[-1].lower()

        # rewind buffer before each read
        uf.seek(0)

        if ext == "csv":
            df = pd.read_csv(uf)
            st.dataframe(df.head(), use_container_width=True)
            st.caption(f"{len(df):,} rows × {len(df.columns)} columns")
        else:
            st.info("🛈 No preview available for this file type.")

        # optional remove button
        if st.button("🗑️ Remove", key=f"remove_{fname}"):
            del st.session_state.files[fname]
            st.session_state.data_uploaded = False
            st.rerun()
else:
    st.info("No data uploaded yet.")

if st.session_state.hypotheses:
    # with st.expander(st.session_state.hypotheses.name, expanded=False):
    st.session_state.hypotheses.seek(0)  # rewind buffer before read
    st.markdown(f"##### Filename {st.session_state.hypotheses.name}")
    st.text_area(
        "Preview",
        st.session_state.hypotheses.read().decode("utf-8") if st.session_state.hypotheses else "",
        height=200,
        disabled=False,
    )
    # optional remove button
    if st.button("🗑️ Remove", key=f"remove_{st.session_state.hypotheses.name}"):
        st.session_state.hypotheses = None
        st.session_state.hypotheses_uploaded = False
        st.rerun()

else:
    st.info("No hypotheses uploaded yet.")

# if st.session_state.data_uploaded and st.session_state.hypotheses_uploaded:
#     st.info("Click **Next** to process the files.")
#     if st.button("Next", key="next"):
#         st.switch_page("pages/02_Processing_files.py")