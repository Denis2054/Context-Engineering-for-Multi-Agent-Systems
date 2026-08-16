# =============================================================================
# engine.py  —  The Universal Context Engine (NIM Edition)
# commons/dag_engine/engine.py  (private: Denis2054/SFT)
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT CHANGED FROM THE PUBLIC REPO VERSION:
#   TWO additions only — both in context_engine() signature and body:
#
#   1. agent_model (str|None) parameter added to context_engine()
#      Forwarded to run_dag() → dispatch_node() → registry.get_handler()
#      When set to utils.NIM_AGENT_MODEL: agents use Nemotron Nano Omni
#      When None (default): agents use generation_model (OpenAI path)
#
#   2. max_concurrent (int|None) parameter added to context_engine()
#      Forwarded to run_dag() to cap simultaneous NIM API calls.
#      When None (default): run_dag() reads utils.NIM_MAX_CONCURRENT (4)
#
#   EVERYTHING ELSE IS IDENTICAL TO THE PUBLIC REPO.
#   ExecutionTrace, planner(), resolve_dependencies() — all unchanged.
# =============================================================================

import logging
import time
import json
import copy

from helpers  import call_llm_robust, create_mcp_message, count_tokens
from registry import AGENT_TOOLKIT
from run_dag  import run_dag, find_terminal_nodes, resolve_inputs
from adapters import StorageAdapterBase


# =============================================================================
# SECTION A — ExecutionTrace  (unchanged from public repo)
# =============================================================================

class ExecutionTrace:
    """
    Records the full execution flow of one context_engine() call.
    Unchanged from the public repo — NIM runs produce identical trace structure.
    """

    def __init__(self, goal: str):
        self.goal         = goal
        self.dag          = None
        self.steps        = []
        self.status       = "Initialized"
        self.final_output = None
        self.start_time   = time.time()
        logging.info(f"[Trace] Initialized for goal: '{self.goal[:80]}...'")

    def log_dag(self, dag: list):
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

    def log_step(self, node_id: str, agent: str, domain: str,
                 resolved_input: dict, output, tokens_in: int = 0,
                 tokens_out: int = 0):
        entry = {
            "node_id"        : node_id,
            "agent"          : agent,
            "domain"         : domain,
            "resolved_input" : resolved_input,
            "output"         : output,
            "tokens_in"      : tokens_in,
            "tokens_out"     : tokens_out,
            "tokens_saved"   : max(0, tokens_in - tokens_out) if agent == "Summarizer" else 0,
        }
        self.steps.append(entry)
        logging.info(
            f"[Trace] Node '{node_id}' ({agent}/{domain}) logged. "
            f"[In:{tokens_in} Out:{tokens_out}]"
        )

    def finalize(self, status: str, final_output=None):
        self.status       = status
        self.final_output = final_output
        self.duration     = time.time() - self.start_time
        logging.info(
            f"[Trace] Finalized — status='{status}' "
            f"duration={self.duration:.2f}s"
        )

    def summary(self) -> dict:
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
# SECTION B — Planner  (unchanged from public repo)
# =============================================================================

