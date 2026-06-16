# 3.Helper Functions (LLM, Embeddings, and MCP)

# === Imports for this section ===
import logging
import json
import time
import tiktoken
import re
import copy
from tenacity import retry, stop_after_attempt, wait_random_exponential
from openai import APIError # Import specific error for better handling

# === Configure Production-Level Logging ===
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# === LLM Interaction (Hardened with Dependency Injection) ===
@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
def call_llm_robust(system_prompt, user_prompt, client, generation_model, json_mode=False):
    """
    A centralized function to handle all LLM interactions with retries.
    UPGRADE: Now requires the 'client' and 'generation_model' objects to be passed in.
    """
    logging.info("Attempting to call LLM...")
    try:
        response_format = {"type": "json_object"} if json_mode else {"type": "text"}
        # UPGRADE: Uses the passed-in client and model name for the API call.
        response = client.chat.completions.create(
            model=generation_model,
            response_format=response_format,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
        )
        logging.info("LLM call successful.")
        return response.choices[0].message.content.strip()
    except APIError as e:
        logging.error(f"OpenAI API Error in call_llm_robust: {e}")
        raise e
    except Exception as e:
        logging.error(f"An unexpected error occurred in call_llm_robust: {e}")
        raise e

# === Embeddings (Hardened with Dependency Injection) ===
@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
def get_embedding(text, client, embedding_model):
    """
    Generates embeddings for a single text query with retries.
    UPGRADE: Now requires the 'client' and 'embedding_model' objects.
    """
    text = text.replace("\n", " ")
    try:
        # UPGRADE: Uses the passed-in client and model name.
        response = client.embeddings.create(input=[text], model=embedding_model)
        return response.data[0].embedding
    except APIError as e:
        logging.error(f"OpenAI API Error in get_embedding: {e}")
        raise e
    except Exception as e:
        logging.error(f"An unexpected error occurred in get_embedding: {e}")
        raise e

# === Model Context Protocol (MCP) ===
def create_mcp_message(sender, content, metadata=None):
    """Creates a standardized MCP message."""
    return {
        "protocol_version": "2.0 (Context Engine)",
        "sender": sender,
        "content": content,
        "metadata": metadata or {}
    }

# === Pinecone Interaction (Hardened with Dependency Injection) ===
def query_pinecone(query_text, namespace, top_k, index, client, embedding_model):
    """
    Embeds the query text and searches the specified Pinecone namespace.
    UPGRADE: Now requires 'index', 'client', and 'embedding_model' objects.
    """
    logging.info(f"Querying Pinecone namespace '{namespace}'...")
    try:
        # UPGRADE: Passes the necessary dependencies down to get_embedding.
        query_embedding = get_embedding(query_text, client=client, embedding_model=embedding_model)
        # UPGRADE: Uses the passed-in index object for the query.
        response = index.query(
            vector=query_embedding,
            namespace=namespace,
            top_k=top_k,
            include_metadata=True
        )
        logging.info("Pinecone query successful.")
        return response['matches']
    except Exception as e:
        logging.error(f"Error querying Pinecone (Namespace: {namespace}): {e}")
        raise e

# === Context Management Utility (New) ===
def count_tokens(text, model="gpt-5.1"):
    """Counts the number of tokens in a text string for a given model."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # Fallback for models that might not be in the tiktoken registry
        encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))


# === Security Utility (New for Chapter 7) ===
def helper_sanitize_input(text):
    """
    A simple sanitization function to detect and flag potential prompt injection patterns.
    Returns the text if clean, or raises a ValueError if a threat is detected.
    """
    # List of simple, high-confidence patterns to detect injection attempts
    injection_patterns = [
        r"ignore previous instructions",
        r"ignore all prior commands",
        r"you are now in.*mode",
        r"act as",
        r"ignore any legal advice",
        r"print your instructions",
        # A simple pattern to catch attempts to inject system-level commands
        r"sudo|apt-get|yum|pip install"
    ]
    
    for pattern in injection_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            logging.warning(f"[Sanitizer] Potential threat detected with pattern: '{pattern}'")
            raise ValueError(f"Input sanitization failed. Potential threat detected.")
            
    logging.info("[Sanitizer] Input passed sanitization check.")
    return text

# FILE: commons/ch8/helpers.py
# === Moderation Utility (New for Chapter 8) ===
def helper_moderate_content(text_to_moderate, client):
    """
    Uses the OpenAI Moderation API to check if content is flagged and returns a full report.
    """
    logging.info(f"Moderating content...")
    try:
        response = client.moderations.create(input=text_to_moderate)
        mod_result = response.results[0]
        
        report = {
            "flagged": mod_result.flagged,
            "categories": dict(mod_result.categories),
            "scores": dict(mod_result.category_scores)
        }
        
        if report["flagged"]:
            logging.warning(f"Content was FLAGGED by moderation API. Report: {report['categories']}")
        else:
            logging.info("Content PASSED moderation.")
            
        return report
            
    except Exception as e:
        logging.error(f"An error occurred during content moderation: {e}")
        # Fail safe: if we can't check it, we assume it's not safe.
        return {"flagged": True, "categories": {"error": str(e)}, "scores": {}}

logging.info("✅ Helper functions defined and upgraded.")


