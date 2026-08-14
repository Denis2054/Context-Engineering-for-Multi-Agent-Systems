"""Regression ledger for the LangChain Edition.

WHY THIS FILE EXISTS
--------------------
This package was hardened over several rounds. Each round fixed real defects,
and one round INTRODUCED one: rewriting the planner's instruction 4 to add a
BLUEPRINT FIRST rule deleted the canonical "retrieves a blueprint, researches
the facts, then writes" sentence, which removed the Researcher from the default
plan shape. The result was a fluent, on-brand, entirely unsourced deliverable —
a worse failure than the one the edit was meant to fix.

verify_engine.py tests that behaviour is CORRECT. This file tests that behaviour
that was ALREADY correct has not been undone. Every entry below corresponds to a
specific fix made at some point in this project's history. Nothing is ever
removed from this ledger; entries are only added.

Run all three before shipping:
    python verify_regressions.py && python verify_engine.py && python verify_notebook.py
"""

import ast
import json
import os
import re
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)))
if not os.path.exists(os.path.join(SRC, "lc_engine.py")):
    SRC = "/home/claude/langchain"
sys.path.insert(0, SRC)

FAILURES = []
SECTION = {"name": ""}


def section(name):
    SECTION["name"] = name
    print(f"\n{name}")


def ledger(item, condition, detail=""):
    """One historical commitment. `item` names the fix it protects."""
    print(f"  [{'HELD' if condition else 'LOST'}] {item}"
          + (f" — {detail}" if detail and not condition else ""))
    if not condition:
        FAILURES.append(f"{SECTION['name']} :: {item}")


SOURCE = {}
for name in ("lc_utils", "lc_helpers", "lc_agents", "lc_registry",
             "lc_engine", "lc_dashboard", "lc_boot"):
    SOURCE[name] = open(os.path.join(SRC, f"{name}.py"), encoding="utf-8").read()
ALL = "\n".join(SOURCE.values())

README = open(os.path.join(SRC, "README.md"), encoding="utf-8").read()
NB = json.load(open(os.path.join(SRC, "Universal_Context_Engine_LangChain.ipynb"),
                    encoding="utf-8"))
NB_TEXT = "\n".join(
    c["source"] if isinstance(c["source"], str) else "".join(c["source"])
    for c in NB["cells"])

import lc_agents          # noqa: E402
import lc_engine          # noqa: E402
import lc_helpers         # noqa: E402
import lc_registry        # noqa: E402
import lc_utils           # noqa: E402

PROMPT = str(lc_engine.PLANNER_PROMPT.messages[0].prompt.template)


# =============================================================================
section("R1. Branding and framing (established round 1)")
# =============================================================================
ledger("no '100% LangChain' claim survives anywhere",
       "100% LangChain" not in ALL + README + NB_TEXT)
ledger("no 'hybrid' framing survives anywhere",
       "hybrid" not in (ALL + README + NB_TEXT).lower())
ledger("every module still carries the Edition header",
       all("LangChain Edition" in s for s in SOURCE.values()))
ledger("layer/substrate framing present in README and notebook",
       "context engine layer on a langchain substrate" in README.lower()
       and "context engine layer on a langchain substrate" in NB_TEXT.lower())
ledger("Colab badge still points at the book repo, not the scratch repo",
       "Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/langchain/"
       in NB_TEXT and "Denis2054/SFT" not in NB_TEXT)
ledger("no placeholder URLs reintroduced",
       not any(p in NB_TEXT + README
               for p in ("YOUR_USERNAME", "YOUR_REPO", "FILENAME.ipynb")))


# =============================================================================
section("R2. Notebook integrity (established round 1)")
# =============================================================================
written = {}
for cell in NB["cells"]:
    if cell["cell_type"] != "code":
        continue
    src = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
    m = re.match(r"%%writefile\s+(\S+)\n", src)
    if m:
        written[m.group(1)] = src[m.end():]

ledger("all seven modules still written by the notebook", len(written) == 7,
       sorted(written))
ledger("byte identity notebook <-> modules still holds",
       all(written.get(f"{n}.py") == SOURCE[n] for n in SOURCE),
       [n for n in SOURCE if written.get(f"{n}.py") != SOURCE[n]])
ledger("notebook remains standalone (no downloads)",
       not re.search(r"!(wget|curl)\b", NB_TEXT)
       and "downloaded the seven engine modules" not in NB_TEXT)
ledger("no stored outputs shipped",
       all(not c.get("outputs") for c in NB["cells"] if c["cell_type"] == "code"))
