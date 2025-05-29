import streamlit as st

# 👇 MUST be the first Streamlit statement
st.set_page_config(
    page_title="Home",   # ← this becomes the sidebar label
    page_icon="🏠",
    layout="wide",
)

from utils import init_state, add_green_button_css
init_state(); add_green_button_css()

# # page lablels
# home = st.Page("app.py"),
# upload = st.Page("pages/01_Upload.py"),
# processing = st.Page("pages/02_Processing_files.py"),
# hypotheses_manager = st.Page("pages/03_Hypotheses_manager.py"),
# plan_manager = st.Page("pages/04_Plan_manager.py"),
# plan_execution = st.Page("pages/05_Plan_execution.py"),
# report_builder = st.Page("pages/06_Report_builder.py"),


print("Session state:", st.session_state)

upload = st.Page("pages/01_Upload.py", icon="✔️") if bool(st.session_state.data_uploaded and st.session_state.hypotheses_uploaded) else st.Page("pages/01_Upload.py")
processing = st.Page("pages/02_Processing_files.py", icon="✔️") if st.session_state.processing_done else st.Page("pages/02_Processing_files.py")
hypotheses_manager = st.Page("pages/03_Hypotheses_manager.py", icon="✔️") if st.session_state.all_hypotheses_accepted else st.Page("pages/03_Hypotheses_manager.py")
plan_manager = st.Page("pages/04_Plan_manager.py", icon="✔️") if st.session_state.all_plans_generated else st.Page("pages/04_Plan_manager.py")
plan_execution = st.Page("pages/05_Plan_execution.py", icon="✔️") if st.session_state.all_plans_executed else st.Page("pages/05_Plan_execution.py")
report_builder = st.Page("pages/06_Report_builder.py", icon="✔️") if st.session_state.report_generated else st.Page("pages/06_Report_builder.py")


selected_page = st.navigation({"Workflow": [upload, processing, hypotheses_manager, plan_manager, plan_execution, report_builder]}, position="sidebar")
selected_page.run()


print(f"Data and hypo: {bool(st.session_state.data_uploaded and st.session_state.hypotheses_uploaded)}")

# st.rerun()

