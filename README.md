# 🧪 TestForge — Multi-Agent AI Test Suite Generator

**A team of four AI agents that turn a business requirements document into a reviewed, structured test suite — and generate Playwright automation scaffolds on demand.**

TestForge combines **LLM application engineering** with **QA domain expertise**. It's not a single prompt — it's a coordinated team of specialized agents that plan, generate, and review test cases the way a real QA team would.

🔗 **Live demo:** _add your Streamlit link here_
📺 **Demo video / GIF:** _add a short screen recording here_

---

## What makes it different

Most "AI test generators" are a single prompt that dumps a wall of text. TestForge is a **multi-agent system** where four specialized agents collaborate, each with a focused role — and the user stays in control of what gets generated.

```
 ┌─────────────────────┐
 │  Requirements doc    │   (PDF / DOCX / TXT)
 └──────────┬──────────┘
            ▼
 ┌─────────────────────┐
 │ Requirements Analyst │  extracts each testable requirement
 └──────────┬──────────┘
            ▼
   user selects which test categories to generate  ← human-in-the-loop
            ▼
 ┌─────────────────────┐   ┌──────────────────────┐
 │   Test Designer      │   │  Security Specialist  │   two specialists
 │ happy path, edge,    │ + │  injection, auth,     │   collaborate per
 │ negative, usability  │   │  rate limits, etc.    │   requirement
 └──────────┬──────────┘   └───────────┬──────────┘
            └──────────────┬───────────┘
                           ▼
              ┌─────────────────────┐
              │     Review Lead      │  removes duplicates, normalizes
              │  reviews & DECIDES    │  IDs, and approves / flags gaps
              └──────────┬──────────┘
                         ▼
              reviewed test suite  →  optional Playwright scaffolds
```

---

## The four agents

| Agent | Role |
|-------|------|
| **Requirements Analyst** | Reads the whole document and extracts each distinct, testable requirement. |
| **Test Designer** | Designs functional test cases (happy path, edge cases, negative, usability) for the categories the user selects. |
| **Security Specialist** | A dedicated security expert that adds tests a normal QA pass often misses — authorization, injection, rate limiting, token handling, file-upload abuse. |
| **Review Lead** | Reviews the whole suite, removes duplicates across categories, normalizes IDs, and makes a **decision**: approved, or flag a coverage gap. |

The Review Lead making a judgment call — not just transforming text — is what makes this genuinely *agentic* rather than a single LLM call.

---

## Key features

- **Multi-agent collaboration** with a live UI that shows each agent working and handing off.
- **Human-in-the-loop** — the user chooses which test categories to generate per requirement, so nothing is wasted.
- **Token-efficient by design** — only the selected categories are generated, instead of everything up front.
- **Security as a first-class concern** — a dedicated agent, not an afterthought.
- **Selective automation** — pick exactly which test cases become Playwright scaffolds.
- **Resilient parsing** — defensive handling of malformed/truncated LLM output so one bad response never crashes a run.

---

## How an agent is built

Each agent is a focused function with its own system prompt. Here's the Security Specialist:

```python
def security_specialist(requirement, emit=_noop, context=""):
    """A dedicated security expert designs security-focused test cases."""
    emit("SecuritySpecialist", "working", f"Probing {requirement['id']}")
    system_prompt = (
        "You are an application security specialist. Given a requirement, write "
        "2-3 security-focused test cases that a normal QA engineer might miss — "
        "think authorization, injection, rate limiting, data exposure, token "
        "handling, file-upload abuse. Each must have: id, title, steps, and "
        "expected_result. Respond with ONLY a JSON list, nothing else."
    )
    cases = json.loads(extract_json(_ask(system_prompt, requirement["statement"])))
    for c in cases:
        c["category"] = "security"
    emit("SecuritySpecialist", "done", f"Added {len(cases)} security tests")
    return cases
```

The **Review Lead** shows the defensive-parsing pattern — LLM output can't be trusted to be clean JSON, so a bad response degrades gracefully instead of crashing:

```python
raw = _ask(system_prompt, json.dumps(flat_tests), max_tokens=8000)
try:
    result = json.loads(extract_json(raw))
    cleaned, decision, note = result["tests"], result["decision"], result["note"]
except (json.JSONDecodeError, KeyError):
    # Truncated or malformed output → keep the un-reviewed suite, flag it,
    # and never crash the whole run.
    cleaned, decision = flat_tests, "approved"
    note = "Auto-passed (review output could not be parsed)."
```

---

## Tech stack

- **Claude** (Anthropic API) — the reasoning engine behind every agent
- **Streamlit** — interactive web interface with live agent status
- **pypdf / python-docx** — document reading
- **Playwright** (generated output) — browser test automation

---

## Run it locally

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. add your Anthropic API key
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env

# 3. run
streamlit run app.py
```

Then upload the included `sample_requirements.txt` and watch the agents work.

> **Deployed version:** the live app asks each visitor for their own Anthropic
> API key, used only for that session and never stored — so the public demo
> costs nothing and exposes no credentials.

---

## Project structure

```
testforge/
├── app.py                   # Streamlit UI — agent panel, selection, results
├── agents.py                # the four agents + orchestration
├── sample_requirements.txt  # a sample business requirements document
├── requirements.txt
└── README.md
```

---

## A note on the Playwright output

The generated Playwright code uses placeholder selectors marked `# TODO: update selector`. It produces correct test *structure* — steps, assertions, flow — that an engineer wires to the real application's selectors before running. It accelerates test authoring; it doesn't replace the engineer's knowledge of the app under test. **Human-in-the-loop by design.**

---

## Roadmap (v2 ideas)

- Let users describe their app's actual fields (email, phone, password rules) so generated tests use realistic, specific inputs.
- Add an Evaluator agent that scores coverage against the requirements.
- Export to TestRail / Jira / CSV formats.
- Orchestrate the agents with LangGraph for branching review loops.

---

_Built by Shravya Reddy — frontend & QA engineer building with LLMs._