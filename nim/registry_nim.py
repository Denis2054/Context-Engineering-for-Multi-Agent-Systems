# =============================================================================
# registry_nim.py  —  Domain-Aware Agent Registry
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# The registry does two jobs that look unrelated and are in fact the same job
# seen from two directions:
#
#   1. It tells the PLANNER what exists. get_capabilities_description() renders
#      the prose block that is pasted into the planner's system prompt. If an
#      agent is not described there, no plan will ever reference it.
#
#   2. It tells the FOREMAN how to call it. get_handler() turns the pair
#      (agent name, domain) into a closure the Foreman can invoke with nothing
#      but an MCP envelope.
#
# One structure feeding both sides is what keeps the planner's mental model and
# the executor's reality from drifting apart. Add an agent here and both the
# prompt and the dispatch table update together.
#
# DUAL-MODEL ROUTING
# ------------------
# get_handler() takes an optional `agent_model`. When it is None the agents run
# on whatever the planner runs on, which is the single-model behaviour. When it
# is set, the planner keeps `generation_model` and every agent gets
# `agent_model`.
#
# That one parameter is the whole of the NIM cost strategy. Planning is called
# once and must be right, so it gets the 120B model. Agent calls are called
# once per node and are individually easy, so they get the 30B model. On an
# eight-node DAG that is one expensive call and eight cheap ones instead of
# nine expensive ones.
#
# THE A2A SEAM
# ------------
# Three registry entries — Researcher, Legal:Researcher, Marketing:Researcher —
# point at the same function. Nothing about the code differs. What differs is
# the namespace the adapter resolves for that domain, and the governance edges
# the Harness will enforce around the node.
#
# That is deliberate. Today a "cross-domain call" is a dictionary lookup in one
# process. When Legal moves behind its own service, the change is confined to
# dispatch_node() in run_dag_nim.py: the lookup becomes an HTTP POST. The
# planner, the capabilities block, and the topology rules do not move, because
# they were written against domains rather than against processes.
# =============================================================================

import logging

import agents
from helpers import create_mcp_message


