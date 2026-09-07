# 21 — CONTEXT LIBRARY

Semantic Blueprints. **HOW** to write, never what is true. The Librarian reads
the INDEX, picks the single best match against the `INTENT` text, and returns
that blueprint's JSON body.

Write `INTENT` as the intent a person would express, not as a filename. It is
the only thing the Librarian matches against.

## INDEX

| Blueprint id | INTENT — choose this when the goal wants... |
|---|---|
| `blueprint_brand_voice` | on-brand marketing copy: clear, confident, aspirational, benefit-led. The house voice. |
| `blueprint_technical_explanation` | a technical explanation or analysis: objective, structured, precise. Breaking down a mechanism or summarising findings. |
| `blueprint_casual_summary` | a quick, casual, easy-to-read summary. Brevity and accessibility over completeness. |
| `blueprint_authoritative_legal` | an authoritative legal or contractual summary: obligations stated precisely, no hedging, no persuasion. |
| `blueprint_social_campaign` | short-form social copy: hooks, benefit bullets, hashtags, a call to action. |
| `blueprint_suspense_narrative` | a suspenseful or tense narrative. Atmosphere and emotional impact. Creative writing. |

---

## blueprint_brand_voice

```json
{
  "id": "blueprint_brand_voice",
  "scene_goal": "Produce on-brand copy that is clear, confident and aspirational.",
  "principles": {
    "clarity": [
      "Use simple, direct language. Avoid jargon and overly technical terms.",
      "Prefer short, declarative sentences.",
      "Structure with clear headings and bullet points for scannability."
    ],
    "confidence": [
      "Use the active voice: 'our system delivers results', not 'results are delivered by our system'.",
      "Be authoritative but not arrogant. State facts and benefits directly.",
      "Avoid hedging language: might, could, perhaps."
    ],
    "aspiration": [
      "Focus on benefits, not just features. Frame the product as a tool for a better outcome.",
      "Use forward-looking language: imagine, transform, unlock.",
      "Speak to the reader's goals and ambitions."
    ]
  },
  "forbidden": [
    "Casual slang or unprofessional language.",
    "Specific quantitative promises that cannot be universally guaranteed.",
    "Any claim not present in the supplied source material.",
    "Presenting a competitor's figures as our own."
  ],
  "instruction": "Rewrite the supplied facts into copy that adheres strictly to the three principles and violates none of the forbidden items. Preserve source attribution."
}
```

## blueprint_technical_explanation

```json
{
  "id": "blueprint_technical_explanation",
  "scene_goal": "Explain the mechanism or findings clearly and concisely.",
  "style_guide": "Maintain an objective, formal tone. Use precise terminology. Prioritise factual accuracy and clarity over narrative flair.",
  "structure": ["Definition", "Function or Operation", "Key Findings and Impact", "Sources"],
  "instruction": "Organise the supplied facts into the defined structure, adhering to the style_guide. Where the sources are silent, say they are silent rather than inferring."
}
```

## blueprint_casual_summary

```json
{
  "id": "blueprint_casual_summary",
  "scene_goal": "Summarise information quickly and casually.",
  "style_guide": "Use informal language. Keep it brief and engaging. Imagine explaining it to a friend.",
  "length": "150 words maximum",
  "instruction": "Summarise the supplied facts using the casual style guide. Keep every number accurate even while the tone is loose."
}
```

## blueprint_authoritative_legal

```json
{
  "id": "blueprint_authoritative_legal",
  "scene_goal": "State obligations precisely enough that a reader can rely on the wording.",
  "style_guide": "Precise, impersonal, non-persuasive. Third person.",
  "structure": [
    "One sentence stating what the document is",
    "Numbered obligations, each naming the party bound",
    "Numbered exceptions and carve-outs",
    "Term and termination",
    "Sources"
  ],
  "length": "400 words maximum",
  "rules": [
    "Quote defined terms exactly as the source defines them.",
    "Never soften an obligation into a recommendation. 'Shall' is not 'should'.",
    "Where the source is silent, write that it is silent. Do not infer.",
    "Cite the source document for every obligation stated."
  ],
  "forbidden": ["marketing language", "second person", "reassurance", "legal advice"],
  "instruction": "Organise the supplied facts into the structure, obeying every rule."
}
```

## blueprint_social_campaign

```json
{
  "id": "blueprint_social_campaign",
  "scene_goal": "Drive a specific action with short-form copy.",
  "structure": [
    "Hook, one line, under 12 words",
    "Two or three benefit bullets, each tied to a named capability",
    "Call to action",
    "Hashtags"
  ],
  "style_guide": "Confident and concrete. One idea per line. No paragraphs.",
  "rules": [
    "Prefer a specific number over a superlative.",
    "Every claim must trace to the supplied source material.",
    "Name a competitor only where the source material does."
  ],
  "instruction": "Produce copy in the defined structure. Adapt length to the platform named in the facts, if one is named."
}
```

## blueprint_suspense_narrative

```json
{
  "id": "blueprint_suspense_narrative",
  "scene_goal": "Increase tension and create suspense.",
  "style_guide": "Use short, sharp sentences. Focus on sensory details: sounds, shadows. Maintain a slightly eerie but age-appropriate tone.",
  "participants": [
    {"role": "Agent", "description": "The protagonist experiencing the events."},
    {"role": "Source_of_Threat", "description": "The underlying danger or mystery."}
  ],
  "instruction": "Rewrite the supplied facts into a narrative adhering strictly to the scene_goal and style_guide."
}
```
