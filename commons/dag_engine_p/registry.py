# =============================================================================
# registry.py  —  Domain-Aware Agent Registry
# commons/dag_engine/registry.py
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT CHANGED FROM commons/engine/registry.py:
#   1. Each agent entry now declares a `domain` field.
#   2. `get_handler()` accepts `domain` and `adapter` instead of the five
#      individual Pinecone params (index, namespace_context, namespace_knowledge,
#      embedding_model split across callers). The adapter carries all of that.
#   3. `Legal:Researcher` is registered as a second entry for the same
#      agent_researcher function, routed to the Legal namespace via the adapter.
#   4. `get_capabilities_description()` now declares each agent's domain so
#      the Planner can correctly assign the `domain` field in DAG nodes.
#   5. `get_registry_description()` added for harness audit and docx generation.
#
# WHAT DID NOT CHANGE:
#   - The four agent functions themselves are unchanged.
#   - The lambda-wrapping pattern is preserved — same closure structure,
#     adapter replaces the five individual params.
#   - AGENT_TOOLKIT is still the module-level singleton.
#
# RELATIONSHIP TO OTHER FILES:
#   - Imported by: engine.py, run_dag.py
#   - Imports:     agents.py (agent functions)
#                  helpers.py (create_mcp_message — kept for structural parity)
# =============================================================================

import logging
import agents
from helpers import create_mcp_message


# =============================================================================
# SECTION A — THE REGISTRY CLASS
# =============================================================================

class AgentRegistry:
    """
    Domain-aware registry of all agents available to the DAG engine.

    Each entry declares:
        fn      — the agent function (from agents.py, unchanged)
        domain  — the governance domain this agent belongs to

    The registry is keyed by "AgentName" for General-domain agents and
    "Domain:AgentName" for domain-specific agents. The Planner uses the
    capabilities description to assign the correct agent name and domain
    to each DAG node.
    """

    def __init__(self):
        # ------------------------------------------------------------------
        # AGENT REGISTRY
        # Key format:
        #   "AgentName"          — General domain (used for most POC agents)
        #   "Domain:AgentName"   — Domain-specific agent (A2A seam)
        #
        # All four original agents remain in the General domain.
        # Legal:Researcher is the first domain-specific entry — same function,
        # different domain routing via the adapter's resolve_namespace().
        # ------------------------------------------------------------------
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
            # Same agent_researcher function, but routed to the Legal namespace
            # via adapter.resolve_namespace("Legal", "knowledge").
            # In Phase 2, this entry gains a `remote_endpoint` field and
            # dispatch_node() routes it as an HTTP call instead.
            "Legal:Researcher": {
                "fn"    : agents.agent_researcher,
                "domain": "Legal",
            },

            # --- Marketing domain agents ---
            # Marketing:Researcher uses the same function, routed to the
            # Marketing namespace. Currently Marketing shares the same physical
            # Pinecone namespaces as General — the domain distinction is logical.
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
    # Returns a lambda ready to call with one argument: mcp_message
    # ------------------------------------------------------------------

    def get_handler(self, agent_name: str, domain: str,
                    client, adapter, generation_model: str,
                    embedding_model: str):
        """
        Resolve an agent name + domain to a callable handler.

        The handler is a lambda that accepts one argument (mcp_message)
        and returns an MCP-envelope dict. All other dependencies are
        closed over from the arguments to this method.

        Lookup priority:
            1. "Domain:AgentName"  — domain-specific entry (e.g. "Legal:Researcher")
            2. "AgentName"         — General entry (fallback for General-domain nodes)

        Args:
            agent_name (str):       Agent name from the DAG node (e.g. "Researcher").
            domain (str):           Domain from the DAG node (e.g. "Legal").
            client:                 OpenAI-compatible LLM client.
            adapter:                StorageAdapter instance (PineconeAdapter or subclass).
            generation_model (str): Model name for generation calls.
            embedding_model (str):  Model name for embedding calls.

        Returns:
            Callable: lambda(mcp_message) → dict

        Raises:
            ValueError: If neither "Domain:AgentName" nor "AgentName" is registered.
        """
        # Try domain-specific key first
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
            f"key='{qualified_key}' → fn={handler_fn.__name__} domain={resolved_domain}"
        )

        # ------------------------------------------------------------------
        # Resolve namespaces via adapter for this domain.
        # adapter.resolve_namespace() maps (domain, role) → physical namespace.
        # This replaces the five individual params from the old get_handler().
        # ------------------------------------------------------------------
        try:
            ns_knowledge = adapter.resolve_namespace(resolved_domain, "knowledge")
            ns_context   = adapter.resolve_namespace(resolved_domain, "context")
        except KeyError:
            # Domain not in adapter namespace map — fall back to General namespaces.
            # Log a warning so the developer knows to register the domain.
            logging.warning(
                f"[Registry] Domain '{resolved_domain}' not in adapter namespace map. "
                f"Falling back to General namespaces."
            )
            ns_knowledge = adapter.resolve_namespace("General", "knowledge")
            ns_context   = adapter.resolve_namespace("General", "context")

        # ------------------------------------------------------------------
        # Return the appropriate lambda based on agent name.
        # Pattern is identical to the original registry — adapter replaces
        # the five individual Pinecone params.
        # ------------------------------------------------------------------

        base_name = agent_name  # e.g. "Researcher" from "Legal:Researcher"

        if base_name == "Librarian":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client          = client,
                index           = adapter._index,
                embedding_model = embedding_model,
                namespace_context = ns_context,
            )

        elif base_name == "Researcher":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client            = client,
                index             = adapter._index,
                generation_model  = generation_model,
                embedding_model   = embedding_model,
                namespace_knowledge = ns_knowledge,
            )

        elif base_name == "Summarizer":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client           = client,
                generation_model = generation_model,
            )

        elif base_name == "Writer":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client           = client,
                generation_model = generation_model,
            )

        else:
            # Generic fallback — pass the full adapter for future agents
            # that declare their own dependency signature.
            logging.warning(
                f"[Registry] No specific lambda pattern for '{base_name}'. "
                f"Using generic pass-through. Ensure the agent function "
                f"accepts (mcp_message, client, adapter, generation_model)."
            )
            return lambda mcp_message: handler_fn(
                mcp_message,
                client           = client,
                adapter          = adapter,
                generation_model = generation_model,
            )

    # ------------------------------------------------------------------
    # get_capabilities_description
    # Injected into the Planner prompt so the LLM knows which agents
    # exist, what domain they belong to, and what inputs they require.
    # ------------------------------------------------------------------

    def get_capabilities_description(self) -> str:
        """
        Returns a structured plain-text description of all registered agents
        for injection into the Planner's system prompt.

        Each agent entry includes its domain so the Planner assigns the
        correct `domain` field in every DAG node it emits.
        """
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
    # get_registry_description — for audit log and docx generation
    # ------------------------------------------------------------------

    def get_registry_description(self) -> dict:
        """
        Return a structured summary of all registered agents.
        Used by the harness audit log and the docx documentation generator.
        """
        return {
            agent_key: {
                "function" : entry["fn"].__name__,
                "domain"   : entry["domain"],
            }
            for agent_key, entry in self._registry.items()
        }


# =============================================================================
# MODULE-LEVEL SINGLETON
# Matches the original pattern — AGENT_TOOLKIT is the shared instance.
# =============================================================================

AGENT_TOOLKIT = AgentRegistry()
logging.info("✅ Agent Registry (DAG edition) initialised.")
