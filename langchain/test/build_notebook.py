"""Build Universal_Context_Engine_LangChain.ipynb from the verified modules.

The seven %%writefile cells are generated directly from the .py files on disk,
so the notebook and the standalone modules cannot drift apart. build_notebook.py
is the single source of truth for that relationship; verify_notebook.py proves
it afterwards.
"""
import json
import os

SRC = "/home/claude/langchain"
OUT = os.path.join(SRC, "Universal_Context_Engine_LangChain.ipynb")

MODULES = [
    "lc_utils.py",
    "lc_helpers.py",
    "lc_agents.py",
    "lc_registry.py",
    "lc_engine.py",
    "lc_dashboard.py",
    "lc_boot.py",
]

REPO = "Denis2054/Context-Engineering-for-Multi-Agent-Systems"
NB_PATH = f"{REPO}/blob/main/langchain/Universal_Context_Engine_LangChain.ipynb"

cells = []


def md(text):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": text.strip() + "\n"})


def code(text, title=None):
    meta = {}
    if title:
        meta["cellView"] = "form"
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": meta,
        "outputs": [],
        "source": text.strip() + "\n",
    })


def writefile(filename):
    """A cell whose body is byte-for-byte the file on disk."""
    with open(os.path.join(SRC, filename), encoding="utf-8") as f:
        body = f.read()
    assert body.endswith("\n"), f"{filename} must end with a newline"
    cells.append({
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": f"%%writefile {filename}\n" + body,
    })


# =============================================================================
# 0 — badge
# =============================================================================
md(f'<a href="https://colab.research.google.com/github/{NB_PATH}" '
   f'target="_parent"><img src="https://colab.research.google.com/assets/colab-badge.svg" '
   f'alt="Open In Colab"/></a>')

# =============================================================================
# 1 — title
# =============================================================================
md("""
# Universal Context Engine — LangChain Edition

Copyright 2025-2026, Denis Rothman. LangChain port of the Universal Context Engine.

**What this is:** *a Context Engine layer on a LangChain substrate.* The same Universal Context Engine, rebuilt on LangChain and LangGraph — reading the *same* Pinecone index, the *same* namespaces, and using the *same* OpenAI models as the original.

The two parts are not peers. LangChain is the **substrate**: models, prompts, retrievers, tool schemas, graph runtime. The Context Engine is the **layer** that runs on it: the plan artifact, context chaining, per-chunk defense, the audit trace. Change the substrate and the layer survives — which is the whole point.

| Setting | Value |
|---|---|
| Pinecone index | `genai-mas-mcp-ch3` |
| Blueprint namespace | `ContextLibrary` (metadata field `blueprint_json`, top&#8209;k 1) |
| Knowledge namespace | `KnowledgeStore` (metadata fields `text`, `source`, top&#8209;k 3) |
| Generation model | `gpt-5.1` |
| Embedding model | `text-embedding-3-small` (1536 dims) |

**Nothing is written to Pinecone.** This notebook only reads the vectors the Chapter 8 and Chapter 9 ingestion notebooks already created. There is no re-embedding and no new index.

---

### ⚠️ Prerequisite — the index must already be populated

Run these two notebooks first, in this order:

1. `Chapter08/Data_Ingestion.ipynb` — legal data.
2. `Chapter09/Data_Ingestion_Marketing.ipynb` — **with `clear_index=False`**, so marketing data is appended rather than replacing the legal data.

Section I below runs `lc_utils.check_index()`, which verifies the index dimension and confirms both namespaces contain vectors before you spend anything on a run. If that check fails, stop and fix the ingestion — every downstream cell will otherwise return plausible-looking emptiness with no error.

---

### What LangChain absorbs, and what it does not

| Hand-built in the book | Provided by the framework | Still hand-built here |
|---|---|---|
| `call_llm_robust()` + `tenacity` | `ChatOpenAI(...).with_retry()` | — |
| `json_mode=True` + `json.loads()` + hotfix patch | `.with_structured_output(Plan)` | the `Plan` / `PlanStep` / `AgentInput` schema itself |
| `get_embedding()` | `OpenAIEmbeddings(...)` | — |
| `query_pinecone()` | `PineconeVectorStore(...).as_retriever()` | the two-namespace, two-`text_key` split |
| 4 agent functions + MCP envelopes | 4 `@tool`-decorated LCEL chains | the four system prompts |
| `AgentRegistry` + hand-written capabilities | tool `args_schema` generation | the `ROLE:`/`INPUTS:` rendering the Planner reads |
| execution loop | LangGraph `StateGraph` | Plan-and-Execute itself; `$$STEP_N_OUTPUT$$` context chaining |
| `count_tokens()` (tiktoken estimate) | `usage_metadata` (real billed tokens) | per-**step** attribution against the plan cursor |
| `ExecutionTrace` | LangSmith run tree | the audit-shaped local trace and its offline dashboard |
| `helper_sanitize_input()` | *nothing* | per-chunk injection screening, in full |
| `helper_moderate_content()` | *nothing in v1* | the moderation call and its fail-safe policy |

Roughly two thirds of this codebase is framework. The remaining third — the right-hand column — is the engine. See **Section VII** for the full account.

The original notebook's **Robust Planner hotfix cell is not reproduced**. It existed because the model sometimes returned the plan in the wrong JSON shape; a Pydantic schema with a `Literal` agent field makes that shape error structurally impossible.

---

### How to run

1. Add your keys to **Colab Secrets** (key icon in the left sidebar):
   `API_KEY` (OpenAI), `PINECONE_API_KEY`, and optionally `LANGSMITH_API_KEY`.
2. **Runtime → Run all**, or run Sections I and II then pick individual Control Decks.
3. No GPU needed. Set the runtime to CPU.
""")

