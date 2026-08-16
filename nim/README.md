# Universal Context Engine — DAG Edition · NIM

A governed, concurrent, multi-domain agent engine that **plans before it acts, validates the plan before it executes, and records everything it did**. All inference runs on NVIDIA NIM: a large model plans, a small fast model executes.

*Copyright 2025-2026, Denis Rothman*

---

## Table of contents

- [The core idea](#the-core-idea)
- [Quick start](#quick-start)
- [Prerequisite: populating the index](#prerequisite-populating-the-index)
- [Architecture](#architecture)
- [The two-model split](#the-two-model-split)
- [The nine modules](#the-nine-modules)
- [Key concepts](#key-concepts)
  - [The plan as an artefact](#1-the-plan-as-an-artefact)
  - [Two gates](#2-two-gates)
  - [Discovered concurrency and the semaphore](#3-discovered-concurrency-and-the-semaphore)
  - [Context Library vs Knowledge Store](#4-context-library-vs-knowledge-store)
  - [Your vector store is an untrusted input channel](#5-your-vector-store-is-an-untrusted-input-channel)
  - [The A2A seam](#6-the-a2a-seam)
  - [The storage contract](#7-the-storage-contract)
  - [The trace and the glass box](#8-the-trace-and-the-glass-box)
- [Configuration reference](#configuration-reference)
- [Notebook walkthrough](#notebook-walkthrough)
- [Extending the engine](#extending-the-engine)
- [Design trade-offs and limitations](#design-trade-offs-and-limitations)
- [Troubleshooting](#troubleshooting)
- [File manifest](#file-manifest)

---

## The core idea

Most agent systems decide what to do one step at a time. An LLM picks an action, takes it, observes the result, and picks again. That loop is flexible and it has one structural consequence: **there is no artefact to inspect**. By the time you can see what the agent chose, it has already done it.

This engine inverts that. A planner emits the *entire* shape of the work as JSON — every node, every domain, every dependency — before any of it runs:

```json
{"nodes": [
  {"id": "blueprint", "agent": "Librarian",  "domain": "General",
   "input": {"intent_query": "on-brand marketing brief"}, "depends_on": []},
  {"id": "legal",     "agent": "Researcher", "domain": "Legal",
   "input": {"topic_query": "confidentiality obligations"}, "depends_on": []},
  {"id": "market",    "agent": "Researcher", "domain": "Marketing",
   "input": {"topic_query": "QuantumDrive vs ChronoTech"}, "depends_on": []},
  {"id": "condense",  "agent": "Summarizer", "domain": "General",
   "input": {"text_to_summarize": "$$market$$",
             "summary_objective": "claims needing legal review"},
   "depends_on": ["market"]},
  {"id": "brief",     "agent": "Writer",     "domain": "General",
   "input": {"blueprint": "$$blueprint$$", "facts": "$$condense$$"},
   "depends_on": ["blueprint", "condense"]}
]}
```

Everything distinctive about this system follows from that object existing:

| Because the plan exists as data… | …you get |
|---|---|
| edges are inspectable before execution | **Gate 2** — refuse "Marketing may not initiate Legal work" *before* anyone acts |
| independence is visible | **concurrency** the scheduler discovers rather than being told |
| the plan can be produced without running | **`plan_only()`** — a full governance test for one LLM call |
| every node is named in advance | **per-node audit** with resolved inputs and raw outputs |

The trade is real and stated plainly throughout: **governability bought with adaptivity**. This engine cannot re-plan when a node discovers something surprising. For work that must produce an auditable artefact and refuse what it is not permitted to do, that is the right trade. For open-ended exploration, it is not.

---

## Quick start

**1. Populate the index** — see the [next section](#prerequisite-populating-the-index). Nothing works without it.

**2. Add secrets.** In Colab, the key icon in the left sidebar. Outside Colab, environment variables — the code checks Colab Secrets, then the environment, then prompts.

| Secret | Used for | Required |
|---|---|---|
| `NVIDIA_API_KEY` | all LLM inference — starts with `nvapi-` | yes |
| `PINECONE_API_KEY` | the vector store | yes |
| `API_KEY` | OpenAI: moderation, and embeddings on the default path | yes on the default path |

Free NVIDIA credits: **[build.nvidia.com](https://build.nvidia.com)**.

**3. Open `Universal_DAG_Engine_NIM.ipynb` and Run All.** CPU runtime — all inference is remote, no GPU needed.

The notebook is **standalone**. Nine `%%writefile` cells write the entire engine into the runtime's filesystem. Nothing is cloned, nothing is downloaded, and there is no private repository you need access to. The `.py` files in this repository are byte-identical to those cells, so you can equally `pip`-free drop them into your own project and import them.

---

## Prerequisite: populating the index

> **The index must already be populated.** Run these two notebooks first, in this order:
>
> 1. `Chapter08/Data_Ingestion.ipynb` — legal data.
> 2. `Chapter09/Data_Ingestion_Marketing.ipynb` — **with `clear_index=False`**, so marketing data is appended rather than replacing the legal data.

That second flag is not a detail. Without it, Chapter 9 *replaces* the legal corpus, and you end up with a Marketing-only index that passes a naive namespace check and fails every Legal query — while producing fluent output the whole time.

Section 3.2 of the notebook runs `utils.check_index()`, which blocks on exactly two conditions:

| Failure | Why it is dangerous |
|---|---|
| **Empty or missing namespace** | Zero matches is not an error. The Researcher reports "no data found", the Writer writes around the hole, and the dashboard is green. |
| **Dimension mismatch** | Either Pinecone rejects the query (loud, fine) or the dimensions coincide and you get similarity scores computed between two unrelated coordinate systems — confident retrieval that means nothing. |

Neither raises an exception on its own. That is precisely why the pre-flight check exists.

**This notebook writes nothing to Pinecone.** It only reads the vectors the ingestion notebooks created. No re-embedding, no new index.

---

## Architecture

```text
                          User Goal
                              │
                              ▼
      ┌───────────────────────────────────────────────────┐
      │  GATE 1 — before planning                         │
      │  sanitize → moderate → business rules             │
      │  A veto here costs zero tokens                    │
      └───────────────────────────────────────────────────┘
                              │ PASS
                              ▼
      ┌───────────────────────────────────────────────────┐
      │  PLANNER  →  NIM Nemotron Super (120B)            │
      │  Emits the whole plan as JSON:                    │
      │  {id, agent, domain, input, depends_on}           │
      └───────────────────────────────────────────────────┘
                              │
                              ▼
      ┌───────────────────────────────────────────────────┐
      │  GATE 2 — the plan exists, nothing has run         │
      │  Every cross-domain edge checked against the       │
      │  governance topology. Cost of a veto: one call     │
      └───────────────────────────────────────────────────┘
                              │ PASS
                              ▼
      ┌───────────────────────────────────────────────────┐
      │  FOREMAN  (run_dag_nim.py)                        │
      │  while unfinished:                                │
      │      ready = deps satisfied                       │
      │      run ready concurrently, Semaphore(4)         │
      │                                                    │
      │   wave 1   [Librarian]  [Legal:Res]  [Mkt:Res]    │
      │                 │            │           │         │
      │   wave 2        │            └─→ [Summarizer]     │
      │                 │                     │            │
      │   wave 3        └───────────────→ [Writer]        │
      │                                                    │
      │  agent calls → NIM Nemotron Nano (30B)            │
      │  retrieval   → Pinecone                            │
      └───────────────────────────────────────────────────┘
                              │
                              ▼
              final_output  +  ExecutionTrace
```

Nothing in the code declares "wave 1". The Foreman recomputes which nodes are ready on every pass, and the wave structure falls out of the dependency graph. A chain of eight produces eight waves of one node and behaves exactly like a sequential engine — with no special case for it.

---

## The two-model split

| Layer | Model | Called | Why this size |
|---|---|---|---|
| **Planner** | `nvidia/nemotron-3-super-120b-a12b` | once per run | Must emit valid JSON whose agent names and input keys match the registry exactly. Hard structured output, and a malformed plan wastes every downstream call. |
| **Agents** | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | once per node | Narrow, self-contained tasks. A sparse 30B model activating ~3B parameters per token gives most of the quality at a fraction of the latency — and latency dominates when four nodes run at once. |
| **Embeddings** | `text-embedding-3-small` (OpenAI) | once per retrieval | Must match the vectors already in your index. |
| **Moderation** | OpenAI `/moderations` | once per goal | The one call with no NVIDIA equivalent. |

On an eight-node DAG that is **one expensive call and eight cheap ones**, instead of nine expensive ones.

The entire mechanism is one optional parameter. `registry.get_handler(..., agent_model=...)`: when `None`, agents use whatever the planner uses (single-model, the OpenAI-edition behaviour); when set, the planner keeps `generation_model` and every agent gets `agent_model`.

> **Model IDs drift.** These are the IDs configured in `utils_nim.py`. If `verify_nim_connectivity()` reports HTTP 404, run `utils.list_nim_models(nim_client)` — it asks the endpoint what your key can actually reach rather than trusting a constant.

---

## The nine modules

| File | Layer | Responsibility |
|---|---|---|
| `utils_nim.py` | infrastructure | installation, secret resolution, the three clients, connectivity probe, index pre-flight, embedding-backend resolution |
| `helpers_nim.py` | transport | **every** outbound call (four of them), retry policy, reasoning-output normalisation, guardrails, token accounting |
| `agents_nim.py` | agents | Librarian, Researcher, Summarizer, Writer |
| `adapters_nim.py` | storage | the four-promise contract and its Pinecone implementation |
| `registry_nim.py` | routing | the agent catalogue, the planner's capabilities block, dual-model routing |
| `harness_nim.py` | governance | Gate 1 (business rules) and Gate 2 (topology) |
| `run_dag_nim.py` | execution | the Foreman: readiness scheduling, the async semaphore, the A2A seam |
| `engine_nim.py` | orchestration | planner, `ExecutionTrace`, `context_engine`, `plan_only` |
| `dashboard_nim.py` | observability | glass-box HTML renderers |

Dependency order (this is also the `sys.modules` registration order in §2.3 of the notebook, and reordering it breaks the imports):

```
utils → helpers → agents → adapters → registry → harness → run_dag → engine
```

### Why raw HTTP instead of the SDK

Every API call in the system is a `requests.post` to a documented JSON contract. The OpenAI Python SDK is versioned against OpenAI's own surface; pointing it at a compatible third-party endpoint works until a minor release changes request serialisation, at which point a runtime that silently upgraded a transitive dependency throws import-time errors unrelated to your code.

The cost is that `helpers_nim.py` handles retries and error mapping itself. The benefit is that **the same three functions drive NVIDIA, OpenAI, a self-hosted vLLM, or an Ollama instance** with no branch beyond the base URL carried on the client object. The `openai.OpenAI` objects are still used — purely as credential holders. No SDK method is ever called.

---

## Key concepts

### 1. The plan as an artefact

`planner()` makes one call and returns a list of node dicts. The `$$node_id$$` placeholders are resolved at execution time by `resolve_inputs()`, which substitutes the **whole output object** of the referenced node — not a string interpolation. That is why the Writer and Summarizer accept several input shapes: they receive whatever the upstream node happened to return.

Three rules in the planner prompt exist because of specific, reproducible failures:

- **Exact input keys.** The resolver looks up literal dictionary keys. `"query"` where the agent expects `"topic_query"` fails at execution, after the planning call is already paid for.
- **Matching domains.** Gate 2 validates against declared domains; a wrong one costs a whole planning call.
- **Do not chain unnecessarily.** Left to itself a planner emits a linear chain, because most plans in most training data are linear. **Concurrency has to be explicitly asked for.**

### 2. Two gates

**Gate 1 — before planning.** Three checks in ascending order of cost, so the cheapest rejection happens first and the network call is skipped for a goal that was never going to pass:

1. `helper_sanitize_input()` — regex screen, free and local
2. `helper_moderate_content()` — OpenAI moderation, the only networked check
3. business rules — `FORBIDDEN_TERMS` / `REQUIRED_TERMS`

A veto here costs **zero LLM tokens**.

**Gate 2 — after planning, before execution.** This is the gate a ReAct-style loop cannot have. Every cross-domain edge is checked against `TOPOLOGY_DAG`:

```python
TOPOLOGY_DAG = {
    "General"    : ["Legal", "Finance", "HR", "Marketing", "Research", "Compliance"],
    "Legal"      : ["General", "Finance", "Compliance"],
    "Finance"    : ["Compliance"],
    "HR"         : ["Legal", "Finance"],
    "Marketing"  : ["General", "Research"],
    "Research"   : [],          # terminal — never initiates
    "Compliance" : [],          # terminal — never initiates
}
```

Read each entry as *"a node in this domain may hand its output to a node in any of these domains."*

**The fan-in correction.** `Legal → General` and `Marketing → General` exist because of a bug worth understanding, since the same mistake recurs in every rules engine of this shape. The intent is to stop one department *commissioning* work from another. But a Legal Researcher whose findings flow into a General Writer is not commissioning anything — it is *reporting back*. The data flows Legal → General while the authority flowed General → Legal.

Without those two edges, Gate 2 vetoed **every** useful multi-domain plan, because every useful multi-domain plan fans back in to a General Writer. The rule was enforcing the letter of a policy against the direction of its intent.

### 3. Discovered concurrency and the semaphore

The Foreman's loop is four lines of idea:

```python
while done != all_ids:
    ready = [n for n in dag if n.id not in done and all(d in done for d in n.depends_on)]
    if not ready: raise RuntimeError("cycle")      # deadlock detection
    run(ready)                                      # concurrently
```

**Limiting concurrency makes it faster.** This is the counter-intuitive part. `ThreadPoolExecutor(max_workers=len(nodes))` fires every ready node simultaneously. Against a ~40 RPM ceiling, four requests in the same millisecond collect four `429`s, and the exponential backoff that was supposed to save you serialises everything anyway — so you pay full latency *plus* the retries.

`asyncio.Semaphore(4)` turns that burst into a queue. A fifth node waits for a slot instead of being rejected, and waiting for a slot is strictly cheaper than backing off.

Two details in the async path are load-bearing:

- **The semaphore wraps the API call only.** A slot frees the instant a response returns, not at the end of the wave.
- **The commit is deferred.** Nodes write to a local dict during a wave; `completed_outputs` is updated only after `gather()` returns. This keeps the reference table immutable while `resolve_inputs()` reads it, removing a race that would appear only under load and only sometimes.

The original `ThreadPoolExecutor` implementation is preserved at the bottom of `run_dag_nim.py`, unused. Diffing the two is the clearest statement of what changed.

`asyncio.to_thread` bridges the two models: async for admission control, threads for the blocking `requests.post`.

### 4. Context Library vs Knowledge Store

Two namespaces, two notions of relevance, and the split is the core idea of a *Context* Engine:

| Namespace | Holds | Retrieved by | `top_k` | Why |
|---|---|---|---|---|
| `ContextLibrary` | Semantic Blueprints — brand voice, structure, tone | Librarian | **1** | Style. There is one right answer. |
| `KnowledgeStore` | Source documents — specs, contracts, releases | Researcher | **3** | Substance. Synthesis benefits from corroboration. |

Collapsing them would ask a single similarity search to serve two incompatible notions of relevance. Keeping them apart is what lets the Writer apply **Marketing's voice to Legal's facts** without either contaminating the other.

### 5. Your vector store is an untrusted input channel

Sanitisation runs in **two** places, and the second is the one people forget:

1. **Harness Gate 1**, on the user's goal, before any model is called.
2. **Inside `agent_researcher`**, on **every chunk retrieved from Pinecone**, individually, before those chunks are pasted into a prompt.

A goal-level check cannot protect you from a poisoned document, because the poisoned text was not in the goal — it arrived later, from your own vector store, selected by a similarity search. A document ingested six months ago can carry an instruction that only detonates when a retrieval happens to surface it.

Screening is **per-chunk, not all-or-nothing**. One poisoned paragraph in a three-chunk retrieval costs you that paragraph, not the whole node. Only when *every* chunk fails does the agent give up — and it says so explicitly rather than returning a confident answer built on nothing.

The Legal fixture ingested in Chapter 8 contains exactly such a chunk. Section 7.2 of the notebook is where you watch it get dropped.

**On precision.** `INJECTION_PATTERNS` is deliberately blunt and over-triggers. `act as` will match a contract clause reading *"this schedule shall act as an addendum"*, and that chunk gets dropped. That is the correct default for a teaching system — a visible false positive is a lesson, a missed injection is not — but it is a real trade-off. In production you would tighten the patterns and **log every rejection for review** rather than dropping silently.

### 6. The A2A seam

Three registry keys — `Researcher`, `Legal:Researcher`, `Marketing:Researcher` — point at the **same function**. Nothing about the code differs. What differs is the namespace the adapter resolves and the governance edges the Harness enforces.

Today a "cross-domain call" is a dictionary lookup in one process. When Legal moves behind its own service, the change is confined to `dispatch_node()` in `run_dag_nim.py`: the lookup becomes an HTTP POST. The planner, the capabilities block, and the topology rules do not move — **they were written against domains rather than processes**.

`dispatch_node()` logs every cross-domain hop, so you can see exactly where the network boundary would fall.

### 7. The storage contract

The engine never imports `pinecone`. It holds an adapter with four methods:

| Promise | Status | Why |
|---|---|---|
| `search_meaning(query, namespace, top_k)` | implemented | semantic vector search |
| `search_exact(filter, namespace)` | **raises** | Pinecone free tier has no metadata filtering |
| `read_state(key)` | **raises** | Pinecone is a vector store, not a key/value store |
| `write_state(key, value)` | **raises** | same |

Declaring promises you have not kept is deliberate. Omitting them means a future `OracleAdapter` invents its own names and nothing composes. Declaring them means the contract is visible now, and any path reaching for a missing capability **fails loudly with a message naming what to wire in**.

`read_state` / `write_state` matter more than they look: they are where the Foreman's in-memory `completed_outputs` dict becomes a **state of record** the moment execution distributes across machines. The seam is named `[PLANE 1 SEAM]` in `run_dag_nim.py`.

### 8. The trace and the glass box

`ExecutionTrace` is built **during** the run, not reconstructed from logs afterwards. It records both gate verdicts, the plan, and every node's resolved input, raw output, token counts, and duration.

The dashboard renders it and computes **nothing**. That constraint is what makes it trustworthy — a dashboard that recalculates its own totals can disagree with the audit record it claims to display, and the pretty one usually wins that argument.

The failure it exists to prevent is a **confident answer built on nothing**: a Researcher that retrieved zero chunks, a Librarian that fell back to a neutral blueprint, a Summarizer that discarded the clause the Writer needed. All three produce fluent, plausible output. None is visible unless you can open the node and read what actually went in.

Two derived metrics are worth knowing:

- **`tokens_saved`** — attributed to the Summarizer alone, the only node whose purpose is reduction and therefore the only node where input-minus-output is meaningful rather than an artefact of a short task.
- **`wall_clock_saved_s`** — the sum of every node's duration minus actual elapsed time. Roughly zero on a sequential DAG; on a concurrent one it is exactly what the scheduler bought you.

Output is plain inline-styled HTML — no CSS, no JavaScript, no CDN. It renders identically in Colab, JupyterLab, VS Code, and a saved `.html` export.

---

## Configuration reference

### Embedding backend — the one setting where a mistake is silent

A Pinecone index stores vectors of a fixed width produced by one specific model. Query vectors must come from that same model, or you get either a rejected query (loud) or similarity scores computed between two unrelated coordinate systems (silent, and dangerous).

```python
EMBEDDING_BACKEND = "openai"    # notebook §3.1
```

| Value | Index | Model | Dim | Embedding client | Requires |
|---|---|---|---|---|---|
| `"openai"` *(default)* | `genai-mas-mcp-ch3` | `text-embedding-3-small` | 1536 | `openai_client` | nothing — this is what Ch8/Ch9 built |
| `"nvidia"` | `genai-mas-mcp-nim` | `nvidia/nv-embedqa-e5-v5` | 1024 | `nim_client` | re-ingesting with NVIDIA vectors |

`utils.resolve_embedding_backend()` returns index name, model, dimension, and which client to use as one bundle, so the four values cannot drift apart.

**The default does not compromise the NIM migration.** *All* inference — planning and every agent call — still runs on NIM. Only the embedding call touches OpenAI, and only because re-indexing a corpus to save one API call per retrieval is a poor trade.

Switching to `"nvidia"` requires re-ingestion. Note that NVIDIA's retrieval embedders are **asymmetric** — they encode a question and a document differently — so ingestion must use `input_type="passage"` and retrieval `input_type="query"`. `get_embedding()` handles the query side automatically and never sends `input_type` to OpenAI, which rejects unknown arguments with a 400.

### Constants (`utils_nim.py`, Section A)

| Constant | Default | Effect |
|---|---|---|
| `NIM_PLANNER_MODEL` | `nvidia/nemotron-3-super-120b-a12b` | one call per run |
| `NIM_AGENT_MODEL` | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` | one call per node |
| `NIM_EMBEDDING_MODEL` | `nvidia/nv-embedqa-e5-v5` | only on the `"nvidia"` backend |
| `NIM_MAX_CONCURRENT` | `4` | semaphore cap. Raise to 8+ on a paid tier — nothing else changes |
| `NIM_BASE_URL` | `https://integrate.api.nvidia.com/v1` | point at a self-hosted NIM container to run fully on-prem |

### Governance (`harness_nim.py`)

| Constant | Purpose |
|---|---|
| `TOPOLOGY_DAG` | which domain may hand work to which |
| `FORBIDDEN_TERMS` | Gate 1 substring veto list |
| `REQUIRED_TERMS` | Gate 1 allow-list. Empty = permissive. Populate to restrict the engine to a subject area |
| `INJECTION_PATTERNS` | in `helpers_nim.py` — the regex screen used by both sanitisation sites |

---

## Notebook walkthrough

| Section | What happens | Cost |
|---|---|---|
| **I.** The engine, written to disk | Nine `%%writefile` cells. Text only — no imports, no network, no credentials | free |
| **II.** Bootstrap | install → clients → `sys.modules` wiring → connectivity probe | ~20 tokens |
| **III.** Configuration | embedding backend → index pre-flight → adapter → Harness | one metadata request |
| **IV.** The glass box | import the dashboard renderers | free |
| **V.** The Engine Room | define `execute_and_display()` | free |
| **VI.** Plan without executing | `plan_only()` — both gates real, nothing runs | **1 call** |
| **VII.** Control Decks | seven runs, cheap and instructive first | varies |
| **VIII.** Inspector | live registry, topology, adapter — no run needed | free |
| **IX.** Export the trace | persist `trace.summary()` as JSON | free |
| **X.** Trade-offs | what the design buys and what it costs | — |
| **XI.** Troubleshooting | failure → cause → fix | — |

### The `sys.modules` bridge (§2.3)

The engine's internal modules import each other by **short name**: `engine_nim.py` contains `from helpers import call_llm_robust`, not `from helpers_nim import ...`. That is intentional — the same source works unchanged whether the file on disk is `helpers.py` (a plain checkout) or `helpers_nim.py` (this notebook, where the suffix keeps the NIM edition from colliding with the OpenAI edition in one directory).

```python
import helpers_nim ; sys.modules["helpers"] = helpers_nim
```

Registering the module under its short name means that when `engine_nim` later runs `from helpers import ...`, Python finds it in the cache and never touches the filesystem.

**Order is not optional.** Each module must be registered *before* any module that imports it at top level is itself imported. Reversing two lines produces a `ModuleNotFoundError` naming a file that does not exist.

### The Control Decks (§VII)

| Deck | Demonstrates | What to watch |
|---|---|---|
| 7.1 Smoke test | the whole path is alive | resolved inputs — a literal `$$node_id$$` means a broken reference |
| 7.2 Legal | **per-chunk injection screening** | the poisoned document absent from the Sources list |
| 7.3 Marketing | the A2A seam | same function, different domain badge |
| 7.4 Gate 1 veto | zero-cost refusal | all token pills at zero, no node cards, and a *stated reason* |
| 7.5 Gate 2 veto | governing a **plan**, not an action | the named edge; then `Legal → General` fan-in passing |
| 7.6 Canonical run | five domains, concurrent | wave-1 node count, domain colours, `Saved by concurrency`, the Writer's confluence |
| 7.7 Free-form | your goal | — |

---

## Extending the engine

### Add an agent

Three edits, and the third is the one people miss:

1. Write the function in `agents_nim.py` — takes an MCP envelope, returns an MCP envelope.
2. Register it in `AgentRegistry.__init__` with its `fn` and `domain`, and add a closure branch in `get_handler()` matching its signature.
3. **Describe it in `get_capabilities_description()`** with its exact input key names. The planner's entire view of the world is that string — an agent not described there will never appear in a plan.

Test with `plan_only()`: one call tells you whether the planner picked it up.

### Add a domain

1. Add it to `NAMESPACE_MAP` (notebook §3.3) with its context and knowledge namespaces.
2. Add it to `TOPOLOGY_DAG` in `harness_nim.py`, and add it as a permitted target wherever other domains should be able to reach it.
3. Register domain-qualified agents (`"Finance:Researcher"`).
4. Describe them in the capabilities block.
5. Optionally add a colour to `DOMAIN_COLORS` in `dashboard_nim.py`.

An unregistered domain degrades to General with a warning rather than crashing — a planner hallucinating a domain should produce a usable run and a visible warning.

### Tighten governance

Pass a stricter graph rather than editing the default, so per-deployment policy stays out of the module:

```python
gate = Harness(client=openai_client, topology={
    "General"  : ["Legal"],
    "Legal"    : ["General"],
    "Marketing": [],          # can be read from, can initiate nothing
})
```

### Scale concurrency

`NIM_MAX_CONCURRENT = 4 → 8` in `utils_nim.py`. Nothing else changes. Or override per run: `execute_and_display(goal, max_concurrent=8)`.

### Swap the storage backend

Subclass `StorageAdapterBase`, implement all four promises, and pass it where `PineconeAdapter` goes. The engine never learns which backend it is talking to. Implementing `search_exact` unlocks structured filtering; implementing `read_state`/`write_state` unlocks distributed execution.

### Distribute a domain

Add one branch to `dispatch_node()`:

```python
if node_domain != local_domain and node_domain in REMOTE_DOMAINS:
    return requests.post(f"{REMOTE_DOMAINS[node_domain]}/run",
                         json={"node": node, "input": resolved_input}).json()
```

Then implement `read_state`/`write_state` so node outputs survive beyond one process. Nothing else in the codebase moves.

### Run fully on-premises

Point `NIM_BASE_URL` at a self-hosted NIM container. Because the transport is raw HTTP with no SDK coupling, the engine runs identically on a laptop, a server, Kubernetes, or DGX Cloud.

---

## Design trade-offs and limitations

Stated plainly, because the trade is real.

**The plan is fixed before execution begins.** If a Researcher discovers something that should change the shape of the work, this engine will not change shape. Re-planning on new information is a genuine capability of ReAct-style loops that this design gives up. **Governability bought with adaptivity.**

| Limitation | Rationale / consequence |
|---|---|
| **Failure is all-or-nothing** | One failed node aborts the run. Deliberate — a DAG whose Legal verification failed must not quietly produce a marketing brief. The trace keeps everything that completed. |
| **Token counts are estimates** | `tiktoken` implements OpenAI's vocabularies; Nemotron tokenises differently. The *ratios* are sound; the absolute numbers are not a bill. |
| **Three of four storage promises raise** | Structured filtering and distributed state both need a backend the Pinecone free tier does not provide. |
| **Moderation fails open** | A network failure returns "not flagged" with `available=False` in the audit trail. An outage should not silently reject every goal. A regulated deployment would invert this and fail closed. |
| **The sanitizer over-triggers** | Blunt regexes drop legitimate chunks. Right default for teaching; tighten and log in production. |
| **Single-process** | The A2A seam is marked and not crossed. |
| **Moderation requires OpenAI** | No NVIDIA equivalent exists. Gate 1's other two checks are local and always apply. |

---

## Troubleshooting

### Setup

**`NVIDIA_API_KEY must start with 'nvapi-'`** — the secret is missing, misnamed, or not a NIM key. `_get_secret()` already strips whitespace and takes the first line, so a pasted newline is handled.

**`Client.__init__() got an unexpected keyword argument 'proxies'`** — a clash between `openai` and `httpx`, not a key problem. `openai < 1.55.3` passes `proxies=` to `httpx.Client`; `httpx 0.28` removed it. `install_dependencies()` specifies `openai>=1.55.3` as a **floor, not an exact pin** — pinning an old version downgrades a working Colab environment into the broken combination. `initialize_nim_clients()` also falls back to a plain credential object if the SDK cannot be constructed, so you should not need a runtime restart.

**`Pinecone client failed to initialise` when the Pinecone key is fine** — each client is built in its own `try` block precisely so one failure cannot null the others. Read the `FAIL` line in the output rather than the assertion that follows it.

**`ModuleNotFoundError: No module named 'helpers'`** — §2.3 was skipped, or the runtime restarted after it. Re-run it. If you reordered its lines, restore the original order.

**`%%writefile` ran but the import still fails** — the magic must be the **very first line** of the cell. A blank line or comment above it and no file is written. Check with `!ls -la *.py`.

### Connectivity

| Status | Cause | Fix |
|---|---|---|
| `401` | key invalid or expired | regenerate at build.nvidia.com |
| `402` | credits exhausted | check your balance |
| `404` | model ID moved | `utils.list_nim_models(nim_client)`, update the constants |
| `429` | rate limit (~40 RPM free) | lower `NIM_MAX_CONCURRENT`, or wait 60s |

### Index and retrieval

**Dimension mismatch** — index and embedding model disagree. Switch `EMBEDDING_BACKEND` or point `INDEX_NAME` at the matching index. 1536 = `text-embedding-3-small`; 1024 = `nv-embedqa-e5-v5`.

**Empty namespace** — ingestion has not run, or ran against a different index. Run Ch8, then Ch9 **with `clear_index=False`**.

**Retrieval returns irrelevant results and nothing errors** — almost always the embedding client and index disagreeing in a dimension-compatible way. Re-run §3.1 and §3.2, then expand a Researcher node and read the retrieved text.

**`Embedding endpoint rejected the payload`** — an OpenAI client was handed an `nvidia/*` model or vice versa. Do not set `embedding_client` by hand; let `resolve_embedding_backend()` do it.

### Planning

**`No parseable JSON in model output`** — `extract_json()` already handles `<think>` blocks, fences, and leading commentary, so this means no JSON at all, usually an empty completion. Check connectivity, then isolate with `plan_only()`.

**The plan is a linear chain** — the planner defaulted to a chain despite rule 7. Phrase independent requirements explicitly. If it persists, the capabilities block is the lever.

**Gate 2 vetoes a reasonable-looking plan** — read the named edge. Either the planner assigned a wrong domain, or the topology is genuinely too strict. Fix the topology; do not disable the gate.

**A resolved input contains a literal `$$node_id$$`** — the planner referenced a node without declaring it in `depends_on`. The validator logs this at run start; search for `[Validator]`.

### Execution

**`asyncio.run() cannot be called from a running event loop`** — `nest_asyncio` was not applied. Re-run §2.1. The Foreman falls back to a worker thread, so this should not surface; if it does, restart the runtime.

**`DEADLOCK — the DAG contains a cycle`** — the planner produced a circular dependency. Re-run, or inspect first with `plan_only()`.

**A node fails and the whole run aborts** — by design. The trace holds every node that completed; the message names the node and agent.

### Output

**The final output is fluent and wrong** — the most important failure, and the reason for the glass box. Expand each node in order and read the resolved inputs. Usual causes: the Researcher retrieved nothing (check Sources), the Librarian fell back to the neutral default (look for `"Generate the content neutrally"`), or the Summarizer dropped the clause the Writer needed (compare its input to its output).

**Post-flight moderation redacted the output** — Gate 1 screens the *input*, this screens the *output*. Different checks against different text. Set `moderation_active=False` to see the raw generation.

---

## File manifest

```
Universal_DAG_Engine_NIM.ipynb   the notebook — standalone, writes all nine modules
README.md                        this file

utils_nim.py                     infrastructure, secrets, clients, pre-flight
helpers_nim.py                   transport, retries, guardrails, token accounting
agents_nim.py                    Librarian, Researcher, Summarizer, Writer
adapters_nim.py                  storage contract + PineconeAdapter
registry_nim.py                  agent catalogue, capabilities, dual-model routing
harness_nim.py                   Gate 1 and Gate 2
run_dag_nim.py                   the Foreman — scheduling and concurrency
engine_nim.py                    planner, ExecutionTrace, context_engine, plan_only
dashboard_nim.py                 glass-box HTML renderers
```

The `.py` files are byte-identical to the notebook's `%%writefile` cells. Run the notebook as-is, or import the modules into your own project.

### Runtime dependencies

`openai>=1.55.3` (credential objects only), `pinecone`, `requests`, `tenacity`, `tiktoken`, `nest_asyncio`. Installed by `utils.install_dependencies()`.

The `openai` version is a **floor rather than an exact pin**, because `openai < 1.55.3` is incompatible with `httpx >= 0.28`. And since the engine only ever reads `.base_url` and `.api_key` off a client object, `initialize_nim_clients()` substitutes a five-line `APICredentials` stand-in when the SDK cannot be constructed at all — a dependency the engine does not use should not be able to stop it starting.

### Related notebooks

| Notebook | Relationship |
|---|---|
| `Chapter08/Data_Ingestion.ipynb` | **prerequisite** — legal corpus |
| `Chapter09/Data_Ingestion_Marketing.ipynb` | **prerequisite** — marketing corpus, `clear_index=False` |
| `Universal_Context_Engine_LangChain.ipynb` | the same Context Engine layer on a LangChain/LangGraph substrate |

---

*Copyright 2025-2026, Denis Rothman*
