# =============================================================================
# run_dag.py  —  The Foreman (DAG Executor)
# commons/dag_engine/run_dag.py
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT THIS FILE DOES:
#   Replaces the original `for step in plan:` linear loop in engine.py with a
#   true DAG executor. The foreman reads the Execution DAG produced by the
#   Planner, identifies which nodes are READY (all dependencies complete),
#   runs them — concurrently where possible — and repeats until all nodes
#   are done or a cycle is detected.
#
# THREE GUARANTEES THIS FILE PROVIDES:
#   1. Correct ordering  — a node never runs before its dependencies finish.
#   2. Concurrency       — independent nodes in the same ready-set run in
#                          parallel via ThreadPoolExecutor.
#   3. Cycle detection   — if work remains but nothing is ready, the DAG
#                          contains a loop and execution halts with a clear
#                          error rather than hanging forever.
#
# PLANE 1 / PLANE 2 SEAMS (marked with comments, not yet implemented):
#   - Plane 1 (state of record): completed_outputs currently lives in memory.
#     In Stage 4 this line becomes: store.write(node_id, output)
#   - Plane 2 (A2A): domain dispatch currently routes locally.
#     In Stage 6 this becomes an HTTP call to a remote domain's engine.
#
# RELATIONSHIP TO OTHER FILES:
#   - Called by:  engine.py  (context_engine → run_dag)
#   - Calls:      registry.py (to resolve agent name → handler)
#                 adapters.py (passed in as `adapter`, used by agents)
# =============================================================================

import logging
import copy
from concurrent.futures import ThreadPoolExecutor, as_completed


# =============================================================================
# SECTION A — INPUT RESOLVER
# Replaces $$node_id$$ placeholders with actual outputs from completed nodes.
# This is the data that flows along the DAG's edges.
# =============================================================================

def resolve_inputs(node_input, completed_outputs):
    """
    Walk the node's input dict and replace every $$node_id$$ reference
    with that node's completed output.

    The foreman guarantees this is only called after all dependencies
    have finished, so every reference will resolve successfully.

    Args:
        node_input (dict): The raw input dict from the DAG node, possibly
                           containing $$ref$$ placeholders.
        completed_outputs (dict): Map of node_id -> output for all finished nodes.

    Returns:
        dict: A deep copy of node_input with all placeholders replaced.
    """
    resolved = copy.deepcopy(node_input)

    def walk(value):
        if isinstance(value, str) and value.startswith("$$") and value.endswith("$$"):
            source_id = value[2:-2]
            resolved_value = completed_outputs.get(source_id, value)
            if resolved_value == value:
                logging.warning(
                    f"[Resolver] Reference '$${ source_id }$$' not found in "
                    f"completed outputs. Available: {list(completed_outputs.keys())}"
                )
            return resolved_value
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    return walk(resolved)


# =============================================================================
# SECTION B — DOMAIN DISPATCH
# Routes a node to the correct agent based on its declared domain.
#
# LOCAL DISPATCH (Phase 1 / POC):
#   Both General and domain-specific agents are resolved through the local
#   registry. The domain field governs which namespace the adapter uses.
#
# [PLANE 2 — A2A SEAM]:
#   When a node's domain differs from the engine's own domain AND a remote
#   registry entry exists for that domain, this function becomes an HTTP call
#   to the remote domain's engine endpoint instead of a local agent call.
#   That change is isolated entirely to this function — the foreman (run_dag)
#   and the engine (context_engine) are both unaware of the difference.
# =============================================================================

