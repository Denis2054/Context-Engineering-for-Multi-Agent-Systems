# =============================================================================
# engine_nim.py  —  Planner, Trace, and the Orchestrator
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# The top layer. context_engine() is the only function a caller needs, and it
# runs a fixed five-stage pipeline:
#
#   Gate 1  ->  Plan  ->  Gate 2  ->  Execute  ->  Finalise
#
# Nothing in that sequence is conditional. The engine cannot skip the plan, and
# it cannot execute a plan that Gate 2 refused. That rigidity is the product:
# an execution path with no branches is an execution path you can audit.
#
# WHAT THE PLANNER PRODUCES
# -------------------------
# One call, one artefact: a JSON list of nodes. Not a decision about what to do
# next — the whole shape of the work, as data, before any of it happens.
#
# Everything distinctive about this architecture follows from that artefact
# existing. Gate 2 can validate cross-domain edges because the edges are in
# front of it. The Foreman can run four nodes at once because it can see that
# four nodes have no dependencies. plan_only() can show you the DAG for the
# price of one call, without executing anything. None of that is available to
# an engine that decides its next step one step at a time.
#
# The trade is stated plainly: the plan is fixed before execution starts. If a
# Researcher discovers something that should change the shape of the work, this
# engine will not change shape. Re-planning on new information is a genuine
# capability of ReAct-style loops that this design gives up in exchange for
# being inspectable.
# =============================================================================

import json
import logging
import time

from helpers  import call_llm_robust, create_mcp_message, count_tokens, extract_json
from registry import AGENT_TOOLKIT
from run_dag  import run_dag, find_terminal_nodes, resolve_inputs
from adapters import StorageAdapterBase


# =============================================================================
# SECTION A — EXECUTION TRACE
#
# The audit record: what was asked, what was planned, what each gate decided,
# what every node received and returned, and what it cost.
#
# Built during the run rather than reconstructed from logs afterwards, because
# a trace assembled from log lines is a story about the run and this is meant
# to be the run itself. The dashboard renders it; nothing in the dashboard is
# computed from anywhere else.
# =============================================================================

class ExecutionTrace:
    """
    A complete, structured record of one context_engine() call.

    Records both gate verdicts as well as every node, so a vetoed run produces
    a trace that explains itself rather than an empty one.
    """

    def __init__(self, goal: str):
        self.goal         = goal
        self.dag          = None
        self.steps        = []
        self.status       = "Initialized"
        self.final_output = None
        self.gate1_result = None
        self.gate2_result = None
        self.duration     = 0.0
        self.start_time   = time.time()
        logging.info(f"[Trace] opened for goal: '{self.goal[:80]}...'")

    def log_gate(self, gate_number: int, result: dict):
        """Record a gate verdict so the dashboard can render it."""
        if gate_number == 1:
            self.gate1_result = result
        else:
            self.gate2_result = result
        verdict = "PASS" if result.get("allowed") else "VETO"
        logging.info(f"[Trace] Gate {gate_number}: {verdict}")

    def log_dag(self, dag: list):
        """Record the planner's output — the plan as an artefact."""
        self.dag = dag
        logging.info(f"[Trace] DAG logged: {len(dag)} node(s) {[n['id'] for n in dag]}")
        logging.debug(f"[Trace] DAG detail: {json.dumps(dag, indent=2, default=str)}")

    def log_step(self, node_id: str, agent: str, domain: str,
                 resolved_input, output, tokens_in: int = 0,
                 tokens_out: int = 0, duration_s: float = 0.0):
        """
        Record one completed node.

        `tokens_saved` is attributed only to the Summarizer, and only when it
        shrank its input. That is the one node whose entire purpose is
        reduction, so it is the one place where in-minus-out is a meaningful
        number rather than an artefact of a task that happens to produce short
        output.
        """
        self.steps.append({
            "node_id"       : node_id,
            "agent"         : agent,
            "domain"        : domain,
            "resolved_input": resolved_input,
            "output"        : output,
            "tokens_in"     : tokens_in,
            "tokens_out"    : tokens_out,
            "duration_s"    : round(duration_s, 2),
            "tokens_saved"  : max(0, tokens_in - tokens_out) if agent == "Summarizer" else 0,
        })
        logging.info(
            f"[Trace] '{node_id}' ({agent}/{domain}) "
            f"[in {tokens_in} / out {tokens_out} / {duration_s:.2f}s]"
        )

    def finalize(self, status: str, final_output=None):
        """Close the trace and stop the clock."""
        self.status       = status
        self.final_output = final_output
        self.duration     = time.time() - self.start_time
        logging.info(f"[Trace] closed — {status} in {self.duration:.2f}s")

    def summary(self) -> dict:
        """
        Flatten the trace into a dict for rendering, logging, or persistence.

        `wall_clock_saved_s` is worth reading carefully: it is the difference
        between the sum of every node's duration and the run's actual elapsed
        time. On a purely sequential DAG it is roughly zero. On a DAG with
        concurrent waves it is the time concurrency bought — the clearest
        single number for what the Foreman's scheduler is doing.
        """
        total_in    = sum(s["tokens_in"]  for s in self.steps)
        total_out   = sum(s["tokens_out"] for s in self.steps)
        saved       = sum(s["tokens_saved"] for s in self.steps)
        node_time   = sum(s.get("duration_s", 0) for s in self.steps)
        duration    = round(self.duration, 2)

        return {
            "goal"              : self.goal,
            "status"            : self.status,
            "duration_s"        : duration,
            "node_time_s"       : round(node_time, 2),
            "wall_clock_saved_s": round(max(0.0, node_time - duration), 2),
            "dag_nodes"         : len(self.dag) if self.dag else 0,
            "steps_complete"    : len(self.steps),
            "tokens_in"         : total_in,
            "tokens_out"        : total_out,
            "tokens_saved"      : saved,
            "dag"               : self.dag,
            "steps"             : self.steps,
            "gate1_result"      : self.gate1_result,
            "gate2_result"      : self.gate2_result,
            "final_output"      : self.final_output,
        }


