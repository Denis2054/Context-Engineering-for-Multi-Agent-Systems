# === Imports ===
import logging
import time
import json
import copy
from helpers import call_llm_robust, create_mcp_message, count_tokens # Added count_tokens import
from registry import AGENT_TOOLKIT

# === 6.1. The Tracer ===
class ExecutionTrace:
    """Logs the entire execution flow for debugging and analysis."""
    def __init__(self, goal):
        self.goal = goal
        self.plan = None
        self.steps = []
        self.status = "Initialized"
        self.final_output = None
        self.start_time = time.time()
        logging.info(f"ExecutionTrace initialized for goal: '{self.goal}'")

    def log_plan(self, plan):
        self.plan = plan
        logging.info("Plan has been logged to the trace.")

    # UPGRADE: Added tokens_in and tokens_out parameters
    def log_step(self, step_num, agent, planned_input, mcp_output, resolved_input, tokens_in=0, tokens_out=0):
        """Logs the details of a single execution step, including token metrics."""
        self.steps.append({
            "step": step_num,
            "agent": agent,
            "planned_input": planned_input,
            "resolved_context": resolved_input,
            "output": mcp_output['content'],
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            # Calculate savings specifically for the summarizer
            "tokens_saved": max(0, tokens_in - tokens_out) if agent == "Summarizer" else 0
        })
        logging.info(f"Step {step_num} ({agent}) logged to the trace. [In: {tokens_in}, Out: {tokens_out}]")

    def finalize(self, status, final_output=None):
        self.status = status
        self.final_output = final_output
        self.duration = time.time() - self.start_time
        logging.info(f"Trace finalized with status '{status}'. Duration: {self.duration:.2f}s")

# === 6.2. The Planner ===
def planner(goal, capabilities, client, generation_model):
    """Analyzes the goal and generates a structured Execution Plan using the LLM."""
    logging.info("Planner activated. Analyzing goal and generating execution plan...")
    system_prompt = f"""
You are the strategic core of the Context Engine. Analyze the user's high-level GOAL and create a step-by-step EXECUTION PLAN.

AVAILABLE CAPABILITIES
---
{capabilities}
---
END CAPABILITIES

INSTRUCTIONS:
1. The output MUST be a single JSON object with a "plan" key containing a list of step objects.
2. Use Context Chaining: format "$$STEP_N_OUTPUT$$" for values requiring previous outputs.
"""
    try:
        plan_json_string = call_llm_robust(
            system_prompt,
            goal,
            client=client,
            generation_model=generation_model,
            json_mode=True
        )
        plan_data = json.loads(plan_json_string)
        return plan_data["plan"]
    except Exception as e:
        logging.error(f"Planner failed to generate a valid plan. Error: {e}")
        raise e

# === 6.3. The Executor ===
def resolve_dependencies(input_params, state):
    """Helper function to replace $$REF$$ placeholders with data from the execution state."""
    resolved_input = copy.deepcopy(input_params)
    def resolve(value):
        if isinstance(value, str) and value.startswith("$$") and value.endswith("$$"):
            ref_key = value[2:-2]
            return state.get(ref_key, value)
        elif isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [resolve(item) for item in value]
        return value
    return resolve(resolved_input)

def context_engine(goal, client, pc, index_name, generation_model, embedding_model, namespace_context, namespace_knowledge):
    """The main entry point for the Context Engine. Manages Planning and Execution."""
    logging.info(f"--- [Context Engine] Starting New Task --- Goal: {goal}")
    trace = ExecutionTrace(goal)
    registry = AGENT_TOOLKIT

    try:
        index = pc.Index(index_name)
        capabilities = registry.get_capabilities_description()
        plan = planner(goal, capabilities, client=client, generation_model=generation_model)
        trace.log_plan(plan)
    except Exception as e:
        trace.finalize(f"Failed during Planning/Init: {e}")
        return None, trace

    # --- Phase 2: Execute ---
    state = {}
    for step in plan:
        step_num = step.get("step")
        agent_name = step.get("agent")
        planned_input = step.get("input")

        logging.info(f"--- Executor: Starting Step {step_num}: {agent_name} ---")
        try:
            handler = registry.get_handler(
                agent_name,
                client=client,
                index=index,
                generation_model=generation_model,
                embedding_model=embedding_model,
                namespace_context=namespace_context,
                namespace_knowledge=namespace_knowledge
            )
            
            # 1. Resolve inputs
            resolved_input = resolve_dependencies(planned_input, state)
            
            # UPGRADE: Count Input Tokens (The context being sent to the agent)
            t_in = count_tokens(str(resolved_input))
            
            # 2. Call the agent
            mcp_resolved_input = create_mcp_message("Engine", resolved_input)
            mcp_output = handler(mcp_resolved_input)
            output_data = mcp_output["content"]
            
            # UPGRADE: Count Output Tokens (The response generated by the agent)
            t_out = count_tokens(str(output_data))
            
            # 3. Update state and log results
            state[f"STEP_{step_num}_OUTPUT"] = output_data
            
            # UPGRADE: Pass token counts into the log_step call
            trace.log_step(
                step_num, 
                agent_name, 
                planned_input, 
                mcp_output, 
                resolved_input, 
                tokens_in=t_in, 
                tokens_out=t_out
            )
            
            logging.info(f"--- Executor: Step {step_num} completed. ---")
            
        except Exception as e:
            error_message = f"Execution failed at step {step_num} ({agent_name}): {e}"
            logging.error(f"--- Executor: FATAL ERROR --- {error_message}")
            trace.finalize(f"Failed at Step {step_num}")
            return None, trace

    # --- Finalization ---
    final_output = state.get(f"STEP_{len(plan)}_OUTPUT")
    trace.finalize("Success", final_output)
    logging.info("--- [Context Engine] Task Complete ---")
    return final_output, trace