def dispatch_node(node, resolved_input, registry, adapter, client, generation_model,
                  embedding_model, local_domain="General"):
    """
    Dispatch a single DAG node to its agent, routing by domain.

    Args:
        node (dict):             The DAG node descriptor.
                                 Must contain: id, agent, domain, input, depends_on
        resolved_input (dict):   The node's input with all $$refs$$ replaced.
        registry:                AgentRegistry instance (from registry.py).
        adapter:                 StorageAdapter instance (from adapters.py).
        client:                  LLM client (OpenAI-compatible).
        generation_model (str):  Model name for generation calls.
        embedding_model (str):   Model name for embedding calls.
        local_domain (str):      The domain this engine instance owns.
                                 Nodes with a different domain are A2A candidates.

    Returns:
        The agent's output (unwrapped from MCP envelope).
    """
    node_id     = node["id"]
    agent_name  = node["agent"]
    node_domain = node.get("domain", "General")

    # -----------------------------------------------------------------
    # [PLANE 2 — A2A SEAM]
    # If node_domain != local_domain, this is a cross-domain call.
    # Phase 1: we still route locally (same process, different namespace).
    # Phase 2: replace the block below with an HTTP POST to the remote
    #          domain's /run endpoint and return its response directly.
    # -----------------------------------------------------------------
    if node_domain != local_domain:
        logging.info(
            f"[Dispatcher] Cross-domain node '{node_id}': "
            f"{local_domain} → {node_domain} "
            f"(local dispatch — A2A seam, Phase 1)"
        )
    else:
        logging.info(
            f"[Dispatcher] Local node '{node_id}': domain={node_domain}"
        )

    # Resolve agent handler from registry (domain-aware in registry.py)
    handler = registry.get_handler(
        agent_name,
        domain=node_domain,
        client=client,
        adapter=adapter,
        generation_model=generation_model,
        embedding_model=embedding_model,
    )

    # Wrap input in MCP envelope and call the agent
    from helpers import create_mcp_message, count_tokens
    mcp_input  = create_mcp_message("Engine", resolved_input)
    mcp_output = handler(mcp_input)

    return mcp_output


# =============================================================================
# SECTION C — THE FOREMAN  (run_dag)
# The heart of the upgrade. Replaces `for step in plan:` with a
# readiness-poll loop that handles any DAG shape.
# =============================================================================

def run_dag(dag, registry, adapter, client, generation_model,
            embedding_model, trace, local_domain="General"):
    """
    Walk the Execution DAG by readiness, running independent nodes
    concurrently and collecting outputs.

    The algorithm:
        WHILE unfinished nodes remain:
            1. Find every node whose depends_on set is fully in `done`.
            2. If none found but work remains → CYCLE DETECTED → raise.
            3. Run all ready nodes concurrently (ThreadPoolExecutor).
            4. Collect outputs, mark nodes done, log to trace.
            5. Repeat.

    Args:
        dag (list[dict]):        The Execution DAG — list of node dicts.
                                 Each node: {id, agent, domain, input, depends_on}
        registry:                AgentRegistry instance.
        adapter:                 StorageAdapter instance.
        client:                  LLM client.
        generation_model (str):  Generation model name.
        embedding_model (str):   Embedding model name.
        trace:                   ExecutionTrace instance (from engine.py).
        local_domain (str):      Domain this engine instance owns.

    Returns:
        dict: completed_outputs — map of node_id -> agent output.

    Raises:
        RuntimeError: If a cycle is detected (nothing ready but work remains).
        RuntimeError: If any node raises an exception during execution.
    """
    from helpers import count_tokens

    # ------------------------------------------------------------------
    # [PLANE 1 — STATE OF RECORD SEAM]
    # In Phase 1: completed_outputs is an in-memory dict (scratchpad).
    # In Stage 4: each write becomes store.write_state(node_id, output)
    #             and each read becomes store.read_state(node_id).
    # The seam is this dict — swap it for adapter calls when ready.
    # ------------------------------------------------------------------
    completed_outputs = {}
    done              = set()
    all_ids           = {node["id"] for node in dag}

    logging.info(
        f"[Foreman] Starting DAG execution. "
        f"Total nodes: {len(dag)}. IDs: {sorted(all_ids)}"
    )

    # Validate DAG structure before executing
    _validate_dag_structure(dag)

    # ---------------------------------------------------------------
    # MAIN EXECUTION LOOP
    # ---------------------------------------------------------------
    while done != all_ids:

        # --- (1) Find every node whose prerequisites are all complete ---
        ready = [
            node for node in dag
            if node["id"] not in done
            and all(dep in done for dep in node.get("depends_on", []))
        ]

        # --- (2) Cycle detection — the Acyclic guarantee ---
        # If work remains but NOTHING is ready, every unfinished node
        # is waiting on another unfinished node — a loop.
        if not ready:
            remaining = [n["id"] for n in dag if n["id"] not in done]
            msg = (
                f"[Foreman] DEADLOCK — DAG contains a cycle. "
                f"No node is runnable. Stuck nodes: {remaining}"
            )
            logging.error(msg)
            trace.finalize(f"Failed: cycle detected. Stuck: {remaining}")
            raise RuntimeError(msg)

        logging.info(
            f"[Foreman] Ready set ({len(ready)} node(s)): "
            f"{[n['id'] for n in ready]}"
        )

        # --- (3) Run the ready set concurrently ---
        # All nodes in `ready` are independent of each other right now.
        # ThreadPoolExecutor runs them in parallel.
        # For a single-node ready set this is equivalent to a direct call.
        if len(ready) == 1:
            # Shortcut: no threading overhead for a single node
            _execute_single_node(
                ready[0], completed_outputs, done, trace,
                registry, adapter, client,
                generation_model, embedding_model, local_domain
            )
        else:
            # Fan-out: run all ready nodes in parallel
            _execute_parallel_nodes(
                ready, completed_outputs, done, trace,
                registry, adapter, client,
                generation_model, embedding_model, local_domain
            )

    logging.info(
        f"[Foreman] DAG execution complete. "
        f"All {len(all_ids)} node(s) finished."
    )
    return completed_outputs