# =============================================================================
# I. Initialization
# =============================================================================
md("# I. Initialization")

md("""
## Engine modules

This notebook is **standalone**. The seven cells below write the engine's modules
into the Colab filesystem with `%%writefile` — nothing is downloaded, and there is
no dependency on a repository being reachable at run time.

The standalone `.py` files shipped alongside this notebook are byte-identical to
these cells, so you can either run the notebook as-is or import the modules into
your own project. Editing a cell and re-running it replaces the module on disk;
restart the runtime afterwards so the import cache picks up the change.

| File | Replaces | Contains |
|---|---|---|
| `lc_utils.py` | `utils.py` | installation, Colab Secrets, index diagnostics |
| `lc_helpers.py` | `helpers.py` | model, embeddings, two vector stores, guardrails, token tracking |
| `lc_agents.py` | `agents.py` | Librarian, Researcher, Summarizer, Writer as tools |
| `lc_registry.py` | `registry.py` | the toolkit; capabilities generated from schemas |
| `lc_engine.py` | `engine.py` | Plan schema, planner, LangGraph orchestrator, trace |
| `lc_dashboard.py` | notebook cell | the HTML trace dashboard |
| `lc_boot.py` | — | one call that wires everything together |
""")

for module in MODULES:
    writefile(module)

md("## Installation and environment setup")

code("""
# Install the LangChain stack and load API keys from Colab Secrets.
# The %%writefile cells above only wrote text to disk, so nothing has been
# imported yet and this is the first cell that needs the network.
import lc_utils

installed = lc_utils.install_dependencies()
assert installed, "Installation failed. Read the pip output above before continuing."

# Reads Colab Secrets and exports them as environment variables.
#   API_KEY            -> OPENAI_API_KEY
#   PINECONE_API_KEY   -> PINECONE_API_KEY
#   LANGSMITH_API_KEY  -> LANGSMITH_API_KEY (optional, enables hosted tracing)
#
# Unlike the original, no client objects are created here and none are passed
# around later. LangChain builds its own clients from the environment.
ok = lc_utils.initialize_environment()
assert ok, "Fix the secrets above before continuing."
""")

md("""
## Pre-flight: inspect the Pinecone index

Two failure modes cost you a whole run and report nothing: an empty namespace
returns zero documents with no error, and a dimension mismatch returns irrelevant
answers with no error. This one call rules out both for the price of a metadata
request.
""")

