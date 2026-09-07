# BUILD GUIDE — Context Engine in a Claude Project

Read this first. It takes about 20 minutes end to end, and nothing needs to run
on your machine.

---

## What changed from the last plan, and why

The earlier guide targeted Claude Code: a repo, Python validators, and hooks.
You can't run anything locally, so that substrate is out. This build targets
**Claude Projects on claude.ai**, which works identically on Team and on Pro, so
your downgrade in a couple of months changes nothing here.

The trade is honest and worth stating up front. In Claude Code the gates were
Python scripts with exit codes: a veto that could not be argued with. In a
Project, the gates are protocol files that Claude follows. That is weaker. What
you get in exchange is a system with no installation, no keys, no Pinecone, no
embedding model to keep in sync with an index, and a corpus you change by
swapping a markdown file. For your purpose — building the engine once and then
creating as many use cases as you want by managing data files — that is the
right trade.

## The 14 files

Three layers. Only the middle one changes when you change use case.

### Layer 1 — the kernel (1 file, pasted not uploaded)

| File | Where it goes |
|---|---|
| `01_PROJECT_INSTRUCTIONS.md` | paste its content into the Project's instructions box |

This must be always-on, not retrieved, which is why it is pasted rather than
uploaded. It is short on purpose.

### Layer 2 — the engine (5 files, upload once, never edit)

| File | Replaces |
|---|---|
| `10_ENGINE_CONSTITUTION.md` | your module docstrings and the notebook prose |
| `11_AGENT_ROSTER.md` | `agents.py` + `registry.py` capabilities block |
| `12_PLANNER_PROTOCOL.md` | `engine.py` `planner()` — upgraded to a DAG |
| `13_GOVERNANCE.md` | Gate 1 + Gate 2, `helper_sanitize_input`, moderation |
| `14_EXECUTION_AND_TRACE.md` | `context_engine()` executor + `ExecutionTrace` + dashboard |

**Not one of these five mentions marketing, legal, or any subject matter.** That
is the domain-agnostic core you asked for.

### Layer 3 — the domain pack (4 files, this is what you swap)

| File | Replaces |
|---|---|
| `20_DOMAIN_MANIFEST.md` | the `config` dict, the namespaces, the topology |
| `21_CONTEXT_LIBRARY.md` | `context_blueprints` from your ingestion notebook |
| `22_KNOWLEDGE_marketing.md` | `marketing_documents/` in the KnowledgeStore namespace |
| `23_KNOWLEDGE_legal.md` | the legal corpus, plus two test fixtures |

### Tooling (4 files, keep on your machine)

| File | Purpose |
|---|---|
| `40_CONTROL_DECK.md` | ready-to-paste goals. Replaces the Control Deck cells |
| `30_NEW_DOMAIN_PACK_TEMPLATES.md` | blank templates for the next use case |
| `50_Pack_Builder.ipynb` | Colab notebook: your documents folder in, packs out |
| `00_BUILD_GUIDE.md` | this file |

---

## Steps

### 1. Create the Project

claude.ai, left sidebar, **Projects**, **New project**. Name it
`Context Engine — Marketing`. Available on both Team and Pro.

### 2. Paste the kernel

Open `01_PROJECT_INSTRUCTIONS.md`, copy everything below the `---` line, and
paste it into the Project's instructions box. Save.

This is the only always-on text. Everything else is retrieved on demand, which
is why the kernel says *which files to read* rather than repeating them.

### 3. Upload the nine engine and pack files

Into the Project's knowledge area:

```
10_ENGINE_CONSTITUTION.md
11_AGENT_ROSTER.md
12_PLANNER_PROTOCOL.md
13_GOVERNANCE.md
14_EXECUTION_AND_TRACE.md
20_DOMAIN_MANIFEST.md
21_CONTEXT_LIBRARY.md
22_KNOWLEDGE_marketing.md
23_KNOWLEDGE_legal.md
```

**Do not upload** `00`, `01`, `30`, `40` or `50`. The kernel is pasted; the rest
are your tooling, and putting an operator console into the engine's knowledge is
how a control deck ends up being read as a policy.

The number prefixes matter: they make load order and precedence obvious to you
and to Claude when it cites a file.

### 4. Smoke test

New chat in the Project:

```
INSPECT
```

