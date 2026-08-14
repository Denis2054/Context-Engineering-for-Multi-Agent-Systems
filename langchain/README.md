# Universal Context Engine — LangChain Edition

**A Context Engine layer on a LangChain substrate.**

The Universal Context Engine, ported onto **LangChain 1.x** and **LangGraph 1.x**,
reading the *same* Pinecone index, the *same* namespaces, and using the *same*
OpenAI models as the original.

The two parts are not peers, and this is not a blend of two systems. LangChain is
the **substrate** — models, prompts, retrievers, tool schemas, graph runtime. The
Context Engine is the **layer** that runs on top of it — the plan artifact,
context chaining, per-chunk defense, plan governance, the audit trace. Roughly two
thirds of the code is substrate; the remaining third is the layer, and the layer
is what determines behaviour.

This folder is the framework pole of the repository. `sovereign_ai/` is the
other: zero framework, zero external API, maximum control. Same layer, opposite
substrates. Between them they make one point, which is the point of the book:

> **The architecture is the product. The framework is a deployment choice.**

The plan artifact, the dual-RAG split, the four specialists, the per-chunk
defense and the glass-box trace all survive a complete change of substrate. That
is what domain-agnostic *and* framework-agnostic looks like in practice.

---

## ⚠️ Prerequisite

The Pinecone index must already be populated. Run these first, in order:

1. `Chapter08/Data_Ingestion.ipynb` — legal data.
2. `Chapter09/Data_Ingestion_Marketing.ipynb` — **with `clear_index=False`**, so
   marketing data is appended rather than replacing the legal data.

The notebook's pre-flight cell (`lc_utils.check_index`) verifies the index
dimension and confirms both namespaces contain vectors before you spend anything
on a run.

## Quick start (Google Colab)

1. Open `Universal_Context_Engine_LangChain.ipynb` in Colab.
2. Add three Colab Secrets (key icon, left sidebar):

   | Secret | Required | Purpose |
   |---|---|---|
   | `API_KEY` | yes | OpenAI key (same name the original notebook used) |
   | `PINECONE_API_KEY` | yes | Pinecone key |
   | `LANGSMITH_API_KEY` | no | enables hosted tracing; validated at start-up and skipped if unusable |

3. **Runtime → Run all.** CPU runtime is fine; no GPU is needed.

The notebook is **standalone**: the seven module files are written to disk by
`%%writefile` cells, so nothing is downloaded and no repository needs to be
reachable at run time. The standalone `.py` files in this folder are
byte-identical to those cells — this is enforced by the build, not by hand, and
verified on every change.

## Fixed configuration

These values are not adjustable without consequences:

| Setting | Value | Note |
|---|---|---|
| Index | `genai-mas-mcp-ch3` | read-only; nothing is ever written |
| Blueprint namespace | `ContextLibrary` | `text_key="blueprint_json"`, k=1 |
| Knowledge namespace | `KnowledgeStore` | `text_key="text"`, k=3 |
| Generation model | `gpt-5.1` | no temperature is set, matching the original |
| Embedding model | `text-embedding-3-small` | **1536 dims — changing this invalidates every vector** |

## Files

| File | Replaces | Contains |
|---|---|---|
| `lc_utils.py` | `utils.py` | installation, Colab Secrets → env vars, index diagnostics |
| `lc_helpers.py` | `helpers.py` | model, embeddings, two vector stores, sanitizer, moderation, token tracking, blueprint diagnostics |
| `lc_agents.py` | `agents.py` | Librarian, Researcher, Summarizer, Writer as `@tool` LCEL chains |
| `lc_registry.py` | `registry.py` | toolkit; capabilities generated from tool schemas |
| `lc_engine.py` | `engine.py` | Plan schema, planner, plan governance, LangGraph orchestrator, trace |
| `lc_dashboard.py` | notebook cell | the HTML trace dashboard |
| `lc_boot.py` | — | `build_context_engine()`, one call that wires everything |
| `requirements.txt` | — | pins, generated from `lc_utils.PACKAGES` |

## Programmatic use

