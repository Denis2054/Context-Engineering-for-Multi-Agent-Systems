# === Imports ===
import logging
import json
from helpers import query_pinecone, call_llm_robust, create_mcp_message

# === 4.1. Context Librarian Agent (Upgraded) ===
def agent_context_librarian(mcp_message, client, index, embedding_model, namespace_context):
    """Retrieves the appropriate Semantic Blueprint from the Context Library."""
    logging.info("[Librarian] Activated. Analyzing intent...")
    try:
        requested_intent = mcp_message['content'].get('intent_query')
        if not requested_intent:
            raise ValueError("Librarian requires 'intent_query' in the input content.")

        results = query_pinecone(
            query_text=requested_intent,
            namespace=namespace_context,
            top_k=1,
            index=index,
            client=client,
            embedding_model=embedding_model
        )

        if results:
            match = results[0]
            logging.info(f"[Librarian] Found blueprint '{match['id']}' (Score: {match['score']:.2f})")
            blueprint_json = match['metadata']['blueprint_json']
            content = {"blueprint_json": blueprint_json}
        else:
            logging.warning("[Librarian] No specific blueprint found. Returning default.")
            content = {"blueprint_json": json.dumps({"instruction": "Generate the content neutrally."})}

        return create_mcp_message("Librarian", content)
    except Exception as e:
        logging.error(f"[Librarian] An error occurred: {e}")
        raise e

# === 4.2. Researcher Agent (UPGRADED for High-Fidelity RAG) ===
from helpers import helper_sanitize_input # Add this new import at the top of the file

def agent_researcher(mcp_message, client, index, generation_model, embedding_model, namespace_knowledge):
    """
    Retrieves and synthesizes factual information, providing source citations.
    UPGRADE: Implements High-Fidelity RAG and input sanitization.
    """
    logging.info("[Researcher] Activated. Investigating topic with high fidelity...")
    try:
        topic = mcp_message['content'].get('topic_query')
        if not topic:
            raise ValueError("Researcher requires 'topic_query' in the input content.")

        # 1. Retrieve Chunks from Vector DB
        results = query_pinecone(
            query_text=topic,
            namespace=namespace_knowledge,
            top_k=3,
            index=index,
            client=client,
            embedding_model=embedding_model
        )

        if not results:
            logging.warning("[Researcher] No relevant information found.")
            return create_mcp_message("Researcher", {"answer": "No data found on the topic.", "sources": []})

        # 2. Sanitize and Prepare Source Texts
        sanitized_texts = []
        sources = set() # Use a set to store unique source documents
        for match in results:
            try:
                # Sanitize text before use
                clean_text = helper_sanitize_input(match['metadata']['text'])
                sanitized_texts.append(clean_text)
                # Collect the source document name
                if 'source' in match['metadata']:
                    sources.add(match['metadata']['source'])
            except ValueError as e:
                logging.warning(f"[Researcher] A retrieved chunk failed sanitization and was skipped. Reason: {e}")
                continue # Skip this tainted chunk
        
        if not sanitized_texts:
            logging.error("[Researcher] All retrieved chunks failed sanitization. Aborting.")
            return create_mcp_message("Researcher", {"answer": "Could not generate a reliable answer as retrieved data was suspect.", "sources": []})

        # 3. Synthesize with a Citation-Aware Prompt
        logging.info(f"[Researcher] Found {len(sanitized_texts)} relevant chunks. Synthesizing answer with citations...")
        
        system_prompt = """You are an expert research synthesis AI. Your task is to provide a clear, factual answer to the user's topic based *only* on the provided source texts. After the answer, you MUST provide a "Sources" section listing the unique source document names you used."""
        
        source_material = "\n\n---\n\n".join(sanitized_texts)
        user_prompt = f"Topic: {topic}\n\nSources:\n{source_material}\n\n--- \nSynthesize your answer and list the source documents now."

        findings = call_llm_robust(
            system_prompt,
            user_prompt,
            client=client,
            generation_model=generation_model
        )
        
        # We can also append the sources we found programmatically for robustness
        final_output = f"{findings}\n\n**Sources:**\n" + "\n".join([f"- {s}" for s in sorted(list(sources))])

        return create_mcp_message("Researcher", {"answer_with_sources": final_output})

    except Exception as e:
        logging.error(f"[Researcher] An error occurred: {e}")
        raise e

