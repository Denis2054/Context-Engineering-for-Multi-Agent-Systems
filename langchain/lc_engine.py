# lc_engine.py
# =============================================================================
# Universal Context Engine — LangChain Edition
# The Planner, the Executor, and the Trace.
#
# Replaces: engine.py
#
#   planner()               -> a Pydantic schema + with_structured_output()
#   resolve_dependencies()  -> unchanged in spirit, now operating on graph state
#   context_engine() loop   -> a compiled LangGraph StateGraph
#   ExecutionTrace          -> LangChainTrace (same field names, so the existing
#                              HTML dashboard renders it with almost no change)
#
# WHY THE PLANNER GETS SAFER
# --------------------------
# The original asked for json_mode=True, received a string, ran json.loads() on
# it, and indexed plan_data["plan"]. When the model wrapped things differently
# the whole run died with "NoneType object has no attribute 'get'", which is why
# the notebook shipped a planner_robust_patch hotfix cell.
#
# Here the plan is a Pydantic model:
#   * agent names are a Literal, so an invented agent name is impossible;
#   * arguments are a typed object, so keys cannot be misspelled or placed at
#     the wrong nesting level;
#   * LangChain performs schema generation, JSON-mode configuration, parsing and
#     validation in one call.
# The hotfix cell is therefore not needed and is not reproduced.
#
# WHAT LANGCHAIN DOES NOT PROVIDE HERE
# ------------------------------------
#   * Plan-and-Execute itself. LangChain removed it from core; what survives in
#     langchain-experimental is unmaintained. The two-node graph below is built
#     by hand on the Graph API.
#   * Context chaining. resolve_dependencies() interprets $$STEP_N_OUTPUT$$
#     references that the Planner writes at plan time and the Executor resolves
#     at run time. LangGraph carries state; it does not give the model a
#     dataflow language to declare dependencies in. That is this engine's own.
#   * The audit-shaped trace. LangSmith records a run tree; it does not record
#     planned_input vs resolved_context vs tokens_saved per plan step.
# =============================================================================

from __future__ import annotations

import copy
import logging
import operator
import re
import time
from typing import Annotated, Any, Dict, List, Literal, Optional, TypedDict

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, StateGraph
from pydantic import BaseModel, Field

# The canonical specialist names. If you add an agent you must add it BOTH here
# and to the Literal in PlanStep below — build_engine() asserts that this tuple
# matches the toolkit, so a mismatch fails loudly at assembly time instead of
# quietly at plan time.
AGENT_NAMES = ("Librarian", "Researcher", "Summarizer", "Writer")


# =============================================================================
# 1. The plan schema — replaces json_mode + json.loads + the hotfix patch
# =============================================================================

class AgentInput(BaseModel):
    """
    The union of every argument any specialist accepts. Every field is optional;
    the Planner fills only the ones the chosen agent needs.

    Declaring these explicitly (rather than an open dict) is what removes the
    original's failure mode: the model cannot invent a key, cannot misspell one,
    and cannot hoist arguments out of the input object.
    """
    intent_query: Optional[str] = Field(
        None, description="Librarian: a descriptive phrase of the desired style.")
    topic_query: Optional[str] = Field(
        None, description="Researcher: the subject matter to research.")
    text_to_summarize: Optional[str] = Field(
        None, description="Summarizer: the long text, or $$STEP_N_OUTPUT$$.")
    summary_objective: Optional[str] = Field(
        None, description="Summarizer: a clear goal for the summary.")
    blueprint: Optional[str] = Field(
        None, description="Writer: style instructions, usually $$STEP_N_OUTPUT$$ from the Librarian.")
    facts: Optional[str] = Field(
        None, description="Writer: factual material, usually $$STEP_N_OUTPUT$$ from the Researcher.")
    previous_content: Optional[str] = Field(
        None, description="Writer: existing text to rewrite.")