```python
import lc_utils, lc_boot
lc_utils.initialize_environment()

engine = lc_boot.build_context_engine()

# Inspect the plan without executing it — one planning call, no retrieval,
# no generation, no spend beyond that call.
plan = engine.plan_only("Write a persuasive pitch on our brand guide.")

# Check it against the engine's governance rules. Free: no model call.
import lc_engine
rows = [{"step": s.step, "agent": s.agent,
         "input": s.input.model_dump(exclude_none=True)} for s in plan.plan]
print(lc_engine.validate_plan(rows, "Write a persuasive pitch on our brand guide."))

# Run it. A trace is always returned, including when a goal is blocked.
result, trace = engine.run("Summarize the NDA and cite sources.",
                           moderation_active=True)

from lc_dashboard import render_trace_dashboard
render_trace_dashboard(trace)
```

Override configuration at build time (unknown keys raise immediately):

```python
engine = lc_boot.build_context_engine({"k_knowledge": 5})
```

## Architecture

**Route A (primary)** — LangGraph `StateGraph`, a faithful port of the original
Plan-and-Execute design. One structured LLM call produces a validated plan; a
graph loop executes each step, threading outputs into later inputs through shared
state. The plan is an inspectable object *before* execution, which is what keeps
the Glass Box property intact.

**Route B (Section V of the notebook)** — the same four tools handed to
`create_agent`. Roughly six lines instead of sixty, but there is no plan
artifact, no per-step token attribution, no resolved-context record, and no way
to approve the work before paying for it. Included for comparison, not as a
replacement. The two routes sit at different points on the delegation gradient;
choosing between them should be deliberate.

## What LangChain absorbs

| Hand-built in the book | Provided by the framework | Benefit |
|---|---|---|
| `call_llm_robust` + `tenacity` | `ChatOpenAI(...).with_retry()` | retry applies to every chain, not one function |
| `json_mode` + `json.loads` + hotfix cell | `.with_structured_output(Plan)` | schema, parsing and validation in one call |
| free-form `agent` string | `Literal[...]` field | an invented agent name is structurally impossible |
| hand-written capability list | generated from Pydantic schemas | cannot drift out of sync with the code |
| `agent_writer` unpacking `facts` / `summary` / `answer_with_sources` | typed tool signature | ~20 lines of defensive code deleted |
| `count_tokens` (tiktoken over a dict repr) | `usage_metadata` | exact, billable-accurate counts |
| `ExecutionTrace` observability | LangSmith run tree | full observability with no instrumentation |

**The original notebook's Robust Planner hotfix cell is not reproduced.** It
existed to work around the model returning the plan in the wrong JSON shape; the
Pydantic schema removes that failure mode at the source.

## What LangChain does not provide

Roughly two thirds of this codebase is framework. The remaining third has no
framework equivalent, and is — not coincidentally — the part the book is about.

| Component | Where | Why there is no equivalent |
|---|---|---|
| **Per-chunk sanitization** | `lc_helpers.sanitize`, inside `lc_agents.Researcher` | Middleware sees a whole message. It cannot drop chunk 2 while keeping chunks 1 and 3 — the behaviour that lets a poisoned corpus still produce a cited answer. |
| **Moderation** | `lc_helpers.moderate` | `langchain-core` v1 ships no moderation wrapper; the legacy `OpenAIModerationChain` moved to `langchain-classic`. |
| **Context chaining** | `lc_engine.resolve_dependencies` | LangGraph carries state between nodes; it does not give the model a dataflow language to declare dependencies in. `$$STEP_N_OUTPUT$$` is this engine's own. |
| **Plan-and-Execute** | `lc_engine.build_engine` | Removed from LangChain core; what remains in `langchain-experimental` is unmaintained. Built by hand on the Graph API. |
| **Per-step token attribution** | `lc_helpers.UsageTracker` | LangChain reports usage per model *call*; attributing it to a plan *step* requires snapshotting against the execution cursor. |
| **Audit trace + offline dashboard** | `lc_engine.LangChainTrace`, `lc_dashboard` | LangSmith is a hosted run viewer. It does not record `planned_input` vs `resolved_context` vs `tokens_saved` per step, and it is not an offline, embeddable artifact with no third-party egress. |
| **Capability rendering** | `lc_registry.get_capabilities_description` | The schema is generated by LangChain; the `ROLE:`/`INPUTS:` block the Planner reads is not. |
| **Plan governance** | `lc_engine.validate_plan` | No framework knows that *this* engine requires a blueprint before a Writer step. Architectural policy is domain knowledge; it has to be stated and checked. |

