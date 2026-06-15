# =============================================================================
# engine.py  —  The Universal Context Engine (DAG Edition)
# commons/dag_engine/engine.py
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT CHANGED FROM commons/engine/engine.py:
#
#   ExecutionTrace:
#     - `log_plan(plan)`  →  `log_dag(dag)`  stores graph shape (nodes + edges)
#     - `log_step()` signature updated: step_num → node_id, adds domain field
#     - `finalize()` unchanged
#
#   planner():
#     - Incorporates planner_robust_patch permanently (no more hotfix cell)
#     - Prompt upgraded to emit DAG nodes with `id`, `domain`, `depends_on`
#       instead of flat `{"plan": [{"step": N, ...}]}` shape
#     - Fallback safety: accepts bare list if "nodes" key is absent
#     - `json_mode=True` retained
#
#   context_engine() signature:
#     - Replaces 7 Pinecone-specific params with 3 clean injected deps:
#         adapter   (PineconeAdapter — from adapters.py)
#         registry  (AgentRegistry  — from registry.py)
#         harness   (Harness        — from harness.py, optional)
#     - Gate 1 runs inside context_engine if harness is provided
#     - Gate 2 (topology) runs after planning, before run_dag()
#     - Linear `for step in plan:` loop replaced by `run_dag()` call
#     - Final output resolved via `find_terminal_nodes()` — not assumed last
#
#   resolve_dependencies() retained as a thin alias for backward compat.
#   The real implementation lives in run_dag.py → resolve_inputs().
#
# WHAT DID NOT CHANGE:
#   - ExecutionTrace.finalize() signature
#   - call_llm_robust() usage pattern
#   - json_mode=True on planner LLM call
#   - Logging style and granularity
# =============================================================================

import logging
import time
import json
import copy

from helpers   import call_llm_robust, create_mcp_message, count_tokens
from registry  import AGENT_TOOLKIT
from run_dag   import run_dag, find_terminal_nodes, resolve_inputs
from adapters  import StorageAdapterBase


# =============================================================================
# SECTION A — ExecutionTrace  (DAG edition)
# =============================================================================

