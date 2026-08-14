# Universal Context Engine — LangChain Edition

The Universal Context Engine, ported onto **LangChain 1.x** and **LangGraph 1.x**,
reading the *same* Pinecone index, the *same* namespaces, and using the *same*
OpenAI models as the original.

This folder is the framework pole of the repository. `sovereign_ai/` is the
other: zero framework, zero external API, maximum control. Between them they
make one point, which is the point of the book:

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
| `lc_helpers.py` | `helpers.py` | model, embeddings, two vector stores, sanitizer, moderation, token tracking |
| `lc_agents.py` | `agents.py` | Librarian, Researcher, Summarizer, Writer as `@tool` LCEL chains |
| `lc_registry.py` | `registry.py` | toolkit; capabilities generated from tool schemas |
| `lc_engine.py` | `engine.py` | Plan schema, planner, LangGraph orchestrator, trace |
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
plan = engine.plan_only("Summarize the NDA and cite sources.")

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

Two shims exist to work *around* the framework rather than to use it, and are
named as such in the source:

- `lc_helpers.base_model()` unwraps `RunnableRetry`, because `.with_retry()` does
  not forward `with_structured_output()` or `get_num_tokens()`.
- `lc_helpers._openai_client()` resolves a moderation client through three tiers,
  ending in a directly constructed `openai.OpenAI()`, so a change in
  `langchain-openai`'s internals degrades gracefully instead of disabling a
  guardrail. `openai` is therefore a **declared** dependency, not an accidental
  transitive one.

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

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Retrieval returns 0 documents | Wrong or missing namespace | Case-sensitive: `ContextLibrary`, `KnowledgeStore` |
| Documents have empty `page_content` | Wrong `text_key` | `blueprint_json` vs `text` — they differ per namespace. The agents now log an explicit error |
| Answers irrelevant but not empty | Embedding model mismatch | Must be `text-embedding-3-small`; `check_index()` verifies the dimension |
| `KeyError` on a prompt fragment | Unescaped `{` in a prompt | Double every literal brace: `{{`, `}}` |
| Planner picks the wrong agent | Vague tool docstring | The docstring *is* the interface the model reads |
| Moderation blocks everything | Endpoint unreachable | Fail-safe is deliberate; the status reads *moderation unavailable*, not *flagged* |
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

## Dependencies

See `requirements.txt`, generated from `lc_utils.PACKAGES`. Change both together.

`tenacity` and `tiktoken` are no longer needed directly: `.with_retry()` and
`usage_metadata` replace them.

---

Copyright 2025-2026, Denis Rothman. Companion to
*Context Engineering for Multi-Agent Systems* (Packt).