def planner(goal: str, capabilities: str, client, generation_model: str) -> list:
    """
    Analyze the goal and produce an Execution DAG as a list of node dicts.

    Unchanged from public repo. On the NIM path, this is called with
    client=nim_client and generation_model=NIM_PLANNER_MODEL (Super).
    The Super model has superior JSON schema compliance for DAG generation
    and a 1M token context window.
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
1. `id`         — unique, snake_case, descriptive.
2. `agent`      — MUST be one of the exact agent names listed in AVAILABLE CAPABILITIES.
3. `domain`     — MUST match the domain declared for that agent in AVAILABLE CAPABILITIES.
4. `input`      — MUST use the exact input key names shown for that agent. No others.
5. `depends_on` — list every node_id whose output this node references via $$ref$$.
                  If no dependencies, use an empty list [].
6. References   — use $$node_id$$ (not $$STEP_N_OUTPUT$$).
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

        if isinstance(dag_data, list):
            logging.warning("[Planner] LLM returned bare list. Accepting.")
            nodes = dag_data
        elif "nodes" in dag_data:
            nodes = dag_data["nodes"]
        elif "plan" in dag_data:
            logging.warning("[Planner] Legacy plan format. Converting.")
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
# SECTION C — resolve_dependencies  (unchanged — thin alias)
# =============================================================================

def resolve_dependencies(input_params: dict, state: dict) -> dict:
    return resolve_inputs(input_params, state)


# =============================================================================
# SECTION D — context_engine  (NIM edition)
# =============================================================================

def context_engine(goal: str, client, adapter: StorageAdapterBase,
                   generation_model: str, embedding_model: str,
                   registry=None, harness=None,
                   agent_model: str = None,
                   max_concurrent: int = None) -> tuple:
    """
    The main entry point for the Universal Context Engine (NIM edition).

    NIM ADDITIONS vs public repo:
        agent_model (str|None):
            When set to utils.NIM_AGENT_MODEL, agent LLM calls use Nemotron
            Nano Omni while the Planner continues to use generation_model
            (NIM Super). Enables dual-model routing with one parameter.
            Default None = all calls use generation_model (OpenAI path).

        max_concurrent (int|None):
            Caps simultaneous in-flight LLM calls in the async parallel
            executor. Default None → run_dag reads utils.NIM_MAX_CONCURRENT.
            Pass an explicit int to override (e.g. 8 on paid NIM tier).

    All other args and return value are IDENTICAL to the public repo.

    Typical NIM usage:
        from utils import NIM_PLANNER_MODEL, NIM_AGENT_MODEL

        final_output, trace = context_engine(
            goal             = goal,
            client           = nim_client,
            adapter          = adapter,
            generation_model = NIM_PLANNER_MODEL,   # Super for Planner
            embedding_model  = "text-embedding-3-small",
            registry         = AGENT_TOOLKIT,
            harness          = gate,
            agent_model      = NIM_AGENT_MODEL,     # Nano for agents
        )

    Returns:
        tuple: (final_output, trace)
    """
    logging.info(
        f"[Engine] Starting. Goal: '{goal[:80]}...'\n"
        f"         Planner model: {generation_model}\n"
        f"         Agent model  : {agent_model or 'same as planner'}\n"
        f"         Max concurrent: {max_concurrent or 'auto (NIM_MAX_CONCURRENT)'}"
    )

    trace    = ExecutionTrace(goal)
    registry = registry or AGENT_TOOLKIT

    # ------------------------------------------------------------------
    # GATE 1 — Business rules (unchanged)
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
    # PLANNING — Planner uses generation_model (NIM Super on NIM path)
    # ------------------------------------------------------------------
    try:
        capabilities = registry.get_capabilities_description()
        dag = planner(
            goal,
            capabilities,
            client           = client,
            generation_model = generation_model,   # Super on NIM, gpt-5.1 on OpenAI
        )
        trace.log_dag(dag)

    except Exception as e:
        logging.error(f"[Engine] Planning failed: {e}")
        trace.finalize(f"Failed during Planning: {e}")
        return None, trace

    # ------------------------------------------------------------------
    # GATE 2 — Topology validation (unchanged)
    # ------------------------------------------------------------------
    if harness is not None:
        gate2_result = harness.validate_topology(dag)
        if not gate2_result["allowed"]:
            logging.warning(f"[Engine] Gate 2 VETO: {gate2_result['reason']}")
            trace.finalize(f"Vetoed at Gate 2: {gate2_result['reason']}")
            return None, trace
        logging.info("[Engine] Gate 2 passed.")

    # ------------------------------------------------------------------
    # EXECUTION — agents use agent_model (NIM Nano) or generation_model
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
            agent_model      = agent_model,       # ← NIM Nano or None
            max_concurrent   = max_concurrent,    # ← semaphore cap or None
        )

    except RuntimeError as e:
        logging.error(f"[Engine] Execution failed: {e}")
        trace.finalize(f"Failed during Execution: {e}")
        return None, trace
    except Exception as e:
        logging.error(f"[Engine] Unexpected execution error: {e}")
        trace.finalize(f"Failed during Execution: {e}")
        return None, trace

    # ------------------------------------------------------------------
    # FINALISATION (unchanged)
    # ------------------------------------------------------------------
    terminal_ids = find_terminal_nodes(dag)

    if len(terminal_ids) == 1:
        final_output = completed_outputs.get(terminal_ids[0])
    else:
        final_output = {
            tid: completed_outputs.get(tid) for tid in terminal_ids
        }
        logging.info(
            f"[Engine] Multiple terminal nodes: {terminal_ids}. "
            f"Returning dict of outputs."
        )

    trace.finalize("Success", final_output)
    logging.info("[Engine] Task complete.")
    return final_output, trace
