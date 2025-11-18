# Changelog

This changelog contains the notable updates to the **Context Enginnering for Multi-Agent Systems** repository.   
🐬 Indicates *new bonus notebooks* to explore.


## [November 18, 2025]

### List of notebooks upgraded
`Chapter05/Context_Engine_MAS_MCP.ipynb` 
`Chapter05/Context_Engine_Pre_Production.ipynb` 
`Chapter06/Context_Engine_Content_Reduction.ipynb` 
`Chapter07/NASA_Research_Assistant_and_Retrocompatibility.ipynb`     

### List of notebooks upgraded and fixed   
`Chapter08/Legal_assistant_Explorer.ipynb` 
`Chapter09/Marketing_Assistant.ipynb` 

### Upgraded
**GPT 5:** 

GPT-5 has been upgraded to GPT-5.1, which improves API response time.
OpenAI API library has been upgraded to 2.8.1 in `commons/utils.py,` which is now the reference installation file for all notebooks in the repository.

OpenAI provided the following release notes that address, among other issues, latency for reasoning, which is important for MAS programs such as MAS Context Engine.

"We’ve released GPT-5.1 in the API, the next model in the GPT-5 series built to balance intelligence and speed across agentic and coding tasks.
Here’s what’s new in GPT 5.1:

Adaptive reasoning that adjusts thinking time by task complexity—spending more time on complex tasks and responding faster on simple tasks.
New reasoning_effort = 'none' mode, offers a fast, accurate non-reasoning path for **latency sensitive use cases**. *Defaults to none when unspecified.*
Extended prompt caching with retention up to 24 hours to reduce latency for long-running conversations.
Upgrades to coding: more communicative, highly steerable, better code quality, improved frontend UI generation.
New tools: apply_patch (structured diffs) and shell (controlled local CLI).
Pricing: Same pricing and rate limits as GPT-5."

### Fixed
- **Moderation API Type:** Resolved a critical formatting issue in `Marketing_Assistant.ipynb` (Cell 4) where the OpenAI Moderation API failed with `Error code: 400` when agents returned structured data (dictionaries or lists). Added logic to serialize these outputs into strings before submission.

### Added
- **JSON Support:** Added `import json` to the execution cell to support data serialization.

### Changed
- **Output Rendering:** Updated the `execute_and_display` function to detect JSON outputs and render them as formatted Markdown code blocks for improved readability in the notebook.

## [November 7, 2025]

Repository made public.
