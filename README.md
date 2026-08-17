# Context Engineering for Multi-Agent Systems
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
<h3 align="center">
Move beyond prompting to build a Context Engine in a transparent architecture of context and reasoning
</h3>

<img src="./Chapter10/universal_context_engine.png" alt="Universal Context Engine Blueprint" width="40%" align="left" style="margin-right: 20px;">

[**🎞️▶️**](https://denis2054.github.io/Context-Engineering-for-Multi-Agent-Systems/media/player.html) **In 21st‑century Agentic AI, Natural‑Language‑Programmed LLMs are the execution agents, and the domain‑agnostic dual‑RAG MAS is the environment they operate in.**
This repository provides a production-ready blueprint for the Agentic Era, allowing you to replace rigid, hard-coded workflows with a dynamic, **transparent**, **observable**, and **sovereign** **Context Engine**. By building universal, domain-agnostic Multi-Agent Systems through high-level semantic orchestration, you can save thousands of lines of code while maintaining 100% observability.

<br clear="left"/>
<p align="center">Copyright 2025-2026, Denis Rothman. <strong>Last updated: August 16, 2026</strong></p>

**August 16, 2026 — The NVIDIA NIM NEMOTRON DAG Edition of the Context Engine:** The NVIDIA NIM NEMOTRON Edition of the Context Engine adds a real-time DAG planner to the context engine:🐬`nim/Universal_DAG_Engine_NIM.ipynb`      and   🐳☁️ Docker + Railway deployment resources added to the repo.

**August 14, 2026 — LangChain Edition of the Context Engine:** The LangChain Edition of the Context Engine adds a Context Engine layer on a LangChain substrate:🐬`langchain/Universal_Context_Engine_LangChain.ipynb`       

**June 3, 2026 — New Gradio Standalone UI:** `Chapter10/Universal_Context_Engine_Gradio_UI.ipynb` now contains a deployable **Gradio web app** — live public URL in Colab, one-command deploy to Hugging Face Spaces.

<p align="center">See the <a href="./CHANGELOG.md">Changelog</a> for updates, fixes, and upgrades(past, present, coming).</p>

Save thousands of lines of code by building universal, domain-agnostic Multi-Agent Systems (MAS) using the ultimate new programming language:
[**🛰️ View Software Evolution Timeline**](https://denis2054.github.io/Context-Engineering-for-Multi-Agent-Systems/media/index.html)

🐬 March 14, 2026 update of the January 24, 2026 Release: **OpenAI gpt-5.4 implemented** in the Universal Context Engine
**Sovereign Universal Context Engine**: A new **Glass Box Context Engine** implementation - `Chapter10/Universal_Context_Engine.ipynb` and `Chapter10/Universal_Context_Engine_UI.ipynb`- demonstrating **domain-agnostic architecture** by running *cross-domain* use cases on the same core.

**Token Analytics**: engine.py and the Dashboard provide rigorous transparency into token usage (Input, Output, Difference) for cost and verbosity analysis.

The Token & Cost Analytics built into engine.py and the Dashboard implement what is now termed **tokenomics** in agentic AI systems (Salim et al., MSR 2026; Bergemann et al., ACM EC 2025) — rigorous per-step tracking of token consumption, cost, and verbosity across the full multi-agent pipeline.

### 🔧 LLM API Update

For a detailed list of affected notebooks and all changes, see the  ➡️ [CHANGELOG.md](./CHANGELOG.md)

**LLM API update:**  
Several notebooks have been upgraded to use **GPT‑5.1** along with the latest OpenAI library standards
These improvements provide *better performance, lower reasoning latency,* and more reliable handling of structured agent outputs.

This update also includes fixes to the **Moderation API**, ensuring safer and more robust processing of multi‑agent interactions.

**Alternative: Sovereign AI Without External LLM APIs:**

If you prefer not to rely on an external LLM API, a full **DeepSeek‑R1 Sovereign AI Implementation Guide and the Hardware benchmark notebook** (with code) is available:

➡️ **[DeepSeek‑R1 Sovereign AI Guide](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/sovereign_ai/README.md)**

</p>

<br>
<p align="center">
  <strong>🚀 NEW: Interactive Trace Dashboard</strong><br>
  <em>Available in the Context Engine Room of Chapters 8 & 9: Visualize agent reasoning with our new HTML-based trace renderer.</em><br>
  <a href="./Chapter08/dashboard_concept.svg">Dashboard Concept</a>
</p>

<p align="center">
Denis Rothman</p>

<p align="center">
   <a href="https://packt.link/I1tSU" alt="Discord" title="Learn more on the Discord server"><img width="32px" src="https://cliply.co/wp-content/uploads/2021/08/372108630_DISCORD_LOGO_400.gif"/></a>
  &#8287;&#8287;&#8287;&#8287;&#8287;
  <a href="https://packt.link/free-ebook/9781806690053"><img width="32px" alt="Free PDF" title="Free PDF" src="https://cdn-icons-png.flaticon.com/512/4726/4726010.png"/></a>
 &#8287;&#8287;&#8287;&#8287;&#8287;
  <a href="https://packt.link/gbp/9781806690053"><img width="32px" alt="Graphic Bundle" title="Graphic Bundle" src="https://cdn-icons-png.flaticon.com/512/2659/2659360.png"/></a>
  &#8287;&#8287;&#8287;&#8287;&#8287;
   <a href="https://www.amazon.com/Context-Engineering-Multi-Agent-Systems-architecture/dp/1806690055/ref=tmm_pap_swatch_0?_encoding=UTF8&sr=8-3"><img width="32px" alt="Amazon" title="Get your copy" src="https://cdn-icons-png.flaticon.com/512/15466/15466027.png"/></a>
  &#8287;&#8287;&#8287;&#8287;&#8287;
</p>
<details open> 
 <summary><h2>About the book</h2></summary>
<a href="https://www.packtpub.com/en-us/product/context-engineering-for-multi-agent-systems-9781806690046">
<img src="https://m.media-amazon.com/images/I/419o1BGjp0L.jpg" alt="Context Engineering  for Multi-Agent Systems, First Edition" height="1000px" align="right">
</a>

Generative AI is powerful, yet often unpredictable. This guide shows you how to turn that unpredictability into reliability by thinking beyond prompts and approaching AI like an architect. At its core is the Context Engine, a glass-box, multi-agent system you’ll learn to design, strengthen, and apply across real-world scenarios.
Written by an AI guru and author of various cutting-edge AI books, this book takes you on a hands-on journey from the foundations of context design to building a fully operational Context Engine. Instead of relying on brittle prompts that give only simple instructions, you’ll begin with semantic blueprints that map goals and roles with precision, then orchestrate specialized agents using the Model Context Protocol (MCP). As the engine evolves, you’ll integrate memory and high-fidelity retrieval with citations, implement safeguards against data poisoning and prompt injection, and enforce moderation to keep outputs aligned with policy. You’ll also harden the system into a resilient architecture, then see it pivot seamlessly across domains, from legal compliance to strategic marketing, proving its domain independence.
By the end of this book, you’ll be equipped with the skills needed to engineer an adaptable, verifiable architecture you can repurpose across domains and deploy with confidence.
</details>

<details open>
<summary><h2>Key Architecture Highlights</h2></summary>
<ul>
<li><strong>Glass Box Architecture:</strong> Provides 100% observability into agent reasoning through interactive trace dashboards and detailed execution logs.</li>
<li><strong>Universal Context Engine:</strong> A domain-agnostic core that runs cross-domain use cases (e.g., Legal and Marketing) without changing a single line of code.</li>
<li><strong>Dual High-Fidelity RAG:</strong> Implements research agents(dual: instructions and facts) with automated input sanitization and source-verifiable citations to ensure accuracy and defense.</li>
<li><strong> Telemetry‑driven context layers:</strong> Continuous ingestion and structuring of environmental signals that form the dynamic operational context for multi‑agent reasoning.</li>
<li><strong>Protocol-Driven:</strong> Orchestrates specialized agents using the Model Context Protocol (MCP) for seamless, modular multi-agent workflows.</li>
<li><strong>Token & Cost Analytics:</strong> Integrated tracking of input/output tokens to monitor cost-efficiency and model verbosity at every step.</li>
</ul>
</details>

<details open> 
  <summary><h2>Key Learnings</h2></summary>
<ul>
<li>Develop memory models to retain short-term and cross-session context</li>
<li>Craft semantic blueprints and drive multi-agent orchestration with MCP</li>
<li>Implement high-fidelity RAG pipelines with verifiable citations</li>
<li>Apply safeguards against prompt injection and data poisoning</li>
<li>Enforce moderation and policy-driven control in AI workflows</li>
<li>Repurpose the Context Engine across legal, marketing, and beyond</li>
<li>Deploy a scalable, observable Context Engine in production</li>
</ul>
  </details>
<details open>
<summary><h3>📣 The Live Workshop Session Cohort 2 Takeaways</h3></summary>
<img src="media/april2026_workshop.png" alt="April 2026 Workshop was a productive move forward" width="340" style="float: left; margin: 0 18px 12px 0;"/>

✅ The Levels of Efficient Context · ✅ Dual RAG · ✅ Agent Orchestration · ✅ Compliance & Risk

**Stop tinkering with prompts. Start engineering context.** Most AI implementations fail at scale because they rely on black-box prompting — sending a request into the void and hoping for a coherent reply. Following the success of our January session, **Cohort 2** of this hands-on workshop is now open. We move beyond simple instructions to build a Context Engine: a transparent, glass-box architecture where agents don't just guess — they execute a precise, structured plan.

The workshop frames the new software stack as a **delegation gradient** across four runtimes — from the human running a context engine in their head, through embedded copilots, configured platforms, and engineered systems. Mastery of the underlying tiers is what makes any of them deployable. We close with the question that sits underneath every enterprise AI decision in 2026: which tier does this problem belong in, and what does compliance actually require?

Save thousands of lines of code by building universal, domain-agnostic Multi-Agent Systems (MAS) using the ultimate new programming language: **natural language, engineered as context.**

[**🧭 The Tiers of Context Engines — Tier 3 → Tier 2 → Tier 1.5 → Tier 1**](https://denis2054.github.io/Context-Engineering-for-Multi-Agent-Systems/media/three_tier_context_engines.html)

[**⚖️ Compliance & Risk Management — GDPR · HIPAA · SOC 2 · ISO · FedRAMP**](https://denis2054.github.io/Context-Engineering-for-Multi-Agent-Systems/media/compliance_risk_management.html)

</details>

<details open> 
<summary><h2>🎥 Deep Dive: Architecture → Context → Agents → Code</h2></summary>

This recorded session walks through the entire stack behind the sentence:
**“In 21st‑century Agentic AI, Natural‑Language‑Programmed LLMs are the agents, and the domain‑agnostic dual‑RAG MAS is the environment they operate in.”**
The deep dive unpacks each term step‑by‑step:   
- **21st‑century Agentic AI** — why agents are natural‑language‑programmed programs     
- **LLMs as agents** — how reasoning, memory, and protocols turn models into actors     
- **Domain‑agnostic Context Engine** — the universal core that runs any use case     
- **Dual‑RAG MAS** — the two‑channel research architecture (instructions + facts)     
- **Environment design** — how telemetry, context layers, and MCP orchestrate agents     
- **Full drill‑down to code** — notebooks, pipelines, and execution traces     
- **Full climb back up** — how the code re‑forms the architecture end‑to‑end     
[📺**Watch the full deep dive on LinkedIn**](https://www.linkedin.com/posts/denis-rothman_ai-agenticera-contextengineering-activity-7424026873652850688-eXw8)   
If you are an architect or lead looking for:   
✅ ROI & Domain Agnosticism logic  
✅ Glass-Box Observability traces  
✅ Sovereign RAG blueprints   
Join the engineering discussion here: [**Link to GitHub Discussion**](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/discussions/2)

</details> 
 
<details open> 
<summary><h2>Chapters: From Architecture to code</h2></summary>

| Chapters | Colab | Kaggle |  Studio Lab |
| :-------- | :-------- | :------- | :-------- |
| **Chapter 1: From Prompts to Context: Building the Semantic Blueprint** | | | |
| <ul><li>SLR.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter01/SLR.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter01/SLR.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter01/SLR.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| <ul><li>Use_Case.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter01/Use_Case.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter01/Use_Case.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter01/Use_Case.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 2: Building a Multi-Agent System with MCP** | | | |
| <ul><li>MAS_MCP.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter02/MAS_MCP.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter02/MAS_MCP.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> |<a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter02/MAS_MCP.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| <ul><li>MAS_MCP_control.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter02/MAS_MCP_control.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter02/MAS_MCP_control.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter02/MAS_MCP_control.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 3: Building the Context-Aware Multi-Agent System** | | | |
| <ul><li>RAG_Pipeline.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter03/RAG_Pipeline.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter03/RAG_Pipeline.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter03/RAG_Pipeline.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| <ul><li>Context_Aware_MAS.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter03/Context_Aware_MAS.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter03/Context_Aware_MAS.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter03/Context_Aware_MAS.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 4: Assembling the Context Engine** | | | |
| <ul><li>Context_Engine.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter04/Context_Engine.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter04/Context_Engine.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter04/Context_Engine.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 5: Hardening the Context Engine** | | | |
| <ul><li>Context_Engine_MAS_MCP.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter05/Context_Engine_MAS_MCP.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter05/Context_Engine_MAS_MCP.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter05/Context_Engine_MAS_MCP.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| <ul><li>Context_Engine_Pre_Production.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter05/Context_Engine_Pre_Production.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter05/Context_Engine_Pre_Production.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter05/Context_Engine_Pre_Production.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 6: Building the Summarizer Agent for Context Reduction** | | | |
| <ul><li>Context_Engine_Content_Reduction.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter06/Context_Engine_Content_Reduction.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter06/Context_Engine_Content_Reduction.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter06/Context_Engine_Content_Reduction.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 7: High-Fidelity RAG and Defense: The NASA-Inspired Research Assistant** | | | |
Domain‑agnostic Universal Context Engine architectures are powered by environment‑ingestion agents illustrated in `High_Fidelity_Data_Ingestion.ipynb`that dynamically construct the operational context for complex, cross‑domain agentic systems.
| <ul><li>High_Fidelity_Data_Ingestion.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter07/High_Fidelity_Data_Ingestion.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter07/High_Fidelity_Data_Ingestion.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter07/High_Fidelity_Data_Ingestion.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
Domain‑agnostic Universal Context Engine architectures are also driven by MAS‑RAG‑Context Engines, illustrated in `NASA_Research_Assistant_and_Retrocompatibility.ipynb`, which combine high‑fidelity retrieval, defense, and multi‑agent reasoning into a unified operational environment.
| <ul><li>NASA_Research_Assistant_and_Retrocompatibility.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter07/NASA_Research_Assistant_and_Retrocompatibility.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter07/NASA_Research_Assistant_and_Retrocompatibility.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter07/NASA_Research_Assistant_and_Retrocompatibility.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 8: Architecting for Reality: Moderation, Latency, and Policy-Driven AI** | | | |
| <ul><li>Data_Ingestion.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter08/Data_Ingestion.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter08/Data_Ingestion.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter08/Data_Ingestion.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| <ul><li>Legal_assistant_Explorer.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter08/Legal_assistant_Explorer.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter08/Legal_assistant_Explorer.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter08/Legal_assistant_Explorer.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 9: Architecting for Brand and Agility: The Strategic Marketing Engine** | | | | |
| <ul><li>Data_Ingestion_Marketing.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter09/Data_Ingestion_Marketing.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter09/Data_Ingestion_Marketing.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter09/Data_Ingestion_Marketing.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| <ul><li>Marketing_Assistant.ipynb</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter09/Marketing_Assistant.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter09/Marketing_Assistant.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter09/Marketing_Assistant.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
| **Chapter 10: The Blueprint for Production-Ready AI** | | | |
The Universal Context Engine provides full **architectural sovereignty** through *glass‑box reasoning*, *verifiable multi‑agent traces*, and complete *control over memory*, *dual RAG*, *moderation*, and *orchestration*. Its **domain‑agnostic core** can be deployed in restricted, *mission‑critical*, *strategic environments* where transparency, auditability, and **sovereignty are mandatory**.
The `Universal_Context_Engine.ipynb` version runs a list of explicit scenarios for batch processing.
| <ul><li>🐬Universal_Context_Engine.ipynb - March 14, 2026 update of the January 24, 2026 Release: **OpenAI gpt-5.4**</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter10/Universal_Context_Engine.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter10/Universal_Context_Engine.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter10/Universal_Context_Engine.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
The `Universal_Context_Engine_UI.ipynb`provides an IPython interface for interactive sessions that highlights how the industry is converging toward domain‑agnostic, environment‑driven agentic systems built on transparent, context‑rich architectures. 
| <ul><li>🐬Universal_Context_Engine_Gradio_UI.ipynb - **June 3, 2026 Release**</li></ul> | <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter10/Universal_Context_Engine_Gradio_UI.ipynb"><img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab"></a><br> | <a href="https://www.kaggle.com/kernels/welcome?src=https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter10/Universal_Context_Engine_Gradio_UI.ipynb"><img src="https://kaggle.com/static/images/open-in-kaggle.svg" alt="Open In Kaggle"></a><br> | <a href="https://studiolab.sagemaker.aws/import/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/Chapter10/Universal_Context_Engine_Gradio_UI.ipynb"><img src="https://studiolab.sagemaker.aws/studiolab.svg" alt="Open In Studio Lab"></a><br> |
The `Universal_Context_Engine_Gradio_UI.ipynb` can serve as an alternative to the IPython widget interface, providing a full **Gradio web application** that generates a live public URL directly from Colab. The same Glass Box engine runs unchanged underneath — only the presentation layer is new. The app can also be exported as `app.py` and deployed permanently to **Hugging Face Spaces** or any container host, making it the recommended interface for demos, workshops, and stakeholder presentations.

![Context Engineering Production Blueprint](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/raw/main/Chapter10/context_engineering_blueprint.svg)
</details>

## 🗺️ One Architecture, Three Editions

Everything below — LangChain, Sovereign, NIM Nemotron — is the same engine: the same planner, the same two governance gates, the same dual-RAG namespaces, the same domain-agnostic registry. What changes across the three sections is only which model answers the calls and which framework carries the plumbing.

![Universal Context Engine Architecture](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/raw/main/media/universal_context_engine_architecture.png)

| | swap the **model** | swap the **substrate** |
|---|---|---|
| **LangChain** *(below)* | OpenAI | LangChain / LangGraph |
| **Sovereign** *(below)* | DeepSeek‑R1 | zero framework, zero external API |
| **NIM Nemotron** *(below)* | NVIDIA Nemotron | native — plus a real-time DAG planner |

*The architecture is the product. The model and the framework are both deployment choices.*

## 🛡️ The LangChain Edition of the Universal Context Engine

The Universal Context Engine, ported onto LangChain 1.x and LangGraph 1.x, reading the same Pinecone index, the same namespaces, and using the same OpenAI models as the original.
This folder is the repository's framework pole. sovereign_ai/ is the other: zero framework, zero external API, maximum control. Between them they make one point, which is the point of the book:

*The architecture is the product. The framework is a deployment choice.*

[Read the LangChain guide](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/langchain/README.md)

<ul>
  <li>
   <strong>🐬Launch the LangChain Edition of the Universal Context Engine</strong> in Google Colab
    <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/langchain/Universal_Context_Engine_LangChain.ipynb">
      <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab">
    </a>
  </li>
</ul>

## 🛡️ Sovereign AI & Open-Source Engineering

For organizations requiring **100% data privacy** and **zero external API dependencies**, this repository provides a dedicated **Sovereign Path**.  
By leveraging high‑reasoning open‑source models like **DeepSeek‑R1**, you can achieve **industrial‑grade performance** entirely on your own infrastructure. <br>      
### 🔑 Key Highlights of the Sovereign Path<br>
⚡**Performance**: Benchmarked at **~9.75 seconds** on **NVIDIA H100** hardware for complex multi‑step reasoning.<br>
🔍**Transparency**: Provides **100% Glass‑Box observability** using local reasoning traces (`</think>` blocks).<br>
🛠️**Independence**: Fully disconnected execution with **no vendor lock‑in** and **no unpredictable API costs**.   

[Read the DeepSeek-R1 Sovereign AI Guide and the Hardware benchmark notebook](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/sovereign_ai/README.md)

<ul>
  <li>
   <strong>Launch the DeepSeek‑R1 Sovereign AI Guide</strong> in Google Colab
    <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/sovereign_ai/DeepSeek%E2%80%91R1_Sovereign_AI_Guide.ipynb">
      <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab">
    </a>
  </li>
</ul>


## 🛡️ The NVIDIA NIM NEMOTRON Edition of the Universal Context Engine

What the NVIDIA NIM Nemotron version adds to the universal content engine:     

Nemotron is a hybrid: most of its self-attention layers are replaced by Mamba-2 state-space layers, with only a thin residual of attention retained — so context is carried in a fixed-size recurrent state rather than a KV cache that grows with every token, and throughput stays roughly linear in sequence length instead of quadratic.

The DAG mirrors that optimization one level up: where Mamba drops the quadratic all-to-all of attention and mixture-of-experts activates only the parameters a token needs, the planner drops the unnecessary edges of a linear chain and the Foreman runs only the nodes whose dependencies are actually met — sparsity and parallelism in the orchestration, matching sparsity and parallelism in the silicon.

[How this works](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/nim/README.md)

<ul>
  <li>
   <strong>🐬Launch the NIM NEMOTRON version of the Universal Context Engine</strong> in Google Colab
    <a href="https://colab.research.google.com/github/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/nim/Universal_DAG_Engine_NIM.ipynb">
      <img src="https://colab.research.google.com/assets/colab-badge.svg" alt="Open In Colab">
    </a>
  </li>
</ul>

🐳☁️ **Docker + Railway Deployment:** The NIM Nemotron engine is also packaged as a deployable FastAPI service — build it with Docker, ship it to Railway, and verify it live via Swagger. <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/docker/docker-original.svg" width="18"/> <img src="https://railway.app/brand/logo-light.svg" width="18"/>

[See the full Docker & Railway deployment guide](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/blob/main/nemotron_docker_railway/README.md)

☸️ *Also deployed and verified on Kubernetes with the same Docker container image that runs with concurrent requests* <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/kubernetes/kubernetes-original.svg" width="18"/>

<details open> 
  <summary><h2>Requirements for this book</h2></summary>
Before running the code, make sure your development environment is set up and you have the necessary API keys (LangChain, OpenAI, Pinecone, and — for the NIM edition — NVIDIA).
 

### ✅ Prerequisites
- **Python**: Version **3.10+**
- **Environment Options:**
  - Google Colab **or**
  - Local Python environment with:
     - `openai`
    - `pinecone`          # (formerly `pinecone-client` — the package was renamed)
    - `tiktoken`
    - `tenacity`
    - `nest_asyncio`      # required by the NIM edition's notebook (Colab kernel + asyncio)
    - `fastapi`           # only if you run the Gradio/deployment notebooks in Chapter 10

### 🚀 Quick Start

Get up and running using cloud-based virtual machines using the Google Colab links provided for each notebook.       
No local installation is required.

#### 1. Get Your API Keys
* **OpenAI**: Sign up and generate a key at [platform.openai.com](https://platform.openai.com/).
* **Pinecone**: Sign up and generate a free API key at [pinecone.io](https://www.pinecone.io/).
* **NVIDIA NIM** *(only for the NIM edition)*: free key at [build.nvidia.com](https://build.nvidia.com).

### 2. Run the Notebooks
Click the badges below to launch the notebooks directly in a pre-configured Google Colab VM. You will be asked to add your API keys to the Colab Secrets Manager upon launch.

### ✅ Project Structure
Create a GitHub or local workspace containing at least:
- `helpers.py`
- `agents.py`
- `registry.py`
- `engine.py`
- Notebook files for each chapter

### ✅ Required API Keys
- **OpenAI** – model access and moderation
- **Pinecone** – vector database storage and retrieval
- **NVIDIA NIM** *(NIM edition only)* – planning and agent inference
- **(Optional)** Google Cloud or AWS – for deployment sections in Chapter 10

### ✅ System Requirements
| Requirement | Minimum | Recommended |
|------------|---------|--------------|
| CPU | Dual-core | Any modern multi-core |
| RAM | 8 GB | 16 GB or Google Colab Pro |
| GPU | Optional, but helpful for embeddings and token-heavy operations |

> **Note:** From **Chapter 5 onward**, modular components depend on earlier notebooks. Ensure your environment is configured correctly, as setup steps may not be repeated in later chapters.

### ✅ Additional Notes
- Local execution may incur **token and API costs** with large contexts.
- The **Summarizer Agent** (Chapter 6) helps reduce token usage.
- Familiarity with **RAG workflows** and **MCP-based agent orchestration** is recommended.
- Refer to **Appendix: Context Engine Reference Guide** for quick lookup of component structures and explanations.

</details>
<details open> 
  <summary><h2>About the Author</h2></summary>

<a href="https://www.linkedin.com/in/denis-rothman-0b034043/">
  <img src="https://cdn.jsdelivr.net/gh/devicons/devicon/icons/linkedin/linkedin-original.svg" alt="LinkedIn" width="30" height="30"/>
</a>
 
Denis Rothman is an AI systems architect and author whose work bridges foundational AI research with today’s generative and agentic architectures. A graduate of Sorbonne University and Paris‑Diderot University, he designed one of the earliest patented *word2matrix* numerical encoding systems which was a precursor to modern embedding techniques. He designed one of the first industrial conversational agents, deployed as an automated language teacher for Moët & Chandon and other global companies.
Throughout his career, Denis has built large‑scale AI systems across industries, from IBM resource optimizers to worldwide Advanced Planning and Scheduling (APS) solutions, always focusing on transparent, explainable, and production‑ready architectures.
Building on decades of applied AI engineering, he has become a leading voice in the agentic era of AI, authoring influential books on transformers, RAG pipelines, business‑ready generative AI, and now *Context Engineering for Multi‑Agent Systems*. His work emphasizes model‑agnostic engineering, semantic design, and the construction of resilient, domain‑independent AI systems that go far beyond prompting.
Denis continues to publish hands‑on frameworks, open‑source architectures, and practical guides that help engineers, researchers, and organizations build the next generation of verifiable, context‑driven AI systems.        

</details>
<details open> 
  <summary><h2>Other books and resources to expand the scope of the Context Engineering Agentic Ecosystem </h2></summary>
<ul>
  <li><b>Bring AI to the data:</b> <a href="https://github.com/Denis2054/RAG-Driven-Generative-AI-2nd-Edition#bringing-ai-to-the-data">RAG-Driven Generative AI, Second Edition</a>
    <br>Architecture & Code: <a href="https://github.com/Denis2054/RAG-Driven-Generative-AI-2nd-Edition/blob/main/Chapter05/Universal_Context_Engine_Converged_Edition.ipynb">Universal Context Engine, Converged Edition</a> · <a href="https://github.com/Denis2054/RAG-Driven-Generative-AI-2nd-Edition/blob/main/Chapter01/RAG_Overview_db.ipynb">RAG Overview (data-in-place)</a>
  </li>
 <li><b>Bring humans to AI for supervision and quality:</b> <a href="https://github.com/Denis2054/Building-Business-Ready-Generative-AI-Systems">Building Business-Ready Generative AI Systems</a>
<br>Architecture & Code: <a href="https://github.com/Denis2054/Building-Business-Ready-Generative-AI-Systems/blob/main/Chapter09/Pinecone_Security.ipynb">Guardrails and Security</a> · <a href="https://github.com/Denis2054/Building-Business-Ready-Generative-AI-Systems/blob/main/Chapter09/GenAISys_Customer_Service.ipynb">Human-Facing Customer Service</a> · <a href="https://github.com/Denis2054/Building-Business-Ready-Generative-AI-Systems/blob/main/Chapter01/Contextual_Awareness_and_Memory_Retention.ipynb">Short- and Long-Term Session Memory</a> · <a href="https://github.com/Denis2054/Building-Business-Ready-Generative-AI-Systems/blob/main/Chapter04/Event-driven_GenAISys_framework.ipynb">AI as a Live Meeting Participant</a>
  </li>
  <li><b>Explore where it all began and is evolving:</b> <a href="https://github.com/Denis2054/Transformers-for-NLP-and-Computer-Vision-3rd-Edition">Transformers for Natural Language Processing and Computer Vision, Third Edition</a>
    <br>Architecture & Code: <a href="https://github.com/Denis2054/Transformers-for-NLP-and-Computer-Vision-3rd-Edition/blob/main/Chapter02/Multi_Head_Attention_Sub_Layer.ipynb">Multi-Head Attention from Scratch</a> · <a href="https://github.com/Denis2054/Transformers-for-NLP-and-Computer-Vision-3rd-Edition/blob/main/Chapter02/DeepSeek_R1_Zero_RL.ipynb">DeepSeek-R1's Training Innovations</a>
  </li>
</ul>
</details>
<details open> 
  <summary><h2>Contributing </h2></summary>
  
We welcome contributions! High interaction through Issues, PRs, and Comments helps the Context Engine grow and improves the trending visibility for the community.
### How to get started:
1.  **Check Issues:** Look for the [**good first issue**](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/issues?q=is%3Aopen+is%3Aissue+label%3A%22good+first+issue%22) label for approachable tasks.
2.  **Discussions:** Join our [**Discussions tab**](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/discussions) to propose new features or "Context Chaining" techniques.
3.  **Pull Requests:** Submit improvements to the core `engine.py` or new specialized agents in `agents.py`.
</details>
<details open> 
  <summary><h2>Insight</h2></summary>
 Last but not least: cool code is great but without a solid Return on Investment(ROI) it will never last in production!
<img src="./media/agentic_roi_framework.gif" alt="Universal Context Engine Blueprint" width="40%" align="left" style="margin-right: 20px;">
</details>
