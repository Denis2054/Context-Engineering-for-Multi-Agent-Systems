# =============================================================================
# agents.py  —  Specialist Agent Functions
# commons/dag_engine/agents.py
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT CHANGED FROM commons/engine/agents.py:
#   ONE change only:
#     - `helper_sanitize_input` is no longer imported or called inside
#       `agent_researcher`. The Harness (harness.py Gate 1) sanitizes the
#       goal before any agent is ever invoked. Sanitizing again inside the
#       Researcher was redundant and created a second, inconsistent gate.
#
#   The sanitization of retrieved Pinecone chunks (lines 2 and 3 of the
#   Researcher's RAG pipeline) is KEPT — that is a different concern.
#   The harness sanitizes the USER'S GOAL. The Researcher still sanitizes
#   RETRIEVED CHUNKS before passing them to the LLM. Both are correct.
#
# WHAT DID NOT CHANGE:
#   - All four agent function signatures are identical.
#   - All four agent function bodies are identical except the one removal.
#   - Imports are identical except `helper_sanitize_input` is removed from
#     the top-level import (it is still used inside agent_researcher for
#     chunk sanitization — re-imported locally there for clarity).
# =============================================================================

# === Imports ===
import logging
import json
from helpers import query_pinecone, call_llm_robust, create_mcp_message


# =============================================================================
# 4.1  Context Librarian Agent
# =============================================================================