# FILE: commons/ch6/agents.py (UPGRADED agent_writer)

def agent_writer(mcp_message, client, generation_model):
    """Combines research with a blueprint to generate the final output."""
    logging.info("[Writer] Activated. Applying blueprint to source material...")
    try:
        # --- FINAL UPGRADE: Unpack structured inputs from any source agent ---
        blueprint_data = mcp_message['content'].get('blueprint')
        facts_data = mcp_message['content'].get('facts')
        previous_content = mcp_message['content'].get('previous_content')

        blueprint_json_string = blueprint_data.get('blueprint_json') if isinstance(blueprint_data, dict) else blueprint_data

        # FINAL ROBUST LOGIC for handling multiple data contracts
        facts = None
        if isinstance(facts_data, dict):
            # Check for 'facts' (from original Researcher)
            facts = facts_data.get('facts')
            # Check for 'summary' (from Summarizer)
            if facts is None:
                facts = facts_data.get('summary')
            # Check for 'answer_with_sources' (from Hi-Fi Researcher)
            if facts is None:
                facts = facts_data.get('answer_with_sources')
        elif isinstance(facts_data, str):
            facts = facts_data

        if not blueprint_json_string or (not facts and not previous_content):
            raise ValueError("Writer requires a blueprint and either 'facts' or 'previous_content'.")

        # ... (The rest of the agent function remains the same) ...
        
        if facts:
            source_material = facts
            source_label = "SOURCE MATERIAL"
        else:
            source_material = previous_content
            source_label = "PREVIOUS CONTENT (For Rewriting)"

        system_prompt = f"""You are an expert content generation AI. Your task is to generate or rewrite content based on the provided SOURCE MATERIAL, strictly following the rules in the SEMANTIC BLUEPRINT. The SOURCE MATERIAL may contain both a synthesized answer and a list of sources; ensure the final output is a single, cohesive piece of content."""
        
        user_prompt = f"""--- SEMANTIC BLUEPRINT (JSON) ---\n{blueprint_json_string}\n\n--- SOURCE MATERIAL ({source_label}) ---\n{source_material}\n\nGenerate the final content now."""

        final_output = call_llm_robust(
            system_prompt,
            user_prompt,
            client=client,
            generation_model=generation_model
        )
        return create_mcp_message("Writer", final_output)
        
    except Exception as e:
        logging.error(f"[Writer] An error occurred: {e}")
        raise e

logging.info("✅ Specialist Agents defined and fully upgraded.")

# FILE: Chapter 6
# === 4.4. Summarizer Agent (New for Context Reduction) ===
def agent_summarizer(mcp_message, client, generation_model):
    """
    Reduces a large text to a concise summary based on an objective.
    Acts as a gatekeeper to manage token counts and costs.
    """
    logging.info("[Summarizer] Activated. Reducing context...")
    try:
        # Unpack the inputs from the MCP message
        text_to_summarize = mcp_message['content'].get('text_to_summarize')
        summary_objective = mcp_message['content'].get('summary_objective')

        if not text_to_summarize or not summary_objective:
            raise ValueError("Summarizer requires 'text_to_summarize' and 'summary_objective' in the input content.")

        # Define the prompts for the LLM
        system_prompt = """You are an expert summarization AI. Your task is to reduce the provided text to its essential points, guided by the user's specific objective. The summary must be concise, accurate, and directly address the stated goal."""
        user_prompt = f"""--- OBJECTIVE ---
{summary_objective}

--- TEXT TO SUMMARIZE ---
{text_to_summarize}
--- END TEXT ---

Generate the summary now."""

        # Call the hardened LLM helper to perform the summarization
        summary = call_llm_robust(
            system_prompt,
            user_prompt,
            client=client,
            generation_model=generation_model
        )

        # Return the summary in the standard MCP format
        return create_mcp_message("Summarizer", {"summary": summary})
    except Exception as e:
        logging.error(f"[Summarizer] An error occurred: {e}")
        raise e