def _cell_parses(cell):
    src = cell["source"] if isinstance(cell["source"], str) else "".join(cell["source"])
    body = re.sub(r"^%%writefile\s+\S+\n", "", src)
    body = re.sub(r"^\s*#@title.*$", "", body, flags=re.M)
    try:
        ast.parse(body)
        return True
    except SyntaxError:
        return False


ledger("every code cell still parses",
       all(_cell_parses(c) for c in NB["cells"] if c["cell_type"] == "code"))


# =============================================================================
section("R3. Robustness fixes (established round 1)")
# =============================================================================
ledger("moderation client resolves through three tiers",
       "root_client" in SOURCE["lc_helpers"]
       and "from openai import OpenAI" in SOURCE["lc_helpers"])
ledger("moderate() still distinguishes flagged from unavailable",
       '"available"' in SOURCE["lc_helpers"]
       and "Halted: moderation unavailable" in SOURCE["lc_boot"])
ledger("openai remains a declared dependency",
       any(p.startswith("openai") for p in lc_utils.PACKAGES))
ledger("UsageTracker.reset() still exists and is used",
       hasattr(lc_helpers.UsageTracker, "reset")
       and "self.tracker.reset()" in SOURCE["lc_boot"])
ledger("failed steps are still recorded on the trace",
       '"status": "error"' in SOURCE["lc_engine"])
ledger("a trace is still returned when a goal is blocked",
       "return None, trace" in SOURCE["lc_boot"])
ledger("executor still filters arguments to the tool schema",
       "toolkit.arg_names(name)" in SOURCE["lc_engine"])
ledger("AGENT_NAMES / Literal mismatch still raises at assembly",
       "Add the new agent to AGENT_NAMES" in SOURCE["lc_engine"])
ledger("unknown config keys still raise",
       "Unknown configuration key" in SOURCE["lc_boot"])
ledger("empty page_content still logs the text_key cause",
       "text_key is wrong" in SOURCE["lc_agents"])
ledger("plan_only still caches its planner",
       "self._planner is None" in SOURCE["lc_boot"])
ledger("requirements.txt still matches PACKAGES",
       sorted(l.strip() for l in open(os.path.join(SRC, "requirements.txt"))
              if l.strip() and not l.startswith("#")) == sorted(lc_utils.PACKAGES))


# =============================================================================
section("R4. Context chaining and trace (established round 1)")
# =============================================================================
state = {"STEP_1_OUTPUT": {"a": 1}, "STEP_2_OUTPUT": "facts"}
ledger("whole-string reference still preserves type",
       lc_engine.resolve_dependencies({"x": "$$STEP_1_OUTPUT$$"}, state)["x"] == {"a": 1})
ledger("embedded reference still interpolates",
       lc_engine.resolve_dependencies({"x": "see $$STEP_2_OUTPUT$$"}, state)["x"]
       == "see facts")
ledger("unresolved reference is still left intact",
       lc_engine.resolve_dependencies({"x": "$$STEP_9_OUTPUT$$"}, state)["x"]
       == "$$STEP_9_OUTPUT$$")
ledger("trace field names unchanged",
       all(hasattr(lc_engine.LangChainTrace("g"), f) for f in
           ("goal", "plan", "steps", "status", "final_output", "duration",
            "usage", "moderation", "plan_warnings")))


# =============================================================================
section("R5. Guardrails (established rounds 1-2)")
# =============================================================================
ledger("sanitizer patterns unchanged from the original engine",
       lc_helpers.INJECTION_PATTERNS == [
           r"ignore previous instructions", r"ignore all prior commands",
           r"you are now in.*mode", r"act as", r"ignore any legal advice",
           r"print your instructions", r"sudo|apt-get|yum|pip install"])
ledger("SanitizationError is still a ValueError subclass",
       issubclass(lc_helpers.SanitizationError, ValueError))
ledger("sanitization is still PER CHUNK inside the Researcher",
       "for doc in docs" in SOURCE["lc_agents"] and "continue" in SOURCE["lc_agents"])
ledger("rejected chunks still name the source document",
       "REJECTED chunk from" in SOURCE["lc_agents"])
ledger("LangSmith key is still validated before tracing is enabled",
       "_validate_langsmith" in SOURCE["lc_utils"])
ledger("legacy LANGCHAIN_TRACING_V2 is still cleared",
       "LANGCHAIN_TRACING_V2" in SOURCE["lc_utils"])
ledger("disable_langsmith() is still public",
       callable(getattr(lc_utils, "disable_langsmith", None)))


