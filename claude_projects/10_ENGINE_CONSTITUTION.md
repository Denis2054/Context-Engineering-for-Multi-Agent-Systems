# 10 — ENGINE CONSTITUTION

The philosophy. Domain-agnostic. Never edit this file to change use case.

## The core idea

Most agent systems decide what to do one step at a time. An LLM picks an
action, takes it, observes the result, and picks again. That loop is flexible
and it has one structural consequence: there is no artefact to inspect. By the
time anyone can see what the agent chose, it has already done it.

This engine inverts that. The planner emits the entire shape of the work as
JSON before any of it runs. Every distinctive property of this system follows
from that object existing:

| Because the plan exists as data | You get |
|---|---|
| edges are inspectable before execution | Gate 2 can refuse "Marketing may not initiate Legal work" before anyone acts |
| independence is visible | concurrency the scheduler discovers rather than being told |
| the plan can be produced without running | `PLAN:` mode, a full governance test for no execution cost |
| every node is named in advance | a per-node audit trail with resolved inputs and raw outputs |

The trade is real and it is stated plainly: **governability bought with
adaptivity**. This engine cannot re-plan when a node discovers something
surprising. For work that must produce an auditable artefact and refuse what it
is not permitted to do, that is the right trade. For open-ended exploration it
is not.

## The two stores

This is the idea that makes it a *Context* Engine rather than a RAG pipeline.
Two stores, two incompatible notions of relevance, kept apart on purpose.

| Store | Holds | Read by | How many | Why |
|---|---|---|---|---|
| **Context Library** | Semantic Blueprints: voice, structure, tone rules | Librarian | exactly **1** | Style. There is one right answer. |
| **Knowledge Packs** | Source documents: specs, contracts, notes | Researcher | up to **3** | Substance. Synthesis benefits from corroboration. |

Collapsing them would ask a single retrieval to serve two purposes at once.
Keeping them apart is what lets the Writer apply Marketing's voice to Legal's
facts without either contaminating the other.

## Your knowledge packs are an untrusted input channel

Screening happens in **two** places and the second is the one people forget.

1. **Gate 1**, on the user's goal, before planning.
2. **Inside the Researcher**, on every document it selects, individually,
   before that text enters its reasoning.

A goal-level check cannot protect you from a poisoned document, because the
poisoned text was never in the goal. It arrived later, out of your own corpus,
selected because it looked relevant. A document added six months ago can carry
an instruction that only fires when a retrieval happens to surface it.

Screening is **per-document, not all-or-nothing**. One poisoned document in a
three-document retrieval costs you that document, not the whole node. Only when
every candidate fails does the node give up, and then it says so.

## Domain agnosticism

Nothing in files `10` through `14` mentions marketing, legal, or any subject.
The engine knows about *domains* as an abstraction: named governance zones with
their own knowledge and their own permitted edges. A domain is declared in
`20_DOMAIN_MANIFEST` and nowhere else.

To change what this engine does, replace three files and nothing else:

- `20_DOMAIN_MANIFEST` — which domains exist and who may hand work to whom
- `21_CONTEXT_LIBRARY` — the blueprints
- `22_KNOWLEDGE_*` — the source documents

The roster, the planner, the gates, the executor and the trace do not move.
That is the whole design goal: build the engine once, then change the use case
by managing data files.

## The A2A seam

`Researcher`, `Legal:Researcher` and `Marketing:Researcher` are the **same
agent**. Nothing about their behaviour differs. What differs is the knowledge
pack they read and the governance edges Gate 2 enforces around their node.

That is deliberate. Today a cross-domain call is a role change inside one
conversation. When a domain moves behind its own service, only the dispatch
mechanism changes, because the roster and the topology were written against
domains rather than against processes.

## The failure this engine exists to prevent

A fluent, confident, plausible answer built on nothing.

A Researcher that retrieved zero documents, a Librarian that fell back to the
neutral blueprint, a Summarizer that dropped the clause the Writer needed. All
three produce polished output. None is visible unless someone can open the node
and read what actually went in. That is why the trace is mandatory and why the
resolved input is shown before the output.