class ExecutionTrace:
    """
    Records the full execution flow of one context_engine() call.

    DAG edition changes vs linear edition:
      - `log_plan(plan)`  →  `log_dag(dag)`   stores nodes + edges
      - `log_step()` uses node_id (string) instead of step_num (int)
      - `log_step()` adds `domain` field for cross-domain visibility
      - All other behaviour identical
    """

    def __init__(self, goal: str):
        self.goal         = goal
        self.dag          = None          # Execution DAG (nodes + edges)
        self.steps        = []            # One entry per completed node
        self.status       = "Initialized"
        self.final_output = None
        self.start_time   = time.time()
        logging.info(f"[Trace] Initialized for goal: '{self.goal[:80]}...'")

    # ------------------------------------------------------------------
    # log_dag  —  replaces log_plan
    # Stores the full DAG shape: node ids, agents, domains, edges.
    # ------------------------------------------------------------------
    def log_dag(self, dag: list):
        """Store the Execution DAG produced by the planner."""
        self.dag = dag
        node_summary = [
            {
                "id"        : n["id"],
                "agent"     : n["agent"],
                "domain"    : n.get("domain", "General"),
                "depends_on": n.get("depends_on", []),
            }
            for n in dag
        ]
        logging.info(
            f"[Trace] DAG logged. {len(dag)} node(s): "
            f"{[n['id'] for n in dag]}"
        )
        logging.debug(f"[Trace] DAG shape: {json.dumps(node_summary, indent=2)}")

    # ------------------------------------------------------------------
    # log_step  —  one entry per completed DAG node
    # ------------------------------------------------------------------
    def log_step(self, node_id: str, agent: str, domain: str,
                 resolved_input: dict, output, tokens_in: int = 0,
                 tokens_out: int = 0):
        """
        Log the result of one completed DAG node.

        Args:
            node_id (str):         The node's unique id (e.g. "legal_researcher").
            agent (str):           Agent name (e.g. "Researcher").
            domain (str):          Domain (e.g. "Legal").
            resolved_input (dict): Input with all $$refs$$ replaced.
            output:                Agent output (content of MCP envelope).
            tokens_in (int):       Token count of resolved_input.
            tokens_out (int):      Token count of output.
        """
        entry = {
            "node_id"         : node_id,
            "agent"           : agent,
            "domain"          : domain,
            "resolved_input"  : resolved_input,
            "output"          : output,
            "tokens_in"       : tokens_in,
            "tokens_out"      : tokens_out,
            # Token savings only meaningful for Summarizer
            "tokens_saved"    : max(0, tokens_in - tokens_out) if agent == "Summarizer" else 0,
        }
        self.steps.append(entry)
        logging.info(
            f"[Trace] Node '{node_id}' ({agent}/{domain}) logged. "
            f"[In:{tokens_in} Out:{tokens_out}]"
        )

    # ------------------------------------------------------------------
    # finalize  —  unchanged from linear edition
    # ------------------------------------------------------------------
    def finalize(self, status: str, final_output=None):
        self.status       = status
        self.final_output = final_output
        self.duration     = time.time() - self.start_time
        logging.info(
            f"[Trace] Finalized — status='{status}' "
            f"duration={self.duration:.2f}s"
        )

    # ------------------------------------------------------------------
    # summary  —  structured dict for docx / HTML generation
    # ------------------------------------------------------------------
    def summary(self) -> dict:
        """
        Return a structured summary of the full execution.
        Used by the documentation and animated HTML generators.
        """
        total_in  = sum(s["tokens_in"]    for s in self.steps)
        total_out = sum(s["tokens_out"]   for s in self.steps)
        saved     = sum(s["tokens_saved"] for s in self.steps)

        return {
            "goal"          : self.goal,
            "status"        : self.status,
            "duration_s"    : round(getattr(self, "duration", 0), 2),
            "dag_nodes"     : len(self.dag) if self.dag else 0,
            "steps_complete": len(self.steps),
            "tokens_in"     : total_in,
            "tokens_out"    : total_out,
            "tokens_saved"  : saved,
            "dag"           : self.dag,
            "steps"         : self.steps,
            "final_output"  : self.final_output,
        }


# =============================================================================
# SECTION B — Planner  (robust patch folded in permanently)
# =============================================================================

