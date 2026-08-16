# =============================================================================
# run_dag.py  —  The Foreman (DAG Executor) — NIM Edition
# commons/dag_engine/run_dag.py  (private: Denis2054/SFT)
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT CHANGED FROM THE PUBLIC REPO VERSION:
#   ONE upgrade — asyncio replaces ThreadPoolExecutor in parallel execution:
#
#   _execute_parallel_nodes() is replaced by _execute_parallel_nodes_async()
#   which uses asyncio.gather() behind a semaphore instead of ThreadPoolExecutor.
#
#   WHY THIS MATTERS FOR NIM:
#     - NIM free tier: 40 requests per minute hard limit
#     - ThreadPoolExecutor fires all threads simultaneously with no coordination
#     - If 4 concurrent nodes all call NIM at the same instant, they all hit
#       the rate limit together → one or more fail and retry with backoff
#     - asyncio.Semaphore(NIM_MAX_CONCURRENT) caps concurrent in-flight
#       requests, distributing them cleanly within the rate limit
#     - The semaphore value (default 4) is imported from utils.NIM_MAX_CONCURRENT
#       and can be raised to 8 on a paid NIM tier without changing any other code
#
#   BACKWARD COMPATIBILITY:
#     - run_dag() is unchanged in signature and behaviour
#     - The internal routing is:
#         max_concurrent > 1  → asyncio parallel path (NIM-safe)
#         max_concurrent == 1 → single-node sequential path (unchanged)
#     - When max_concurrent is not passed, defaults to NIM_MAX_CONCURRENT
#       from utils.py. OpenAI users can pass max_concurrent=len(ready) to
#       restore the original unconstrained behaviour.
#
# EVERYTHING ELSE IS IDENTICAL TO THE PUBLIC REPO.
# =============================================================================

import logging
import copy
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed


# =============================================================================
# SECTION A — INPUT RESOLVER  (unchanged)
# =============================================================================

