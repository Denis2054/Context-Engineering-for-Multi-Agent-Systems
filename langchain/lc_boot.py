# lc_boot.py
# =============================================================================
# Universal Context Engine — LangChain Edition
# Assembly. One call wires every component together.
#
# This file has no counterpart in the original project: the original assembled
# itself inside the notebook by passing `client`, `pc` and a config dict into
# every function. Here the wiring happens once and produces a single object.
# =============================================================================

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import lc_agents
import lc_engine
import lc_helpers
import lc_registry


@dataclass
class ContextEngine:
    """Everything the engine needs, assembled and ready to run."""
    config: Dict[str, Any]
    llm: Any
    base_llm: Any
    embeddings: Any
    context_store: Any
    knowledge_store: Any
    blueprint_retriever: Any
    knowledge_retriever: Any
    toolkit: Any
    graph: Any
    tracker: Any
    tools: List = field(default_factory=list)
    _planner: Any = None

    # ------------------------------------------------------------------ #
    def run(self, goal: str, moderation_active: bool = False
            ) -> Tuple[Optional[str], lc_engine.LangChainTrace]:
        """
        Execute a goal. Returns (result, trace).

        Mirrors the original notebook's execute_and_display flow: pre-flight
        moderation on the goal, the engine, then post-flight moderation on the
        output. Rendering is left to the caller.

        CONTRACT NOTE: a trace is ALWAYS returned, including when the goal is
        blocked before the engine runs. A blocked goal is an audit event, and an
        audit trail with a hole in it where the refusals should be is not an
        audit trail. Callers should check `trace.status`, not `trace is None`.
        """
        trace = lc_engine.LangChainTrace(goal)

        # A fresh tracker per run so token counts are per-run, not cumulative.
        self.tracker.reset()

        if moderation_active:
            print("--- [Safety Guardrail] Performing Pre-Flight Moderation Check on Goal ---")
            report = lc_helpers.moderate(goal, self.llm)
            trace.log_moderation("pre", report)

            if not report["available"]:
                print("\n🛑 Moderation could not be performed. Execution halted (fail-safe).")
                print(f"   Reason: {report['error']}")
                trace.finalize("Halted: moderation unavailable")
                return None, trace

            if report["flagged"]:
                print("\n🛑 Goal failed pre-flight moderation. Execution halted.")
                flagged = [k for k, v in report["categories"].items() if v]
                print("   Categories:", ", ".join(flagged) or "unspecified")
                trace.finalize("Halted: pre-flight moderation")
                return None, trace

        result, trace = lc_engine.context_engine(
            goal, self.graph, tracker=self.tracker, trace=trace
        )

        if result and moderation_active:
            text = result if isinstance(result, str) else str(result)
            report = lc_helpers.moderate(text, self.llm)
            trace.log_moderation("post", report)

            if report["flagged"] or not report["available"]:
                reason = ("failed post-flight moderation" if report["flagged"]
                          else "could not be checked (moderation unavailable)")
                print(f"\n🛑 Generated output {reason} and will be redacted.")
                result = ("[Content flagged as potentially harmful by moderation "
                          "policy and has been redacted.]")
                trace.final_output = result
                trace.status = "Redacted: post-flight moderation"

        return result, trace

    # ------------------------------------------------------------------ #
    def plan_only(self, goal: str) -> lc_engine.Plan:
        """Produce the plan without executing it. Useful for teaching and audit.

        Costs exactly one planning call: no retrieval, no generation.
        """
        if self._planner is None:
            self._planner = lc_engine.build_planner(
                self.llm, self.toolkit.get_capabilities_description()
            )
        return self._planner(goal)

    def capabilities(self) -> str:
        return self.toolkit.get_capabilities_description()


def build_context_engine(config: Optional[dict] = None,
                         verbose: bool = True) -> ContextEngine:
    """
    Wire the whole engine together.

        engine = build_context_engine()
        result, trace = engine.run("Summarize the NDA.")

    Any key in lc_helpers.CONFIG can be overridden:

        engine = build_context_engine({"k_knowledge": 5})

    Do NOT override embedding_model unless you have re-ingested the index; the
    stored vectors are 1536-dimensional text-embedding-3-small.
    """
    cfg = dict(lc_helpers.CONFIG)
    if config:
        unknown = set(config) - set(cfg)
        if unknown:
            raise KeyError(
                f"Unknown configuration key(s): {sorted(unknown)}. "
                f"Valid keys: {sorted(cfg)}"
            )
        cfg.update(config)

    llm = lc_helpers.build_llm(cfg)
    base_llm = lc_helpers.base_model(llm)
    embeddings = lc_helpers.build_embeddings(cfg)
    context_store, knowledge_store = lc_helpers.build_stores(embeddings, cfg)
    blueprint_retriever, knowledge_retriever = lc_helpers.build_retrievers(
        context_store, knowledge_store, cfg
    )

    tools = lc_agents.build_agents(
        llm, blueprint_retriever, knowledge_retriever, lc_helpers.sanitize
    )
    toolkit = lc_registry.build_toolkit(tools)
    tracker = lc_helpers.UsageTracker()

    graph = lc_engine.build_engine(
        llm, toolkit, tracker=tracker, count_tokens=lc_helpers.count_tokens
    )

    if verbose:
        print("Context Engine assembled (LangChain Edition).")
        print(f"   index      : {cfg['index_name']}")
        print(f"   generation : {cfg['generation_model']}")
        print(f"   embeddings : {cfg['embedding_model']}")
        print(f"   namespaces : {cfg['namespace_context']} (k={cfg['k_blueprint']}), "
              f"{cfg['namespace_knowledge']} (k={cfg['k_knowledge']})")
        print(f"   agents     : {', '.join(toolkit.names())}")

    return ContextEngine(
        config=cfg, llm=llm, base_llm=base_llm, embeddings=embeddings,
        context_store=context_store, knowledge_store=knowledge_store,
        blueprint_retriever=blueprint_retriever, knowledge_retriever=knowledge_retriever,
        toolkit=toolkit, graph=graph, tracker=tracker, tools=tools,
    )


# =============================================================================
# Route B — the idiomatic create_agent alternative, for comparison
# =============================================================================

def build_react_agent(engine: ContextEngine):
    """
    The same four tools handed to LangChain's standard agent builder.

    Difference from Route A: there is no plan object. The model calls one tool,
    sees the result, and decides what to do next. Six lines instead of sixty —
    at the cost of the up-front, inspectable, auditable plan that the Glass Box
    design depends on. Run both and compare the traces.

    Note also what is lost besides the plan: the per-step token attribution, the
    resolved-context record, and the ability to inspect and approve the work
    before any of it is paid for.
    """
    from langchain.agents import create_agent

    return create_agent(
        model=engine.base_llm,
        tools=engine.tools,
        system_prompt=(
            "You are the strategic core of the Context Engine. Achieve the "
            "user's goal using the available specialists. Typically: retrieve a "
            "Semantic Blueprint with the Librarian, gather grounded facts with "
            "the Researcher, then produce the deliverable with the Writer. "
            "Never invent facts that are not in the retrieved material."
        ),
    )


logging.info("LangChain Context Engine assembly module loaded.")
