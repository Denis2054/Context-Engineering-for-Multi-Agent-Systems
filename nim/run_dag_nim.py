# =============================================================================
# run_dag_nim.py  —  The Foreman (DAG Executor)
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# The Foreman takes a validated plan and makes it happen. It is the only
# component that knows about ordering, concurrency, and failure, and it knows
# nothing about what any agent actually does.
#
# The loop is four lines of idea:
#
#   while some nodes are unfinished:
#       ready = every unfinished node whose dependencies have all completed
#       run every node in `ready` concurrently
#       record their outputs
#
# There is no topological sort and no explicit layering. Readiness is recomputed
# from scratch each pass, which means concurrency is discovered rather than
# scheduled: if three nodes happen to have no outstanding dependencies, three
# nodes run. A chain of eight produces eight passes of one node each and
# behaves exactly like a sequential engine, with no special case.
#
# WHY ASYNCIO RATHER THAN A THREAD POOL
# -------------------------------------
# The public edition used ThreadPoolExecutor. It submits every ready node at
# once and lets the OS sort it out, which is fine against an endpoint with
# generous limits and actively harmful against one with a hard request-per-
# minute ceiling. Four simultaneous requests arriving in the same millisecond
# on the NIM free tier is how you collect four 429s at once — and then the
# backoff jitter that was supposed to save you serialises everything anyway,
# so you pay full latency plus the retries.
#
# asyncio.Semaphore turns the burst into a queue. In-flight requests are capped
# at NIM_MAX_CONCURRENT; a fifth node waits for a slot instead of being
# rejected. The result is counter-intuitive and consistent: limiting
# concurrency makes the run faster, because time spent waiting for a free slot
# is cheaper than time spent in exponential backoff.
#
# The agent calls themselves are synchronous — `requests.post` blocks — so each
# one is handed to `asyncio.to_thread`. The event loop coordinates; the threads
# do the waiting. Async for admission control, threads for I/O.
#
# The original ThreadPoolExecutor implementation is preserved at the bottom of
# this file, unused. Comparing the two side by side is the clearest way to see
# what the upgrade actually changed.
# =============================================================================

import asyncio
import copy
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


# =============================================================================
# SECTION A — EVENT LOOP COMPATIBILITY
#
# A Jupyter kernel is already running an event loop, so a bare `asyncio.run()`
# inside a cell raises "asyncio.run() cannot be called from a running event
# loop". Three environments have to work: a plain script, a notebook with
# nest_asyncio available, and a notebook without it.
# =============================================================================