# =============================================================================
# SECTION D — EXECUTION HELPERS  (single and parallel)
# =============================================================================

def _execute_single_node(node, completed_outputs, done, trace,
                         registry, adapter, client,
                         generation_model, embedding_model, local_domain):
    """Run one node synchronously and record its output."""
    from helpers import count_tokens, create_mcp_message

    node_id = node["id"]
    logging.info(f"[Foreman] Executing node '{node_id}' (single).")

    resolved_input = resolve_inputs(node["input"], completed_outputs)
    t_in           = count_tokens(str(resolved_input))

    try:
        mcp_output = dispatch_node(
            node, resolved_input, registry, adapter,
            client, generation_model, embedding_model, local_domain
        )
    except Exception as e:
        msg = f"Node '{node_id}' ({node['agent']}) failed: {e}"
        logging.error(f"[Foreman] {msg}")
        raise RuntimeError(msg) from e

    output_data = mcp_output["content"]
    t_out       = count_tokens(str(output_data))

    # [PLANE 1 SEAM] — write to in-memory scratchpad
    completed_outputs[node_id] = output_data
    done.add(node_id)

    trace.log_step(
        node_id=node_id,
        agent=node["agent"],
        domain=node.get("domain", "General"),
        resolved_input=resolved_input,
        output=output_data,
        tokens_in=t_in,
        tokens_out=t_out,
    )
    logging.info(f"[Foreman] Node '{node_id}' complete. [In:{t_in} Out:{t_out}]")


def _execute_parallel_nodes(nodes, completed_outputs, done, trace,
                             registry, adapter, client,
                             generation_model, embedding_model, local_domain):
    """
    Run multiple independent nodes concurrently using ThreadPoolExecutor.
    All nodes in this batch are already confirmed independent of each other.
    Results are collected and written to completed_outputs after all finish.
    """
    from helpers import count_tokens

    logging.info(
        f"[Foreman] Parallel execution: "
        f"{[n['id'] for n in nodes]}"
    )

    futures = {}
    results = {}

    with ThreadPoolExecutor(max_workers=len(nodes)) as executor:
        for node in nodes:
            node_id        = node["id"]
            resolved_input = resolve_inputs(node["input"], completed_outputs)

            future = executor.submit(
                dispatch_node,
                node, resolved_input, registry, adapter,
                client, generation_model, embedding_model, local_domain
            )
            # Store both the future and the context needed after completion
            futures[future] = (node, resolved_input)

        for future in as_completed(futures):
            node, resolved_input = futures[future]
            node_id = node["id"]

            try:
                mcp_output = future.result()
            except Exception as e:
                msg = f"Node '{node_id}' ({node['agent']}) failed in parallel: {e}"
                logging.error(f"[Foreman] {msg}")
                raise RuntimeError(msg) from e

            output_data = mcp_output["content"]
            t_in        = count_tokens(str(resolved_input))
            t_out       = count_tokens(str(output_data))

            results[node_id] = (node, resolved_input, output_data, t_in, t_out)
            logging.info(
                f"[Foreman] Parallel node '{node_id}' complete. "
                f"[In:{t_in} Out:{t_out}]"
            )

    # Write all parallel results to completed_outputs and trace
    # (done after the executor context to avoid race conditions on the dict)
    for node_id, (node, resolved_input, output_data, t_in, t_out) in results.items():
        # [PLANE 1 SEAM] — write to in-memory scratchpad
        completed_outputs[node_id] = output_data
        done.add(node_id)

        trace.log_step(
            node_id=node_id,
            agent=node["agent"],
            domain=node.get("domain", "General"),
            resolved_input=resolved_input,
            output=output_data,
            tokens_in=t_in,
            tokens_out=t_out,
        )