code("""
#@title Pre-flight: confirm the index is populated and correctly dimensioned
index_ok = lc_utils.check_index("genai-mas-mcp-ch3")
assert index_ok, "Index pre-flight failed. Run the Chapter 8 and 9 ingestion notebooks first."
""", title=True)

# =============================================================================
# II. Assembly
# =============================================================================
md("""
# II. Engine assembly

One call builds the model, the embeddings, both vector stores, both retrievers,
the four agents, the toolkit, the token tracker and the compiled LangGraph.
""")

code("""
import lc_boot

engine = lc_boot.build_context_engine()
""")

md("""
## Verify the retrieval layer before running anything

This is the single most important check in the whole port. One Pinecone index,
two namespaces, **two different `text_key` values**, two different `k` values.
Get `text_key` wrong and documents come back with empty `page_content` — no
error, just silently useless context.
""")

code("""
#@title Retrieval smoke test (run this before any Control Deck)
# Blueprint side: ContextLibrary, text_key='blueprint_json', k=1
bp_docs = engine.blueprint_retriever.invoke("a formal structured legal summary")
print(f"ContextLibrary -> {len(bp_docs)} document(s)")
for d in bp_docs:
    print("  page_content[:200]:", repr(d.page_content[:200]))
    print("  metadata keys     :", list(d.metadata.keys()))

print()

# Knowledge side: KnowledgeStore, text_key='text', k=3
kn_docs = engine.knowledge_retriever.invoke("confidentiality obligations termination notice")
print(f"KnowledgeStore -> {len(kn_docs)} document(s)")
for d in kn_docs:
    print("  source:", d.metadata.get("source"), "|", repr(d.page_content[:120]))

assert bp_docs and bp_docs[0].page_content, \\
    "ContextLibrary returned empty text: check text_key='blueprint_json'"
assert kn_docs and kn_docs[0].page_content, \\
    "KnowledgeStore returned empty text: check text_key='text'"
print("\\nRetrieval layer OK.")
""", title=True)

md("""
## Blueprint retrieval quality — check before you demonstrate

The Librarian retrieves at `k=1`: exactly one blueprint, with no indication of how
close the runner-up was. Over a small `ContextLibrary` the nearest neighbour can be
effectively arbitrary — a request for *a formal structured legal summary* can return
a **casual** blueprint, and the Writer will then faithfully produce casual prose.

That is the engine working correctly on a bad retrieval, which is the most
expensive kind of failure to debug live. This cell makes the scores visible.
A margin below 0.05 between the top two hits means the selection is close to a
coin flip, and the fix is ingestion — more clearly differentiated blueprints —
not code.
""")

code("""
#@title Blueprint retrieval diagnostics (scores and margins)
import lc_helpers

lc_helpers.blueprint_diagnostics(engine.context_store, [
    "a formal structured legal summary",
    "a persuasive marketing pitch",
    "a quick casual summary for a colleague",
], k=3)
""", title=True)

md("""
## The capabilities block — generated, not hand-written

In the original, `registry.get_capabilities_description()` was a 30-line f-string
maintained by hand and kept in sync with four function signatures by discipline
alone. Here it is derived from the tools' own Pydantic schemas, so it cannot
drift out of sync with the code.

The *rendering format* is still ours — LangChain describes a tool to a model, but
not in the `ROLE:`/`INPUTS:` shape this Planner prompt expects. What the framework
removed is the duplication, not the design.
""")

code("""
#@title Inspect the auto-generated capabilities
print(engine.capabilities())
""", title=True)

md("""
## Trace dashboard

The dashboard is carried over from the original notebook with its CSS unchanged.
Three additions: the execution **plan** has its own card, each step shows the
provider's **real billed tokens** alongside the context-size measurement, and a
**failed step renders in red with its error text** instead of the run ending
silently.

Read the pills as:
- **CTX IN / CTX OUT** — size of the context handed to the step and of what it returned. This is the original notebook's metric and what the Summarizer's *SAVED* figure comes from.
- **LLM IN / LLM OUT** — tokens the provider actually billed for this step, from `usage_metadata`. A retrieval-only step (Librarian) shows *retrieval only* because it makes no model call.

Expect these numbers to differ from the original notebook's screenshots. They
measure different things, and these are exact.
""")

