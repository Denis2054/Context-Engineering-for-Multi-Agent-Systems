# <!-- YOUR_PROJECT_TITLE --> — Context Engineering Workshop
<!-- Replace the title above with something like:
     "Acme Corp AI Workshop — Context Engineering"  -->

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

<h3 align="center">
<!-- YOUR_TAGLINE -->
<!-- Example: "Applied Context Engineering for the Legal & Marketing AI Teams at Acme Corp" -->
</h3>

---

> **Workshop fork of** [Context Engineering for Multi-Agent Systems](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems) by Denis Rothman.  
> This repository is maintained by **<!-- YOUR_NAME / TEAM_NAME -->** at **<!-- YOUR_CORPORATION -->** for internal training purposes.  
> All original code is preserved. This README surfaces only the chapters covered in the workshop (Chapters 8–10).

---

## 👤 About This Fork

| Field | Value |
| :--- | :--- |
| **Organization** | <!-- YOUR_CORPORATION --> |
| **Department / Team** | <!-- YOUR_DEPARTMENT --> |
| **Workshop Lead** | <!-- YOUR_NAME --> |
| **Contact** | <!-- YOUR_EMAIL_OR_SLACK --> |
| **Workshop Date** | <!-- YYYY-MM-DD --> |
| **Fork Created** | <!-- YYYY-MM-DD --> |

---

## 🎯 Workshop Scope

This fork focuses on **Chapters 8, 9, and 10** — the production-oriented chapters that demonstrate:

- **Policy-driven moderation** and latency-aware architecture (Ch. 8)
- **Domain-specific deployment** for a strategic marketing engine (Ch. 9)
- **Production-ready blueprints** with the Universal Context Engine (Ch. 10)

> **Note:** The full codebase for all chapters (1–10) is intact in this repository. Only the README has been scoped to the workshop chapters.

---

## 🚀 Quick Start

### Prerequisites

