# pages/01_📂_Upload.py
# ───────────────────────────────────────────────────────────────────────────
from __future__ import annotations

# ── std-lib ───────────────────────────────────────────────────────────────
import copy
from io import BytesIO
from pathlib import Path

# ── 3rd-party ─────────────────────────────────────────────────────────────
import pandas as pd
import streamlit as st

# ── app modules ───────────────────────────────────────────────────────────
from info import STAGE_INFO
from utils import (
    DEFAULT_STATE,
    init_state,
    add_green_button_css,
    update_csv_key,
    update_txt_key,
)

# ───────────────────────────── init & CSS ────────────────────────────────
init_state()                  # includes st.set_page_config(…)
add_green_button_css()

# ─────────────────────────── helpers ─────────────────────────────────────
def reset_state() -> None:
    st.session_state.clear()
    st.session_state.update(copy.deepcopy(DEFAULT_STATE))
    st.rerun()


@st.dialog("Confirm delete")
def confirm_delete() -> None:
    st.warning("This will delete all uploaded files and analyses.")
    col1, col2 = st.columns(2)
    if col1.button("✅  Yes, delete everything"):
        reset_state()
    if col2.button("❌  Cancel"):
        st.rerun()


def preview_csv(fname: str, uf: "UploadedFile") -> None:
    uf.seek(0)
    df = pd.read_csv(uf)
    st.dataframe(df.head(), use_container_width=True)
    st.caption(f"{len(df):,} rows × {len(df.columns)} columns")


# ───────────────────── sidebar: navigation & actions ─────────────────────
with st.sidebar:
    st.header(":gear: Actions")

    if st.session_state.data_uploaded and st.session_state.hypotheses_uploaded:
        if st.button("Next ➡️", key="next"):
            st.switch_page("pages/02_Processing_files.py")

    if st.button("🗑️ Remove all files"):
        confirm_delete()

# ───────────────────── main instructions (once per state) ────────────────
if st.session_state.app_state == "upload":
    st.markdown(STAGE_INFO["upload"])

# ───────────────────────── upload controls ───────────────────────────────
col_csv, col_hyp = st.columns(2)

# — CSV uploader —
with col_csv:
    csv_up = st.file_uploader(
        "Add CSV",
        type="csv",
        key=f"csv_up_{st.session_state.uploader_csv_key}",
    )
    if csv_up and st.button("UPLOAD", key=f"upload_csv_{st.session_state.uploader_csv_key}"):
        st.session_state.files[csv_up.name] = csv_up
        st.session_state.data_uploaded = True
        update_csv_key()
        st.success(f"Saved **{csv_up.name}**")
        st.rerun()

# — Hypotheses: upload OR manual —
with col_hyp:
    st.subheader("Hypotheses")
    txt_up = st.file_uploader(
        "Upload TXT",
        type="txt",
        key=f"txt_up_{st.session_state.uploader_txt_key}",
    )
    if txt_up and st.button("UPLOAD", key=f"upload_txt_{st.session_state.uploader_txt_key}"):
        txt_up.seek(0)
        st.session_state.hypotheses_text = txt_up.read().decode("utf-8")
        st.session_state.hypotheses_file = txt_up          # keep original file
        st.session_state.hypotheses_name = txt_up.name
        st.session_state.hypotheses_uploaded = True
        update_txt_key()
        st.success(f"Saved **{txt_up.name}**")
        st.rerun()

    # Manual entry (available whether or not a file was chosen)
    if not st.session_state.hypotheses_uploaded:
        manual_text = st.text_area("Type / paste hypotheses", height=200)
        if st.button("💾 Save typed hypotheses", disabled=manual_text.strip() == ""):
            st.session_state.hypotheses_text = manual_text
            st.session_state.hypotheses_name = "manual_hypotheses.txt"
            st.session_state.hypotheses_uploaded = True
            st.success("Hypotheses saved")
            st.rerun()

# ───────────────────── show existing uploads ─────────────────────────────
if st.session_state.files:
    st.markdown("#### Files in current session")
    for fname, uf in st.session_state.files.items():
        st.markdown(f"##### **{fname}**  ({uf.size/1024:.2f} KB)")
        if Path(fname).suffix.lower() == ".csv":
            preview_csv(fname, uf)
        else:
            st.info("🛈 No preview available for this file type.")
        if st.button("🗑️ Remove", key=f"remove_{fname}"):
            del st.session_state.files[fname]
            st.session_state.data_uploaded = bool(st.session_state.files)
            st.rerun()
else:
    st.info("No CSV uploaded yet.")

# ───── hypotheses editor (always editable once present) ──────────────────
if st.session_state.hypotheses_uploaded:
    edited_text = st.text_area(
        "Hypotheses (editable)",
        st.session_state.hypotheses_text,
        height=300,
        key="hypotheses_editor",
    )

    cols = st.columns([1, 1, 6])

    # NEW: explicit “Save hypotheses” button
    if cols[0].button("💾 Save", key="save_hypotheses"):
        st.session_state.hypotheses_text = edited_text
        st.toast("Hypotheses saved ✅", icon="💾")

    # already-existing remove button (unchanged)
    if cols[1].button("🗑️ Remove", key="remove_hypotheses"):
        for k in ("hypotheses_file", "hypotheses_text", "hypotheses_name"):
            st.session_state.pop(k, None)
        st.session_state.hypotheses_uploaded = False
        st.rerun()
else:
    st.info("No hypotheses provided yet.")