# =============================================================================
# SECTION E — DAG VALIDATOR
# Runs before execution to catch structural problems early.
# =============================================================================

def _validate_dag_structure(dag):
    """
    Pre-flight structural validation of the DAG.
    Catches problems before any LLM calls are made.

    Checks:
        - All node ids are unique.
        - All depends_on references point to real node ids.
        - All $$ref$$ strings in inputs have a matching depends_on entry.

    Does NOT check for cycles — the foreman detects those at runtime.
    """
    all_ids = {}
    for node in dag:
        node_id = node.get("id")
        if not node_id:
            raise ValueError(f"DAG node missing 'id' field: {node}")
        if node_id in all_ids:
            raise ValueError(
                f"DAG contains duplicate node id: '{node_id}'"
            )
        all_ids[node_id] = node

    for node in dag:
        node_id    = node["id"]
        depends_on = node.get("depends_on", [])

        # Check all dependency ids exist
        for dep in depends_on:
            if dep not in all_ids:
                raise ValueError(
                    f"Node '{node_id}' depends_on '{dep}' "
                    f"which does not exist in the DAG."
                )

        # Check $$refs$$ in inputs have matching depends_on entries
        _check_refs(node.get("input", {}), depends_on, node_id)

    logging.info(
        f"[Validator] DAG structure valid. "
        f"{len(dag)} nodes, all dependencies resolved."
    )


def _check_refs(value, depends_on, node_id):
    """Recursively verify $$ref$$ strings match depends_on declarations."""
    if isinstance(value, str):
        if value.startswith("$$") and value.endswith("$$"):
            ref = value[2:-2]
            if ref not in depends_on:
                logging.warning(
                    f"[Validator] Node '{node_id}' references '$${ ref }$$' "
                    f"in input but '{ref}' is not in depends_on. "
                    f"This may cause a resolution failure at runtime."
                )
    elif isinstance(value, dict):
        for v in value.values():
            _check_refs(v, depends_on, node_id)
    elif isinstance(value, list):
        for item in value:
            _check_refs(item, depends_on, node_id)


# =============================================================================
# SECTION F — UTILITY: find_terminal_nodes
# Identifies nodes that no other node depends on.
# Used by engine.py to determine the final output node(s).
# =============================================================================

def find_terminal_nodes(dag):
    """
    Return the ids of nodes that no other node depends on.
    These are the 'leaf' nodes of the DAG — the final deliverables.

    In a linear chain A→B→C, only C is terminal.
    In a diamond A→(B,C)→D, only D is terminal.
    In a forked DAG A→(B,C) with no join, both B and C are terminal.

    Returns:
        list[str]: Node ids with no outgoing dependents.
    """
    all_ids       = {node["id"] for node in dag}
    depended_upon = set()

    for node in dag:
        for dep in node.get("depends_on", []):
            depended_upon.add(dep)

    terminal = sorted(all_ids - depended_upon)
    logging.info(f"[Foreman] Terminal nodes: {terminal}")
    return terminal
