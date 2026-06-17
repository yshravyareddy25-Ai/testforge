import os
import json
from dotenv import load_dotenv
from anthropic import Anthropic
from pypdf import PdfReader
from docx import Document as DocxDocument

load_dotenv()
client = Anthropic()


def extract_json(text):
    """LLMs often wrap JSON in markdown fences. Strip so json.loads works."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


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


def extract_requirements(document_text):
    """NEW Step 0: Agent reads the whole requirements document and extracts
    each distinct, testable requirement as a short statement."""
    system_prompt = (
        "You are a senior business analyst. Read the requirements document and "
        "extract each distinct, testable requirement as a short, clear "
        "statement. Group related rules into one requirement where sensible. "
        "Return a JSON array of objects, each with: 'id' (like REQ-1), 'title' "
        "(short name), and 'statement' (the testable requirement in one or two "
        "sentences). Respond with ONLY the JSON array, nothing else."
    )
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=2000,
        system=system_prompt,
        messages=[{"role": "user", "content": document_text}],
    )
    return json.loads(extract_json(message.content[0].text))


def plan_test_categories(requirement):
    """Step 1: Agent decides which test categories a requirement needs."""
    system_prompt = (
        "You are a senior QA engineer. Given a software requirement, decide "
        "which categories of test cases are needed. Choose from: happy_path, "
        "edge_cases, negative_tests, security, performance, usability. Only "
        "include categories that genuinely apply. Respond with ONLY a JSON "
        "list of category names, nothing else."
    )
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system=system_prompt,
        messages=[{"role": "user", "content": f"Requirement: {requirement}"}],
    )
    return json.loads(extract_json(message.content[0].text))


def generate_test_cases(requirement, category):
    """Step 2: Generate concrete test cases for ONE category."""
    system_prompt = (
        "You are a senior QA engineer writing test cases. Given a requirement "
        f"and the test category '{category}', write 2-3 specific test cases. "
        "Each must have: id, title, steps (a list of strings), and "
        "expected_result. Respond with ONLY a JSON list of objects, nothing else."
    )
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=900,
        system=system_prompt,
        messages=[{"role": "user", "content":
                   f"Requirement: {requirement}\nCategory: {category}"}],
    )
    return json.loads(extract_json(message.content[0].text))


def generate_tests_for_requirement(requirement_statement):
    """Plan + generate + flatten tests for a single requirement."""
    categories = plan_test_categories(requirement_statement)
    tests = []
    for category in categories:
        cases = generate_test_cases(requirement_statement, category)
        for c in cases:
            c["category"] = category
            tests.append(c)
    return tests


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
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=700,
        system=system_prompt,
        messages=[{"role": "user", "content": json.dumps(test_case)}],
    )
    code = message.content[0].text.strip()
    # strip markdown fences if the model added them anyway
    if code.startswith("```"):
        code = code.split("```")[1]
        if code.startswith("python"):
            code = code[6:]
    return code.strip()


def run_agent_on_document(document_text, progress=None):
    """Full agent: extract requirements from a document, then generate a
    test suite for each. Returns a dict: requirement -> list of tests."""
    def say(msg):
        if progress:
            progress(msg)

    say("Reading document and extracting requirements...")
    requirements = extract_requirements(document_text)

    suite = {}
    for req in requirements:
        label = f"{req['id']}: {req['title']}"
        say(f"Generating tests for {label}...")
        suite[label] = generate_tests_for_requirement(req["statement"])

    return suite


# also keep the single-requirement entry point
def run_agent(requirement, progress=None):
    def say(msg):
        if progress:
            progress(msg)
    say("Generating tests...")
    return {requirement: generate_tests_for_requirement(requirement)}


def generate_automation(suite, progress=None):
    """For each requirement, generate Playwright code for its happy_path tests.
    Returns a dict: requirement label -> list of {title, code}."""
    def say(msg):
        if progress:
            progress(msg)

    automation = {}
    for req_label, tests in suite.items():
        happy = [t for t in tests if t.get("category") == "happy_path"]
        if not happy:
            continue
        scripts = []
        for t in happy:
            say(f"Writing Playwright test: {t['title']}...")
            code = generate_playwright_code(t)
            scripts.append({"title": t["title"], "code": code})
        automation[req_label] = scripts
    return automation


if __name__ == "__main__":
    text = read_document("sample_requirements.txt")
    suite = run_agent_on_document(text, progress=print)
    print(json.dumps(suite, indent=2))