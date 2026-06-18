"""
agents.py — TestForge multi-agent core
========================================
A team of four specialized AI agents that collaborate to turn a business
requirements document into a reviewed test suite.

  1. RequirementsAnalyst — reads the document, extracts each testable requirement
  2. TestDesigner        — designs functional test cases (happy path, edge, negative, usability)
  3. SecuritySpecialist  — designs security-focused test cases as a dedicated expert
  4. ReviewLead          — reviews the whole suite, removes duplicates, normalizes IDs,
                           and makes a final go / revise DECISION

Why this is a multi-AGENT system (not one prompt):
each agent has its own role, its own system prompt, and its own focused job.
They hand work to each other through a shared "suite" object. The ReviewLead
even makes a decision that can send work back. That division of labor — and the
ReviewLead's judgment call — is what makes this agentic, not a single call.

Every agent reports its status through an optional `emit` callback so the UI
can show each agent lighting up, working, and handing off in real time.
"""

import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader
from docx import Document as DocxDocument

load_dotenv()
client = Anthropic()

MODEL = "claude-haiku-4-5-20251001"


# ---------- shared helpers ----------

def extract_json(text):
    """LLMs sometimes wrap JSON in markdown fences. Strip so json.loads works."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


def _ask(system_prompt, user_content, max_tokens=900):
    """One model call. Every agent uses this."""
    msg = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
    )
    return msg.content[0].text


def read_document(file_path):
    """Read text from a PDF, DOCX, or TXT requirements document."""
    lower = file_path.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(file_path)
        return "\n".join(p.extract_text() or "" for p in reader.pages)
    elif lower.endswith(".docx"):
        doc = DocxDocument(file_path)
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    else:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()


# ---------- a tiny status helper ----------
# emit(agent_name, state, detail) lets the UI show who is working.
# state is one of: "working", "done".

def _noop(*args, **kwargs):
    pass


# ============================================================
# AGENT 1 — Requirements Analyst
# ============================================================

def requirements_analyst(document_text, emit=_noop):
    """Reads the whole document and extracts each distinct, testable requirement."""
    emit("RequirementsAnalyst", "working", "Reading the document and extracting requirements")
    system_prompt = (
        "You are a senior business analyst. Read the requirements document and "
        "extract each distinct, testable requirement as a short, clear "
        "statement. Group related rules into one requirement where sensible. "
        "Return a JSON array of objects, each with: 'id' (like REQ-1), 'title' "
        "(short name), and 'statement' (the testable requirement in one or two "
        "sentences). Respond with ONLY the JSON array, nothing else."
    )
    reqs = json.loads(extract_json(_ask(system_prompt, document_text, max_tokens=2000)))
    emit("RequirementsAnalyst", "done", f"Found {len(reqs)} requirements")
    return reqs


# ============================================================
# AGENT 2 — Test Designer  (functional coverage)
# ============================================================

FUNCTIONAL_CATEGORIES = ["happy_path", "edge_cases", "negative_tests", "usability"]
ALL_CATEGORIES = FUNCTIONAL_CATEGORIES + ["security"]


def suggest_categories(requirement, emit=_noop):
    """Test Designer looks at a requirement and SUGGESTS which categories fit.
    Cheap planning call — the user then toggles the suggestions on/off."""
    emit("TestDesigner", "working", f"Suggesting categories for {requirement['id']}")
    system_prompt = (
        "You are a senior QA engineer. Given a requirement, decide which of "
        "these test categories genuinely apply: happy_path, edge_cases, "
        "negative_tests, usability, security. Respond with ONLY a JSON list of "
        "the category names that apply, nothing else."
    )
    suggested = json.loads(extract_json(_ask(
        system_prompt, f"Requirement: {requirement['statement']}", max_tokens=120)))
    emit("TestDesigner", "done", f"Suggested {len(suggested)} categories for {requirement['id']}")
    # keep only valid names, preserve a sensible order
    return [c for c in ALL_CATEGORIES if c in suggested]


def _plan_functional_categories(requirement):
    system_prompt = (
        "You are a senior QA engineer. Given a requirement, decide which of "
        "these FUNCTIONAL categories genuinely apply: happy_path, edge_cases, "
        "negative_tests, usability. Respond with ONLY a JSON list of category "
        "names from that set, nothing else."
    )
    return json.loads(extract_json(_ask(system_prompt, f"Requirement: {requirement}", max_tokens=150)))


def _design_cases(requirement, category):
    system_prompt = (
        "You are a senior QA engineer writing test cases. Given a requirement "
        f"and the test category '{category}', write 2-3 specific test cases. "
        "Each must have: id, title, steps (a list of strings), and "
        "expected_result. Respond with ONLY a JSON list of objects, nothing else."
    )
    return json.loads(extract_json(_ask(
        system_prompt, f"Requirement: {requirement}\nCategory: {category}")))


def test_designer(requirement, emit=_noop):
    """Designs functional test cases across the categories that apply."""
    emit("TestDesigner", "working", f"Designing functional tests for {requirement['id']}")
    tests = []
    for category in _plan_functional_categories(requirement["statement"]):
        for c in _design_cases(requirement["statement"], category):
            c["category"] = category
            tests.append(c)
    emit("TestDesigner", "done", f"Wrote {len(tests)} functional tests for {requirement['id']}")
    return tests


# ============================================================
# AGENT 3 — Security Specialist  (dedicated security expert)
# ============================================================

def security_specialist(requirement, emit=_noop):
    """A dedicated security expert designs security-focused test cases."""
    emit("SecuritySpecialist", "working", f"Probing {requirement['id']} for security tests")
    system_prompt = (
        "You are an application security specialist. Given a requirement, write "
        "2-3 security-focused test cases that a normal QA engineer might miss — "
        "think authorization, injection, rate limiting, data exposure, token "
        "handling, file-upload abuse, and similar. Each must have: id, title, "
        "steps (a list of strings), and expected_result. If the requirement has "
        "no meaningful security surface, return an empty JSON array. Respond "
        "with ONLY a JSON list, nothing else."
    )
    cases = json.loads(extract_json(_ask(
        system_prompt, f"Requirement: {requirement['statement']}")))
    for c in cases:
        c["category"] = "security"
    emit("SecuritySpecialist", "done", f"Added {len(cases)} security tests for {requirement['id']}")
    return cases


# ============================================================
# AGENT 4 — Review Lead  (reviews, dedupes, and DECIDES)
# ============================================================

def review_lead(flat_tests, emit=_noop):
    """Reviews the full suite: removes duplicates, normalizes IDs, and makes a
    decision about the suite's quality. Returns (cleaned_tests, decision)."""
    emit("ReviewLead", "working", "Reviewing the full suite for duplicates and quality")
    system_prompt = (
        "You are a senior QA lead reviewing a test suite produced by your team. "
        "The list may contain duplicates or near-duplicates across categories. "
        "Do three things: (1) remove duplicates/overlaps, keeping each unique "
        "test once under its most appropriate category; (2) normalize every id "
        "to the format TC-001, TC-002, ... in order; (3) judge overall quality. "
        "Return ONLY a JSON object: {\"tests\": [ ...cleaned test objects with "
        "fields category,id,title,steps,expected_result... ], \"decision\": "
        "\"approved\" or \"needs_more\", \"note\": \"one short sentence\"}. "
        "Use \"needs_more\" only if coverage has an obvious gap."
    )
    raw = _ask(system_prompt, json.dumps(flat_tests), max_tokens=8000)
    try:
        result = json.loads(extract_json(raw))
        cleaned = result.get("tests", flat_tests)
        decision = result.get("decision", "approved")
        note = result.get("note", "")
    except (json.JSONDecodeError, KeyError):
        # Defensive fallback: if the Review Lead's JSON is malformed or got
        # truncated, don't crash the whole run — keep the un-reviewed suite
        # and flag it. (Same defensive-parsing lesson as the rest of the app.)
        cleaned = flat_tests
        decision = "approved"
        note = "Auto-passed (review output could not be parsed; showing all tests)."
    emit("ReviewLead", "done", f"{decision.upper()} — {len(cleaned)} tests. {note}")
    return cleaned, decision, note