def _run_coroutine(coro):
    """
    Execute a coroutine from synchronous code, whatever the host environment.

    Strategy, in order:
      1. No loop running (a script) — asyncio.run().
      2. Loop running and nest_asyncio importable (a notebook) — patch and
         reuse the live loop.
      3. Loop running, no nest_asyncio — run it on a fresh loop in a worker
         thread, so the caller's loop is untouched.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)          # no loop: the simple case

    try:
        import nest_asyncio
        nest_asyncio.apply()
        return asyncio.get_event_loop().run_until_complete(coro)
    except ImportError:
        logging.warning(
            "[Foreman] nest_asyncio is not installed. Running the DAG on a "
            "separate event loop in a worker thread. `pip install nest_asyncio` "
            "for the cleaner path."
        )
        import threading
        box = {}

        def _worker():
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                box["result"] = loop.run_until_complete(coro)
            except BaseException as e:       # noqa: BLE001 — re-raised below
                box["error"] = e
            finally:
                loop.close()

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join()
        if "error" in box:
            raise box["error"]
        return box.get("result")


# =============================================================================
# SECTION B — INPUT RESOLUTION
#
# The planner cannot know what a node will produce, so it writes a placeholder:
# "$$research_step$$". At execution time that placeholder is replaced with the
# actual output of the node called `research_step`.
#
# This is the mechanism that turns a list of independent agent calls into a
# pipeline, and it is worth noticing that the substitution is by WHOLE OBJECT,
# not by string interpolation. A reference resolves to the upstream agent's
# entire output dict, which is why the Writer and Summarizer accept several
# input shapes: they receive whatever the upstream node happened to return.
#
# The walk is recursive because a node's input can nest references inside
# dicts and lists.
# =============================================================================

def resolve_inputs(node_input, completed_outputs):
    """
    Replace every $$node_id$$ placeholder with that node's completed output.

    Args:
        node_input (dict):        the node's input as the planner wrote it.
        completed_outputs (dict): node_id -> output, for finished nodes.

    Returns:
        dict: a deep copy with every resolvable reference substituted.

    An unresolvable reference is left as the literal placeholder and logged as
    a warning rather than raised. The agent then fails with a message naming
    the input it could not use, which points at the planner — the actual
    source of the fault — rather than at the resolver.
    """
    resolved = copy.deepcopy(node_input)

    def walk(value):
        if isinstance(value, str) and value.startswith("$$") and value.endswith("$$"):
            source_id = value[2:-2]
            substituted = completed_outputs.get(source_id, value)
            if substituted == value:
                logging.warning(
                    f"[Resolver] '$${source_id}$$' not found in completed "
                    f"outputs. Available: {list(completed_outputs.keys())}"
                )
            return substituted
        if isinstance(value, dict):
            return {k: walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return value

    return walk(resolved)


# =============================================================================
# SECTION C — DOMAIN DISPATCH  [THE A2A SEAM]
#
# Every agent invocation in the system funnels through this one function. That
# is not incidental — it is the point.
#
# Today a cross-domain call is a registry lookup and a function call in the
# same process. Tomorrow, when Legal runs behind its own service with its own
# credentials and its own index, this function grows an `if node_domain !=
# local_domain: POST to that domain's /run endpoint` branch, and nothing else
# in the codebase changes.
#
# The planner already emits domains. The Harness already validates cross-domain
# edges. The registry already resolves per-domain namespaces. All three were
# written against domains rather than processes, so distribution is one
# function's worth of work rather than an architecture migration. The log line
# below marks the seam on every cross-domain hop so you can see where the
# network boundary would fall.
# =============================================================================

def dispatch_node(node, resolved_input, registry, adapter, client,
                  generation_model, embedding_model,
                  local_domain="General", agent_model=None):
    """
    Route one node to its agent and return the agent's MCP envelope.

    Args:
        node (dict):            the DAG node.
        resolved_input (dict):  input with all $$refs$$ substituted.
        registry:               AgentRegistry.
        adapter:                StorageAdapter.
        client:                 LLM / embedding credential holder.
        generation_model (str): planner model.
        embedding_model (str):  must match the index.
        local_domain (str):     the domain this process represents.
        agent_model (str|None): agent model; None means "same as planner".

    Returns:
        dict: the agent's MCP envelope.
    """
    node_id     = node["id"]
    agent_name  = node["agent"]
    node_domain = node.get("domain", "General")

    if node_domain != local_domain:
        logging.info(
            f"[Dispatcher] cross-domain node '{node_id}': "
            f"{local_domain} -> {node_domain} (local dispatch — A2A seam)"
        )
    else:
        logging.info(f"[Dispatcher] local node '{node_id}' domain={node_domain}")

    handler = registry.get_handler(
        agent_name,
        domain           = node_domain,
        client           = client,
        adapter          = adapter,
        generation_model = generation_model,
        embedding_model  = embedding_model,
        agent_model      = agent_model,
    )

    from helpers import create_mcp_message
    return handler(create_mcp_message("Engine", resolved_input))


# =============================================================================
# SECTION D — THE FOREMAN
# =============================================================================

def run_dag(dag, registry, adapter, client, generation_model,
            embedding_model, trace, local_domain="General",
            agent_model=None, max_concurrent=None):
    """
    Execute a validated DAG, running independent nodes concurrently.

    Args:
        dag (list[dict]):        validated node list.
        registry:                AgentRegistry.
        adapter:                 StorageAdapter.
        client:                  LLM / embedding credential holder.
        generation_model (str):  planner model.
        embedding_model (str):   must match the index.
        trace (ExecutionTrace):  receives one log_step() per completed node.
        local_domain (str):      this process's domain.
        agent_model (str|None):  agent model; None means "same as planner".
        max_concurrent (int|None): semaphore cap. None reads NIM_MAX_CONCURRENT.

    Returns:
        dict: node_id -> output, for every node.

    Raises:
        RuntimeError: on a cycle, or on any node failure.

    ON FAILURE POLICY
    -----------------
    One failed node aborts the run. There is no partial-success mode and no
    retry-the-node-with-a-different-plan.

    That is the right default for a governed engine: a DAG whose Legal
    verification node failed must not quietly produce a marketing brief, and
    "some of the checks ran" is not a state anyone can sign off on. The trace
    retains every node that completed before the failure, so diagnosis does not
    require re-running.
    """
    from helpers import count_tokens

    if max_concurrent is None:
        try:
            from utils import NIM_MAX_CONCURRENT
            max_concurrent = NIM_MAX_CONCURRENT
        except ImportError:
            max_concurrent = 4

    # [PLANE 1 — STATE OF RECORD SEAM]
    # An in-process dict today. When execution distributes, these three lines
    # become adapter.write_state() / adapter.read_state() calls, which is why
    # those promises are declared in adapters_nim.py rather than omitted.
    completed_outputs = {}
    done              = set()
    all_ids           = {node["id"] for node in dag}

    logging.info(
        f"[Foreman] starting. nodes={len(dag)} "
        f"max_concurrent={max_concurrent} "
        f"agent_model={agent_model or 'same as planner'}"
    )

    _validate_dag_structure(dag)

    wave = 0
    while done != all_ids:
        wave += 1

        ready = [
            node for node in dag
            if node["id"] not in done
            and all(dep in done for dep in node.get("depends_on", []))
        ]

        # Unfinished nodes and nothing ready means a cycle. The structural
        # validator cannot catch this — it checks that references exist, not
        # that the graph is acyclic — so the deadlock is detected here, by the
        # scheduler noticing it has nothing to do and work remaining.
        if not ready:
            remaining = [n["id"] for n in dag if n["id"] not in done]
            msg = f"[Foreman] DEADLOCK — the DAG contains a cycle. Stuck: {remaining}"
            logging.error(msg)
            trace.finalize(f"Failed: cycle detected. Stuck: {remaining}")
            raise RuntimeError(msg)

        logging.info(
            f"[Foreman] wave {wave}: {len(ready)} ready — {[n['id'] for n in ready]}"
        )

        if len(ready) == 1:
            _execute_single_node(
                ready[0], completed_outputs, done, trace,
                registry, adapter, client,
                generation_model, embedding_model,
                local_domain, agent_model,
            )
        else:
            _run_coroutine(
                _execute_parallel_nodes_async(
                    ready, completed_outputs, done, trace,
                    registry, adapter, client,
                    generation_model, embedding_model,
                    local_domain, agent_model, max_concurrent,
                )
            )

    logging.info(
        f"[Foreman] complete. {len(all_ids)} node(s) in {wave} wave(s)."
    )
    return completed_outputs


# =============================================================================
# SECTION E — EXECUTION PATHS
# =============================================================================

def _execute_single_node(node, completed_outputs, done, trace,
                         registry, adapter, client,
                         generation_model, embedding_model,
                         local_domain, agent_model=None):
    """Run one node synchronously. Used whenever the ready set holds exactly one."""
    from helpers import count_tokens

    node_id = node["id"]
    logging.info(f"[Foreman] executing '{node_id}' (single).")

    resolved_input = resolve_inputs(node["input"], completed_outputs)
    t_in           = count_tokens(str(resolved_input))
    started        = time.time()

    try:
        mcp_output = dispatch_node(
            node, resolved_input, registry, adapter,
            client, generation_model, embedding_model,
            local_domain, agent_model,
        )
    except Exception as e:
        msg = f"Node '{node_id}' ({node['agent']}) failed: {e}"
        logging.error(f"[Foreman] {msg}")
        raise RuntimeError(msg) from e

    elapsed     = time.time() - started
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
        duration_s     = elapsed,
    )
    logging.info(
        f"[Foreman] '{node_id}' done in {elapsed:.2f}s [in {t_in} / out {t_out}]"
    )


async def _execute_parallel_nodes_async(nodes, completed_outputs, done, trace,
                                        registry, adapter, client,
                                        generation_model, embedding_model,
                                        local_domain, agent_model, max_concurrent):
    """
    Run a ready set concurrently, capped by a semaphore.

    Two details are load-bearing:

    THE SEMAPHORE is acquired around the API call and released the moment the
    response returns, so a slot frees for a waiting node immediately rather
    than at the end of the wave.

    THE COMMIT IS DEFERRED. Nodes write into a local `results` dict while
    running; `completed_outputs` and the trace are updated only after
    asyncio.gather() returns. That keeps `completed_outputs` immutable for the
    duration of the wave, which matters because resolve_inputs() reads it. A
    node that mutated it mid-wave could change what a sibling resolves — a
    genuine race, and one that would appear only under load and only sometimes.
    Deferring the commit removes it by construction.
    """
    from helpers import count_tokens

    sem     = asyncio.Semaphore(max_concurrent)
    results = {}

    logging.info(
        f"[Foreman] async wave: {[n['id'] for n in nodes]} "
        f"(semaphore={max_concurrent})"
    )

    async def run_one(node):
        node_id = node["id"]
        # Resolved BEFORE the semaphore is acquired: substitution is pure
        # dictionary work and holding a slot during it would waste the slot.
        resolved_input = resolve_inputs(node["input"], completed_outputs)
        t_in           = count_tokens(str(resolved_input))

        async with sem:
            logging.info(f"[Foreman] '{node_id}' acquired a slot.")
            started = time.time()
            try:
                # dispatch_node blocks on requests.post, so it goes to a thread.
                # The event loop stays free to admit the next node the instant
                # a slot opens.
                mcp_output = await asyncio.to_thread(
                    dispatch_node,
                    node, resolved_input, registry, adapter,
                    client, generation_model, embedding_model,
                    local_domain, agent_model,
                )
            except Exception as e:
                msg = f"Node '{node_id}' ({node['agent']}) failed: {e}"
                logging.error(f"[Foreman] {msg}")
                raise RuntimeError(msg) from e
            elapsed = time.time() - started

        output_data = mcp_output["content"]
        t_out       = count_tokens(str(output_data))
        results[node_id] = (node, resolved_input, output_data, t_in, t_out, elapsed)
        logging.info(
            f"[Foreman] '{node_id}' done in {elapsed:.2f}s [in {t_in} / out {t_out}]"
        )

    # gather() propagates the first exception, so one failed node aborts the
    # wave and, through run_dag, the run.
    await asyncio.gather(*[run_one(node) for node in nodes])

    # Commit phase — after every task in the wave has finished.
    for node_id, (node, resolved_input, output_data, t_in, t_out, elapsed) in results.items():
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
            duration_s     = elapsed,
        )


def _execute_parallel_nodes(nodes, completed_outputs, done, trace,
                            registry, adapter, client,
                            generation_model, embedding_model,
                            local_domain, agent_model=None):
    """
    The original ThreadPoolExecutor implementation. Retained, unused.

    Kept because the diff against _execute_parallel_nodes_async() is the
    clearest statement of what the NIM upgrade actually changed. Note what is
    absent here: any notion of a concurrency cap. `max_workers=len(nodes)`
    means every ready node fires at once, which is precisely the behaviour that
    collides with a request-per-minute ceiling.
    """
    from helpers import count_tokens

    logging.warning(
        "[Foreman] _execute_parallel_nodes() called directly. This path has no "
        "rate-limit semaphore. run_dag() routes to the asyncio path instead."
    )

    futures, results = {}, {}

    with ThreadPoolExecutor(max_workers=len(nodes)) as executor:
        for node in nodes:
            resolved_input = resolve_inputs(node["input"], completed_outputs)
            future = executor.submit(
                dispatch_node,
                node, resolved_input, registry, adapter,
                client, generation_model, embedding_model,
                local_domain, agent_model,
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
            results[node_id] = (
                node, resolved_input, output_data,
                count_tokens(str(resolved_input)),
                count_tokens(str(output_data)),
            )

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
# SECTION F — STRUCTURAL VALIDATION
#
# Cheap checks that run before the first API call. Every fault found here would
# otherwise surface mid-run, after money has been spent.
#
# What this does NOT check is acyclicity — that is left to the scheduler, which
# detects it as a deadlock. Two detectors for two different classes of problem:
# static faults here, dynamic ones in the loop.
# =============================================================================

def _validate_dag_structure(dag):
    """
    Verify ids are present and unique, and that every dependency exists.

    Raises:
        ValueError: on a missing id, a duplicate id, or a dangling dependency.
    """
    all_ids = {}
    for node in dag:
        node_id = node.get("id")
        if not node_id:
            raise ValueError(f"DAG node is missing an 'id' field: {node}")
        if node_id in all_ids:
            raise ValueError(f"DAG contains a duplicate node id: '{node_id}'")
        all_ids[node_id] = node

    for node in dag:
        depends_on = node.get("depends_on", [])
        for dep in depends_on:
            if dep not in all_ids:
                raise ValueError(
                    f"Node '{node['id']}' depends_on '{dep}', "
                    f"which does not exist in the DAG."
                )
        _check_refs(node.get("input", {}), depends_on, node["id"])

    logging.info(
        f"[Validator] structure valid: {len(dag)} node(s), "
        f"all dependencies resolvable."
    )


def _check_refs(value, depends_on, node_id):
    """
    Warn when a node references $$X$$ without declaring X in depends_on.

    A warning rather than an error, because the plan may still succeed: if X
    happens to complete in an earlier wave the reference resolves anyway. But
    it is a latent scheduling bug — the Foreman has not been told to wait — so
    it is worth surfacing. This is the single most common planner mistake, and
    seeing the warning in the log is usually enough to explain a node that
    received a literal "$$X$$" string as its input.
    """
    if isinstance(value, str):
        if value.startswith("$$") and value.endswith("$$"):
            ref = value[2:-2]
            if ref not in depends_on:
                logging.warning(
                    f"[Validator] node '{node_id}' references '$${ref}$$' but "
                    f"'{ref}' is not in its depends_on. The Foreman may run "
                    f"this node before '{ref}' completes."
                )
    elif isinstance(value, dict):
        for v in value.values():
            _check_refs(v, depends_on, node_id)
    elif isinstance(value, list):
        for item in value:
            _check_refs(item, depends_on, node_id)


# =============================================================================
# SECTION G — TERMINAL NODES
# =============================================================================

def find_terminal_nodes(dag):
    """
    Return the ids of nodes nothing else depends on — the DAG's outputs.

    Usually one: the Writer. When a plan fans out to several terminals the
    engine returns a dict of all of them rather than guessing which one the
    user meant.
    """
    all_ids       = {node["id"] for node in dag}
    depended_upon = {dep for node in dag for dep in node.get("depends_on", [])}
    terminal      = sorted(all_ids - depended_upon)
    logging.info(f"[Foreman] terminal nodes: {terminal}")
    return terminal
