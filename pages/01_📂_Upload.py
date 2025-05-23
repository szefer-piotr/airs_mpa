# pages/01_📂_Upload.py

from __future__ import annotations

import pandas as pd
import streamlit as st
from utils import init_state, add_green_button_css
from info import STAGE_INFO
import pandas as pd


from assistants import create as get_assistants
from assistants import client

ASSISTANTS = get_assistants()


init_state()
add_green_button_css()


if st.session_state.app_state == "upload":
    st.markdown(STAGE_INFO["upload"])


# ── CSV
# csv_file = st.file_uploader("Choose a CSV file", type="csv", key="csv_uploader")
# if csv_file:
#     st.toast("CSV file uploaded!", icon="🎉")
#     df_preview = pd.read_csv(csv_file)
#     st.session_state.files[csv_file.name] = csv_file
#     st.session_state.data_uploaded = True
#     with st.expander("Data preview"):
#         st.dataframe(df_preview.head())

# # ── TXT
# txt_file = st.file_uploader("Choose a TXT file", type="txt", key="txt_uploader")
# if txt_file:
#     st.toast("TXT file uploaded!", icon="📝")
#     st.session_state.hypotheses = txt_file.read().decode("utf‑8")
#     st.session_state.hypotheses_uploaded = True
#     with st.expander("Hypotheses preview"):
#         st.text_area("File content", st.session_state.hypotheses, height=180)

# # Auto‑advance once both files are uploaded
# if (
#     st.session_state.data_uploaded
#     and st.session_state.hypotheses_uploaded
#     and st.session_state.app_state == "upload"
# ):
#     st.session_state.app_state = "processing"
#     st.rerun()


if "uploader_csv_key" not in st.session_state:
    st.session_state.uploader_csv_key = 0
if "uploader_txt_key" not in st.session_state:
    st.session_state.uploader_txt_key = 0

def update_csv_key():
    st.session_state.uploader_csv_key += 1

def update_txt_key():
    st.session_state.uploader_txt_key += 1

# ── upload controls ────────────────────────────────────────────────────────
col_csv, col_txt = st.columns(2)

with col_csv:
    csv_up = st.file_uploader("Add CSV", type="csv", key=f"csv_up_{st.session_state.uploader_csv_key}")
    if csv_up:
        if st.button("UPLOAD", key=f"upload_csv_{st.session_state.uploader_csv_key}"):
            st.session_state.files[csv_up.name] = csv_up
            st.success(f"Saved **{csv_up.name}**")
            update_csv_key()
            st.rerun()
        

with col_txt:
    txt_up = st.file_uploader("Add TXT", type="txt", key=f"txt_up_{st.session_state.uploader_txt_key}")
    if txt_up:
        if st.button("UPLOAD", key=f"upload_txt_{st.session_state.uploader_txt_key}"):
            st.session_state.files[txt_up.name] = txt_up
            st.success(f"Saved **{txt_up.name}**")
            update_txt_key()
            st.rerun()

# ── show existing uploads ──────────────────────────────────────────────────
if st.session_state.files:
    st.markdown("#### Files in current session")
    for fname, uf in st.session_state.files.items():
        with st.expander(fname, expanded=False):
            ext = fname.split(".")[-1].lower()

            # rewind buffer before each read
            uf.seek(0)

            if ext == "csv":
                df = pd.read_csv(uf)
                st.dataframe(df.head(), use_container_width=True)
                st.caption(f"{len(df):,} rows × {len(df.columns)} columns")
            elif ext == "txt":
                txt = uf.read().decode("utf-8")
                st.text_area(
                    "Preview",
                    txt if len(txt) < 10_000 else txt[:9_000] + " …",
                    height=200,
                    disabled=True,
                )
            else:
                st.info("🛈 No preview available for this file type.")

            # optional remove button
            if st.button("🗑️ Remove", key=f"remove_{fname}"):
                print(f"Session state: {st.session_state.files[fname]}")
                del st.session_state.files[fname]
                st.rerun()

else:
    st.info("No files uploaded yet.")

# ── auto-advance flag (other pages will check it) ──────────────────────────
st.session_state.data_uploaded      = any(f.endswith(".csv") for f in st.session_state.files)
st.session_state.hypotheses_uploaded = any(f.endswith(".txt") for f in st.session_state.files)
