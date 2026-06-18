"""
app.py — TestForge (multi-agent, user-driven)
Run with:  streamlit run app.py

Flow:
  1. Upload a requirements document
  2. Requirements Analyst extracts requirements
  3. Test Designer SUGGESTS test categories per requirement
  4. User toggles categories on/off  (human-in-the-loop)
  5. Generate ONLY what's selected  (token-efficient)
  6. Review Lead reviews + decides
  7. User picks which tests to turn into Playwright scaffolds
"""

import os
import json
import tempfile
import streamlit as st
from dotenv import load_dotenv

from agents import (
    read_document, requirements_analyst,
    run_selected_suite, generate_automation, ALL_CATEGORIES,
)

load_dotenv()
st.set_page_config(page_title="TestForge", page_icon="🧪", layout="centered")

st.markdown("""
<style>
  .stApp { background:#0e1116; }
  #MainMenu, footer, header { visibility:hidden; }
  .block-container { padding-top:2rem; max-width:880px; }
  .tf-title { font-family:'SF Mono','Menlo',monospace; font-size:1.9rem; font-weight:700;
              color:#e8edf4; letter-spacing:-.02em; margin:0 0 .2rem; }
  .tf-accent { color:#3fb950; }
  .tf-sub { color:#8b97a8; font-size:.95rem; margin:0 0 1.4rem; line-height:1.5; }
  [data-testid="stFileUploaderDropzone"] { background:#161b22 !important; border:1px dashed #30363d !important; }
  [data-testid="stFileUploaderDropzone"] * { color:#c9d1d9 !important; }
  .stButton button { background:#238636; color:#fff; border:none; border-radius:9px;
                     padding:.5rem 1.5rem; font-weight:600; }
  .stButton button:hover { background:#2ea043; color:#fff; }
  .req-head { font-family:'SF Mono',monospace; font-size:.95rem; font-weight:700; color:#58a6ff;
              margin:1.4rem 0 .3rem; padding-bottom:.35rem; border-bottom:1px solid #21262d; }
  .cat-head { font-family:'SF Mono',monospace; font-size:.7rem; font-weight:700; color:#3fb950;
              letter-spacing:.08em; margin:.8rem 0 .35rem; text-transform:uppercase; }
  .cat-head.security { color:#f78166; }
  .tc-card { background:#161b22; border:1px solid #30363d; border-left:3px solid #3fb950;
             border-radius:6px; padding:.75rem .95rem; margin:.35rem 0; }
  .tc-card.security { border-left-color:#f78166; }
  .tc-id { font-family:'SF Mono',monospace; font-size:.7rem; color:#58a6ff; }
  .tc-title { color:#e8edf4; font-weight:600; font-size:.9rem; margin:.1rem 0 .4rem; }
  .tc-step { color:#c9d1d9; font-size:.84rem; margin:.1rem 0; }
  .tc-exp { color:#8b97a8; font-size:.82rem; margin-top:.4rem; border-top:1px solid #21262d; padding-top:.4rem; }
  .tc-exp b { color:#3fb950; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="tf-title">Test<span class="tf-accent">Forge</span></div>', unsafe_allow_html=True)
st.markdown(
    '<div class="tf-sub">Four AI agents help you build a test suite. The Requirements '
    'Analyst reads your document, the Test Designer suggests test types, you choose what '
    'to generate, the Security Specialist adds security tests, and the Review Lead checks the result.</div>',
    unsafe_allow_html=True,
)

AGENTS = [
    ("RequirementsAnalyst", "Requirements Analyst", "#58a6ff", "Extracts requirements"),
    ("TestDesigner", "Test Designer", "#3fb950", "Suggests & writes tests"),
    ("SecuritySpecialist", "Security Specialist", "#f78166", "Adds security tests"),
    ("ReviewLead", "Review Lead", "#a371f7", "Reviews & decides"),
]

ss = st.session_state
ss.setdefault("agent_state", {a[0]: "idle" for a in AGENTS})
ss.setdefault("requirements", None)
ss.setdefault("suggestions", {})
ss.setdefault("result", None)
ss.setdefault("automation", None)

def render_team(placeholder):
    cols = placeholder.columns(4)
    for col, (key, name, color, desc) in zip(cols, AGENTS):
        state = ss.agent_state.get(key, "idle")
        dot = "#8b97a8" if state == "idle" else color
        ring = color if state == "working" else "#30363d"
        badge = "● working" if state == "working" else ("✓ done" if state == "done" else "idle")
        col.markdown(f"""
        <div style="background:#161b22;border:1px solid {ring};border-radius:12px;
                    padding:12px 10px;min-height:116px;transition:all .3s;">
          <div style="display:flex;align-items:center;gap:6px;margin-bottom:6px;">
            <span style="width:9px;height:9px;border-radius:50%;background:{dot};display:inline-block;"></span>
            <span style="font-family:'SF Mono',monospace;font-size:.7rem;font-weight:700;color:{color if state!='idle' else '#8b97a8'};">{name}</span>
          </div>
          <div style="font-size:.68rem;color:#8b97a8;line-height:1.35;">{desc}</div>
          <div style="font-size:.63rem;color:{color if state!='idle' else '#6e7681'};margin-top:8px;font-family:'SF Mono',monospace;">{badge}</div>
        </div>""", unsafe_allow_html=True)

team_box = st.empty()
render_team(team_box)
st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

uploaded = st.file_uploader("Requirements document", type=["pdf", "docx", "txt"], label_visibility="collapsed")

log_box = st.empty()
def make_emit():
    logs = []
    def emit(agent, state, detail):
        if agent in ss.agent_state:
            ss.agent_state[agent] = state
        render_team(team_box)
        logs.append(f"[{agent}] {detail}")
        log_box.markdown(
            "<div style='font-family:SF Mono,monospace;font-size:.74rem;color:#8b97a8;"
            "background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:10px 12px;'>"
            + "<br>".join(logs[-6:]) + "</div>", unsafe_allow_html=True)
    return emit

if uploaded is not None and st.button("Analyze document"):
    ss.agent_state = {a[0]: "idle" for a in AGENTS}
    ss.result = None
    ss.automation = None
    suffix = os.path.splitext(uploaded.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        tmp_path = tmp.name
    text = read_document(tmp_path)
    os.unlink(tmp_path)

    emit = make_emit()
    reqs = requirements_analyst(text, emit)
    ss.requirements = reqs

if ss.requirements and not ss.result:
    st.markdown('<div class="req-head">Choose what to generate</div>', unsafe_allow_html=True)

    # category explanations so the user can choose informedly
    CATEGORY_HELP = {
        "happy_path": "The main success path — the feature working as intended.",
        "edge_cases": "Boundary conditions — limits, empty values, exact thresholds.",
        "negative_tests": "Invalid input & misuse — things that should be rejected.",
        "usability": "Clarity & ease of use — labels, feedback, error messages.",
        "security": "Abuse & protection — auth, injection, rate limits, data exposure.",
    }
    cat_rows = "".join(
        f"<div style='margin:.15rem 0;'><span style='color:#3fb950;font-family:SF Mono,monospace;"
        f"font-size:.74rem;'>{c.replace('_',' ')}</span> "
        f"<span style='color:#8b97a8;font-size:.78rem;'>— {CATEGORY_HELP[c]}</span></div>"
        for c in ALL_CATEGORIES
    )
    st.markdown(
        "<div style='background:#0d1117;border:1px solid #21262d;border-radius:10px;"
        "padding:12px 14px;margin-bottom:.8rem;'>"
        "<div style='color:#c9d1d9;font-size:.8rem;font-weight:600;margin-bottom:.4rem;'>"
        "What each test category covers:</div>" + cat_rows + "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='color:#8b97a8;font-size:.82rem;margin-bottom:.4rem;'>"
                "Select the categories you want for each requirement, then generate. "
                "Only what you select is generated.</div>", unsafe_allow_html=True)

    for req in ss.requirements:
        label = f"{req['id']}: {req['title']}"
        st.markdown(f"<div style='color:#58a6ff;font-size:.85rem;font-family:SF Mono,monospace;"
                    f"margin:.7rem 0 .2rem;'>{label}</div>", unsafe_allow_html=True)
        cols = st.columns(len(ALL_CATEGORIES))
        for col, cat in zip(cols, ALL_CATEGORIES):
            col.checkbox(cat.replace("_", " "), value=False,
                         key=f"sel_{label}_{cat}")

    if st.button("Generate selected tests"):
        selections = {}
        for req in ss.requirements:
            label = f"{req['id']}: {req['title']}"
            chosen = [cat for cat in ALL_CATEGORIES if ss.get(f"sel_{label}_{cat}")]
            if chosen:
                selections[label] = chosen
        if not selections:
            st.warning("Select at least one category to generate.")
        else:
            ss.agent_state["TestDesigner"] = "idle"
            ss.agent_state["SecuritySpecialist"] = "idle"
            ss.agent_state["ReviewLead"] = "idle"
            emit = make_emit()
            ss.result = run_selected_suite(ss.requirements, selections, emit)

if ss.result:
    result = ss.result
    suite = result["suite"]
    total = sum(len(v) for v in suite.values())
    dcolor = "#3fb950" if result["decision"] == "approved" else "#f78166"
    st.markdown(
        f"<div style='margin:14px 0;padding:12px 14px;background:#161b22;border:1px solid {dcolor};"
        f"border-radius:10px;'><span style='font-family:SF Mono,monospace;font-size:.72rem;color:{dcolor};"
        f"font-weight:700;'>REVIEW LEAD: {result['decision'].upper()}</span>"
        f"<div style='color:#c9d1d9;font-size:.85rem;margin-top:4px;'>{result['note']} · {total} tests</div></div>",
        unsafe_allow_html=True)

    for req_label, tests in suite.items():
        if not tests:
            continue
        st.markdown(f'<div class="req-head">{req_label}</div>', unsafe_allow_html=True)
        by_cat = {}
        for t in tests:
            by_cat.setdefault(t.get("category", "other"), []).append(t)
        for category, cat_tests in by_cat.items():
            sec = "security" if category == "security" else ""
            st.markdown(f'<div class="cat-head {sec}">{category.replace("_"," ")}</div>', unsafe_allow_html=True)
            for t in cat_tests:
                steps = "".join(f'<div class="tc-step">{i}. {s}</div>' for i, s in enumerate(t.get("steps", []), 1))
                st.markdown(
                    f'<div class="tc-card {sec}"><span class="tc-id">{t.get("id","")}</span>'
                    f'<div class="tc-title">{t.get("title","")}</div>{steps}'
                    f'<div class="tc-exp"><b>Expected:</b> {t.get("expected_result","")}</div></div>',
                    unsafe_allow_html=True)

    st.download_button("Download suite as JSON", data=json.dumps(suite, indent=2),
                       file_name="test_suite.json", mime="application/json")

    st.divider()
    st.markdown('<div class="req-head">Choose tests to automate</div>', unsafe_allow_html=True)
    st.markdown("<div style='color:#8b97a8;font-size:.82rem;margin-bottom:.6rem;'>"
                "Tick the tests you want Playwright scaffolds for.</div>", unsafe_allow_html=True)
    chosen_auto = []
    for req_label, tests in suite.items():
        if not tests:
            continue
        st.markdown(f"<div style='color:#58a6ff;font-size:.8rem;font-family:SF Mono,monospace;"
                    f"margin:.5rem 0 .2rem;'>{req_label}</div>", unsafe_allow_html=True)
        for idx, t in enumerate(tests):
            if st.checkbox(f"[{t.get('category','')}] {t.get('title','')}", key=f"auto_{req_label}_{idx}"):
                chosen_auto.append(t)
    st.markdown(f"<div style='color:#8b97a8;font-size:.8rem;margin:.5rem 0;'>{len(chosen_auto)} selected</div>",
                unsafe_allow_html=True)
    if st.button("⚡ Generate Playwright automation for selected"):
        if not chosen_auto:
            st.warning("Select at least one test to automate.")
        else:
            alog = st.empty()
            def emit_a(agent, state, detail):
                alog.markdown(f"<div style='color:#8b97a8;font-size:.8rem;'>⚙️ {detail}</div>", unsafe_allow_html=True)
            ss.automation = generate_automation(chosen_auto, emit=emit_a)
            alog.empty()

if ss.automation:
    st.markdown('<div class="req-head">Playwright automation (scaffolds)</div>', unsafe_allow_html=True)
    st.markdown("<div style='color:#8b97a8;font-size:.82rem;margin-bottom:.5rem;'>"
                "Selectors are placeholders marked # TODO — wire them to your real app before running.</div>",
                unsafe_allow_html=True)
    all_code = ""
    for s in ss.automation:
        st.markdown(f"**{s['title']}**")
        st.code(s["code"], language="python")
        all_code += s["code"] + "\n\n\n"
    st.download_button("Download selected tests as .py", data=all_code,
                       file_name="test_automation.py", mime="text/x-python")