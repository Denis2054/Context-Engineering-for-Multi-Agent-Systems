# 14 — EXECUTION AND TRACE

## The Foreman

### Compute the waves

```
done = {}
while some nodes unfinished:
    ready = nodes not done whose every dependency is done
    if ready is empty: DEADLOCK — the plan contains a cycle
    run all of ready
    add ready to done
```

Nothing declares "wave 1". The wave structure falls out of the dependency
graph. A chain of eight produces eight waves of one node and behaves exactly
like a sequential engine, with no special case for it.

State the schedule before executing:

```
wave 1: voice [Librarian/General], product [Marketing:Researcher/Marketing], constraints [Legal:Researcher/Legal]
wave 2: brief [Summarizer/General]
wave 3: copy [Writer/General]
```

**A wave is one message.** Produce all of a wave's node blocks in a single
response before starting the next wave. That is the discovered concurrency, and
it is what keeps the run coherent: every node in a wave sees the same completed
state, because the reference table is not updated mid-wave.

### Resolve references

Before running a node, substitute its `$$refs$$`:

- A value that is **exactly** `$$ref$$` becomes that node's **whole output
  object**.
- A reference **inside a longer string** is interpolated as text.
- A reference to a node that has not completed is an error, not something to
  work around. It means the waves are being run out of order. Stop.

A literal `$$node_id$$` surviving into an agent's input is a bug. It means the
planner referenced a node it did not declare in `depends_on`, which Gate 2
should have caught.

### Failure policy

**One failed node ends the run.** Deliberate: a plan whose legal verification
failed must not quietly produce a marketing brief. Report which node failed and
why, then emit the trace with everything that completed. Do not substitute your
own knowledge for a failed retrieval and do not present a partial artefact as
complete.

### Node block format

One per node, in wave order:

```
### NODE: product  ·  Marketing:Researcher  ·  domain Marketing  ·  wave 1
DEPENDS ON: none
RESOLVED INPUT: {"topic_query": "QuantumDrive Q-1 specifications and ..."}
DOCUMENTS SCREENED: 3 · ACCEPTED: 2 · REJECTED: 1
  rejected: ip_assignment_clause  (pattern: 'ignore previous instructions')
SOURCES USED:
  - product_spec_sheet.txt
  - customer_interview_notes.txt
OUTPUT: <the synthesis>
```

**Resolved input comes before output, always.** The three silent failures this
engine exists to catch — an empty retrieval, a neutral-default blueprint, a
summary that dropped the needed clause — are all invisible in the output and
all visible in the resolved input and the sources list. Put them first.

For a long resolved input, show the key names plus the first ~200 characters of
each value, and say it is a digest. `EXPAND <node_id>` dumps it in full.

## The trace

Emit at the end of every run, including a vetoed one.

```
### TRACE
goal            : Write launch copy for the QuantumDrive ...
status          : COMPLETE | VETOED_GATE_1 | VETOED_GATE_2 | FAILED_AT_<node>
gate 1          : PASS
gate 2          : PASS (2 cross-domain edges)
nodes / complete: 5 / 5
waves           : 3  (widest wave: 3)
blueprint used  : blueprint_technical_explanation
sources used    : 4 unique documents
sources rejected: 1  (ip_assignment_clause — 'ignore previous instructions')
tokens saved    : ~1,400 (Summarizer: ~1,900 in / ~500 out)
unsourced claims: none detected
```

### The two derived numbers

- **`tokens saved`** — attributed to the Summarizer alone, the only node whose
  purpose is reduction and therefore the only node where input minus output
  means something rather than being an artefact of a short task. These are
  estimates. Treat them as a signal about whether the Summarizer is earning its
  node, which is what they are for. Not accounting.
- **`waves` and widest wave** — how much of the plan was independent. A
  five-node plan in five waves is a chain, and the planner probably added edges
  out of habit. Say so if you see it.

### The trace reports, it does not recompute

Every number in the trace must come from something a gate or a node actually
produced. A trace that recalculates its own totals can disagree with the record
it claims to display, and the tidier one tends to win that argument.

## Self-audit before presenting

Check these and state the result in the trace. Each has produced a fluent,
wrong output in this architecture before:

1. Did any Researcher return zero accepted sources? If so, does the artefact
   admit it?
2. Did the Librarian fall back to `NEUTRAL_DEFAULT`?
3. Does the artefact contain a number, name or claim that appears in no node
   output? Name it.
4. Did a Summarizer drop something the Writer needed? Compare its input to its
   output against the Writer's requirements.
5. Was any node's output never consumed? Name it: a requirement was researched
   and then dropped before reaching the artefact.