Two shims exist to work *around* the framework rather than to use it, and are
named as such in the source:

- `lc_helpers.base_model()` unwraps `RunnableRetry`, because `.with_retry()` does
  not forward `with_structured_output()` or `get_num_tokens()`.
- `lc_helpers._openai_client()` resolves a moderation client through three tiers,
  ending in a directly constructed `openai.OpenAI()`, so a change in
  `langchain-openai`'s internals degrades gracefully instead of disabling a
  guardrail. `openai` is therefore a **declared** dependency, not an accidental
  transitive one.

## Blueprint-first governance

The Semantic Blueprint is this engine's signature idea, and it is also the thing a
Planner will quietly skip. Left to itself, a model reads the Librarian as optional
and plans `Researcher -> Summarizer -> Writer` — producing competent content in an
arbitrary voice. In an early run of this notebook the Librarian was selected in
only **one plan out of five**.

> For a corporate demo this is the thing to fix, because the deck that best
> showcases your architecture is the one the Planner declines to use. One sentence
> in the Librarian docstring (`"Call this first whenever the goal asks for content
> to be written, rewritten, or styled"`) plus one line in the planner prompt would
> likely flip it. Cheap, and testable via `plan_only` with no spend.

That is what was done, in three layers — the third of which does not depend on the
model complying:

1. **`lc_agents.Librarian`** — the docstring *is* the interface the Planner reads.
   It now states that the Librarian must be called first for any written,
   rewritten or styled deliverable, and the Writer's docstring states that its
   `blueprint` argument must come from a preceding Librarian step.
2. **`lc_engine.PLANNER_PROMPT`** — instruction 4 declares a Writer step with no
   preceding Librarian step **invalid**; instruction 5 exempts pure
   retrieve/summarize goals so the rule does not over-trigger.
3. **`lc_engine.validate_plan()`** — a deterministic check on every plan. Prompt
   instructions are probabilistic; a governed deployment also needs the policy
   *verified*. It catches three conditions:

   | Finding | Meaning |
   |---|---|
   | `BLUEPRINT-FIRST VIOLATION` | the plan reaches the Writer with no Librarian before it |
   | `CHAINING GAP` | the Librarian ran, but its blueprint is not chained into the Writer |
   | `UNGROUNDED CONTENT` | the Planner wrote its own text into `facts`, `previous_content` or `text_to_summarize` instead of a `$$STEP_N_OUTPUT$$` reference |
   | `GROUNDING GAP` | the plan reaches the Writer with no Researcher behind it |
   | no Writer for a styled goal | the deliverable will be raw research or a summary |

### Why `UNGROUNDED CONTENT` matters most

A live run of this notebook produced the plan `Librarian -> Writer`, where the
Writer's `facts` argument held eleven lines of prose the **Planner had written
itself**. The engine executed it faithfully and returned a polished, on-brand,
entirely invented pitch — with no Sources section, having never touched the
knowledge base, never run the sanitizer, and never cited anything. The dashboard
reported `Success`.

That is the single worst failure this engine can produce, and it is invisible on
inspection because the prose is good. Instruction 6 of the planner prompt now
forbids authoring factual content, and `validate_plan` checks it rather than
trusting it: content arguments must be `$$STEP_N_OUTPUT$$` references, and a
Writer with no Researcher behind it is reported as a `GROUNDING GAP`.

Findings are recorded on `trace.plan_warnings` and rendered as an amber banner on
the dashboard. They **do not fail the run** — reporting, not enforcing, is the
right default for a teaching artifact. To enforce instead, return
`{"error": findings[0]}` from `plan_node` in `lc_engine.py`.

Section IV of the notebook contains a free regression test: one planning call per
goal, no retrieval, no generation, so prompt wording can be iterated on without
paying for full runs.

## Blueprint retrieval quality

Separate from *whether* the Librarian is called is *what it returns*. It retrieves
at `k=1` — one blueprint, no indication of how close the runner-up was. Over a
small `ContextLibrary` the nearest neighbour can be effectively arbitrary: a
request for *a formal structured legal summary* can return a **casual** blueprint,
and the Writer will then faithfully produce casual prose. The engine is working
correctly on a bad retrieval, which is the most expensive kind of failure to debug
in front of an audience.