code("""
from lc_dashboard import render_trace_dashboard

print("Dashboard ready.")
""")

md("""
## Engine Room

The same `execute_and_display()` entry point as the original, so the Control Decks
below look almost identical. Note the shorter signature: `client`, `pc`,
`index_name`, the model names and the namespaces are all baked into the assembled
`engine`.

One contract change worth knowing: a trace is **always** returned, including when
a goal is blocked by pre-flight moderation. A blocked goal is an audit event, and
it now renders like any other run.
""")

code('''
def execute_and_display(goal, moderation_active=False, ctx_engine=None,
                        label="LangGraph Plan-and-Execute"):
    """Run the LangChain Context Engine and render the HTML dashboard."""
    ctx_engine = ctx_engine or engine

    result, trace = ctx_engine.run(goal, moderation_active=moderation_active)

    render_trace_dashboard(trace, engine_label=label)
    return result
''')

# =============================================================================
# III. Control decks
# =============================================================================
md("""
# III. Control Decks

The same goals as the original notebook, so outputs can be compared side by side.

1. Change the `goal` variable.
2. Run the cell.

The configuration dictionary is gone: it lives in `engine` now. To change models
or namespaces, rebuild with
`engine = lc_boot.build_context_engine({"generation_model": "..."})`.
""")

md("## I — Marketing")

code("""
#@title CONTROL DECK: Moderation
# A simple, safe goal that exercises the full moderation workflow:
# pre-flight on the goal, post-flight on the generated output.
goal = "Summarize the key points of the QuantumDrive"

execute_and_display(goal, moderation_active=True)
""", title=True)

code("""
#@title Product Marketing Copy Generation
goal = ("Analyze the ChronoTech press release and summarize their core product "
        "messaging and value proposition. Please cite your sources.")

execute_and_display(goal, moderation_active=False)
""", title=True)

code("""
#@title Writing a brand pitch recommendation
# Tests the Researcher's ability to report a negative finding and the Writer's
# ability to handle it gracefully, without hallucinating.
goal = "Write a persuasive pitch on our brand tone and voice guide"

execute_and_display(goal, moderation_active=False)
""", title=True)

md("## II — Legal")

code("""
#@title CONTROL DECK: Moderation
# The goal is worded to disambiguate "summarize": retrieve first, then summarize.
# A goal of "Summarize the key points of the NDA" leaves the Planner ambiguous
# about whether to use the Researcher or jump straight to the Summarizer.
goal = ("First, retrieve the content of the Non-Disclosure Agreement (NDA) from "
        "the knowledge base. Then, summarize its key points.")

execute_and_display(goal, moderation_active=True)
""", title=True)

code("""
#@title CONTROL DECK TEMPLATE 1: High-Fidelity RAG
# Exercises the high-fidelity Researcher: retrieval with `source` metadata,
# per-chunk sanitization, and citation generation.
goal = ("What are the key confidentiality obligations in the Service Agreement v1, "
        "and what is the termination notice period? Please cite your sources.")

# LIMIT TEST — uncomment to watch the sanitizer drop a poisoned chunk while the
# remaining chunks still produce an answer. Look for the
# "[Sanitizer] Potential threat detected" warning in the log output, and note
# that the poisoned document does NOT appear in the Sources list.
# goal = "What did Mr. Smith advise his client regarding the assets?"

execute_and_display(goal, moderation_active=False)
""", title=True)

# =============================================================================
# IV. Glass box
# =============================================================================
md("""
# IV. The Glass Box — inspect a plan before executing it

The engine's central claim is that behaviour comes from context, not from
hard-coded rules. Route A makes that auditable: the plan is a validated object
you can read *before* anything runs and before any money is spent.

Change the goal and watch the plan change while the code stays identical. That is
the domain-agnostic thesis, demonstrated rather than asserted.
""")