class PlanStep(BaseModel):
    step: int = Field(description="Step number, starting at 1.")
    agent: Literal["Librarian", "Researcher", "Summarizer", "Writer"] = Field(
        description="Which specialist executes this step.")
    input: AgentInput = Field(description="Arguments for that specialist.")


class Plan(BaseModel):
    plan: List[PlanStep] = Field(description="The ordered execution plan.")


PLANNER_PROMPT = ChatPromptTemplate.from_messages([
    ("system",
     "You are the strategic core of the Context Engine. Analyze the user's "
     "high-level GOAL and create a step-by-step EXECUTION PLAN.\n\n"
     "AVAILABLE CAPABILITIES\n---\n{capabilities}\n---\nEND CAPABILITIES\n\n"
     "INSTRUCTIONS:\n"
     "1. Number steps from 1, in execution order.\n"
     "2. Use Context Chaining: where a value must come from an earlier step, "
     "write the literal string \"$$STEP_N_OUTPUT$$\" (N is that step's number) "
     "instead of the value.\n"
     "3. Fill only the input fields the chosen agent actually needs; leave the "
     "rest null.\n"
     "4. CANONICAL FLOW: a typical plan retrieves a blueprint with the "
     "Librarian, researches the facts with the Researcher, then writes the "
     "final content with the Writer. Start from this shape and depart from it "
     "only when the goal clearly does not need one of the three.\n"
     "5. BLUEPRINT FIRST — this rule is not optional. If the goal asks for "
     "content to be written, rewritten, styled, pitched, drafted or generated, "
     "then step 1 MUST be the Librarian, and the Writer step MUST receive that "
     "blueprint through $$STEP_1_OUTPUT$$. A plan containing a Writer step with "
     "no preceding Librarian step is INVALID. The Semantic Blueprint governs "
     "tone and structure; skipping it produces content in an arbitrary voice.\n"
     "6. A goal that only asks to retrieve, summarize, extract or answer — with "
     "no styled deliverable — does not need the Librarian.\n"
     "7. GROUND EVERYTHING — this rule is not optional. You must NEVER write "
     "your own factual content into 'facts', 'previous_content' or "
     "'text_to_summarize'. Those fields accept ONLY a \"$$STEP_N_OUTPUT$$\" "
     "reference to a step that retrieved the material. Every Writer step "
     "therefore needs a Researcher step before it. You do not know what is in "
     "the knowledge base; inventing content produces a fluent, confident, "
     "entirely unsourced answer, which is the single worst failure this engine "
     "can produce.\n"
     "8. Insert a Summarizer step between the Researcher and the Writer when the "
     "research is likely to be long."),
    ("human", "{goal}"),
])


def build_planner(llm, capabilities: str):
    """Return a Runnable that turns a goal string into a validated Plan."""
    from lc_helpers import base_model
    structured = base_model(llm).with_structured_output(Plan).with_retry(
        stop_after_attempt=4, wait_exponential_jitter=True
    )
    chain = PLANNER_PROMPT | structured

    def plan_for(goal: str, config=None) -> Plan:
        return chain.invoke({"goal": goal, "capabilities": capabilities}, config=config)

    plan_for.chain = chain          # exposed so the notebook can inspect it
    return plan_for


# =============================================================================
# 1b. Plan validation — the deterministic backstop to the prompt
#
# Instruction 4 above tells the Planner that a Writer step requires a preceding
# Librarian step. Prompt instructions are probabilistic. In a governed
# deployment the policy must also be CHECKED, and a violation must appear in the
# audit record rather than only in whatever the model happened to do.
#
# These are warnings, not hard failures: the run proceeds, but the trace carries
# the finding. Escalating to a hard failure is a one-line change in plan_node.
# =============================================================================

# Verbs that imply a styled deliverable, and therefore a blueprint.
STYLED_OUTPUT_VERBS = (
    "write", "rewrite", "draft", "pitch", "compose", "craft",
    "generate", "produce", "style", "tone of voice", "copy for",
)