`lc_helpers.blueprint_diagnostics(store, queries, k=3)` prints the top-k hits with
similarity scores and flags any selection whose margin over the runner-up is below
0.05. `check_index()` additionally warns when `ContextLibrary` holds fewer than
five blueprints. Both point at the same conclusion: **retrieval quality is an
ingestion problem, not an engine problem.**

`check_index()` also reports **near-miss namespaces** — names differing from an
engine namespace only by case, hyphens or underscores. Pinecone namespaces are
case-sensitive, so an index can hold both `ContextLibrary` and `context-library`
as entirely separate stores, and pointing the engine at the wrong one fails
silently.

This is reported as a `[NOTE ]` and **never blocks**. `describe_index_stats()`
cannot distinguish "the operator mistyped a namespace" from "another project
shares this index", and only you know which. Acting on a heuristic it cannot
adjudicate is how a diagnostic starts blocking healthy indexes.

That principle is enforced across the whole pre-flight:

| Severity | Condition | Blocks? |
|---|---|---|
| `[FAIL ]` | dimension mismatch — the vectors cannot be read at all | yes |
| `[EMPTY]` | an engine namespace has no vectors | yes |
| `[WARN ]` | fewer than five blueprints — retrieval will be weak | no |
| `[NOTE ]` | a near-miss namespace name exists | no |
| `[INFO ]` | vectors in namespaces the engine does not read | no |

Only conditions that make the engine **unable to run** block. Remediation advice
is printed for the condition that actually failed, never generically — a
dimension mismatch does not tell you to re-run the ingestion notebooks, and a
populated index is never told to populate itself.

## Behaviour deliberately preserved

- **Per-chunk sanitization.** The Researcher sanitizes each retrieved Document
  individually, skipping tainted chunks and continuing with the rest, aborting
  only if none survive. This is why the legal Control Deck still produces an
  answer when a chunk contains an injection attempt, and why the poisoned
  document never appears in the Sources list. Do not move this into middleware.
- **All system prompts** are copied verbatim from the original `agents.py`.
- **Retrieval depths** `k=1` and `k=3` match the original `top_k` values.
- **No temperature is set**, matching the original. Adding one makes output
  differences impossible to attribute.
- **Pre- and post-flight moderation**, on the goal and on the generated output.
- **The trace dashboard**, with its CSS unchanged.

## Guardrail semantics

Moderation distinguishes two findings that a regulated deployment must record
differently:

| `trace.status` | Meaning |
|---|---|
| `Halted: pre-flight moderation` | the goal was flagged |
| `Halted: moderation unavailable` | the check could not run; fail-safe applied |
| `Redacted: post-flight moderation` | output was produced, then withheld |

A trace is returned in all three cases. A blocked goal is an audit event, and an
audit trail with holes where the refusals should be is not an audit trail.