code("""
#@title Plan-only: no execution, no cost beyond one planning call
import json
import lc_engine

for goal in [
    "First, retrieve the content of the Non-Disclosure Agreement (NDA) from the knowledge base. Then, summarize its key points.",
    "Analyze the ChronoTech press release and summarize their core product messaging and value proposition. Please cite your sources.",
    "Write a persuasive pitch on our brand tone and voice guide",
]:
    plan = engine.plan_only(goal)
    rows = [{"step": s.step, "agent": s.agent,
             "input": s.input.model_dump(exclude_none=True)} for s in plan.plan]

    print("=" * 100)
    print("GOAL:", goal)
    print("-" * 100)
    for step in rows:
        print(f"  {step['step']}. {step['agent']:<11} "
              f"{json.dumps(step['input'], ensure_ascii=False)[:140]}")

    findings = lc_engine.validate_plan(rows, goal)
    print("  GOVERNANCE:", "compliant" if not findings else "")
    for f in findings:
        print("     -", f)
    print()
""", title=True)

md("""
## Blueprint-first: the governance rule, and how to test it for free

The Semantic Blueprint is this engine's signature idea, and it is also the thing a
Planner will quietly skip. Left to itself, a model reads the Librarian as optional
and plans `Researcher -> Summarizer -> Writer`, producing competent content in an
arbitrary voice.

**For a corporate demo this is the thing to fix, because the deck that best
showcases your architecture is the one the Planner declines to use. One sentence in
the Librarian docstring (`"Call this first whenever the goal asks for content to be
written, rewritten, or styled"`) plus one line in the planner prompt would likely
flip it. Cheap, and testable via `plan_only` with no spend.**

Both halves are now in place, plus a third that does not depend on the model
complying:

1. **`lc_agents.Librarian`** — the docstring, which *is* the interface the Planner
   reads, now states that it must be called first for any written, rewritten or
   styled deliverable.
2. **`lc_engine.PLANNER_PROMPT`** — instruction 4 declares a Writer step with no
   preceding Librarian step to be **invalid**, and instruction 5 exempts pure
   retrieve/summarize goals so the rule does not over-trigger.
3. **`lc_engine.validate_plan()`** — a deterministic check that runs on every plan.
   Prompt instructions are probabilistic; a governed deployment also needs the
   policy *verified*. Findings are recorded on the trace and rendered as an amber
   banner on the dashboard. They do not fail the run — to enforce rather than
   report, return `{"error": findings[0]}` from `plan_node`.

The cell below is the free regression test. It costs one planning call per goal —
no retrieval, no generation — so you can iterate on prompt wording without paying
for full runs.
""")

code("""
#@title Blueprint-first regression test (planning calls only, no execution)
import lc_engine

STYLED = [
    "Write a persuasive pitch on our brand tone and voice guide",
    "Draft a formal client-facing summary of the Service Agreement",
    "Rewrite our product one-pager in the house marketing voice",
]
UNSTYLED = [
    "First, retrieve the content of the NDA from the knowledge base. Then, summarize its key points.",
    "What is the termination notice period in the Service Agreement v1?",
]

passed = 0
for goal in STYLED + UNSTYLED:
    plan = engine.plan_only(goal)
    rows = [{"step": s.step, "agent": s.agent,
             "input": s.input.model_dump(exclude_none=True)} for s in plan.plan]
    agents = [r["agent"] for r in rows]
    findings = lc_engine.validate_plan(rows, goal)

    expects_blueprint = goal in STYLED
    got_blueprint = "Librarian" in agents
    ok = (not findings) and (got_blueprint == expects_blueprint)
    passed += ok

    # A styled deliverable must also be GROUNDED: the Writer's facts have to be
    # a reference to a retrieval step, never text the Planner wrote itself.
    if expects_blueprint and "Researcher" not in agents:
        print("        ! ungrounded: no Researcher step behind the Writer")

    print(f"[{'PASS' if ok else 'FAIL'}] {' -> '.join(agents)}")
    print(f"        {goal[:88]}")
    for f in findings:
        print(f"        ! {f}")

print(f"\\n{passed}/{len(STYLED) + len(UNSTYLED)} goals planned as expected.")
""", title=True)