- **Python** 3.10+
- A **Google Colab** account (recommended — no local setup needed)
- API keys:
  - [OpenAI](https://platform.openai.com/) — model access and moderation
  - [Pinecone](https://www.pinecone.io/) — vector database (free tier sufficient)

### Running the Notebooks

Click any badge below to launch the notebook directly in Google Colab.  
You will be prompted to add your API keys via the Colab Secrets Manager.

---

## 📚 Workshop Chapters

<details open>
<summary><h3>Chapter 8: Architecting for Reality — Moderation, Latency, and Policy-Driven AI</h3></summary>

This chapter shows how to harden a Context Engine for real-world constraints: content moderation, latency budgets, and policy enforcement across multi-agent workflows.

| Notebook | Colab | Kaggle | Studio Lab |
| :--- | :--- | :--- | :--- |
| `Data_Ingestion.ipynb` | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter08/Data_Ingestion.ipynb) | [![Open In Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://www.kaggle.com/kernels/welcome?src=https://github.com/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter08/Data_Ingestion.ipynb) | [![Open In Studio Lab](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter08/Data_Ingestion.ipynb) |
| `Legal_assistant_Explorer.ipynb` | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter08/Legal_assistant_Explorer.ipynb) | [![Open In Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://www.kaggle.com/kernels/welcome?src=https://github.com/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter08/Legal_assistant_Explorer.ipynb) | [![Open In Studio Lab](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter08/Legal_assistant_Explorer.ipynb) |

</details>

---

<details open>
<summary><h3>Chapter 9: Architecting for Brand and Agility — The Strategic Marketing Engine</h3></summary>

This chapter deploys the domain-agnostic Context Engine in a marketing context, demonstrating how the same architecture pivots across domains without code changes.

| Notebook | Colab | Kaggle | Studio Lab |
| :--- | :--- | :--- | :--- |
| `Data_Ingestion_Marketing.ipynb` | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter09/Data_Ingestion_Marketing.ipynb) | [![Open In Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://www.kaggle.com/kernels/welcome?src=https://github.com/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter09/Data_Ingestion_Marketing.ipynb) | [![Open In Studio Lab](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter09/Data_Ingestion_Marketing.ipynb) |
| `Marketing_Assistant.ipynb` | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter09/Marketing_Assistant.ipynb) | [![Open In Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://www.kaggle.com/kernels/welcome?src=https://github.com/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter09/Marketing_Assistant.ipynb) | [![Open In Studio Lab](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter09/Marketing_Assistant.ipynb) |

</details>

---

<details open>
<summary><h3>Chapter 10: The Blueprint for Production-Ready AI</h3></summary>

The Universal Context Engine delivers full **architectural sovereignty** through *glass-box reasoning*, *verifiable multi-agent traces*, and complete control over *memory*, *dual RAG*, *moderation*, and *orchestration*. Its **domain-agnostic core** is deployable in mission-critical, restricted environments where transparency and auditability are mandatory.

**`Universal_Context_Engine.ipynb`** — batch processing mode: runs a predefined list of explicit scenarios.

| Notebook | Colab | Kaggle | Studio Lab |
| :--- | :--- | :--- | :--- |
| 🐬 `Universal_Context_Engine.ipynb` | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter10/Universal_Context_Engine.ipynb) | [![Open In Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://www.kaggle.com/kernels/welcome?src=https://github.com/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter10/Universal_Context_Engine.ipynb) | [![Open In Studio Lab](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter10/Universal_Context_Engine.ipynb) |

**`Universal_Context_Engine_UI.ipynb`** — interactive IPython interface for live sessions, highlighting how the industry is converging on domain-agnostic, environment-driven agentic systems.

| Notebook | Colab | Kaggle | Studio Lab |
| :--- | :--- | :--- | :--- |
| 🐬 `Universal_Context_Engine_UI.ipynb` | [![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter10/Universal_Context_Engine_UI.ipynb) | [![Open In Kaggle](https://kaggle.com/static/images/open-in-kaggle.svg)](https://www.kaggle.com/kernels/welcome?src=https://github.com/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter10/Universal_Context_Engine_UI.ipynb) | [![Open In Studio Lab](https://studiolab.sagemaker.aws/studiolab.svg)](https://studiolab.sagemaker.aws/import/github/<!-- YOUR_GITHUB_USERNAME -->/<!-- YOUR_REPO_NAME -->/blob/main/Chapter10/Universal_Context_Engine_UI.ipynb) |

![Context Engineering Production Blueprint](https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems/raw/main/Chapter10/context_engineering_blueprint.svg)

</details>

---

## 🏢 About <!-- YOUR_CORPORATION -->

<!-- 
Write 2–4 sentences about your organization and why this workshop is relevant to your team.
Example:
  "Acme Corp is a global financial services firm. This workshop is part of our AI Center of Excellence
  initiative to upskill engineering leads in production-grade agentic system design."
-->

---

## 📝 Workshop Notes

<!-- 
Add any organization-specific notes here, such as:
- Internal Pinecone or OpenAI API key distribution instructions
- VPN or firewall requirements
- Links to your internal Confluence/Notion docs
- Slack channel for support: #workshop-context-engineering
-->

---

## ⚠️ A Note on Latency

The Context Engine performs complex, multi-step reasoning — not single-shot answers. The processing time you observe in Colab reflects the engine dynamically planning and executing a sequence of API calls (planning → RAG → generation). This is expected behavior, equivalent to the "thinking" time in advanced platforms like ChatGPT or Gemini for complex requests.

---

## 📜 Citation & Original Repository

This repository is a workshop fork. All intellectual property, architecture designs, and code belong to the original author.

```
Denis Rothman,
Context Engineering for Multi-Agent Systems,
Packt Publishing, 2025–2026.
https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems
```

**Original repository:** https://github.com/Denis2054/Context-Engineering-for-Multi-Agent-Systems  
**Book:** [Context Engineering for Multi-Agent Systems — Packt](https://www.packtpub.com/en-us/product/context-engineering-for-multi-agent-systems-9781806690046)  
**Author LinkedIn:** [Denis Rothman](https://www.linkedin.com/in/denis-rothman-0b034043/)

---

<p align="center"><em>Workshop fork maintained by <!-- YOUR_CORPORATION -->. Original work © 2025–2026 Denis Rothman.</em></p>