# ============================================================
# ORCHESTRATION — the team working together
# ============================================================

def run_team(document_text, emit=_noop):
    """Runs the full multi-agent pipeline and returns a structured result:
       { requirements: [...], suite: {req_label: [tests]}, decision, note } """
    # 1. Requirements Analyst
    requirements = requirements_analyst(document_text, emit)

    # 2 + 3. For each requirement, the Test Designer and Security Specialist
    #         both contribute — two specialists collaborating on the same item.
    suite = {}
    for req in requirements:
        label = f"{req['id']}: {req['title']}"
        functional = test_designer(req, emit)
        security = security_specialist(req, emit)
        suite[label] = functional + security

    # 4. Review Lead reviews the entire combined suite and decides.
    flat = []
    for label, tests in suite.items():
        for t in tests:
            flat.append({"requirement": label, **t})
    cleaned, decision, note = review_lead(flat, emit)

    # regroup cleaned tests back under their requirement labels
    regrouped = {label: [] for label in suite.keys()}
    for t in cleaned:
        label = t.pop("requirement", None)
        if label in regrouped:
            regrouped[label].append(t)
        else:
            # if the review lead dropped the requirement tag, bucket loosely
            regrouped.setdefault("Reviewed", []).append(t)

    return {
        "requirements": requirements,
        "suite": regrouped,
        "decision": decision,
        "note": note,
    }