# =============================================================================
# V. Route B
# =============================================================================
md("""
# V. Route B — the same tools, the idiomatic way

Route A (everything above) reproduces the original architecture: **plan first,
then execute**. Route B hands the identical four tools to LangChain's standard
`create_agent` and lets the model decide what to call, one step at a time.

| | Route A — LangGraph | Route B — `create_agent` |
|---|---|---|
| Orchestration code | ~60 lines | ~6 lines |
| Plan artifact | Yes, inspectable before execution | None |
| Auditability | High | Lower — behaviour emerges at run time |
| Per-step token attribution | Yes | No |
| Approval before spend | Possible (`plan_only`) | Not possible |
| Fidelity to the original | Faithful port | A different, simpler system |

Run both on the same goal and compare. The point of this section is the contrast:
Route B is dramatically shorter, and the up-front plan is what you trade away to
get it. Neither is wrong; they belong to different tiers of the delegation
gradient, and the choice should be deliberate.
""")

code('''
#@title Route B: create_agent
import json
from IPython.display import Markdown, display

react_agent = lc_boot.build_react_agent(engine)

goal = ("What are the key confidentiality obligations in the Service Agreement v1, "
        "and what is the termination notice period? Please cite your sources.")

response = react_agent.invoke({"messages": [("user", goal)]})

# Show the tool-calling trajectory the model chose for itself.
print("TRAJECTORY")
print("-" * 80)
for m in response["messages"]:
    kind = m.__class__.__name__
    calls = getattr(m, "tool_calls", None)
    if calls:
        for c in calls:
            print(f"  {kind:<12} -> CALL {c['name']}({json.dumps(c['args'])[:100]})")
    elif kind == "ToolMessage":
        print(f"  {kind:<12} <- {str(m.content)[:100]}...")
    elif m.content:
        print(f"  {kind:<12}    {str(m.content)[:100]}...")

print()
print("=" * 80)
print("FINAL ANSWER")
print("=" * 80)
display(Markdown(response["messages"][-1].content))
''', title=True)

# =============================================================================
# VI. Appendix
# =============================================================================
md("""
# VI. Appendix

## Token accounting for the most recent run

`UsageTracker` is reset at the start of every `engine.run()`, so these figures
describe the last run only, not the session.
""")

code("""
print(engine.tracker.summary())
""")