Plan governance findings are recorded on the same trace, in `plan_warnings`, and
rendered as an amber banner. A run can therefore be `Success` **and** carry a
policy finding — which is exactly the distinction a reviewer needs.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Retrieval returns 0 documents | Wrong or missing namespace | Case-sensitive: `ContextLibrary`, `KnowledgeStore` |
| Documents have empty `page_content` | Wrong `text_key` | `blueprint_json` vs `text` — they differ per namespace. The agents now log an explicit error |
| Answers irrelevant but not empty | Embedding model mismatch | Must be `text-embedding-3-small`; `check_index()` verifies the dimension |
| `KeyError` on a prompt fragment | Unescaped `{` in a prompt | Double every literal brace: `{{`, `}}` |
| Planner picks the wrong agent | Vague tool docstring | The docstring *is* the interface the model reads |
| Moderation blocks everything | Endpoint unreachable | Fail-safe is deliberate; the status reads *moderation unavailable*, not *flagged* |
| Planner skips the Librarian on a write/draft/pitch goal | The blueprint-first rule is not reaching the model | Should no longer occur; verify free with the Section IV regression cell. The dashboard shows an amber governance banner whenever it does |
| Output reads well but has no Sources section | The Planner authored `facts` itself instead of referencing a Researcher step | `validate_plan` raises `UNGROUNDED CONTENT` and `GROUNDING GAP`; the amber banner quotes the invented text |
| Retrieval returns valid but irrelevant results | A namespace differing only by case or hyphens exists in the same index | Pinecone namespaces are case-sensitive, so this fails silently. `check_index` flags near-miss names and fails the pre-flight when the near-miss holds more vectors |
| The right blueprint exists but the wrong one is retrieved | `k=1` over a small or undifferentiated `ContextLibrary` | `lc_helpers.blueprint_diagnostics()`. A margin under 0.05 means the choice is near-arbitrary — fix ingestion, not code |
| A Summarizer shows **EXPANDED** rather than SAVED | The summary was longer than its input | Expected on short passages. Not a broken counter |
| `check_index` total far exceeds the two namespaces | Earlier chapters wrote elsewhere in the same index | Normal, and now itemised in the pre-flight output |
| `langsmith.client: ... 403 Forbidden` | A `LANGSMITH_API_KEY` exists but is expired, revoked, or scoped to another workspace | `initialize_environment()` now validates the key and disables tracing if it fails. If it still appears, the tracer was cached — restart the runtime, or call `lc_utils.disable_langsmith()` |
| `[Sanitizer] Potential threat detected` | **Not an error** — a chunk matched an injection pattern | The defense working. The chunk is dropped, the source is named and not cited, and the run continues |
| `ImportError` after editing a `%%writefile` cell | Stale import cache | Restart the runtime |

## Extending the engine

- **Add an agent:** write a new `@tool` in `lc_agents.py`, return it from
  `build_agents`, add its name to `lc_engine.AGENT_NAMES` **and** the `Literal`
  in `PlanStep`, and add any new argument to `AgentInput`. `build_engine()`
  raises at assembly time if you forget one. The capabilities block updates
  itself.
- **Resume failed runs:** pass a checkpointer to `graph.compile()`.
- **Human approval before spend:** `engine.plan_only(goal)`, or LangGraph's
  `interrupt()` between the `plan` and `execute` nodes.
- **Upgrade paths not taken here:** `Store` for cross-run blueprint memory;
  `ContextualCompressionRetriever` and rerankers for a second relevance pass;
  `EnsembleRetriever` with BM25 for exact clause numbers; `MultiQueryRetriever`
  for recall; LangSmith datasets and evaluators to turn the Control Deck goals
  into a scored regression suite; `langchain-mcp-adapters` to expose the four
  specialists as real MCP servers.

## Verification

Three suites ship with this folder. Run all three before any change is committed:

```bash
python verify_regressions.py   # nothing previously fixed has been undone
python verify_engine.py        # behaviour is correct, against the real libraries
python verify_notebook.py      # notebook and modules are byte-identical, docs match code
```

`verify_engine.py` tests that behaviour is **correct**. `verify_regressions.py`
tests that behaviour which was *already* correct has not been **undone** — a
different question, and the one that actually bit this project.

During hardening, an edit that added a blueprint-first rule to the planner prompt
also deleted the sentence naming the canonical `Librarian -> Researcher -> Writer`
flow. The Researcher quietly dropped out of the default plan shape, and the engine
began producing fluent, on-brand, **entirely unsourced** deliverables that still
reported `Success`. The fix for the first defect created a worse second one, and
nothing in the test suite noticed, because every test asserted the new behaviour
rather than the old.

`verify_regressions.py` is the answer to that. It is a **ledger**: every fix made
in this project's history has an entry, entries are only ever added, and each is
re-asserted on every run. It includes ten *golden plan shapes* — four that must
always validate as compliant, six that must always be rejected, one of which is
the literal plan the broken build produced. It also asserts that the planner
prompt still names all four specialists, so no future edit can silently write one
of them out of the architecture again.

## Dependencies

See `requirements.txt`, generated from `lc_utils.PACKAGES`. Change both together.

`tenacity` and `tiktoken` are no longer needed directly: `.with_retry()` and
`usage_metadata` replace them.

---

Copyright 2025-2026, Denis Rothman. Companion to
*Context Engineering for Multi-Agent Systems* (Packt).
