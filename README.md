# TestForge — AI Test Suite Generator

An agentic AI tool that turns a **business requirements document** into a
complete, structured **test suite** — and generates **Playwright automation
scaffolds** for the happy-path tests.

Built to combine LLM application engineering with QA domain expertise.

## What it does

1. **Upload** a requirements document (PDF, DOCX, or TXT)
2. An AI agent **extracts each distinct requirement** from the document
3. For every requirement, the agent **plans which test categories apply**
   (happy path, edge cases, negative, security, usability)
4. It **generates concrete test cases** for each category — with steps and
   expected results
5. It **reviews its own output** to remove duplicates across categories
6. Optionally, it **generates Python Playwright test scaffolds** for the
   happy-path tests
7. **Download** the suite as JSON and the automation as a `.py` file

## Why it's an "agent"

This isn't a single prompt. The LLM's decisions drive the program flow:
it decides which requirements exist, which test categories each one needs,
and then acts on those decisions across multiple steps — plan → generate →
self-review → assemble. This is multi-step reasoning with human-in-the-loop
output (the generated Playwright selectors are placeholders an engineer
wires to the real application).

## Tech stack

- **Claude** (Anthropic API) — the reasoning engine for every agent step
- **Streamlit** — web interface
- **pypdf / python-docx** — document reading
- **Playwright** (generated output) — browser test automation

## Running it locally

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Create a `.env` file with your Anthropic API key:
   ```
   ANTHROPIC_API_KEY=sk-ant-your-key-here
   ```
3. Run:
   ```bash
   streamlit run app.py
   ```
4. Upload `sample_requirements.txt` (included) and generate a test suite.

## Project structure

```
test-case-agent/
├── app.py                   # Streamlit web interface
├── agent.py                 # the agent: extract, plan, generate, review, automate
├── sample_requirements.txt  # a sample business requirements document
├── requirements.txt
└── README.md
```

## Note on the Playwright output

The generated Playwright code uses placeholder selectors marked with
`# TODO: update selector`. It produces correct test *structure* (steps,
assertions, flow) that an engineer wires to the real application's selectors
before running. It accelerates test authoring; it does not replace the
engineer's knowledge of the application under test.