md("""
# VII. What LangChain does not provide

This notebook is a port onto LangChain, not a replacement by LangChain. The
framework supplies the substrate; the following components have no framework
equivalent and are written out in full in the modules above. They are, not
coincidentally, the parts the book is about.

| Component | Where | Why there is no LangChain equivalent |
|---|---|---|
| **Per-chunk sanitization** | `lc_helpers.sanitize`, used inside `lc_agents.Researcher` | Agent middleware operates on a whole message. It cannot drop chunk 2 while keeping chunks 1 and 3, which is exactly the behaviour that lets a poisoned corpus still produce a cited answer. |
| **Moderation** | `lc_helpers.moderate` | `langchain-core` v1 ships no moderation wrapper; the legacy `OpenAIModerationChain` moved to `langchain-classic`. The OpenAI endpoint is called directly, with a documented fail-safe policy that distinguishes *flagged* from *could not be checked*. |
| **Context chaining** | `lc_engine.resolve_dependencies` | LangGraph carries state between nodes. It does not give the model a dataflow language in which to *declare* dependencies at plan time — `$$STEP_N_OUTPUT$$` is this engine's own. |
| **Plan-and-Execute** | `lc_engine.build_engine` | Removed from LangChain core; what remains in `langchain-experimental` is unmaintained. The two-node graph is built by hand on the Graph API. |
| **Per-step token attribution** | `lc_helpers.UsageTracker` | LangChain reports usage per model call. Attributing it to a *plan step* requires snapshotting against the execution cursor. |
| **The audit trace and dashboard** | `lc_engine.LangChainTrace`, `lc_dashboard` | LangSmith is a hosted run viewer. It does not record `planned_input` vs `resolved_context` vs `tokens_saved` per plan step, and it is not an offline, embeddable artifact. |
| **Capability rendering** | `lc_registry.get_capabilities_description` | The *schema* is generated by LangChain; the `ROLE:`/`INPUTS:` block the Planner prompt reads is not. |
| **Plan governance** | `lc_engine.validate_plan` | No framework knows that *this* engine requires a blueprint before a Writer step. Architectural policy is domain knowledge, and it has to be stated and checked. |

Two shims are also worth naming honestly, because they exist to work *around* the
framework rather than to use it: `lc_helpers.base_model()` unwraps `RunnableRetry`
because `.with_retry()` does not forward `with_structured_output()` or
`get_num_tokens()`; and `lc_helpers._openai_client()` resolves a moderation client
through three tiers, ending in a directly constructed `openai.OpenAI()` so that a
change in `langchain-openai`'s internals degrades gracefully instead of disabling
the guardrail.

## LangSmith

If you added a `LANGSMITH_API_KEY` secret **and it validated at start-up**, every
run above was recorded automatically — full inputs, outputs, timings and token
counts for every node, chain and tool, with no instrumentation code. Open
<https://smith.langchain.com> and look for the project
`universal-context-engine-langchain`.

The key is exercised once against the API before tracing is switched on. A key
that exists but cannot write — expired, revoked, or issued for a different
workspace — is reported at start-up and tracing is disabled, rather than emitting
a `403 Forbidden` warning on every trace flush for the rest of the session. You
can also turn it off at any point with `lc_utils.disable_langsmith()`, though
LangChain caches its tracer on first use, so restart the runtime if a run has
already been traced.

This replaces the *observability* half of the original `ExecutionTrace`, not the
*audit* half. `LangChainTrace` is kept regardless, so the notebook still works and
still renders its dashboard with no LangSmith account and no network egress to a
third party — which is usually the deciding factor in a regulated deployment.
""")