# Arguments that must carry corpus-derived content, never planner-authored prose.
# If the Planner writes literal text into any of these, the deliverable is
# ungrounded: it never passed through retrieval, the sanitizer, or citation.
GROUNDED_ARGS = ("facts", "previous_content", "text_to_summarize")

# Agents whose output is corpus-derived and may therefore ground a later step.
GROUNDING_AGENTS = ("Researcher", "Summarizer", "Librarian")


def validate_plan(plan: List[dict], goal: str = "") -> List[str]:
    """
    Check a plan against the engine's governance rules.

    Returns a list of human-readable findings; an empty list means the plan is
    compliant. Nothing here calls a model, so validation is free and can be run
    on every plan, including inside plan_only().
    """
    findings: List[str] = []
    agents = [s.get("agent") for s in plan]

    if not plan:
        return ["Plan is empty."]

    # --- Rule 1: a Writer requires a Librarian before it. -------------------
    if "Writer" in agents:
        writer_at = agents.index("Writer")
        if "Librarian" not in agents[:writer_at]:
            findings.append(
                "BLUEPRINT-FIRST VIOLATION: the plan reaches the Writer with no "
                "preceding Librarian step. The output will be produced in an "
                "arbitrary voice rather than the one the Semantic Blueprint "
                "specifies."
            )
        else:
            # --- Rule 2: the blueprint must actually be chained through. ----
            librarian_step = plan[agents.index("Librarian")].get("step")
            writer_input = plan[writer_at].get("input", {}) or {}
            expected = f"$$STEP_{librarian_step}_OUTPUT$$"
            if writer_input.get("blueprint") != expected:
                findings.append(
                    f"CHAINING GAP: the Writer's 'blueprint' argument is not "
                    f"{expected}. The Librarian ran, but its blueprint may not "
                    f"reach the Writer."
                )

    # --- Rule 3: a styled goal with no Writer at all. -----------------------
    lowered = (goal or "").lower()
    styled_goal = any(v in lowered for v in STYLED_OUTPUT_VERBS)
    if styled_goal and "Writer" not in agents:
        findings.append(
            "The goal asks for a styled deliverable but the plan contains no "
            "Writer step. The result will be raw research or a summary."
        )

    # --- Rule 4: content arguments must be references, not authored prose. --
    #
    # This is the most important check in this function. A Planner that writes
    # its own text into 'facts' produces a fluent, on-brand, entirely
    # UNSOURCED deliverable: retrieval never ran, the sanitizer never ran, and
    # there is nothing to cite. The dashboard still reports Success, so nothing
    # about the run looks wrong. That is precisely why it must be checked.
    for step in plan:
        step_input = step.get("input", {}) or {}
        for arg in GROUNDED_ARGS:
            value = step_input.get(arg)
            if not isinstance(value, str) or not value.strip():
                continue
            if not _REFERENCE.search(value):
                preview = " ".join(value.split())[:60]
                findings.append(
                    f"UNGROUNDED CONTENT: step {step.get('step')} "
                    f"({step.get('agent')}) received literal text in '{arg}' "
                    f"instead of a $$STEP_N_OUTPUT$$ reference "
                    f"(\"{preview}...\"). This content was authored by the "
                    f"Planner, not retrieved from the corpus: it bypassed "
                    f"retrieval, sanitization and citation."
                )

    # --- Rule 5: a Writer with nothing retrieved behind it. -----------------
    if "Writer" in agents:
        writer_at = agents.index("Writer")
        if not any(a == "Researcher" for a in agents[:writer_at]):
            findings.append(
                "GROUNDING GAP: the plan reaches the Writer with no Researcher "
                "step before it. Nothing in the deliverable will be traceable "
                "to the knowledge base, and it will carry no sources."
            )

    return findings