def planner(goal: str, capabilities: str, client, generation_model: str) -> list:
    """
    Analyze the goal and produce an Execution DAG as a list of node dicts.

    Each node:
        {
            "id"         : "unique_snake_case_id",
            "agent"      : "AgentName",
            "domain"     : "DomainName",
            "input"      : { ...agent-specific keys... },
            "depends_on" : ["id_of_dependency"]   // [] if no dependencies
        }

    The planner_robust_patch from the Universal notebook is folded in here
    permanently. Its two fixes are:
        1. Explicit node schema shown in the prompt (prevents hallucinated keys)
        2. Fallback: if LLM returns a bare list instead of {"nodes": [...]},
           accept it rather than crashing.

    Returns:
        list[dict]: The Execution DAG as a list of node dicts.

    Raises:
        ValueError: If the LLM output cannot be parsed or contains no nodes.
    """
    logging.info("[Planner] Activated. Generating Execution DAG...")

    system_prompt = f"""
You are the strategic core of the Universal Context Engine.
Analyze the user's high-level GOAL and create an EXECUTION DAG.

AVAILABLE CAPABILITIES
---
{capabilities}
---
END CAPABILITIES

OUTPUT FORMAT:
Return a single JSON object with a "nodes" key containing a list of node objects.
Every node MUST follow this EXACT schema — no extra keys, no missing keys:

{{
  "nodes": [
    {{
      "id"         : "unique_snake_case_id",
      "agent"      : "<Agent Name from capabilities>",
      "domain"     : "<Domain from capabilities — must match the agent's declared domain>",
      "input"      : {{
          "<input_key>": "<input_value or $$other_node_id$$ reference>"
      }},
      "depends_on" : ["id_of_node_whose_output_this_node_needs"]
    }}
  ]
}}

CRITICAL RULES:
1. `id`         — unique, snake_case, descriptive (e.g. "legal_researcher", "marketing_librarian").
2. `agent`      — MUST be one of the exact agent names listed in AVAILABLE CAPABILITIES.
3. `domain`     — MUST match the domain declared for that agent in AVAILABLE CAPABILITIES.
4. `input`      — MUST use the exact input key names shown for that agent. No others.
5. `depends_on` — list every node_id whose output this node references via $$ref$$.
                  If no dependencies, use an empty list [].
6. References   — use $$node_id$$ (not $$STEP_N_OUTPUT$$). The node_id is the `id`
                  field of the node being referenced.
7. Concurrency  — nodes with no shared dependencies run in PARALLEL.
                  Only add depends_on when the input genuinely requires another
                  node's output. Do not chain unnecessarily.
8. The Librarian has no dependencies — it always starts immediately.
"""

    try:
        dag_json_string = call_llm_robust(
            system_prompt,
            goal,
            client           = client,
            generation_model = generation_model,
            json_mode        = True
        )

        dag_data = json.loads(dag_json_string)

        # --- Robust patch: accept bare list if "nodes" key is absent ---
        if isinstance(dag_data, list):
            logging.warning(
                "[Planner] LLM returned a bare list instead of {'nodes': [...]}. "
                "Accepting — check prompt compliance."
            )
            nodes = dag_data

        elif "nodes" in dag_data:
            nodes = dag_data["nodes"]

        # Legacy fallback: old planner emitted {"plan": [...]}
        elif "plan" in dag_data:
            logging.warning(
                "[Planner] LLM returned legacy {'plan': [...]} format. "
                "Converting to DAG nodes — consider rerunning."
            )
            nodes = _convert_legacy_plan(dag_data["plan"])

        else:
            raise ValueError(
                f"Planner output missing 'nodes' key. "
                f"Keys found: {list(dag_data.keys())}"
            )

        if not nodes:
            raise ValueError("Planner returned an empty node list.")

        logging.info(
            f"[Planner] DAG generated. {len(nodes)} node(s): "
            f"{[n.get('id', '?') for n in nodes]}"
        )
        return nodes

    except json.JSONDecodeError as e:
        logging.error(f"[Planner] JSON parse error: {e}")
        raise
    except Exception as e:
        logging.error(f"[Planner] Failed to generate DAG: {e}")
        raise


def _convert_legacy_plan(plan: list) -> list:
    """
    Convert a legacy linear plan ({"step": N, "agent": ..., "input": ...})
    to DAG node format. Assumes sequential dependencies.
    Used as a fallback only — the planner prompt should produce DAG format.
    """
    nodes = []
    for i, step in enumerate(plan):
        step_num = step.get("step", i + 1)
        node_id  = f"step_{step_num}"
        nodes.append({
            "id"        : node_id,
            "agent"     : step.get("agent", "Unknown"),
            "domain"    : step.get("domain", "General"),
            "input"     : step.get("input", {}),
            "depends_on": [f"step_{step_num - 1}"] if step_num > 1 else [],
        })
    return nodes


# =============================================================================
# SECTION C — resolve_dependencies  (thin alias for backward compat)
# The real implementation is resolve_inputs() in run_dag.py.
# =============================================================================

def resolve_dependencies(input_params: dict, state: dict) -> dict:
    """
    Backward-compatible alias for run_dag.resolve_inputs().
    `state` here is the completed_outputs dict keyed by node_id.
    """
    return resolve_inputs(input_params, state)


# =============================================================================
# SECTION D — context_engine  (DAG edition)
# =============================================================================