# =============================================================================
section("R6. Retrieval fidelity (established round 1)")
# =============================================================================
cfg = lc_helpers.CONFIG
ledger("blueprint namespace/text_key unchanged",
       (cfg["namespace_context"], cfg["text_key_context"])
       == ("ContextLibrary", "blueprint_json"))
ledger("knowledge namespace/text_key unchanged",
       (cfg["namespace_knowledge"], cfg["text_key_knowledge"])
       == ("KnowledgeStore", "text"))
ledger("retrieval depths still match the original top_k",
       (cfg["k_blueprint"], cfg["k_knowledge"]) == (1, 3))
ledger("embedding model unchanged",
       cfg["embedding_model"] == "text-embedding-3-small")
ledger("no temperature is actually passed to the model",
       not re.search(r"^\s*temperature\s*=", SOURCE["lc_helpers"], re.M))
def _code_only(src):
    """Source with comments and string literals removed, so prose that mentions
    a dangerous call is not mistaken for the call itself."""
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            node.value = ""
    return ast.unparse(tree)


ledger("stores are still read-only (no ingestion call)",
       ".from_documents(" not in _code_only(SOURCE["lc_helpers"]))
ledger("prompts still carry the original wording",
       "expert research synthesis AI" in SOURCE["lc_agents"]
       and "expert summarization AI" in SOURCE["lc_agents"]
       and "expert content generation AI" in SOURCE["lc_agents"])


# =============================================================================
section("R7. Planner prompt coverage — the regression that actually happened")
# =============================================================================
# An edit to one instruction silently dropped the Researcher from the canonical
# plan shape. These assertions make the prompt's coverage of every architectural
# role explicit, so the next edit cannot quietly delete one of them.
for agent in lc_engine.AGENT_NAMES:
    ledger(f"planner prompt still names the {agent}", agent in PROMPT)

ledger("canonical flow sentence still present (REGRESSION GUARD)",
       "CANONICAL FLOW" in PROMPT and "researches the facts" in PROMPT,
       "the Researcher's place in the default plan shape was deleted once before")
ledger("blueprint-first rule present", "BLUEPRINT FIRST" in PROMPT)
ledger("grounding rule present", "GROUND EVERYTHING" in PROMPT)
ledger("grounding rule requires a Researcher before every Writer",
       "needs a Researcher step before it" in PROMPT)
ledger("retrieve-only exemption present", "does not need the Librarian" in PROMPT)
ledger("summarizer guidance present", "Summarizer step" in PROMPT)
ledger("instructions are numbered contiguously",
       [int(n) for n in re.findall(r'"(\d+)\. ', PROMPT)]
       == list(range(1, len(re.findall(r'"(\d+)\. ', PROMPT)) + 1)),
       re.findall(r'"(\d+)\. ', PROMPT))

from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable


class _StubLLM(Runnable):
    def invoke(self, input, config=None, **kwargs):
        return AIMessage(content="stub")


class _StubRetriever(Runnable):
    def invoke(self, input, config=None, **kwargs):
        return []


kit = lc_registry.build_toolkit(lc_agents.build_agents(
    _StubLLM(), _StubRetriever(), _StubRetriever(), lc_helpers.sanitize))
ledger("Librarian docstring still states it must be called FIRST",
       "FIRST" in kit.get("Librarian").description)
ledger("Writer docstring still requires a preceding Librarian",
       "preceding Librarian step" in kit.get("Writer").description)


