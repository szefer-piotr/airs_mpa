import streamlit as st

from pathlib import Path
import base64
import re
from assistants import client
from instructions import report_generation_instructions
from openai import OpenAI

from utils import add_green_button_css
add_green_button_css()

# STAGE 4. REPORT GENERATION
def replace_image_paths_with_html(text: str, img_dir: Path = None, width: int = 600) -> str:
    """
    Find image paths in a string, read those images, convert them to base64 HTML, 
    and replace the paths in the string with HTML <img> tags.

    Parameters:
    - text: The input string potentially containing image paths.
    - img_dir: Optional base directory to resolve relative file names (used for file IDs).
    - width: Width of the embedded image in pixels.

    Returns:
    - Modified string with image paths replaced by embedded HTML <img> tags.
    """
    # Pattern to detect image paths (e.g., /some/path/image.png or just image_id if img_dir is given)
    pattern = re.compile(r'[\w./\\-]+(?:\.png|\.jpg|\.jpeg|\.gif)', re.IGNORECASE)

    def convert_match_to_html(match):
        path_str = match.group(0)
        try:
            # If img_dir is provided and path_str is not an absolute path, treat it as a file_id
            image_path = Path(path_str)
            if img_dir and not image_path.is_absolute():
                image_path = img_dir / path_str

            if not image_path.exists():
                return f"[Image not found: {image_path}]"

            data = image_path.read_bytes()
            b64 = base64.b64encode(data).decode()
            return (
                f'<p align="center"><img src="data:image/png;base64,{b64}" '
                f'width="{width}"></p>'
            )
        except Exception as e:
            return f"[Error loading image: {e}]"

    # Replace each image path with its base64 HTML equivalent
    return pattern.sub(convert_match_to_html, text)



tools = [{"type": "web_search_preview"}]

def build_report_prompt():
    report_prompt = []
    for idx, hyp in enumerate(st.session_state.updated_hypotheses['assistant_response']):
        report_prompt.append(hyp["title"])
        for msg in hyp['plan_execution_chat_history']:
            # print(f"\n\nThe message:\n\n {msg.keys()}")
            if "items" in msg:
                for item in msg["items"]:
                    # Exclude outputs!!!
                    if item["type"] == "image":
                        report_prompt.append(item["file_id"])
                        report_prompt.append(str(item["image_path"]))
                    else:
                        report_prompt.append(item["content"])
            elif "content" in msg:
                report_prompt.append(msg["content"])
    return " ".join(report_prompt)



st.title("📄 Report Builder")

# Sidebar – quick outline of accepted hypotheses
with st.sidebar:
    st.header("Refined Initial Hypotheses")
    for idx, hyp in enumerate(st.session_state.updated_hypotheses["assistant_response"], 1):
        st.markdown(f"**H{idx}.** {hyp['title']}")

# Button to trigger report generation
if "report_generated" not in st.session_state:
    st.session_state.report_generated = False
    st.session_state.report_markdown = ""

# if st.button("📝 Generate full report", disabled=st.session_state.report_generated):
if st.button("📝 Generate full report"):
    # Build a report that contains text, code, images and tables (Can I generate tables?)
    full_prompt = build_report_prompt()

    if "final_report" not in st.session_state:
            st.session_state["final_report"] = []

    with st.spinner("Synthesising report – this may take a minute …"):
        response = client.responses.create(
            model="gpt-4.1",
            instructions=report_generation_instructions,
            input=[{"role": "user", "content": full_prompt}],
            tools=tools
            )
        
        print(response.output_text)
        
        st.session_state["final_report"].append(response.output_text)
        st.session_state.report_generated = True

    st.rerun()

# Display the generated report
if st.session_state.report_generated:
    report_text_with_images = replace_image_paths_with_html(st.session_state.final_report[0])
    st.markdown(report_text_with_images, 
        unsafe_allow_html=True)

    # Offer download as Markdown
    st.download_button(
        "⬇️ Download report (Markdown)",
        st.session_state.final_report[0],
        file_name="scientific_report.md",
        mime="text/markdown",
    )

    # Optionally, add a next‑steps button to reset or exit

with st.sidebar:
    st.header("Actions")

    if st.button("Start new session"):
        st.session_state.clear()
        st.switch_page("pages/01_Upload.py")
        st.rerun()