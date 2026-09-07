# 12 — PLANNER PROTOCOL

One planning pass per run. It produces a plan and executes nothing.

## Output schema — exact, no extra keys, no missing keys

```json
{
  "nodes": [
    {
      "id": "unique_snake_case_id",
      "agent": "<exact agent name from 11_AGENT_ROSTER>",
      "domain": "<a domain declared in 20_DOMAIN_MANIFEST>",
      "input": { "<exact_input_key>": "<literal value or $$other_node_id$$>" },
      "depends_on": ["id_of_node_whose_output_this_node_needs"]
    }
  ]
}
```

Emit it as a single JSON code block, before anything runs, so it can be read
and refused.

## Rules

1. **`id`** — unique, snake_case, descriptive of what the node does.
2. **`agent`** — must be one of the exact names in the roster. Domain-qualified
   agents are written `Domain:Agent`, for example `Legal:Researcher`.
3. **`domain`** — must match the domain that agent is registered under in the
   manifest. Cross-domain edges are validated against the topology, and a wrong
   domain rejects the whole plan.
4. **`input`** — the exact input key names listed for that agent. No synonyms,
   no extra keys, no omissions.
5. **`depends_on`** — every node id whose output this node references via
   `$$ref$$`. Use `[]` when the node has no dependencies. A reference that is
   not declared here is a Gate 2 violation.
6. **References** — write `$$node_id$$` to consume another node's output. The
   reference is replaced by that node's **whole output object**, not by string
   interpolation. That is why the Writer and Summarizer accept several input
   shapes.
7. **Concurrency** — nodes with no dependencies run in the same wave. Add a
   dependency **only** when the input genuinely requires another node's output.

## The rule people get wrong

Rule 7 needs saying twice. Left to itself a planner emits a linear chain,
because most plans in most training data are linear. **Concurrency has to be
asked for.**

For every edge you are about to draw, ask: does this node actually consume that
node's output? If not, delete the edge. A Librarian and two Researchers working
on the same goal have nothing to say to each other and belong in wave 1
together.

## Shape heuristics

- The Librarian never has dependencies. It always starts immediately.
- Insert a Summarizer between a Researcher and the Writer whenever the research
  output is likely to be long, or whenever the Writer needs a filtered view of
  it rather than all of it. Give the Summarizer a real objective, not "summarize
  the text".
- One Researcher per domain per distinct question. Two questions to the same
  domain are two nodes and they run in parallel.
- Every plan that produces an artefact ends at a Writer.
- **Every node's output must be consumed by something, or be the artefact.**
  A node whose output goes nowhere is a planning error: it means a requirement
  in the goal was researched and then dropped before it reached the artefact.
  Check this before you emit the plan.

## Worked example

Goal: *"Write launch copy for the QuantumDrive that respects our
confidentiality obligations, citing sources."*

```json
{
  "nodes": [
    { "id": "voice",       "agent": "Librarian",            "domain": "General",
      "input": { "intent_query": "confident aspirational product copy for creative professionals" },
      "depends_on": [] },
    { "id": "product",     "agent": "Marketing:Researcher",  "domain": "Marketing",
      "input": { "topic_query": "QuantumDrive Q-1 specifications and customer pain points" },
      "depends_on": [] },
    { "id": "constraints", "agent": "Legal:Researcher",      "domain": "Legal",
      "input": { "topic_query": "confidentiality obligations and claims requiring review" },
      "depends_on": [] },
    { "id": "brief",       "agent": "Summarizer",            "domain": "General",
      "input": { "text_to_summarize": "$$product$$",
                 "summary_objective": "the benefit claims that are safe to publish, and the numbers that support them" },
      "depends_on": ["product"] },
    { "id": "copy",        "agent": "Writer",                "domain": "General",
      "input": { "blueprint": "$$voice$$",
                 "facts": "$$brief$$",
                 "previous_content": "$$constraints$$" },
      "depends_on": ["voice", "brief", "constraints"] }
  ]
}
```

Three nodes in wave 1. The legal constraints reach the artefact rather than
being retrieved and abandoned. Note the fan-in: two domains hand their output
to a General Writer, which the topology permits and which is the reason the
fan-in edges exist at all — see `13_GOVERNANCE`.

## After planning

State the plan's shape in one line before Gate 2 runs, so a wrong plan is
obvious at a glance:

`5 nodes, 3 waves, domains: General/Marketing/Legal, terminal: copy`