md("""
## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Retrieval returns 0 documents | Wrong or missing namespace | Namespaces are case-sensitive: `ContextLibrary`, `KnowledgeStore` |
| Documents have empty `page_content` | Wrong `text_key` | `blueprint_json` for ContextLibrary, `text` for KnowledgeStore. The Librarian and Researcher now log an explicit error when this happens |
| Answers are irrelevant but not empty | Embedding model mismatch | Must be `text-embedding-3-small`. `check_index()` verifies the 1536 dimension |
| `KeyError` on a prompt fragment | Unescaped `{` in a prompt | Double every literal brace: `{{` and `}}` |
| Planner picks the wrong agent | Vague tool docstring | The docstring *is* the interface the model reads. Rewrite it |
| `Agent 'X' not found in registry` | Shouldn't happen | The `Literal` in `PlanStep` prevents invented names, and `build_engine` asserts the toolkit matches it |
| Moderation blocks everything | The endpoint could not be reached | Fail-safe is deliberate. The console prints the underlying error and the trace status reads *Halted: moderation unavailable*, distinct from *Halted: pre-flight moderation* |
| `langsmith.client: Failed to send ... 403 Forbidden` | A `LANGSMITH_API_KEY` secret exists but is expired, revoked, or belongs to another workspace | Should no longer occur: `initialize_environment()` validates the key and disables tracing if it fails. If you see it anyway, the tracer was cached from an earlier run — **restart the runtime**, or call `lc_utils.disable_langsmith()`. Nothing in the engine depends on LangSmith |
| Planner skips the Librarian on a "write/draft/pitch" goal | The blueprint-first rule is not reaching the model | Should no longer occur. Verify for free with the regression cell in Section IV; the dashboard shows an amber governance banner whenever it does |
| Output reads well but has no Sources section | The Planner authored `facts` itself instead of referencing a Researcher step | The plan is ungrounded. `validate_plan` now raises `UNGROUNDED CONTENT` and `GROUNDING GAP`, and the amber banner names the invented text |
| Retrieval returns valid but irrelevant results | A namespace differing only by case or hyphens exists in the same index | Pinecone namespaces are case-sensitive, so this fails silently. `check_index` now flags near-miss names and fails the pre-flight when the near-miss holds more vectors |
| The right blueprint exists but the wrong one is retrieved | `k=1` over a small or undifferentiated `ContextLibrary` | Run `lc_helpers.blueprint_diagnostics()` in Section II. A margin under 0.05 means the choice is near-arbitrary — fix the ingestion, not the code |
| A Summarizer step shows **EXPANDED** instead of SAVED | The summary was longer than its input | Expected on short passages; the model elaborates rather than compresses. Not a broken counter |
| `check_index` total is far larger than the two namespaces | Earlier chapters wrote elsewhere in the same index | Normal, and now itemised explicitly in the pre-flight output |
| `[Sanitizer] Potential threat detected` / `[Researcher] REJECTED chunk` | **Not an error.** A retrieved chunk matched an injection pattern | This is the defense working. The chunk is dropped, the rejected document is named and is *not* cited, and the run continues on the surviving chunks. If you want to see it deliberately, use the LIMIT TEST goal in the legal Control Deck |
| `ImportError` after editing a `%%writefile` cell | Stale import cache | Restart the runtime after re-running a module cell |
| Slow first run | Cold Pinecone connection | Normal. Subsequent runs are faster |

## Verifying a change

Three suites ship alongside this notebook. Run all three before committing any
edit to a module or a prompt:

```bash
python verify_regressions.py   # nothing previously fixed has been undone
python verify_engine.py        # behaviour is correct, against the real libraries
python verify_notebook.py      # notebook/module byte identity, docs match code
```

The first is the one worth explaining. During hardening, an edit that added the
blueprint-first rule to the planner prompt also deleted the sentence naming the
canonical `Librarian -> Researcher -> Writer` flow. The Researcher dropped out of
the default plan shape, and the engine began producing fluent, on-brand,
**entirely unsourced** deliverables that still reported `Success`. Every test
passed, because every test asserted the *new* behaviour.

`verify_regressions.py` is a ledger of every fix ever made here — entries are only
added, never removed — including ten golden plan shapes that must validate the
same way forever. Prompt edits are the highest-risk change in this codebase
precisely because they have no compiler; treat them accordingly.

## Modifying the engine

- **Add an agent:** write a new `@tool` in `lc_agents.py`, return it from `build_agents`, add its name to `lc_engine.AGENT_NAMES` **and** to the `Literal` in `PlanStep`, and add any new argument to `AgentInput`. `build_engine()` raises at assembly time if you forget one of these. The capabilities block updates itself.
- **Change retrieval depth:** `lc_boot.build_context_engine({"k_knowledge": 5})`. Unknown keys raise immediately rather than being silently ignored.
- **Change the model:** `lc_boot.build_context_engine({"generation_model": "..."})`. Do **not** change `embedding_model` unless you re-ingest — the stored vectors are 1536-dimensional.
- **Resume failed runs:** pass a checkpointer to `graph.compile()` in `lc_engine.build_engine`. LangGraph will then restart at the failing step rather than from the beginning.
- **Approve plans before execution:** call `engine.plan_only(goal)` first, or add LangGraph's `interrupt()` between the `plan` and `execute` nodes for a true human-in-the-loop gate.
""")

# =============================================================================
# Write it out
# =============================================================================
notebook = {
    "nbformat": 4,
    "nbformat_minor": 0,
    "metadata": {
        "colab": {
            "provenance": [],
            "toc_visible": True,
            "collapsed_sections": [],
        },
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.10",
        },
    },
    "cells": cells,
}

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(notebook, f, indent=1, ensure_ascii=False)
    f.write("\n")

print(f"Wrote {OUT}")
print(f"  {len(cells)} cells "
      f"({sum(c['cell_type'] == 'code' for c in cells)} code, "
      f"{sum(c['cell_type'] == 'markdown' for c in cells)} markdown)")
