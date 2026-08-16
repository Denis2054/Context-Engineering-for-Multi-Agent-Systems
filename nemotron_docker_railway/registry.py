# =============================================================================
# registry.py  —  Domain-Aware Agent Registry (NIM Edition)
# commons/dag_engine/registry.py  (private: Denis2054/SFT)
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT CHANGED FROM THE PUBLIC REPO VERSION:
#   ONE addition only — dual-model routing for NIM:
#
#   get_handler() gains one optional parameter: agent_model (str | None)
#     - When None (default): agents receive generation_model, identical to
#       the public repo behaviour. OpenAI path unchanged.
#     - When set to NIM_AGENT_MODEL: the Planner continues to use
#       generation_model (NIM Super, passed by context_engine), while
#       agents use agent_model (NIM Nano Omni) — faster and cheaper.
#
#   This is a purely additive, backward-compatible change.
#   Calling get_handler() without agent_model works exactly as before.
#
# EVERYTHING ELSE IS IDENTICAL TO THE PUBLIC REPO.
# =============================================================================

import logging
import agents
from helpers import create_mcp_message


class AgentRegistry:
    """
    Domain-aware registry of all agents available to the DAG engine.

    Each entry declares:
        fn      — the agent function (from agents.py, unchanged)
        domain  — the governance domain this agent belongs to

    The registry is keyed by "AgentName" for General-domain agents and
    "Domain:AgentName" for domain-specific agents.
    """

    def __init__(self):
        self._registry = {

            # --- General domain agents ---
            "Librarian": {
                "fn"    : agents.agent_context_librarian,
                "domain": "General",
            },
            "Researcher": {
                "fn"    : agents.agent_researcher,
                "domain": "General",
            },
            "Summarizer": {
                "fn"    : agents.agent_summarizer,
                "domain": "General",
            },
            "Writer": {
                "fn"    : agents.agent_writer,
                "domain": "General",
            },

            # --- Legal domain agents (A2A seam — Phase 1: local dispatch) ---
            "Legal:Researcher": {
                "fn"    : agents.agent_researcher,
                "domain": "Legal",
            },

            # --- Marketing domain agents ---
            "Marketing:Researcher": {
                "fn"    : agents.agent_researcher,
                "domain": "Marketing",
            },
        }

        logging.info(
            f"[Registry] Initialised. "
            f"Registered agents: {sorted(self._registry.keys())}"
        )

    # ------------------------------------------------------------------
    # get_handler — main dispatch method
    # ------------------------------------------------------------------

    def get_handler(self, agent_name: str, domain: str,
                    client, adapter, generation_model: str,
                    embedding_model: str, agent_model: str = None):
        """
        Resolve an agent name + domain to a callable handler.

        NIM ADDITION — agent_model parameter:
            When running on NIM, pass agent_model=utils.NIM_AGENT_MODEL
            so that agent LLM calls use Nemotron Nano Omni (fast, cheap)
            while the Planner continues to use NIM Super (passed as
            generation_model from context_engine).

            When agent_model is None (default), agents use generation_model
            — identical to the public repo behaviour. OpenAI path unchanged.

        Args:
            agent_name (str):       Agent name from the DAG node.
            domain (str):           Domain from the DAG node.
            client:                 LLM client (OpenAI or NIM).
            adapter:                StorageAdapter instance.
            generation_model (str): Model for the Planner (and agents if
                                    agent_model is None).
            embedding_model (str):  Model for embedding calls.
            agent_model (str|None): Model for agent calls when different
                                    from the Planner model (NIM path).
                                    Default None = use generation_model.

        Returns:
            Callable: lambda(mcp_message) → dict
        """
        # Resolve which model agents actually use
        # NIM path: agent_model = NIM_AGENT_MODEL (Nano Omni)
        # OpenAI path: agent_model = None → falls back to generation_model
        effective_agent_model = agent_model if agent_model is not None else generation_model

        if agent_model is not None:
            logging.info(
                f"[Registry] Dual-model routing active. "
                f"Planner: {generation_model} | "
                f"Agents:  {effective_agent_model}"
            )

        # Try domain-specific key first, then plain agent name
        qualified_key = f"{domain}:{agent_name}"
        entry = self._registry.get(qualified_key) or self._registry.get(agent_name)

        if not entry:
            msg = (
                f"Agent '{agent_name}' (domain='{domain}') not found in registry. "
                f"Tried keys: ['{qualified_key}', '{agent_name}']. "
                f"Registered: {sorted(self._registry.keys())}"
            )
            logging.error(f"[Registry] {msg}")
            raise ValueError(msg)

        handler_fn      = entry["fn"]
        resolved_domain = entry["domain"]

        logging.info(
            f"[Registry] Resolving handler: "
            f"key='{qualified_key}' → fn={handler_fn.__name__} "
            f"domain={resolved_domain} model={effective_agent_model}"
        )

        # Resolve namespaces via adapter
        try:
            ns_knowledge = adapter.resolve_namespace(resolved_domain, "knowledge")
            ns_context   = adapter.resolve_namespace(resolved_domain, "context")
        except KeyError:
            logging.warning(
                f"[Registry] Domain '{resolved_domain}' not in adapter namespace map. "
                f"Falling back to General namespaces."
            )
            ns_knowledge = adapter.resolve_namespace("General", "knowledge")
            ns_context   = adapter.resolve_namespace("General", "context")

        base_name = agent_name

        if base_name == "Librarian":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client            = client,
                index             = adapter._index,
                embedding_model   = embedding_model,
                namespace_context = ns_context,
            )

        elif base_name == "Researcher":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client              = client,
                index               = adapter._index,
                generation_model    = effective_agent_model,   # ← NIM Nano or OpenAI
                embedding_model     = embedding_model,
                namespace_knowledge = ns_knowledge,
            )

        elif base_name == "Summarizer":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client           = client,
                generation_model = effective_agent_model,       # ← NIM Nano or OpenAI
            )

        elif base_name == "Writer":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client           = client,
                generation_model = effective_agent_model,       # ← NIM Nano or OpenAI
            )

        else:
            logging.warning(
                f"[Registry] No specific lambda pattern for '{base_name}'. "
                f"Using generic pass-through."
            )
            return lambda mcp_message: handler_fn(
                mcp_message,
                client           = client,
                adapter          = adapter,
                generation_model = effective_agent_model,
            )

    # ------------------------------------------------------------------
    # get_capabilities_description — unchanged from public repo
    # ------------------------------------------------------------------

    def get_capabilities_description(self) -> str:
        return """
Available Agents and their required inputs.

CRITICAL RULES FOR THE PLANNER:
  1. Use the EXACT input key names shown below — no variations.
  2. Every node MUST include a `domain` field matching the agent's domain.
  3. Use $$node_id$$ syntax (not $$STEP_N_OUTPUT$$) to reference prior outputs.
  4. `depends_on` must list every node_id whose output this node references.
  5. Nodes with no dependencies run concurrently — only add depends_on when
     the input genuinely requires another node's output.

─────────────────────────────────────────────────────────────────────
DOMAIN: General
─────────────────────────────────────────────────────────────────────

1. AGENT: Librarian  |  domain: "General"
   ROLE: Retrieves Semantic Blueprints (style and structure instructions
         for the Writer). Always runs early — has no dependencies.
   INPUTS:
     - "intent_query": (String) Descriptive phrase of the desired output style.
   OUTPUT: Blueprint structure (JSON string).

2. AGENT: Researcher  |  domain: "General"
   ROLE: Retrieves and synthesizes factual information from the General
         knowledge store.
   INPUTS:
     - "topic_query": (String) The subject matter to research.
   OUTPUT: Synthesized facts (String).

3. AGENT: Summarizer  |  domain: "General"
   ROLE: Reduces large text to a concise summary for a specific objective.
         Use before the Writer when upstream output may be token-heavy.
   INPUTS:
     - "text_to_summarize": (String or $$ref$$) The text to summarize.
     - "summary_objective": (String) Clear goal for the summary.
   OUTPUT: {"summary": "..."} (dict).

4. AGENT: Writer  |  domain: "General"
   ROLE: Generates final content by applying a Blueprint to source material.
   INPUTS:
     - "blueprint":        (String or $$ref$$) Style instructions (from Librarian).
     - "facts":            (String or $$ref$$) Factual content (from Researcher or Summarizer).
     - "previous_content": (String or $$ref$$) Existing text for rewriting (optional).
   OUTPUT: Final generated text (String).

─────────────────────────────────────────────────────────────────────
DOMAIN: Legal
─────────────────────────────────────────────────────────────────────

5. AGENT: Researcher  |  domain: "Legal"
   ROLE: Retrieves and synthesizes legal information from the Legal
         knowledge store (contracts, NDAs, policies, compliance documents).
         Use when the goal requires legal verification or clause extraction.
   INPUTS:
     - "topic_query": (String) The legal subject matter to research.
   OUTPUT: Synthesized legal findings (String).

─────────────────────────────────────────────────────────────────────
DOMAIN: Marketing
─────────────────────────────────────────────────────────────────────

6. AGENT: Researcher  |  domain: "Marketing"
   ROLE: Retrieves and synthesizes marketing information from the Marketing
         knowledge store (product specs, brand guides, competitor intel,
         SEO keywords, customer research, campaign briefs).
   INPUTS:
     - "topic_query": (String) The marketing subject matter to research.
   OUTPUT: Synthesized marketing findings (String).

─────────────────────────────────────────────────────────────────────
NODE STRUCTURE (every node in your DAG must follow this exactly):
─────────────────────────────────────────────────────────────────────
{
  "id"         : "unique_snake_case_id",
  "agent"      : "AgentName",
  "domain"     : "DomainName",
  "input"      : { ...agent-specific keys as shown above... },
  "depends_on" : ["id_of_node_this_depends_on"]  // [] if no dependencies
}
"""

    # ------------------------------------------------------------------
    # get_registry_description — unchanged from public repo
    # ------------------------------------------------------------------

    def get_registry_description(self) -> dict:
        return {
            agent_key: {
                "function" : entry["fn"].__name__,
                "domain"   : entry["domain"],
            }
            for agent_key, entry in self._registry.items()
        }


# =============================================================================
# MODULE-LEVEL SINGLETON — unchanged from public repo
# =============================================================================

AGENT_TOOLKIT = AgentRegistry()
logging.info("✅ Agent Registry (NIM edition) initialised.")
