# === Imports ===
import logging
import time
import json
import re
import copy
from helpers import call_llm_robust, create_mcp_message, count_tokens
from registry import AGENT_TOOLKIT

# === 6.1. The Tracer ===
class ExecutionTrace:
    """
    Logs the entire execution flow for debugging, performance analytics, and auditing.
    Tracks token consumption and savings per agent.
    """
    def __init__(self, goal):
        self.goal = goal
        self.plan = None
        self.steps = []
        self.status = "Initialized"
        self.final_output = None
        self.start_time = time.time()
        self.duration = 0
        logging.info(f"ExecutionTrace initialized for goal: '{self.goal}'")

    def log_plan(self, plan):
        self.plan = plan
        logging.info("Plan has been successfully logged to the trace.")

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
            # Calculate savings specifically for the Summarizer logic
            "tokens_saved": max(0, tokens_in - tokens_out) if agent == "Summarizer" else 0
        })
        logging.info(f"Step {step_num} ({agent}) logged. [T_IN: {tokens_in}, T_OUT: {tokens_out}]")

    def finalize(self, status, final_output=None):
        self.status = status
        self.final_output = final_output
        self.duration = round(time.time() - self.start_time, 2)
        logging.info(f"Trace finalized with status '{status}' in {self.duration}s")

# === 6.2. The Planner (The Brain) ===
def planner(goal, client, generation_model):
    """
    Generates a step-by-step agent execution plan using variable resolution syntax.
    Enforces strict key names for agent compatibility.
    """
    logging.info(f"Planner activated. Analyzing goal: {goal}")
    
    capabilities = AGENT_TOOLKIT.get_documentation()
    
    system_prompt = f"""You are the Orchestrator for a Multi-Agent Context Engine. 
Your task is to generate a JSON execution plan to achieve the user's goal.

AVAILABLE AGENTS & CAPABILITIES:
{capabilities}

CRITICAL RULES:
1. You MUST use the exact input keys specified (e.g., 'blueprint', 'facts', 'topic_query').
2. Use '$$STEP_N_OUTPUT$$' to reference the output of a previous step.
3. For a final eligibility audit, ensure Step 1 captures evidence and Step 2 captures rules/blueprints.
4. Output MUST be a JSON object with a 'plan' key.
"""
    
    user_prompt = f"Goal: {goal}\n\nGenerate the JSON execution plan now."
    
    plan_json = call_llm_robust(system_prompt, user_prompt, client, generation_model, json_mode=True)
    return json.loads(plan_json)["plan"]

# === 6.3. The Executor (The Engine) ===
def context_engine(goal, client, index, generation_model, embedding_model, namespace_context, namespace_knowledge):
    """
    The main entry point for the Context Engine. 
    Manages the state, resolves variable dependencies, and executes agents in sequence.
    """
    trace = ExecutionTrace(goal)
    
    try:
        # Step 1: Planning
        plan = planner(goal, client, generation_model)
        trace.log_plan(plan)
        
        state = {}
        
        # Step 2: Sequential Execution
        for step_num, step in enumerate(plan, 1):
            agent_name = step["agent"]
            planned_input = step["input"]
            
            logging.info(f"--- Executor: Starting Step {step_num} ({agent_name}) ---")
            
            # A. Variable Resolution Logic (Robust Regex)
            # This replaces $$STEP_N_OUTPUT$$ with real data from the state dictionary
            resolved_input = {}
            for key, val in planned_input.items():
                if isinstance(val, str) and "$$STEP_" in val:
                    match = re.search(r'\$\$STEP_(\d+)_OUTPUT\$\$', val)
                    if match:
                        ref_id = int(match.group(1))
                        resolved_input[key] = state.get(f"STEP_{ref_id}_OUTPUT")
                        logging.info(f"   [Resolver] Injected data from Step {ref_id} into key '{key}'")
                    else:
                        resolved_input[key] = val
                else:
                    resolved_input[key] = val

            # B. Performance Metrics: Count Input Tokens
            t_in = count_tokens(str(resolved_input))

            # C. Agent Execution
            handler = AGENT_TOOLKIT.get_handler(
                agent_name, client, index, generation_model, 
                embedding_model, namespace_context, namespace_knowledge
            )
            mcp_output = handler(create_mcp_message("Engine", resolved_input))
            output_data = mcp_output["content"]
            
            # D. Performance Metrics: Count Output Tokens
            t_out = count_tokens(str(output_data))
            
            # E. Update State and Trace
            state[f"STEP_{step_num}_OUTPUT"] = output_data
            trace.log_step(
                step_num, agent_name, planned_input, mcp_output, 
                resolved_input, tokens_in=t_in, tokens_out=t_out
            )
            
            logging.info(f"--- Executor: Step {step_num} completed. ---")
            
        # Finalization
        final_output = state.get(f"STEP_{len(plan)}_OUTPUT")
        trace.finalize("Success", final_output)
        return final_output, trace

    except Exception as e:
        error_msg = f"Context Engine failed during execution: {e}"
        logging.error(f"--- Executor: FATAL ERROR --- {error_msg}")
        trace.finalize("Failed", {"error": str(e)})
        return None, trace

logging.info("🚀 Context Engine (engine.py) fully upgraded and hardened.")