Expect the agent roster, the topology table, the blueprint index, and both
knowledge pack indexes. If a file is missing from that report, the upload did
not take.

Then, still cheap:

```
PLAN: Summarize the key points of the QuantumDrive Q-1.
```

Expect a JSON plan with a Librarian node and a `Marketing:Researcher` node, both
with no dependencies, both in wave 1. If you get a linear chain of three, the
planner defaulted to a chain; say so and it will re-plan. That habit is the
single most common failure and `12_PLANNER_PROTOCOL` states the rule twice
because of it.

### 5. Run the deck that matters most

From `40_CONTROL_DECK`, Deck 4:

```
RUN: What is the QuantumDrive's retail price in the United Kingdom, and what
discount do we offer education customers?
```

Neither fact is in any pack. Correct behaviour is a Researcher reporting a
negative finding and a Writer stating the material was unavailable. **If a price
appears, stop and fix it before doing anything else.** That is the fluent-and-
wrong failure your whole architecture exists to prevent, and it is the one that
looks like success.

### 6. Work through the rest of the decks

`40_CONTROL_DECK` has nine, ordered cheap and instructive first. Deck 7 is your
Chapter 7/8 injection test running live: it will drop one genuinely poisoned
document and one legitimate one, side by side, which is the honest picture of
what a blunt pattern list costs.

---

## Changing the use case

This is the part you actually asked for. Once step 3 is done, a new use case is
a new set of data files.

**Option A — by hand.** Write a new `20_DOMAIN_MANIFEST`, `21_CONTEXT_LIBRARY`
and one `22_KNOWLEDGE_<domain>` per domain, using
`30_NEW_DOMAIN_PACK_TEMPLATES`. Remove the old pack files from the Project,
upload the new ones, leave `10` through `14` untouched.

**Option B — from Colab.** Run `50_Pack_Builder.ipynb` against a folder of
`.txt` documents. It does what `Data_Ingestion_Marketing.ipynb` did, with
markdown packs as the destination instead of a Pinecone index: loads the
documents, screens them for injection before you ship them, drafts the index
descriptions, writes the packs, drafts the manifest, verifies every document is
reachable, and zips the result. No API keys, no quota, no embedding model.

Either way, the invariant holds: **files `10` through `14` never change.**

### One thing that does need care

In the Pinecone edition, relevance came from cosine similarity over embeddings.
Here it comes from an agent reading a one-line description in an INDEX table and
choosing. **So the description is the retrieval mechanism.** Write each one as
the intent a person would express, not as a filename. The pack builder
auto-drafts them so you have something to edit; edit them. A pack whose
descriptions were never reviewed will retrieve badly and it will not tell you.

---

## What this keeps from your engine

- The plan as an inspectable artefact, now a **DAG** rather than a linear chain
- Gate 1 before planning, at zero cost
- **Gate 2**, which your Chapter 6-8 edition did not have: cross-domain edges
  validated against a topology before anything runs
- Discovered concurrency: waves fall out of the graph
- Context Library vs Knowledge Store, and the two notions of relevance
- Two sanitisation sites, with per-document screening at the second
- The A2A seam: one Researcher, three domain registrations
- The trace, and the resolved input shown before the output
- All-or-nothing failure
- `plan_only` as `PLAN:`, and `execute_and_display` as `RUN:`

## What it costs

- **Governance is protocol, not code.** No exit codes. Claude follows the gates
  because the kernel says to, and a long conversation can drift. Mitigate by
  running `PLAN:` first on any new goal shape, and by re-reading the trace rather
  than trusting the artefact.
- **Concurrency is bookkeeping, not speed.** Waves tell you what was
  independent; they do not run faster. The value is the plan structure and the
  audit, not wall clock.
- **Retrieval is an index read.** Works well to roughly 40 documents per pack.
  Past that, split into more domains.
- **Token counts are estimates.** Useful as a signal about the Summarizer.
  Not accounting.
- **No moderation endpoint.** `13_GOVERNANCE` §1.2 is a content check performed
  by the model, which replaces the API call.

## The trade that does not change

Governability bought with adaptivity. The plan is fixed before execution begins.
If a Researcher discovers something that should change the shape of the work,
this engine will not change shape. That was the right trade in your notebook and
it is the right trade here.

---

*Ported from Context Engineering for Multi-Agent Systems, copyright 2025-2026
Denis Rothman.*
