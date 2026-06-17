"""
app.py — TestForge: requirements doc -> test suite -> Playwright automation.
Run with:  streamlit run app.py
"""

import os
import json
import tempfile
import streamlit as st
from dotenv import load_dotenv

from agent import read_document, run_agent_on_document, generate_automation

load_dotenv()

st.set_page_config(page_title="TestForge", page_icon="🧪", layout="centered")

st.markdown(
    """
    <style>
      .stApp { background: #0f1419; }
      #MainMenu, footer, header { visibility: hidden; }
      .block-container { padding-top: 2.2rem; max-width: 860px; }
      .tf-title { font-family:'SF Mono','Menlo',monospace; font-size:1.9rem;
                  font-weight:700; color:#e6edf3; letter-spacing:-0.02em; margin:0 0 0.2rem; }
      .tf-accent { color:#3fb950; }
      .tf-sub { color:#8b949e; font-size:0.95rem; margin:0 0 1.6rem; }
      .stFileUploader, .stFileUploader * { color:#c9d1d9 !important; }
      [data-testid="stFileUploaderDropzone"] { background:#161b22 !important;
                 border:1px dashed #30363d !important; }
      [data-testid="stFileUploaderDropzone"] button { background:#21262d !important;
                 color:#e6edf3 !important; border:1px solid #30363d !important; }
      .stButton button { background:#238636; color:#fff; border:none;
                 border-radius:8px; padding:0.45rem 1.6rem; font-weight:600; }
      .stButton button:hover { background:#2ea043; color:#fff; }
      .req-head { font-family:'SF Mono','Menlo',monospace; font-size:0.95rem;
                  font-weight:700; color:#58a6ff; margin:1.6rem 0 0.3rem;
                  padding-bottom:0.4rem; border-bottom:1px solid #21262d; }
      .cat-head { font-family:'SF Mono','Menlo',monospace; font-size:0.72rem;
                  font-weight:700; color:#3fb950; letter-spacing:0.08em;
                  margin:0.9rem 0 0.4rem; text-transform:uppercase; }
      .tc-card { background:#161b22; border:1px solid #30363d;
                 border-left:3px solid #3fb950; border-radius:6px;
                 padding:0.8rem 1rem; margin:0.4rem 0; }
      .tc-id { font-family:'SF Mono','Menlo',monospace; font-size:0.72rem; color:#58a6ff; }
      .tc-title { color:#e6edf3; font-weight:600; font-size:0.92rem; margin:0.1rem 0 0.45rem; }
      .tc-step { color:#c9d1d9; font-size:0.86rem; margin:0.12rem 0; }
      .tc-exp { color:#8b949e; font-size:0.84rem; margin-top:0.45rem;
                border-top:1px solid #21262d; padding-top:0.45rem; }
      .tc-exp b { color:#3fb950; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown('<div class="tf-title">Test<span class="tf-accent">Forge</span></div>',
            unsafe_allow_html=True)
st.markdown(
    '<div class="tf-sub">Upload a business requirements document. An AI agent '
    'extracts each requirement, writes a full test suite, and can generate '
    'Playwright automation scaffolds for the happy-path tests.</div>',
    unsafe_allow_html=True,
)

# session state
if "suite" not in st.session_state:
    st.session_state.suite = None
if "automation" not in st.session_state:
    st.session_state.automation = None

uploaded = st.file_uploader("Requirements document", type=["pdf", "docx", "txt"],
                            label_visibility="collapsed")

# --- generate the test suite ---
if uploaded is not None and st.button("Generate test suite"):
    suffix = os.path.splitext(uploaded.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name
    text = read_document(tmp_path)
    os.unlink(tmp_path)

    status = st.empty()
    def show_progress(msg):
        status.markdown(f'<div style="color:#8b949e;font-size:0.86rem;">⚙️ {msg}</div>',
                        unsafe_allow_html=True)

    st.session_state.suite = run_agent_on_document(text, progress=show_progress)
    st.session_state.automation = None  # reset automation for new suite
    status.empty()

# --- display the suite (if we have one) ---
if st.session_state.suite is not None:
    suite = st.session_state.suite
    total = sum(len(v) for v in suite.values())
    st.markdown(
        f'<div style="color:#3fb950;font-size:0.9rem;margin:0.5rem 0;">'
        f'✓ {total} test cases across {len(suite)} requirements</div>',
        unsafe_allow_html=True,
    )

    for req_label, tests in suite.items():
        st.markdown(f'<div class="req-head">{req_label}</div>', unsafe_allow_html=True)
        by_cat = {}
        for t in tests:
            by_cat.setdefault(t.get("category", "other"), []).append(t)
        for category, cat_tests in by_cat.items():
            st.markdown(f'<div class="cat-head">{category.replace("_"," ")}</div>',
                        unsafe_allow_html=True)
            for t in cat_tests:
                steps_html = "".join(
                    f'<div class="tc-step">{i}. {s}</div>'
                    for i, s in enumerate(t["steps"], 1))
                st.markdown(
                    f'<div class="tc-card"><span class="tc-id">{t["id"]}</span>'
                    f'<div class="tc-title">{t["title"]}</div>{steps_html}'
                    f'<div class="tc-exp"><b>Expected:</b> {t["expected_result"]}</div></div>',
                    unsafe_allow_html=True)

    st.download_button("Download suite as JSON", data=json.dumps(suite, indent=2),
                       file_name="test_suite.json", mime="application/json")

    st.divider()

    # --- generate Playwright automation ---
    if st.button("⚡ Generate Playwright automation (happy-path)"):
        status2 = st.empty()
        def show_progress2(msg):
            status2.markdown(f'<div style="color:#8b949e;font-size:0.86rem;">⚙️ {msg}</div>',
                             unsafe_allow_html=True)
        st.session_state.automation = generate_automation(suite, progress=show_progress2)
        status2.empty()

# --- display automation (if generated) ---
if st.session_state.automation:
    st.markdown('<div class="req-head">Playwright automation (scaffolds)</div>',
                unsafe_allow_html=True)
    st.markdown('<div style="color:#8b949e;font-size:0.84rem;margin-bottom:0.6rem;">'
                'Selectors are placeholders marked with # TODO — wire them to your '
                'real app before running.</div>', unsafe_allow_html=True)

    all_code = ""
    for req_label, scripts in st.session_state.automation.items():
        for s in scripts:
            st.markdown(f'**{s["title"]}**')
            st.code(s["code"], language="python")
            all_code += s["code"] + "\n\n\n"

    st.download_button("Download all tests as .py", data=all_code,
                       file_name="test_automation.py", mime="text/x-python")