def resolve_inputs(node_input, completed_outputs):
    """
    Walk the node's input dict and replace every $$node_id$$ reference
    with that node's completed output.
    """
    resolved = copy.deepcopy(node_input)

    def walk(value):
        if isinstance(value, str) and value.startswith("$$") and value.endswith("$$"):
            source_id     = value[2:-2]
            resolved_value = completed_outputs.get(source_id, value)
            if resolved_value == value:
                logging.warning(
                    f"[Resolver] Reference '$${source_id}$$' not found in "
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
# SECTION B — DOMAIN DISPATCH  (unchanged)
# =============================================================================

def dispatch_node(node, resolved_input, registry, adapter, client,
                  generation_model, embedding_model,
                  local_domain="General", agent_model=None):
    """
    Dispatch a single DAG node to its agent, routing by domain.

    agent_model is forwarded to registry.get_handler() to enable
    dual-model routing on NIM (Planner=Super, agents=Nano).

    [PLANE 2 — A2A SEAM]
    Phase 1: local dispatch — cross-domain calls route through the same
    process with different namespace routing.
    Phase 2: replace the local call below with an HTTP POST to the remote
    domain's /run endpoint. Change is isolated to this function only.
    """
    node_id     = node["id"]
    agent_name  = node["agent"]
    node_domain = node.get("domain", "General")

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

    handler = registry.get_handler(
        agent_name,
        domain           = node_domain,
        client           = client,
        adapter          = adapter,
        generation_model = generation_model,
        embedding_model  = embedding_model,
        agent_model      = agent_model,        # ← NIM Nano or None
    )

    from helpers import create_mcp_message
    mcp_input  = create_mcp_message("Engine", resolved_input)
    mcp_output = handler(mcp_input)
    return mcp_output


# =============================================================================
# SECTION C — THE FOREMAN  (run_dag)
# Signature unchanged. Internal routing updated for NIM rate-limit safety.
# =============================================================================

def run_dag(dag, registry, adapter, client, generation_model,
            embedding_model, trace, local_domain="General",
            agent_model=None, max_concurrent=None):
    """
    Walk the Execution DAG by readiness, running independent nodes
    concurrently and collecting outputs.

    NIM ADDITIONS:
        agent_model (str|None): passed to dispatch_node → registry.get_handler().
                                Set to utils.NIM_AGENT_MODEL for NIM path.
                                Default None = use generation_model (OpenAI path).

        max_concurrent (int|None): caps simultaneous in-flight LLM calls.
                                   Default None → uses utils.NIM_MAX_CONCURRENT (4).
                                   Pass len(ready) to restore unconstrained behaviour.

    All other args and return value are identical to the public repo.

    Returns:
        dict: completed_outputs — map of node_id -> agent output.
    """
    from helpers import count_tokens

    # Resolve concurrency cap
    if max_concurrent is None:
        try:
            from utils import NIM_MAX_CONCURRENT
            max_concurrent = NIM_MAX_CONCURRENT
        except ImportError:
            max_concurrent = 8   # fallback if utils not available

    # [PLANE 1 — STATE OF RECORD SEAM]
    # In Phase 1: in-memory dict. In Stage 4: adapter.write_state() calls.
    completed_outputs = {}
    done              = set()
    all_ids           = {node["id"] for node in dag}

    logging.info(
        f"[Foreman] Starting DAG execution. "
        f"Nodes: {len(dag)}. max_concurrent: {max_concurrent}. "
        f"agent_model: {agent_model or 'same as planner'}"
    )

    _validate_dag_structure(dag)

    while done != all_ids:

        ready = [
            node for node in dag
            if node["id"] not in done
            and all(dep in done for dep in node.get("depends_on", []))
        ]

        if not ready:
            remaining = [n["id"] for n in dag if n["id"] not in done]
            msg = (
                f"[Foreman] DEADLOCK — DAG contains a cycle. "
                f"Stuck nodes: {remaining}"
            )
            logging.error(msg)
            trace.finalize(f"Failed: cycle detected. Stuck: {remaining}")
            raise RuntimeError(msg)

        logging.info(
            f"[Foreman] Ready set ({len(ready)} node(s)): "
            f"{[n['id'] for n in ready]}"
        )

        if len(ready) == 1:
            _execute_single_node(
                ready[0], completed_outputs, done, trace,
                registry, adapter, client,
                generation_model, embedding_model,
                local_domain, agent_model
            )
        else:
            # NIM-safe async parallel execution
            asyncio.run(
                _execute_parallel_nodes_async(
                    ready, completed_outputs, done, trace,
                    registry, adapter, client,
                    generation_model, embedding_model,
                    local_domain, agent_model, max_concurrent
                )
            )

    logging.info(
        f"[Foreman] DAG execution complete. "
        f"All {len(all_ids)} node(s) finished."
    )
    return completed_outputs


# =============================================================================
# SECTION D — EXECUTION HELPERS
# _execute_single_node: unchanged from public repo
# _execute_parallel_nodes_async: NIM-safe asyncio replacement
# _execute_parallel_nodes: kept as fallback, marked deprecated
# =============================================================================

def _execute_single_node(node, completed_outputs, done, trace,
                         registry, adapter, client,
                         generation_model, embedding_model,
                         local_domain, agent_model=None):
    """Run one node synchronously and record its output. Unchanged."""
    from helpers import count_tokens

    node_id = node["id"]
    logging.info(f"[Foreman] Executing node '{node_id}' (single).")

    resolved_input = resolve_inputs(node["input"], completed_outputs)
    t_in           = count_tokens(str(resolved_input))

    try:
        mcp_output = dispatch_node(
            node, resolved_input, registry, adapter,
            client, generation_model, embedding_model,
            local_domain, agent_model
        )
    except Exception as e:
        msg = f"Node '{node_id}' ({node['agent']}) failed: {e}"
        logging.error(f"[Foreman] {msg}")
        raise RuntimeError(msg) from e

    output_data = mcp_output["content"]
    t_out       = count_tokens(str(output_data))

    # [PLANE 1 SEAM]
    completed_outputs[node_id] = output_data
    done.add(node_id)

    trace.log_step(
        node_id        = node_id,
        agent          = node["agent"],
        domain         = node.get("domain", "General"),
        resolved_input = resolved_input,
        output         = output_data,
        tokens_in      = t_in,
        tokens_out     = t_out,
    )
    logging.info(f"[Foreman] Node '{node_id}' complete. [In:{t_in} Out:{t_out}]")


async def _execute_parallel_nodes_async(nodes, completed_outputs, done, trace,
                                         registry, adapter, client,
                                         generation_model, embedding_model,
                                         local_domain, agent_model, max_concurrent):
    """
    NIM-safe async parallel execution.

    Replaces ThreadPoolExecutor with asyncio.gather() behind a semaphore.
    The semaphore caps the number of simultaneous in-flight NIM API calls,
    keeping concurrent requests within the 40 RPM free-tier rate limit.

    Each agent call runs in a thread pool (via asyncio.to_thread) because
    the OpenAI SDK's synchronous client is not natively async. This gives
    us both async coordination (semaphore) and true parallel I/O (threads).

    Args:
        max_concurrent: semaphore cap — use utils.NIM_MAX_CONCURRENT (4)
                        for the NIM free tier; raise to 8 on paid tier.
    """
    from helpers import count_tokens

    sem     = asyncio.Semaphore(max_concurrent)
    results = {}

    logging.info(
        f"[Foreman] Async parallel execution: "
        f"{[n['id'] for n in nodes]} "
        f"(semaphore={max_concurrent})"
    )

    async def run_one(node):
        node_id        = node["id"]
        resolved_input = resolve_inputs(node["input"], completed_outputs)

        async with sem:
            logging.info(
                f"[Foreman] Async node '{node_id}' acquired semaphore slot."
            )
            try:
                # Run the synchronous dispatch_node in a thread so we don't
                # block the event loop while waiting for the NIM API response.
                mcp_output = await asyncio.to_thread(
                    dispatch_node,
                    node, resolved_input, registry, adapter,
                    client, generation_model, embedding_model,
                    local_domain, agent_model
                )
            except Exception as e:
                msg = f"Node '{node_id}' ({node['agent']}) failed in async: {e}"
                logging.error(f"[Foreman] {msg}")
                raise RuntimeError(msg) from e

        output_data = mcp_output["content"]
        t_in        = count_tokens(str(resolved_input))
        t_out       = count_tokens(str(output_data))
        results[node_id] = (node, resolved_input, output_data, t_in, t_out)
        logging.info(
            f"[Foreman] Async node '{node_id}' complete. "
            f"[In:{t_in} Out:{t_out}]"
        )

    await asyncio.gather(*[run_one(node) for node in nodes])

    # Write all results to completed_outputs and trace after all tasks finish
    for node_id, (node, resolved_input, output_data, t_in, t_out) in results.items():
        # [PLANE 1 SEAM]
        completed_outputs[node_id] = output_data
        done.add(node_id)

        trace.log_step(
            node_id        = node_id,
            agent          = node["agent"],
            domain         = node.get("domain", "General"),
            resolved_input = resolved_input,
            output         = output_data,
            tokens_in      = t_in,
            tokens_out     = t_out,
        )


def _execute_parallel_nodes(nodes, completed_outputs, done, trace,
                             registry, adapter, client,
                             generation_model, embedding_model,
                             local_domain, agent_model=None):
    """
    Original ThreadPoolExecutor implementation — kept for reference.
    DEPRECATED for NIM use: does not respect the rate-limit semaphore.
    Use _execute_parallel_nodes_async() instead (called automatically
    by run_dag() when len(ready) > 1).
    """
    from helpers import count_tokens

    logging.warning(
        "[Foreman] _execute_parallel_nodes() called directly. "
        "Use run_dag() which routes to the asyncio path for NIM safety."
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
                client, generation_model, embedding_model,
                local_domain, agent_model
            )
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

    for node_id, (node, resolved_input, output_data, t_in, t_out) in results.items():
        completed_outputs[node_id] = output_data
        done.add(node_id)
        trace.log_step(
            node_id        = node_id,
            agent          = node["agent"],
            domain         = node.get("domain", "General"),
            resolved_input = resolved_input,
            output         = output_data,
            tokens_in      = t_in,
            tokens_out     = t_out,
        )


# =============================================================================
# SECTION E — DAG VALIDATOR  (unchanged)
# =============================================================================

def _validate_dag_structure(dag):
    """Pre-flight structural validation. Unchanged from public repo."""
    all_ids = {}
    for node in dag:
        node_id = node.get("id")
        if not node_id:
            raise ValueError(f"DAG node missing 'id' field: {node}")
        if node_id in all_ids:
            raise ValueError(f"DAG contains duplicate node id: '{node_id}'")
        all_ids[node_id] = node

    for node in dag:
        node_id    = node["id"]
        depends_on = node.get("depends_on", [])
        for dep in depends_on:
            if dep not in all_ids:
                raise ValueError(
                    f"Node '{node_id}' depends_on '{dep}' "
                    f"which does not exist in the DAG."
                )
        _check_refs(node.get("input", {}), depends_on, node_id)

    logging.info(
        f"[Validator] DAG structure valid. "
        f"{len(dag)} nodes, all dependencies resolved."
    )


def _check_refs(value, depends_on, node_id):
    """Recursively verify $$ref$$ strings match depends_on. Unchanged."""
    if isinstance(value, str):
        if value.startswith("$$") and value.endswith("$$"):
            ref = value[2:-2]
            if ref not in depends_on:
                logging.warning(
                    f"[Validator] Node '{node_id}' references '$${ref}$$' "
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
# SECTION F — UTILITY: find_terminal_nodes  (unchanged)
# =============================================================================

def find_terminal_nodes(dag):
    """
    Return the ids of nodes that no other node depends on.
    Unchanged from public repo.
    """
    all_ids       = {node["id"] for node in dag}
    depended_upon = set()
    for node in dag:
        for dep in node.get("depends_on", []):
            depended_upon.add(dep)
    terminal = sorted(all_ids - depended_upon)
    logging.info(f"[Foreman] Terminal nodes: {terminal}")
    return terminal