# =============================================================================
section("R8. Golden plan shapes — behaviour that must never regress")
# =============================================================================
# Each entry is a plan shape that was correct at some point in this project.
# validate_plan must agree, forever. Deterministic: no model call.
GOLDEN = [
    # (label, goal, plan, expect_compliant)
    ("canonical styled flow", "Write a persuasive pitch on our brand guide", [
        {"step": 1, "agent": "Librarian", "input": {"intent_query": "persuasive pitch"}},
        {"step": 2, "agent": "Researcher", "input": {"topic_query": "brand guide"}},
        {"step": 3, "agent": "Writer", "input": {"blueprint": "$$STEP_1_OUTPUT$$",
                                                 "facts": "$$STEP_2_OUTPUT$$"}},
    ], True),
    ("canonical flow with summarizer", "Draft a formal client summary", [
        {"step": 1, "agent": "Librarian", "input": {"intent_query": "formal summary"}},
        {"step": 2, "agent": "Researcher", "input": {"topic_query": "service agreement"}},
        {"step": 3, "agent": "Summarizer", "input": {"text_to_summarize": "$$STEP_2_OUTPUT$$",
                                                     "summary_objective": "key terms"}},
        {"step": 4, "agent": "Writer", "input": {"blueprint": "$$STEP_1_OUTPUT$$",
                                                 "facts": "$$STEP_3_OUTPUT$$"}},
    ], True),
    ("retrieval-only goal", "What is the termination notice period?", [
        {"step": 1, "agent": "Researcher", "input": {"topic_query": "termination notice"}},
    ], True),
    ("retrieve then summarize", "Retrieve the NDA then summarize its key points", [
        {"step": 1, "agent": "Researcher", "input": {"topic_query": "NDA"}},
        {"step": 2, "agent": "Summarizer", "input": {"text_to_summarize": "$$STEP_1_OUTPUT$$",
                                                     "summary_objective": "key points"}},
    ], True),
    # --- shapes that must ALWAYS be rejected ---
    ("writer with no librarian", "Write a pitch", [
        {"step": 1, "agent": "Researcher", "input": {"topic_query": "x"}},
        {"step": 2, "agent": "Writer", "input": {"facts": "$$STEP_1_OUTPUT$$"}},
    ], False),
    ("blueprint not chained", "Write a pitch", [
        {"step": 1, "agent": "Librarian", "input": {"intent_query": "x"}},
        {"step": 2, "agent": "Researcher", "input": {"topic_query": "y"}},
        {"step": 3, "agent": "Writer", "input": {"blueprint": "be formal",
                                                 "facts": "$$STEP_2_OUTPUT$$"}},
    ], False),
    ("THE REGRESSION: librarian -> writer, invented facts",
     "Write a persuasive pitch on our brand tone and voice guide", [
         {"step": 1, "agent": "Librarian", "input": {"intent_query": "persuasive pitch"}},
         {"step": 2, "agent": "Writer", "input": {
             "blueprint": "$$STEP_1_OUTPUT$$",
             "facts": "Key points to emphasize:\n- The guide ensures consistency."}},
     ], False),
    ("summarizer fed invented text", "Summarize the NDA", [
        {"step": 1, "agent": "Summarizer", "input": {
            "text_to_summarize": "The NDA says parties must keep secrets.",
            "summary_objective": "key points"}},
    ], False),
    ("styled goal with no writer", "Draft a brand pitch", [
        {"step": 1, "agent": "Researcher", "input": {"topic_query": "brand"}},
    ], False),
    ("empty plan", "anything", [], False),
]

for label, goal, plan, expect_ok in GOLDEN:
    findings = lc_engine.validate_plan(plan, goal)
    got_ok = not findings
    ledger(f"{label} -> {'compliant' if expect_ok else 'rejected'}",
           got_ok == expect_ok,
           f"findings={[f[:70] for f in findings]}")


# =============================================================================
section("R9. Documentation keeps pace with the code")
# =============================================================================
FINDING_NAMES = ("BLUEPRINT-FIRST VIOLATION", "CHAINING GAP",
                 "UNGROUNDED CONTENT", "GROUNDING GAP")
for name in FINDING_NAMES:
    ledger(f"'{name}' is emitted by the code", name in SOURCE["lc_engine"])
    ledger(f"'{name}' is documented in the README", name in README)

ledger("README documents blueprint-first governance",
       "## Blueprint-first governance" in README)
ledger("README documents retrieval quality",
       "## Blueprint retrieval quality" in README)
README_FLAT = " ".join(
    re.sub(r"^>\s?", "", README, flags=re.M).replace("`", "").split())
ledger("README quotes the corporate-demo rationale verbatim",
       "the deck that best showcases your architecture is the one the Planner "
       "declines to use. One sentence in the Librarian docstring" in README_FLAT)
ledger("README documents near-miss namespace detection",
       "near-miss namespaces" in README)
ledger("notebook prose matches CONFIG",
       all(str(cfg[k]) in NB_TEXT for k in
           ("index_name", "generation_model", "embedding_model",
            "namespace_context", "namespace_knowledge",
            "text_key_context", "text_key_knowledge")))
ledger("free regression cell still in the notebook",
       "Blueprint-first regression test" in NB_TEXT)
ledger("blueprint diagnostics cell still in the notebook",
       "blueprint_diagnostics(" in NB_TEXT)


print("\n" + "=" * 72)
if FAILURES:
    print(f"{len(FAILURES)} REGRESSION(S) — a previously-established fix has been undone:")
    for f in FAILURES:
        print("  -", f)
    sys.exit(1)
print("NO REGRESSIONS. Every fix established in this project is still in place.")
