STAGE_INFO = {
    "upload": "#### Stage I: Upload Files\n\n **Upload a CSV dataset and a TXT file containing your initial hypotheses.**\n\nOnce both are uploaded, the app automatically advances.\n\nFiles are held in `st.session_state`; the CSV preview is displayed with `st.dataframe()` so you can verify the data.",
    "processing":"### Stage II: Processing Files\n\n Great! You have your files uploaded.\n\nNow the app summarizes your dataset and rewrites each raw hypothesis into a clear, testable statement.\n\nYou’ll review them next.\n\nA GPT‑4o Data Summarizer assistant analyzes the CSV, then another GPT‑4o call refines the hypotheses using that summary; results are cached for later stages.",
    "hypotheses_manager": {
        "title": "3 · Hypotheses Manager",
        "description": (
            "Chat with the assistant to fine‑tune each hypothesis, then click "
            "Accept ✔️ to lock it in. All must be accepted before continuing."
        ),
        "how_it_works": (
            "Each hypothesis maintains its own chat history. Acceptance adds a "
            "final_hypothesis field, gating progression."
        ),
    },
    "plan_manager": {
        "title": "4 · Analysis Plan Manager",
        "description": (
            "For every accepted hypothesis, the assistant drafts a numbered "
            "analysis plan. Request revisions until it's perfect, then approve."
        ),
        "how_it_works": (
            "GPT-4o generates JSON-structured plans; the app validates the JSON "
            "before allowing approval."
        ),
    },
    "plan_execution": {
        "title": "5 · Plan Execution",
        "description": (
            "The assistant runs each approved plan in Python, streaming code, "
            "logs, and visuals live. You can pause, discuss, or rerun analyses."
        ),
        "how_it_works": (
            "A code-interpreter assistant streams run events. The app captures "
            "code inputs, outputs, and generated images, storing them for replay."
        ),
    },
    "report_generation": {
        "title": "6 · Scientific Report",
        "description": (
            "The assistant interprets results, searches recent ecological "
            "literature, and produces a full scientific report you can download."
        ),
        "how_it_works": (
            "The Report Generation assistant consolidates analysis outputs, "
            "performs web_search_preview calls for citations, writes an IMRaD "
            "report, and offers it as a Markdown download."
        ),
    },
}