# =============================================================================
# 2. Context chaining — the $$STEP_N_OUTPUT$$ substitution
#
# Not a LangChain feature. The Planner writes these references; the Executor
# resolves them against the outputs of earlier steps.
# =============================================================================

_REFERENCE = re.compile(r"\$\$([A-Za-z0-9_]+)\$\$")


def resolve_dependencies(input_params: Any, state: Dict[str, Any]) -> Any:
    """
    Replace $$REF$$ placeholders with data produced by earlier steps.

    Two cases, deliberately handled differently:

      * The whole string is a reference ("$$STEP_1_OUTPUT$$") -> the stored
        object is substituted as-is, preserving its type.
      * A reference is embedded in a longer string ("Summarize
        $$STEP_1_OUTPUT$$ briefly") -> the stored value is interpolated as text.

    An unresolvable reference is left untouched rather than replaced with None,
    so the failure is visible in the trace instead of silently becoming an empty
    argument.
    """
    resolved = copy.deepcopy(input_params)

    def resolve(value):
        if isinstance(value, str):
            whole = _REFERENCE.fullmatch(value)
            if whole:
                key = whole.group(1)
                if key in state:
                    return state[key]
                logging.warning(f"Unresolved context reference: $${key}$$")
                return value

            def substitute(match):
                key = match.group(1)
                if key in state:
                    return str(state[key])
                logging.warning(f"Unresolved context reference: $${key}$$")
                return match.group(0)

            return _REFERENCE.sub(substitute, value)
        if isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    return resolve(resolved)


# =============================================================================
# 3. The Trace — same shape as the original ExecutionTrace
# =============================================================================

class LangChainTrace:
    """
    Records the run so the HTML dashboard can render it.

    Field names match the original ExecutionTrace exactly (goal, plan, steps,
    status, final_output, duration; and per step: step, agent, planned_input,
    resolved_context, output, tokens_in, tokens_out, tokens_saved) so the
    dashboard needed no rewrite.

    Four fields are new:
      llm_in / llm_out  - the provider's own billed token counts per step;
      status            - per step, "ok" or "error", so a failed run still
                          renders the steps that did complete;
      moderation        - the pre-flight and post-flight reports, kept on the
                          trace so a blocked run leaves an audit record;
      plan_warnings     - governance findings from validate_plan(), so a policy
                          violation is recorded even when the run succeeds.
    """

    def __init__(self, goal: str):
        self.goal = goal
        self.plan: Optional[list] = None
        self.steps: List[dict] = []
        self.status = "Initialized"
        self.final_output: Any = None
        self.start_time = time.time()
        self.duration = 0.0
        self.usage: Dict[str, int] = {}
        self.moderation: Dict[str, Any] = {}
        self.plan_warnings: List[str] = []
        logging.info(f"LangChainTrace initialized for goal: '{goal}'")

    def log_plan(self, plan, warnings=None):
        self.plan = plan
        self.plan_warnings = list(warnings or [])
        logging.info("Plan has been logged to the trace.")
        for finding in self.plan_warnings:
            logging.warning(f"[Plan governance] {finding}")

    def log_step(self, **row):
        row.setdefault("status", "ok")
        self.steps.append(row)
        logging.info(
            f"Step {row.get('step')} ({row.get('agent')}) logged [{row['status']}]. "
            f"[ctx in: {row.get('tokens_in', 0)}, ctx out: {row.get('tokens_out', 0)}, "
            f"llm in: {row.get('llm_in', 0)}, llm out: {row.get('llm_out', 0)}]"
        )

    def log_moderation(self, phase: str, report: Dict[str, Any]):
        """Record a moderation report under 'pre' or 'post'."""
        self.moderation[phase] = report

    def finalize(self, status, final_output=None, usage=None):
        self.status = status
        self.final_output = final_output
        self.duration = time.time() - self.start_time
        self.usage = usage or {}
        logging.info(
            f"Trace finalized with status '{status}'. Duration: {self.duration:.2f}s"
        )


