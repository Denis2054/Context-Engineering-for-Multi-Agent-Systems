# 20 — DOMAIN MANIFEST

**This is the swap point.** Everything in files `10` through `14` is
domain-agnostic. To change what this engine does, replace this file and the
packs it points at. Nothing else moves.

Active configuration: **Marketing + Legal**

---

## Domains

| Domain | Knowledge pack | Purpose |
|---|---|---|
| `General` | `22_KNOWLEDGE_marketing` (fallback) | Orchestration, style, writing. Owns the Librarian, Summarizer and Writer. |
| `Marketing` | `22_KNOWLEDGE_marketing` | Product specs, competitor material, campaign briefs, customer research |
| `Legal` | `23_KNOWLEDGE_legal` | Contracts, confidentiality obligations, claim review requirements |

## Registered agents

| Agent name | Domain | Reads |
|---|---|---|
| `Librarian` | General | `21_CONTEXT_LIBRARY` |
| `Summarizer` | General | its input only |
| `Writer` | General | its input only |
| `Researcher` | General | `22_KNOWLEDGE_marketing` |
| `Marketing:Researcher` | Marketing | `22_KNOWLEDGE_marketing` |
| `Legal:Researcher` | Legal | `23_KNOWLEDGE_legal` |
| `Critic` | — | disabled |

To enable the Critic, move it into this table with domain `General`.

## Context Library

`21_CONTEXT_LIBRARY` — read by the Librarian, one blueprint per retrieval.

## Topology — Gate 2

Read each row as: *a node in this domain may hand its output to a node in any
of these domains.*

| Domain | May hand work to |
|---|---|
| `General` | `Legal`, `Marketing`, `Research`, `Compliance`, `Finance`, `HR` |
| `Legal` | `General`, `Compliance`, `Finance` |
| `Marketing` | `General`, `Research` |
| `Research` | *(nothing — terminal, never initiates)* |
| `Compliance` | *(nothing — terminal, never initiates)* |
| `Finance` | `Compliance` |
| `HR` | `Legal`, `Finance` |

**`Marketing -> Legal` is forbidden.** Marketing may not commission legal work.
It may consume Legal's findings only via a General node, which is the intended
shape: General commissions both, Legal reports back, General writes.

`Legal -> General` and `Marketing -> General` exist because of the fan-in
correction. Read that section of `13_GOVERNANCE` before removing them.

## Business rules — Gate 1

```
FORBIDDEN_TERMS = [
  "insider trading", "bypass compliance", "falsify", "backdate",
  "circumvent the gate", "guaranteed profit"
]
REQUIRED_TERMS = []          # empty = permissive
```

## Notes for this deployment

- Comparative performance claims against a named competitor require the Legal
  pack to be consulted. A plan that makes a comparative claim without a
  `Legal:Researcher` node is incomplete; say so at planning time.
- The Marketing pack contains one document (`competitor_press_release`)
  describing a **competitor's** product. Never present its figures as our own.