# =============================================================================
# SECTION B — THE PLANNER
#
# One call to the largest model available, producing the DAG.
#
# The system prompt below is doing more work than it looks. Three of its rules
# exist because of specific, reproducible failure modes:
#
#   Rule 4 (exact input keys) — the Foreman's resolver looks up literal
#   dictionary keys. "query" instead of "topic_query" produces a node that
#   fails at execution, after the planning call is already paid for.
#
#   Rule 7 (do not chain unnecessarily) — left to itself a planner emits a
#   linear chain, because most plans in most training data are linear. The
#   concurrency this engine is built for has to be explicitly requested, and
#   even then it needs the reason stated: independent nodes run in parallel.
#
#   Rule 3 (domain must match) — Gate 2 validates against declared domains. A
#   plan with missing or invented domains is refused before execution, so a
#   sloppy domain field costs a whole planning call.
# =============================================================================

def planner(goal: str, capabilities: str, client, generation_model: str) -> list:
    """
    Turn a natural-language goal into an Execution DAG.

    Args:
        goal (str):             the user's goal.
        capabilities (str):     rendered by registry.get_capabilities_description().
        client:                 credential holder.
        generation_model (str): the planner model — Super on the NIM path.

    Returns:
        list[dict]: node dicts, each with id / agent / domain / input / depends_on.

    Raises:
        json.JSONDecodeError: the response contained no parseable JSON.
        ValueError:           parseable JSON in an unusable shape.
    """
    logging.info(f"[Planner] activated on {generation_model}.")

    system_prompt = f"""
You are the strategic core of the Universal Context Engine.
Analyze the user's high-level GOAL and produce an EXECUTION DAG.

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
          "<input_key>": "<literal value, or $$other_node_id$$ reference>"
      }},
      "depends_on" : ["id_of_node_whose_output_this_node_needs"]
    }}
  ]
}}

CRITICAL RULES:
1. `id`         — unique, snake_case, descriptive of what the node does.
2. `agent`      — MUST be one of the exact agent names in AVAILABLE CAPABILITIES.
3. `domain`     — MUST match the domain declared for that agent. Cross-domain
                  edges are validated against a governance topology before
                  execution; a wrong domain will cause the whole plan to be
                  rejected.
4. `input`      — MUST use the exact input key names listed for that agent.
                  No synonyms, no extra keys.
5. `depends_on` — list every node_id whose output this node references
                  via $$ref$$. Use [] when the node has no dependencies.
6. References   — write $$node_id$$ to consume another node's output.
7. Concurrency  — nodes with no dependencies execute IN PARALLEL. Add a
                  dependency ONLY when the input genuinely requires another
                  node's output. Do not create a linear chain out of habit;
                  unnecessary dependencies make the run slower for no benefit.
8. The Librarian never has dependencies — it always starts immediately.
9. Insert a Summarizer between a Researcher and the Writer whenever the
   research output is likely to be long.

Return ONLY the JSON object. No commentary, no markdown fences.
"""

    try:
        raw = call_llm_robust(
            system_prompt, goal,
            client           = client,
            generation_model = generation_model,
            json_mode        = True,
            temperature      = 0.1,   # planning wants determinism, not variety
        )

        # extract_json tolerates reasoning blocks, code fences, and stray
        # commentary. Reasoning models produce all three, and none of them
        # indicate a bad plan — only a wrapped one.
        dag_data = extract_json(raw)

        if isinstance(dag_data, list):
            logging.warning("[Planner] returned a bare list — accepting it.")
            nodes = dag_data
        elif isinstance(dag_data, dict) and "nodes" in dag_data:
            nodes = dag_data["nodes"]
        elif isinstance(dag_data, dict) and "plan" in dag_data:
            logging.warning("[Planner] returned the legacy 'plan' shape — converting.")
            nodes = _convert_legacy_plan(dag_data["plan"])
        else:
            raise ValueError(
                f"Planner output has no 'nodes' key. "
                f"Keys present: {list(dag_data.keys()) if isinstance(dag_data, dict) else type(dag_data)}"
            )

        if not nodes:
            raise ValueError("Planner returned an empty node list.")

        logging.info(
            f"[Planner] {len(nodes)} node(s): {[n.get('id', '?') for n in nodes]}"
        )
        return nodes

    except json.JSONDecodeError as e:
        logging.error(f"[Planner] could not parse JSON: {e}")
        raise
    except Exception as e:
        logging.error(f"[Planner] failed: {e}")
        raise