def agent_context_librarian(mcp_message, client, index, embedding_model, namespace_context):
    """Retrieves the appropriate Semantic Blueprint from the Context Library."""
    logging.info("[Librarian] Activated. Analyzing intent...")
    try:
        requested_intent = mcp_message['content'].get('intent_query')
        if not requested_intent:
            raise ValueError("Librarian requires 'intent_query' in the input content.")

        results = query_pinecone(
            query_text      = requested_intent,
            namespace       = namespace_context,
            top_k           = 1,
            index           = index,
            client          = client,
            embedding_model = embedding_model
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


# =============================================================================
# 4.2  Researcher Agent  (High-Fidelity RAG)
#
# CHANGE vs commons/engine/agents.py:
#   REMOVED — helper_sanitize_input() call on the USER GOAL.
#   The harness sanitizes the goal at Gate 1 before this agent runs.
#
#   KEPT   — helper_sanitize_input() on each RETRIEVED CHUNK.
#   Sanitizing retrieved data before passing it to the LLM is a separate,
#   correct defence against poisoned knowledge store content (e.g. the
#   NDA_Template_and_Testimony.txt injection test in the Legal dataset).
# =============================================================================

def agent_researcher(mcp_message, client, index, generation_model,
                     embedding_model, namespace_knowledge):
    """
    Retrieves and synthesizes factual information, providing source citations.
    Implements High-Fidelity RAG with chunk-level sanitization.
    """
    # Local import — kept here to make the continued use of chunk sanitization
    # explicit and visible, separate from the removed goal-level sanitization.
    from helpers import helper_sanitize_input

    logging.info("[Researcher] Activated. Investigating topic with high fidelity...")
    try:
        topic = mcp_message['content'].get('topic_query')
        if not topic:
            raise ValueError("Researcher requires 'topic_query' in the input content.")

        # 1. Retrieve chunks from vector DB
        results = query_pinecone(
            query_text      = topic,
            namespace       = namespace_knowledge,
            top_k           = 3,
            index           = index,
            client          = client,
            embedding_model = embedding_model
        )

        if not results:
            logging.warning("[Researcher] No relevant information found.")
            return create_mcp_message(
                "Researcher",
                {"answer": "No data found on the topic.", "sources": []}
            )

        # 2. Sanitize retrieved CHUNKS (not the goal — that was the harness's job)
        sanitized_texts = []
        sources         = set()
        for match in results:
            try:
                clean_text = helper_sanitize_input(match['metadata']['text'])
                sanitized_texts.append(clean_text)
                if 'source' in match['metadata']:
                    sources.add(match['metadata']['source'])
            except ValueError as e:
                logging.warning(
                    f"[Researcher] A retrieved chunk failed sanitization and "
                    f"was skipped. Reason: {e}"
                )
                continue

        if not sanitized_texts:
            logging.error("[Researcher] All retrieved chunks failed sanitization. Aborting.")
            return create_mcp_message(
                "Researcher",
                {
                    "answer" : "Could not generate a reliable answer — retrieved data was suspect.",
                    "sources": [],
                }
            )

        # 3. Synthesize with a citation-aware prompt
        logging.info(
            f"[Researcher] Found {len(sanitized_texts)} clean chunk(s). "
            f"Synthesizing with citations..."
        )

        system_prompt = (
            "You are an expert research synthesis AI. Your task is to provide a clear, "
            "factual answer to the user's topic based *only* on the provided source texts. "
            "After the answer, you MUST provide a 'Sources' section listing the unique "
            "source document names you used."
        )

        source_material = "\n\n---\n\n".join(sanitized_texts)
        user_prompt = (
            f"Topic: {topic}\n\n"
            f"Sources:\n{source_material}\n\n"
            f"---\nSynthesize your answer and list the source documents now."
        )

        findings = call_llm_robust(
            system_prompt,
            user_prompt,
            client           = client,
            generation_model = generation_model
        )

        final_output = (
            f"{findings}\n\n**Sources:**\n"
            + "\n".join([f"- {s}" for s in sorted(sources)])
        )

        return create_mcp_message("Researcher", {"answer_with_sources": final_output})

    except Exception as e:
        logging.error(f"[Researcher] An error occurred: {e}")
        raise e


# =============================================================================
# 4.3  Writer Agent
# =============================================================================

def agent_writer(mcp_message, client, generation_model):
    """Combines research with a blueprint to generate the final output."""
    logging.info("[Writer] Activated. Applying blueprint to source material...")
    try:
        blueprint_data   = mcp_message['content'].get('blueprint')
        facts_data       = mcp_message['content'].get('facts')
        previous_content = mcp_message['content'].get('previous_content')

        blueprint_json_string = (
            blueprint_data.get('blueprint_json')
            if isinstance(blueprint_data, dict)
            else blueprint_data
        )

        # Robust facts unpacking — handles all upstream agent output shapes
        facts = None
        if isinstance(facts_data, dict):
            facts = (
                facts_data.get('facts')
                or facts_data.get('summary')
                or facts_data.get('answer_with_sources')
            )
        elif isinstance(facts_data, str):
            facts = facts_data

        if not blueprint_json_string or (not facts and not previous_content):
            raise ValueError(
                "Writer requires a blueprint and either 'facts' or 'previous_content'."
            )

        if facts:
            source_material = facts
            source_label    = "SOURCE MATERIAL"
        else:
            source_material = previous_content
            source_label    = "PREVIOUS CONTENT (For Rewriting)"

        system_prompt = (
            "You are an expert content generation AI. Your task is to generate or rewrite "
            "content based on the provided SOURCE MATERIAL, strictly following the rules in "
            "the SEMANTIC BLUEPRINT. The SOURCE MATERIAL may contain both a synthesized "
            "answer and a list of sources; ensure the final output is a single, cohesive "
            "piece of content."
        )

        user_prompt = (
            f"--- SEMANTIC BLUEPRINT (JSON) ---\n{blueprint_json_string}\n\n"
            f"--- SOURCE MATERIAL ({source_label}) ---\n{source_material}\n\n"
            f"Generate the final content now."
        )

        final_output = call_llm_robust(
            system_prompt,
            user_prompt,
            client           = client,
            generation_model = generation_model
        )

        return create_mcp_message("Writer", final_output)

    except Exception as e:
        logging.error(f"[Writer] An error occurred: {e}")
        raise e


# =============================================================================
# 4.4  Summarizer Agent
# =============================================================================

def agent_summarizer(mcp_message, client, generation_model):
    """
    Reduces a large text to a concise summary based on an objective.
    Acts as a token gatekeeper between heavy Researcher output and the Writer.
    """
    logging.info("[Summarizer] Activated. Reducing context...")
    try:
        text_to_summarize = mcp_message['content'].get('text_to_summarize')
        summary_objective = mcp_message['content'].get('summary_objective')

        if not text_to_summarize or not summary_objective:
            raise ValueError(
                "Summarizer requires 'text_to_summarize' and "
                "'summary_objective' in the input content."
            )

        system_prompt = (
            "You are an expert summarization AI. Your task is to reduce the provided "
            "text to its essential points, guided by the user's specific objective. "
            "The summary must be concise, accurate, and directly address the stated goal."
        )

        user_prompt = (
            f"--- OBJECTIVE ---\n{summary_objective}\n\n"
            f"--- TEXT TO SUMMARIZE ---\n{text_to_summarize}\n"
            f"--- END TEXT ---\n\nGenerate the summary now."
        )

        summary = call_llm_robust(
            system_prompt,
            user_prompt,
            client           = client,
            generation_model = generation_model
        )

        return create_mcp_message("Summarizer", {"summary": summary})

    except Exception as e:
        logging.error(f"[Summarizer] An error occurred: {e}")
        raise e


logging.info("✅ Specialist Agents defined (DAG edition — harness owns goal sanitization).")
