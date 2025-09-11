#5.The Agent Registry (Final Hardened Version)
# -------------------------------------------------------------------------
# We now make one final, crucial upgrade to the AgentRegistry.
# We must ensure all dependencies, including namespaces, are passed through.
# -------------------------------------------------------------------------
import logging 
import agents 
class AgentRegistry:
    def __init__(self):
        self.registry = {
            "Librarian": agent_context_librarian,
            "Researcher": agent_researcher,
            "Writer": agent_writer,
        }

    # *** Updated signature to include namespace_context and namespace_knowledge ***
    def get_handler(self, agent_name, client, index, generation_model, embedding_model, namespace_context, namespace_knowledge):
        handler_func = self.registry.get(agent_name)
        if not handler_func:
            logging.error(f"Agent '{agent_name}' not found in registry.")
            raise ValueError(f"Agent '{agent_name}' not found in registry.")

        if agent_name == "Librarian":
            # *** Inject the context namespace into the Librarian handler ***
            return lambda mcp_message: handler_func(mcp_message, client=client, index=index, embedding_model=embedding_model, namespace_context=namespace_context)
        elif agent_name == "Researcher":
            # *** Inject the knowledge namespace into the Researcher handler ***
            return lambda mcp_message: handler_func(mcp_message, client=client, index=index, generation_model=generation_model, embedding_model=embedding_model, namespace_knowledge=namespace_knowledge)
        elif agent_name == "Writer":
            return lambda mcp_message: handler_func(mcp_message, client=client, generation_model=generation_model)
        else:
            return handler_func


    def get_capabilities_description(self):
        """
        Returns a structured description of the agents for the Planner LLM.
        UPGRADE: Now includes an explicit instruction to use exact key names.
        """
        return """
        Available Agents and their required inputs.
        CRITICAL: You MUST use the exact input key names provided for each agent.

        1. AGENT: Librarian
           ROLE: Retrieves Semantic Blueprints (style/structure instructions).
           INPUTS:
             - "intent_query": (String) A descriptive phrase of the desired style or format.
           OUTPUT: The blueprint structure (JSON string).

        2. AGENT: Researcher
           ROLE: Retrieves and synthesizes factual information on a topic.
           INPUTS:
             - "topic_query": (String) The subject matter to research.
           OUTPUT: Synthesized facts (String).

        3. AGENT: Writer
           ROLE: Generates or rewrites content by applying a Blueprint to source material.
           INPUTS:
             - "blueprint": (String/Reference) The style instructions (usually from Librarian).
             - "facts": (String/Reference) Factual information (usually from Researcher).
             - "previous_content": (String/Reference) Existing text for rewriting.
           OUTPUT: The final generated text (String).
        """

# Initialize the global toolkit.
AGENT_TOOLKIT = AgentRegistry()
logging.info("✅ Agent Registry initialized and fully upgraded.")