def _convert_legacy_plan(plan: list) -> list:
    """
    Convert a numbered step list into DAG nodes.

    A compatibility shim for the sequential plan format of earlier chapters.
    Every step becomes dependent on the one before it, which is faithful to
    the original semantics and produces a DAG with no concurrency at all —
    correct, and a good illustration of what the DAG format adds.
    """
    nodes = []
    for i, step in enumerate(plan):
        step_num = step.get("step", i + 1)
        nodes.append({
            "id"        : f"step_{step_num}",
            "agent"     : step.get("agent", "Unknown"),
            "domain"    : step.get("domain", "General"),
            "input"     : step.get("input", {}),
            "depends_on": [f"step_{step_num - 1}"] if step_num > 1 else [],
        })
    return nodes


def resolve_dependencies(input_params: dict, state: dict) -> dict:
    """Alias for run_dag.resolve_inputs(), kept for API compatibility."""
    return resolve_inputs(input_params, state)


# =============================================================================
# SECTION C — PLAN WITHOUT EXECUTING
# =============================================================================

def plan_only(goal: str, client, generation_model: str,
              registry=None, harness=None) -> dict:
    """
    Run Gate 1, plan, and run Gate 2 — then stop.

    Costs exactly one LLM call and executes no agents. Both gates return their
    real verdicts, so this is a complete governance test: you can confirm that
    a policy blocks what it should block without paying for a run, and you can
    read the DAG the planner would have executed.

    This is the cheapest useful thing in the notebook, and the most neglected.
    Prompt changes, capability edits, and topology changes can all be regression
    tested here for the price of one call each.

    Args:
        goal (str):             the goal to plan.
        client:                 credential holder.
        generation_model (str): planner model.
        registry:               AgentRegistry; defaults to AGENT_TOOLKIT.
        harness:                Harness; when None both gates are skipped.

    Returns:
        dict: {goal, gate1, dag, gate2, would_execute, error}
              `would_execute` is True only when both gates passed and a DAG
              was produced.
    """
    registry = registry or AGENT_TOOLKIT
    out = {"goal": goal, "gate1": None, "dag": None,
           "gate2": None, "would_execute": False, "error": None}

    if harness is not None:
        out["gate1"] = harness.gate(goal)
        if not out["gate1"]["allowed"]:
            return out

    try:
        out["dag"] = planner(
            goal,
            registry.get_capabilities_description(),
            client           = client,
            generation_model = generation_model,
        )
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out

    if harness is not None:
        out["gate2"] = harness.validate_topology(out["dag"])
        out["would_execute"] = out["gate2"]["allowed"]
    else:
        out["would_execute"] = True

    return out