class AgentRegistry:
    """
    The catalogue of callable agents, keyed by name and by "Domain:Name".

    Each entry declares the function to call and the governance domain it
    belongs to. Domain membership is not decoration — the Harness reads it at
    Gate 2 to decide which edges of the planned DAG are permitted.
    """

    def __init__(self):
        self._registry = {

            # ---- General: the default domain ----------------------------
            "Librarian" : {"fn": agents.agent_context_librarian, "domain": "General"},
            "Researcher": {"fn": agents.agent_researcher,        "domain": "General"},
            "Summarizer": {"fn": agents.agent_summarizer,        "domain": "General"},
            "Writer"    : {"fn": agents.agent_writer,            "domain": "General"},

            # ---- Legal: same function, different governance --------------
            # Registering the identical callable under a domain-qualified key
            # is what makes the A2A seam visible without yet being distributed.
            "Legal:Researcher": {"fn": agents.agent_researcher, "domain": "Legal"},

            # ---- Marketing ------------------------------------------------
            "Marketing:Researcher": {"fn": agents.agent_researcher, "domain": "Marketing"},
        }

        logging.info(
            f"[Registry] initialised. agents={sorted(self._registry.keys())}"
        )

    # ------------------------------------------------------------------
    # get_handler — resolve (name, domain) to a callable
    # ------------------------------------------------------------------

    def get_handler(self, agent_name: str, domain: str,
                    client, adapter, generation_model: str,
                    embedding_model: str, agent_model: str = None):
        """
        Build a closure that runs one agent, fully wired.

        The returned callable takes exactly one argument: an MCP envelope. Every
        other dependency — client, index, model, namespace — is captured here.
        That is what lets the Foreman schedule a Legal Researcher and a General
        Summarizer through identical code.

        Args:
            agent_name (str):       from the DAG node, e.g. "Researcher".
            domain (str):           from the DAG node, e.g. "Legal".
            client:                 LLM and embedding credential holder.
            adapter:                StorageAdapter; supplies the index and
                                    resolves namespaces.
            generation_model (str): the planner's model.
            embedding_model (str):  must match the index.
            agent_model (str|None): agent model. None means "same as planner".

        Returns:
            Callable[[dict], dict]: envelope in, envelope out.

        Raises:
            ValueError: unknown agent, listing the keys that were tried.
        """
        effective_agent_model = agent_model if agent_model is not None else generation_model

        if agent_model is not None:
            logging.info(
                f"[Registry] dual-model routing | "
                f"planner={generation_model} agents={effective_agent_model}"
            )

        # Domain-qualified key first, bare name as fallback. This is what makes
        # "Legal:Researcher" resolve to the Legal entry while a plain
        # "Researcher" node still finds the General one.
        qualified_key = f"{domain}:{agent_name}"
        entry = self._registry.get(qualified_key) or self._registry.get(agent_name)

        if not entry:
            msg = (
                f"Agent '{agent_name}' (domain='{domain}') is not registered. "
                f"Tried keys: ['{qualified_key}', '{agent_name}']. "
                f"Registered: {sorted(self._registry.keys())}"
            )
            logging.error(f"[Registry] {msg}")
            raise ValueError(msg)

        handler_fn      = entry["fn"]
        resolved_domain = entry["domain"]

        logging.info(
            f"[Registry] {qualified_key} -> {handler_fn.__name__} "
            f"domain={resolved_domain} model={effective_agent_model}"
        )

        # Namespace resolution happens here, once, rather than inside the agent.
        # An unregistered domain degrades to General with a warning instead of
        # failing — a planner hallucinating "Finance" should produce a usable
        # run and a visible warning, not a crash.
        try:
            ns_knowledge = adapter.resolve_namespace(resolved_domain, "knowledge")
            ns_context   = adapter.resolve_namespace(resolved_domain, "context")
        except KeyError:
            logging.warning(
                f"[Registry] domain '{resolved_domain}' is not in the adapter's "
                f"namespace map — falling back to General namespaces."
            )
            ns_knowledge = adapter.resolve_namespace("General", "knowledge")
            ns_context   = adapter.resolve_namespace("General", "context")

        # Each agent has a different signature, so each gets its own closure.
        # Note that only the three generating agents receive a model; the
        # Librarian embeds and retrieves and never calls a chat endpoint.
        if agent_name == "Librarian":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client            = client,
                index             = adapter._index,
                embedding_model   = embedding_model,
                namespace_context = ns_context,
            )

        if agent_name == "Researcher":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client              = client,
                index               = adapter._index,
                generation_model    = effective_agent_model,
                embedding_model     = embedding_model,
                namespace_knowledge = ns_knowledge,
            )

        if agent_name == "Summarizer":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client           = client,
                generation_model = effective_agent_model,
            )

        if agent_name == "Writer":
            return lambda mcp_message: handler_fn(
                mcp_message,
                client           = client,
                generation_model = effective_agent_model,
            )

        logging.warning(
            f"[Registry] no specific closure for '{agent_name}' — "
            f"using the generic pass-through."
        )
        return lambda mcp_message: handler_fn(
            mcp_message,
            client           = client,
            adapter          = adapter,
            generation_model = effective_agent_model,
        )

    # ------------------------------------------------------------------
    # get_capabilities_description — the planner's view of the world
    # ------------------------------------------------------------------

    def get_capabilities_description(self) -> str:
        """
        Render the capabilities block for the planner's system prompt.

        This string is the API documentation the planner reads, and its
        precision determines plan quality more than any other single factor.
        Three things earn their place:

          - EXACT input key names. The Foreman's resolver looks up literal keys.
            A plan that says "query" where the agent expects "topic_query"
            fails at execution, after you have paid for the planning call.

          - The domain of every agent. Gate 2 validates cross-domain edges
            against the topology, so a plan that omits or invents domains is
            vetoed before any agent runs.

          - An explicit instruction to avoid unnecessary dependencies. Left to
            itself a planner will emit a chain, because chains are what plans
            look like in most training data. Concurrency has to be asked for.
        """
        return """
Available Agents and their required inputs.

CRITICAL RULES FOR THE PLANNER:
  1. Use the EXACT input key names shown below — no variations, no synonyms.
  2. Every node MUST include a `domain` field matching the agent's domain.
  3. Use $$node_id$$ syntax to reference the output of a prior node.
  4. `depends_on` must list every node_id whose output this node references.
  5. Nodes with no dependencies run CONCURRENTLY. Only add a dependency when
     the input genuinely requires another node's output. Do not chain by habit.

─────────────────────────────────────────────────────────────────────
DOMAIN: General
─────────────────────────────────────────────────────────────────────

1. AGENT: Librarian  |  domain: "General"
   ROLE: Retrieves Semantic Blueprints — style, tone, and structure rules for
         the Writer. Has no dependencies and should always start immediately.
   INPUTS:
     - "intent_query": (String) Descriptive phrase of the desired output style.
   OUTPUT: {"blueprint_json": "..."} (dict).

2. AGENT: Researcher  |  domain: "General"
   ROLE: Retrieves and synthesizes factual information from the General
         knowledge store, with source citations.
   INPUTS:
     - "topic_query": (String) The subject matter to research.
   OUTPUT: {"answer_with_sources": "..."} (dict).

3. AGENT: Summarizer  |  domain: "General"
   ROLE: Reduces large text to a concise summary serving a stated objective.
         Place between a Researcher and the Writer whenever the research
         output is likely to be long.
   INPUTS:
     - "text_to_summarize": (String or $$ref$$) The text to reduce.
     - "summary_objective": (String) What the summary must achieve.
   OUTPUT: {"summary": "..."} (dict).

4. AGENT: Writer  |  domain: "General"
   ROLE: Produces the final artefact by applying a Blueprint to source material.
   INPUTS:
     - "blueprint":        (String or $$ref$$) Style rules, from the Librarian.
     - "facts":            (String or $$ref$$) Content, from a Researcher or Summarizer.
     - "previous_content": (String or $$ref$$) Existing text to rewrite (optional).
   OUTPUT: Final generated text (String).

─────────────────────────────────────────────────────────────────────
DOMAIN: Legal
─────────────────────────────────────────────────────────────────────

5. AGENT: Researcher  |  domain: "Legal"
   ROLE: Retrieves and synthesizes legal information — contracts, NDAs,
         service agreements, compliance policies. Use whenever the goal
         requires legal verification or clause extraction.
   INPUTS:
     - "topic_query": (String) The legal subject matter to research.
   OUTPUT: {"answer_with_sources": "..."} (dict).

─────────────────────────────────────────────────────────────────────
DOMAIN: Marketing
─────────────────────────────────────────────────────────────────────

6. AGENT: Researcher  |  domain: "Marketing"
   ROLE: Retrieves and synthesizes marketing information — product specs,
         brand guides, competitor intelligence, campaign briefs.
   INPUTS:
     - "topic_query": (String) The marketing subject matter to research.
   OUTPUT: {"answer_with_sources": "..."} (dict).

─────────────────────────────────────────────────────────────────────
NODE STRUCTURE — every node must follow this exactly:
─────────────────────────────────────────────────────────────────────
{
  "id"         : "unique_snake_case_id",
  "agent"      : "AgentName",
  "domain"     : "DomainName",
  "input"      : { ...agent-specific keys exactly as listed above... },
  "depends_on" : ["id_of_node_this_depends_on"]   // [] when independent
}
"""

    # ------------------------------------------------------------------
    # get_registry_description — machine-readable view, for the inspector
    # ------------------------------------------------------------------

    def get_registry_description(self) -> dict:
        """Return {registry_key: {function, domain}} for display and audit."""
        return {
            key: {"function": entry["fn"].__name__, "domain": entry["domain"]}
            for key, entry in self._registry.items()
        }


# =============================================================================
# MODULE-LEVEL SINGLETON
#
# One registry per process. The engine defaults to it, so a caller who does not
# care about registry composition can ignore the argument entirely — while a
# caller who does can build their own AgentRegistry and pass it in.
# =============================================================================

AGENT_TOOLKIT = AgentRegistry()
logging.info("Agent registry loaded (NIM edition).")