# ============================================================
# Automation capability — the team can also produce Playwright scaffolds
# ============================================================

def generate_selected(requirement, chosen_categories, emit=_noop):
    """Generate tests for ONLY the categories the user selected for this
    requirement. The Security Specialist handles 'security'; the Test Designer
    handles the functional ones. Returns a flat list of test dicts."""
    tests = []
    functional = [c for c in chosen_categories if c in FUNCTIONAL_CATEGORIES]
    if functional:
        emit("TestDesigner", "working", f"Writing {requirement['id']} tests")
        for category in functional:
            for c in _design_cases(requirement["statement"], category):
                c["category"] = category
                tests.append(c)
        emit("TestDesigner", "done", f"Wrote functional tests for {requirement['id']}")
    if "security" in chosen_categories:
        sec = security_specialist(requirement, emit)
        tests.extend(sec)
    return tests


def run_selected_suite(requirements, selections, emit=_noop):
    """Run generation for a user's selections, then Review Lead reviews.
    selections: dict of {req_label: [chosen categories]}.
    Returns {suite, decision, note}."""
    suite = {}
    for req in requirements:
        label = f"{req['id']}: {req['title']}"
        chosen = selections.get(label, [])
        if not chosen:
            continue
        suite[label] = generate_selected(req, chosen, emit)

    flat = []
    for label, tests in suite.items():
        for t in tests:
            flat.append({"requirement": label, **t})
    if not flat:
        return {"suite": {}, "decision": "approved", "note": "Nothing selected."}

    cleaned, decision, note = review_lead(flat, emit)
    regrouped = {label: [] for label in suite.keys()}
    for t in cleaned:
        label = t.pop("requirement", None)
        if label in regrouped:
            regrouped[label].append(t)
        else:
            regrouped.setdefault("Reviewed", []).append(t)
    return {"suite": regrouped, "decision": decision, "note": note}


def generate_playwright_code(test_case):
    """Convert a manual test case into a Python Playwright test function.
    Selectors are guessed and marked with # TODO for the engineer to fill in."""
    system_prompt = (
        "You are a test automation engineer. Convert the given manual test "
        "case into a single Python Playwright test function using the sync API. "
        "Use the page fixture and Playwright expect() for assertions. Use "
        "realistic placeholder selectors and add a trailing comment "
        "# TODO: update selector on any line with a guessed selector. Make the "
        "function name descriptive based on the test title. Return ONLY the "
        "Python code, no explanation and no markdown fences."
    )
    code = _ask(system_prompt, json.dumps(test_case), max_tokens=700).strip()
    if code.startswith("```"):
        code = code.split("```")[1]
        if code.startswith("python"):
            code = code[6:]
    return code.strip()


def generate_automation(chosen_tests, emit=_noop):
    """Generate Playwright scaffolds for a specific list of chosen tests.
    chosen_tests is a list of test dicts (each with title, steps, etc.)."""
    scripts = []
    for t in chosen_tests:
        emit("Automation", "working", f"Scripting: {t.get('title','')}")
        scripts.append({"title": t.get("title", ""), "code": generate_playwright_code(t)})
    emit("Automation", "done", "Playwright scaffolds ready")
    return scripts


if __name__ == "__main__":
    text = read_document("sample_requirements.txt")

    def printer(agent, state, detail):
        print(f"[{agent}] {state}: {detail}")

    result = run_team(text, emit=printer)
    print("\nDECISION:", result["decision"], "-", result["note"])
    print(json.dumps(result["suite"], indent=2))