# =============================================================================
# SECTION D — THE ORCHESTRATOR
# =============================================================================

def context_engine(goal: str, client, adapter: StorageAdapterBase,
                   generation_model: str, embedding_model: str,
                   registry=None, harness=None,
                   agent_model: str = None,
                   max_concurrent: int = None,
                   precomputed_gate1: dict = None) -> tuple:
    """
    Run one goal through the full pipeline.

    Args:
        goal (str):               the user's goal.
        client:                   LLM and embedding credential holder. On the
                                  NIM path this is nim_client — note that the
                                  adapter carries its own embedding client, so
                                  embeddings do not necessarily use this one.
        adapter:                  StorageAdapter.
        generation_model (str):   planner model.
        embedding_model (str):    must match the index.
        registry:                 AgentRegistry; defaults to AGENT_TOOLKIT.
        harness:                  Harness. Omitting it skips BOTH gates and
                                  logs a warning — supported for experiments,
                                  never for anything you would ship.
        agent_model (str|None):   agent model. None means "same as planner".
        max_concurrent (int|None):semaphore cap. None reads NIM_MAX_CONCURRENT.
        precomputed_gate1 (dict): a Gate 1 verdict already obtained by the
                                  caller. Supplying it avoids running the
                                  moderation call twice when the notebook has
                                  already gated the goal in order to display
                                  the result.

    Returns:
        tuple: (final_output, trace)

               final_output is None on any veto or failure. The trace is always
               returned and always populated — a vetoed run still explains
               itself, which is the whole point of recording gate verdicts.
    """
    logging.info(
        f"[Engine] start | goal='{goal[:80]}...' "
        f"planner={generation_model} agents={agent_model or generation_model} "
        f"max_concurrent={max_concurrent or 'auto'}"
    )

    trace    = ExecutionTrace(goal)
    registry = registry or AGENT_TOOLKIT

    # ---- STAGE 1: Gate 1 --------------------------------------------------
    if harness is not None:
        gate1 = precomputed_gate1 if precomputed_gate1 is not None else harness.gate(goal)
        trace.log_gate(1, gate1)
        if not gate1["allowed"]:
            logging.warning(f"[Engine] Gate 1 VETO: {gate1['reason']}")
            trace.finalize(f"Vetoed at Gate 1: {gate1['reason']}")
            return None, trace
    else:
        logging.warning(
            "[Engine] no harness supplied — both gates skipped. "
            "Pass a Harness instance for any governed use."
        )

    # ---- STAGE 2: Plan ----------------------------------------------------
    try:
        dag = planner(
            goal,
            registry.get_capabilities_description(),
            client           = client,
            generation_model = generation_model,
        )
        trace.log_dag(dag)
    except Exception as e:
        logging.error(f"[Engine] planning failed: {e}")
        trace.finalize(f"Failed during planning: {e}")
        return None, trace

    # ---- STAGE 3: Gate 2 --------------------------------------------------
    # The plan exists as data and has cost one call. Nothing has executed.
    # This is the last moment a veto is nearly free.
    if harness is not None:
        gate2 = harness.validate_topology(dag)
        trace.log_gate(2, gate2)
        if not gate2["allowed"]:
            logging.warning(f"[Engine] Gate 2 VETO: {gate2['reason']}")
            trace.finalize(f"Vetoed at Gate 2: {gate2['reason']}")
            return None, trace

    # ---- STAGE 4: Execute -------------------------------------------------
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
            agent_model      = agent_model,
            max_concurrent   = max_concurrent,
        )
    except Exception as e:
        logging.error(f"[Engine] execution failed: {e}")
        trace.finalize(f"Failed during execution: {e}")
        return None, trace

    # ---- STAGE 5: Finalise ------------------------------------------------
    # The answer is whatever the terminal nodes produced. One terminal is the
    # normal case; several means the plan fanned out, and returning all of them
    # keyed by node id is more honest than picking one.
    terminal_ids = find_terminal_nodes(dag)

    if len(terminal_ids) == 1:
        final_output = completed_outputs.get(terminal_ids[0])
    else:
        final_output = {tid: completed_outputs.get(tid) for tid in terminal_ids}
        logging.info(
            f"[Engine] {len(terminal_ids)} terminal nodes {terminal_ids} — "
            f"returning a dict of outputs."
        )

    trace.finalize("Success", final_output)
    logging.info("[Engine] complete.")
    return final_output, trace