# =============================================================================
# 4. The graph — replaces the plan-then-execute loop in context_engine()
# =============================================================================

class EngineState(TypedDict, total=False):
    goal: str
    plan: List[dict]
    plan_warnings: List[str]
    cursor: int
    outputs: Dict[str, Any]
    steps: Annotated[List[dict], operator.add]   # appended, never overwritten
    final: Any
    error: str


def build_engine(llm, toolkit, tracker=None, count_tokens=None):
    """
    Compile the Plan-and-Execute graph.

    Nodes:
      plan     -> one structured LLM call producing a validated Plan
      execute  -> run one step, merge its output into shared state, loop

    Because this is a compiled LangGraph you get, for free: streaming of
    intermediate state, optional checkpointing so a failed run can resume at the
    failing step, and automatic LangSmith traces of every node.
    """
    toolkit_names = tuple(toolkit.names())
    if set(toolkit_names) != set(AGENT_NAMES):
        raise ValueError(
            f"Toolkit exposes {toolkit_names} but the Plan schema allows "
            f"{AGENT_NAMES}. Add the new agent to AGENT_NAMES and to the "
            f"Literal in PlanStep, or the Planner can never select it."
        )

    planner = build_planner(llm, toolkit.get_capabilities_description())
    _count = count_tokens or (lambda text, _llm=None: max(1, len(str(text)) // 4))

    # ---------------------------------------------------------------- plan
    def plan_node(state: EngineState, config: RunnableConfig = None) -> dict:
        logging.info("Planner activated. Analyzing goal and generating execution plan...")
        try:
            result = planner(state["goal"], config=config)
            plan = [
                {
                    "step": s.step,
                    "agent": s.agent,
                    "input": s.input.model_dump(exclude_none=True),
                }
                for s in result.plan
            ]
            if not plan:
                return {"error": "Planner returned an empty plan."}

            # Governance check. Findings are recorded, not fatal. To enforce the
            # policy instead of reporting it, return {"error": findings[0]} here.
            findings = validate_plan(plan, state.get("goal", ""))
            for finding in findings:
                logging.warning(f"[Plan governance] {finding}")

            logging.info(f"Plan generated: {len(plan)} step(s).")
            return {"plan": plan, "plan_warnings": findings,
                    "cursor": 0, "outputs": {}}
        except Exception as e:
            logging.error(f"Planner failed to generate a valid plan. Error: {e}")
            return {"error": f"Failed during Planning/Init: {e}"}

    # ------------------------------------------------------------- execute
    def execute_node(state: EngineState, config: RunnableConfig = None) -> dict:
        step = state["plan"][state["cursor"]]
        num, name, planned = step["step"], step["agent"], step["input"]
        logging.info(f"--- Executor: Starting Step {num}: {name} ---")

        resolved: Any = planned
        snap = tracker.snapshot() if tracker else None

        try:
            tool = toolkit.get(name)
            resolved = resolve_dependencies(planned, state.get("outputs", {}))

            # Drop any argument this agent does not accept. The Plan schema is a
            # union of every specialist's arguments, so a Planner that fills one
            # extra field would otherwise depend on Pydantic's silent
            # extra-field behaviour to survive.
            accepted = toolkit.arg_names(name)
            if isinstance(resolved, dict) and accepted:
                dropped = sorted(set(resolved) - accepted)
                if dropped:
                    logging.warning(
                        f"[Executor] Step {num} ({name}): dropping argument(s) "
                        f"{dropped} — not accepted by this agent."
                    )
                    resolved = {k: v for k, v in resolved.items() if k in accepted}

            t_in = _count(resolved, llm)
            output = tool.invoke(resolved, config=config)
            t_out = _count(output, llm)
            delta = tracker.delta(snap) if tracker else {"llm_in": 0, "llm_out": 0}

            key = f"STEP_{num}_OUTPUT"
            is_last = state["cursor"] + 1 >= len(state["plan"])
            logging.info(f"--- Executor: Step {num} completed. ---")

            return {
                "outputs": {**state.get("outputs", {}), key: output},
                "cursor": state["cursor"] + 1,
                "final": output if is_last else state.get("final"),
                "steps": [{
                    "step": num,
                    "agent": name,
                    "status": "ok",
                    "planned_input": planned,
                    "resolved_context": resolved,
                    "output": output,
                    "tokens_in": t_in,
                    "tokens_out": t_out,
                    # The original computed "saved" only for the Summarizer.
                    "tokens_saved": max(0, t_in - t_out) if name == "Summarizer" else 0,
                    "llm_in": delta.get("llm_in", 0),
                    "llm_out": delta.get("llm_out", 0),
                }],
            }

        except Exception as e:
            msg = f"Execution failed at step {num} ({name}): {e}"
            logging.error(f"--- Executor: FATAL ERROR --- {msg}")
            delta = tracker.delta(snap) if tracker else {"llm_in": 0, "llm_out": 0}
            # Record the failed step too, so the dashboard shows where the run
            # stopped and with what resolved input, rather than ending silently.
            return {
                "error": msg,
                "cursor": state["cursor"] + 1,
                "steps": [{
                    "step": num,
                    "agent": name,
                    "status": "error",
                    "planned_input": planned,
                    "resolved_context": resolved,
                    "output": msg,
                    "tokens_in": _count(resolved, llm),
                    "tokens_out": 0,
                    "tokens_saved": 0,
                    "llm_in": delta.get("llm_in", 0),
                    "llm_out": delta.get("llm_out", 0),
                }],
            }

    # ------------------------------------------------------------- routing
    def route(state: EngineState) -> str:
        if state.get("error"):
            return "end"
        if state.get("cursor", 0) < len(state.get("plan") or []):
            return "execute"
        return "end"

    graph = StateGraph(EngineState)
    graph.add_node("plan", plan_node)
    graph.add_node("execute", execute_node)
    graph.set_entry_point("plan")
    graph.add_conditional_edges("plan", route, {"execute": "execute", "end": END})
    graph.add_conditional_edges("execute", route, {"execute": "execute", "end": END})
    return graph.compile()


# =============================================================================
# 5. The public entry point — same contract as the original context_engine()
# =============================================================================

def context_engine(goal: str, engine, tracker=None, recursion_limit: int = 60,
                   trace: Optional[LangChainTrace] = None):
    """
    Run the engine. Returns (final_output, trace).

    Signature note: the original took client, pc, index_name, models and
    namespaces. All of that is now baked into the compiled `engine` object, so
    the runtime call is just the goal.

    A caller may pass an existing `trace` so that pre-flight moderation, which
    happens before the graph runs, is recorded on the same object.
    """
    logging.info(f"--- [Context Engine] Starting New Task --- Goal: {goal}")
    trace = trace or LangChainTrace(goal)

    config: Dict[str, Any] = {"recursion_limit": recursion_limit}
    if tracker is not None:
        config["callbacks"] = [tracker]

    try:
        state = engine.invoke({"goal": goal, "steps": []}, config=config)
    except Exception as e:
        logging.error(f"Engine invocation failed: {e}")
        trace.finalize(f"Failed: {e}", None, tracker.summary() if tracker else {})
        return None, trace

    if state.get("plan"):
        trace.log_plan(state["plan"], state.get("plan_warnings"))
    for row in state.get("steps", []):
        trace.log_step(**row)

    usage = tracker.summary() if tracker else {}

    if state.get("error"):
        trace.finalize(state["error"], None, usage)
        logging.error(f"--- [Context Engine] Task Failed --- {state['error']}")
        return None, trace

    final = state.get("final")
    trace.finalize("Success", final, usage)
    logging.info("--- [Context Engine] Task Complete ---")
    return final, trace
