#6.The Context Engine (Fully Upgraded with Full Dependency Injection)
# -------------------------------------------------------------------------
# We now complete the upgrade of the engine's core components.
# This includes the Planner's JSON output structure and passing
# all configuration variables (model names, namespaces) down the execution chain.
# -------------------------------------------------------------------------
import logging 
# === 6.1. The Tracer (Upgraded with Logging) ===
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

    def log_step(self, step_num, agent, planned_input, mcp_output, resolved_input):
        """Logs the details of a single execution step."""
        self.steps.append({
            "step": step_num,
            "agent": agent,
            "planned_input": planned_input,
            "resolved_context": resolved_input,
            "output": mcp_output['content']
        })
        logging.info(f"Step {step_num} ({agent}) logged to the trace.")

    def finalize(self, status, final_output=None):
        self.status = status
        self.final_output = final_output
        self.duration = time.time() - self.start_time
        logging.info(f"Trace finalized with status '{status}'. Duration: {self.duration:.2f}s")

# === 6.2. The Planner (Hardened with Structured JSON Output) ===
# *** Planner Logic for JSON Mode ***
def planner(goal, capabilities, client, generation_model):
    """
    Analyzes the goal and generates a structured Execution Plan using the LLM.
    UPGRADE: Explicitly defines the JSON structure for robustness in json_mode.
    """
    logging.info("Planner activated. Analyzing goal and generating execution plan...")

    # Updated System Prompt to ensure compatibility with json_mode=True
    # We explicitly request a JSON object containing the key "plan".
    system_prompt = f"""
    You are the strategic core of the Context Engine. Analyze the user's high-level goal and create a structured Execution Plan using the available agents.

    --- AVAILABLE CAPABILITIES ---
    {capabilities}
    --- END CAPABILITIES ---

    INSTRUCTIONS:
    1. The output MUST be a single JSON object.
    2. This JSON object must contain a key named "plan".
    3. The value of the "plan" key MUST be a list of objects, where each object is a "step".
    4. Be strategic. Break down complex goals into distinct steps.
    5. You MUST use Context Chaining. If a step requires input from a previous step, reference it using the syntax $$STEP_X_OUTPUT$$.

    EXAMPLE OUTPUT FORMAT:
    {{
      "plan": [
        {{"step": 1, "agent": "AgentName1", "input": {{"param1": "value1"}}}},
        {{"step": 2, "agent": "AgentName2", "input": {{"param2": "$$STEP_1_OUTPUT$$"}}}}
      ]
    }}
    """

    try:
        plan_json_string = call_llm_robust(
            system_prompt,
            goal,
            client=client,
            generation_model=generation_model,
            json_mode=True
        )

        # Simplified and robust parsing logic (no regex needed when json_mode=True)
        try:
            plan_data = json.loads(plan_json_string)
        except json.JSONDecodeError as e:
            logging.error(f"Planner failed to parse JSON despite json_mode. Raw String: {plan_json_string}")
            raise ValueError(f"Invalid JSON returned by Planner: {e}")

        # Handle the primary expected case: {"plan": [...]}
        if isinstance(plan_data, dict) and "plan" in plan_data and isinstance(plan_data["plan"], list):
            plan = plan_data["plan"]

        # Handle edge cases
        elif isinstance(plan_data, list):
            logging.warning("Planner returned a raw list instead of the requested JSON object.")
            plan = plan_data
        elif isinstance(plan_data, dict) and "step" in plan_data:
            logging.warning("Planner received a single JSON step object; wrapping it in a list.")
            plan = [plan_data]
        else:
            # Addresses the original "The extracted JSON is not a list structure" error.
            logging.error(f"Planner returned an unexpected JSON structure. Response: {plan_json_string}")
            raise ValueError("The extracted JSON does not conform to the expected structure (must be an object containing a 'plan' list).")

        if not plan:
             raise ValueError("The generated plan is empty.")

        logging.info("Planner generated plan successfully.")
        return plan

    except Exception as e:
        logging.error(f"Planner failed to generate a valid plan. Error: {e}")
        raise e

# === 6.3. The Executor (Fully Upgraded) ===
def resolve_dependencies(input_params, state):
    """Helper function to replace $$REF$$ placeholders with data from the execution state."""
    resolved_input = copy.deepcopy(input_params)

    def resolve(value):
        if isinstance(value, str) and value.startswith("$$") and value.endswith("$$"):
            ref_key = value[2:-2]
            if ref_key in state:
                logging.info(f"Executor resolved dependency '{ref_key}'.")
                return state[ref_key]
            else:
                raise ValueError(f"Dependency Error: Reference {ref_key} not found in execution state.")
        elif isinstance(value, dict):
            return {k: resolve(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [resolve(v) for v in value]
        return value

    return resolve(resolved_input)

# *** Updated signature to include namespace_context and namespace_knowledge ***
def context_engine(goal, client, pc, index_name, generation_model, embedding_model, namespace_context, namespace_knowledge):
    """
    The main entry point for the Context Engine. Manages Planning and Execution.
    """
    logging.info(f"--- [Context Engine] Starting New Task --- Goal: {goal}")
    trace = ExecutionTrace(goal)
    registry = AGENT_TOOLKIT

    # Added robustness: Handle Pinecone index connection safely
    try:
        index = pc.Index(index_name)
    except Exception as e:
        logging.error(f"Failed to connect to Pinecone index '{index_name}': {e}")
        trace.finalize("Failed during Initialization (Pinecone Connection)")
        return None, trace


    # --- Phase 1: Plan ---
    try:
        capabilities = registry.get_capabilities_description()
        plan = planner(goal, capabilities, client=client, generation_model=generation_model)
        trace.log_plan(plan)
    except Exception as e:
        # The error logging is already handled within the planner, but we finalize the trace here.
        trace.finalize("Failed during Planning")
        return None, trace

    # --- Phase 2: Execute ---
    state = {}
    for step in plan:
        step_num = step.get("step")
        agent_name = step.get("agent")
        planned_input = step.get("input")

        # Added robustness: Validate step structure
        if not step_num or not agent_name or planned_input is None:
            error_message = f"Invalid step structure in plan: {step}"
            logging.error(f"--- Executor: FATAL ERROR --- {error_message}")
            trace.finalize("Failed during Execution (Invalid Plan Structure)")
            return None, trace

        logging.info(f"--- Executor: Starting Step {step_num}: {agent_name} ---")

        try:
            # *** Pass the namespaces when retrieving the handler ***
            handler = registry.get_handler(
                agent_name,
                client=client,
                index=index,
                generation_model=generation_model,
                embedding_model=embedding_model,
                namespace_context=namespace_context,
                namespace_knowledge=namespace_knowledge
            )

            resolved_input = resolve_dependencies(planned_input, state)
            mcp_resolved_input = create_mcp_message("Engine", resolved_input)

            mcp_output = handler(mcp_resolved_input)

            output_data = mcp_output["content"]
            state[f"STEP_{step_num}_OUTPUT"] = output_data
            trace.log_step(step_num, agent_name, planned_input, mcp_output, resolved_input)
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
