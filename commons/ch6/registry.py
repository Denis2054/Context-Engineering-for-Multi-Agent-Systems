# FILE: commons/registry.py Updating the whole file

# === Imports ===
import logging
import agents
from helpers import create_mcp_message # This might be needed depending on your final structure

# === 5. The Agent Registry (Final Hardened Version) ===
class AgentRegistry:
    def __init__(self):
        self.registry = {
            # ADD the "agents." prefix to each function name
            "Librarian": agents.agent_context_librarian,
            "Researcher": agents.agent_researcher,
            "Writer": agents.agent_writer,
            # --- NEW: Add the Summarizer Agent ---
            "Summarizer": agents.agent_summarizer,
        }

    def get_handler(self, agent_name, client, index, generation_model, embedding_model, namespace_context, namespace_knowledge):
        handler_func = self.registry.get(agent_name)
        if not handler_func:
            logging.error(f"Agent '{agent_name}' not found in registry.")
            raise ValueError(f"Agent '{agent_name}' not found in registry.")

        # --- UPDATED: Add a condition for the Summarizer ---
        if agent_name == "Librarian":
            return lambda mcp_message: handler_func(mcp_message, client=client, index=index, embedding_model=embedding_model, namespace_context=namespace_context)
        elif agent_name == "Researcher":
            return lambda mcp_message: handler_func(mcp_message, client=client, index=index, generation_model=generation_model, embedding_model=embedding_model, namespace_knowledge=namespace_knowledge)
        elif agent_name == "Writer":
            return lambda mcp_message: handler_func(mcp_message, client=client, generation_model=generation_model)
        elif agent_name == "Summarizer":
            return lambda mcp_message: handler_func(mcp_message, client=client, generation_model=generation_model)
        else:
            return handler_func

    def get_capabilities_description(self):
        """Returns a structured description of the agents for the Planner LLM."""
        # --- UPDATED: Add the Summarizer's capabilities ---
        return """
Available Agents and their required inputs.
CRITICAL: You MUST use the exact input key names provided for each agent.

1. AGENT: Librarian
   ROLE: Retrieves Semantic Blueprints (style/structure instructions).
   INPUTS:
     - "intent_query": (String) A descriptive phrase of the desired style.
   OUTPUT: The blueprint structure (JSON string).

2. AGENT: Researcher
   ROLE: Retrieves and synthesizes factual information on a topic.
   INPUTS:
     - "topic_query": (String) The subject matter to research.
   OUTPUT: Synthesized facts (String).

3. AGENT: Summarizer
   ROLE: Reduces large text to a concise summary based on a specific objective. Ideal for managing token counts before a generation step.
   INPUTS:
     - "text_to_summarize": (String/Reference) The long text to be summarized.
     - "summary_objective": (String) A clear goal for the summary (e.g., "Extract key technical specifications").
   OUTPUT: A dictionary containing the summary: {"summary": "..."}.

4. AGENT: Writer
   ROLE: Generates or rewrites content by applying a Blueprint to source material.
   INPUTS:
     - "blueprint": (String/Reference) The style instructions (usually from Librarian).
     - "facts": (String/Reference) Factual information (usually from Researcher or Summarizer).
     - "previous_content": (String/Reference) Existing text for rewriting.
   OUTPUT: The final generated text (String).
"""

# Initialize the global toolkit.
AGENT_TOOLKIT = AgentRegistry()
logging.info("Agent Registry initialized and fully upgraded.")