def context_engine(goal: str, client, adapter: StorageAdapterBase,
                   generation_model: str, embedding_model: str,
                   registry=None, harness=None) -> tuple:
    """
    The main entry point for the Universal Context Engine (DAG edition).

    Sequence:
        [Gate 1]  harness.gate(goal)           — if harness provided
        [Plan]    planner()                    — produces Execution DAG
        [Gate 2]  harness.validate_topology()  — if harness provided
        [Execute] run_dag()                    — concurrent DAG executor
        [Return]  final output + trace

    Args:
        goal (str):                  The user's high-level goal.
        client:                      OpenAI-compatible LLM client.
        adapter (StorageAdapterBase):Storage adapter (PineconeAdapter or subclass).
        generation_model (str):      Model name for generation calls.
        embedding_model (str):       Model name for embedding calls.
        registry:                    AgentRegistry instance. Defaults to AGENT_TOOLKIT.
        harness:                     Harness instance. If None, gates are skipped.
                                     Recommended: always provide in production.

    Returns:
        tuple: (final_output, trace)
            final_output: Output of the terminal DAG node(s).
            trace:        ExecutionTrace instance with full execution record.
    """
    logging.info(f"[Engine] Starting. Goal: '{goal[:80]}...'")
    trace    = ExecutionTrace(goal)
    registry = registry or AGENT_TOOLKIT

    # ------------------------------------------------------------------
    # GATE 1 — Business rules (before any LLM call)
    # ------------------------------------------------------------------
    if harness is not None:
        gate1_result = harness.gate(goal)
        if not gate1_result["allowed"]:
            logging.warning(f"[Engine] Gate 1 VETO: {gate1_result['reason']}")
            trace.finalize(f"Vetoed at Gate 1: {gate1_result['reason']}")
            return None, trace
        logging.info("[Engine] Gate 1 passed.")
    else:
        logging.warning(
            "[Engine] No harness provided — Gate 1 skipped. "
            "Recommended: pass a Harness instance for production use."
        )

    # ------------------------------------------------------------------
    # PLANNING — produce the Execution DAG
    # ------------------------------------------------------------------
    try:
        capabilities = registry.get_capabilities_description()
        dag = planner(
            goal,
            capabilities,
            client           = client,
            generation_model = generation_model,
        )
        trace.log_dag(dag)

    except Exception as e:
        logging.error(f"[Engine] Planning failed: {e}")
        trace.finalize(f"Failed during Planning: {e}")
        return None, trace

    # ------------------------------------------------------------------
    # GATE 2 — Topology validation (after planning, before execution)
    # ------------------------------------------------------------------
    if harness is not None:
        gate2_result = harness.validate_topology(dag)
        if not gate2_result["allowed"]:
            logging.warning(f"[Engine] Gate 2 VETO: {gate2_result['reason']}")
            trace.finalize(f"Vetoed at Gate 2: {gate2_result['reason']}")
            return None, trace
        logging.info("[Engine] Gate 2 passed.")

    # ------------------------------------------------------------------
    # EXECUTION — run the DAG
    # ------------------------------------------------------------------
    try:
        completed_outputs = run_dag(
            dag              = dag,
            registry         = registry,
            adapter          = adapter,
            client           = client,
            generation_model = generation_model,
            embedding_model  = embedding_model,
            trace            = trace,
            local_domain     = "General",
        )

    except RuntimeError as e:
        # Cycle detected or node failure — already logged by run_dag
        logging.error(f"[Engine] Execution failed: {e}")
        trace.finalize(f"Failed during Execution: {e}")
        return None, trace

    except Exception as e:
        logging.error(f"[Engine] Unexpected execution error: {e}")
        trace.finalize(f"Failed during Execution: {e}")
        return None, trace

    # ------------------------------------------------------------------
    # FINALISATION — find terminal node output(s)
    # ------------------------------------------------------------------
    terminal_ids = find_terminal_nodes(dag)

    if len(terminal_ids) == 1:
        final_output = completed_outputs.get(terminal_ids[0])
    else:
        # Multiple terminal nodes — return all outputs as a dict
        final_output = {
            tid: completed_outputs.get(tid)
            for tid in terminal_ids
        }
        logging.info(
            f"[Engine] Multiple terminal nodes: {terminal_ids}. "
            f"Returning dict of outputs."
        )

    trace.finalize("Success", final_output)
    logging.info("[Engine] Task complete.")
    return final_output, trace
