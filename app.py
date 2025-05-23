import streamlit as st

# 👇 MUST be the first Streamlit statement
st.set_page_config(
    page_title="Home",   # ← this becomes the sidebar label
    page_icon="🏠",
    layout="wide",
)

from utils import init_state, add_green_button_css
init_state(); add_green_button_css()

st.title("Welcome to the research assistant")
st.title("🌿 Ecological Research Assistant – Home")
st.markdown("""
Welcome! Use the sidebar to move through each stage:

1. **Upload** – load your dataset + raw hypotheses  
2. **Processing** – automatic dataset summary & first hypothesis draft  
3. **Hypothesis Manager** – chat & accept refined versions  
4. **Plan Manager** – create statistical plans for each hypothesis  
5. **Plan Execution** – run Python code & visualise results  
6. **Report Builder** – generate a full markdown report  
""")