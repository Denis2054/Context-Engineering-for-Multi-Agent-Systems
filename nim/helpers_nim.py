# =============================================================================
# helpers_nim.py  —  Transport, Retrieval, Guardrails, Accounting
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# Everything above this file — agents, registry, foreman, engine — is pure
# orchestration logic. This file is where that logic finally touches a network
# socket. Four outbound calls exist in the entire system and all four live here:
#
#   call_llm_robust()        POST {base_url}/chat/completions
#   get_embedding()          POST {base_url}/embeddings
#   query_pinecone()         Pinecone index.query()
#   helper_moderate_content() POST api.openai.com/v1/moderations
#
# WHY RAW HTTP INSTEAD OF THE SDK
# -------------------------------
# The OpenAI Python SDK is versioned against OpenAI's own API surface. Pointing
# it at a compatible third-party endpoint works until a minor release changes
# how a request is serialised, at which point a Colab runtime that silently
# upgraded a transitive dependency starts throwing import-time errors that have
# nothing to do with your code.
#
# `requests.post` to a documented JSON contract has no such coupling. The cost
# is that this file must handle retries and error mapping itself; the benefit is
# that the same three functions drive NVIDIA, OpenAI, and any other
# OpenAI-compatible endpoint — vLLM, Ollama, a self-hosted NIM container —
# with no branch beyond the base URL carried on the client object.
#
# The client objects are still `openai.OpenAI` instances. They are used purely
# as credential holders: this module reads `.base_url` and `.api_key` off them
# and never calls a method.
# =============================================================================

import copy
import json
import logging
import re
import time

from tenacity import retry, stop_after_attempt, wait_random_exponential, retry_if_exception_type

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")


# =============================================================================
# SECTION A — RETRY POLICY
#
# A single class of exception is retried, and only that class. Retrying a 400
# is pointless — the request is malformed and will stay malformed. Retrying a
# 401 is worse than pointless: it burns four attempts against a dead key.
#
# This matters more on NIM than on OpenAI. The free tier's ~40 RPM ceiling is
# low enough that four concurrent nodes can brush against it during a burst,
# and a 429 that is not retried takes down the whole DAG, discarding the work
# of every node that already succeeded.
# =============================================================================

class RetryableAPIError(Exception):
    """Raised for transient conditions worth another attempt: 429 and 5xx."""


class FatalAPIError(Exception):
    """Raised for conditions no amount of retrying will fix: 400, 401, 403, 404."""


def _classify_http(status_code: int, body: str) -> Exception:
    """Map an HTTP status onto the retry policy, with a message worth reading."""
    snippet = (body or "")[:400]

    if status_code == 429:
        return RetryableAPIError(f"HTTP 429 rate limited. {snippet}")
    if status_code >= 500:
        return RetryableAPIError(f"HTTP {status_code} upstream error. {snippet}")
    if status_code == 401:
        return FatalAPIError(f"HTTP 401 unauthorized — key invalid or expired. {snippet}")
    if status_code == 402:
        return FatalAPIError(f"HTTP 402 payment required — credits exhausted. {snippet}")
    if status_code == 404:
        return FatalAPIError(f"HTTP 404 model not found — check the model ID. {snippet}")
    return FatalAPIError(f"HTTP {status_code}. {snippet}")


def _client_endpoint(client, path: str):
    """
    Read base_url and api_key off a client object and build a full endpoint URL.

    The client is never invoked. This is the whole of the coupling between this
    module and the OpenAI SDK, and it is why the same code drives NIM, OpenAI,
    and any other compatible endpoint.
    """
    try:
        base_url = str(client.base_url).rstrip("/")
        api_key  = client.api_key
    except Exception as e:
        raise FatalAPIError(
            f"Could not read base_url/api_key from client object: {e}"
        )
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    return f"{base_url}{path}", headers


# =============================================================================
# SECTION B — REASONING-MODEL OUTPUT NORMALISATION
#
# Nemotron Nano Omni is a reasoning model, and reasoning models return text in
# shapes that a plain chat model does not:
#
#   - `content` empty, the answer in `reasoning_content`
#   - the answer wrapped in <think>...</think>
#   - JSON fenced inside a ```json block
#   - JSON preceded by a sentence of commentary
#
# None of those are errors. All of them break `json.loads()`. Normalising here
# means the planner, the agents, and the trace all see clean text, and it means
# the fix lives in one place rather than being rediscovered in four.
# =============================================================================

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_FENCE       = re.compile(r"^```(?:json|JSON)?\s*|\s*```$", re.MULTILINE)


def strip_reasoning(text: str) -> str:
    """Remove <think> blocks and stray code fences from a model response."""
    if not text:
        return ""
    return _FENCE.sub("", _THINK_BLOCK.sub("", text)).strip()


def extract_json(text: str):
    """
    Parse JSON from a model response that may not be pure JSON.

    Three attempts, cheapest first:
      1. parse the whole string
      2. parse it after stripping reasoning blocks and code fences
      3. slice from the first brace to the last matching one and parse that

    Args:
        text (str): raw model output.

    Returns:
        dict | list: the parsed object.

    Raises:
        json.JSONDecodeError: when no attempt yields valid JSON.
    """
    for candidate in (text, strip_reasoning(text)):
        if not candidate:
            continue
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            pass

    cleaned = strip_reasoning(text or "")
    for opener, closer in (("{", "}"), ("[", "]")):
        start = cleaned.find(opener)
        end   = cleaned.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(cleaned[start:end + 1])
            except json.JSONDecodeError:
                continue

    raise json.JSONDecodeError(
        "No parseable JSON in model output", cleaned or "", 0
    )


# =============================================================================
# SECTION C — LLM CALL
# =============================================================================

@retry(retry=retry_if_exception_type(RetryableAPIError),
       wait=wait_random_exponential(min=2, max=45),
       stop=stop_after_attempt(5),
       reraise=True)
def call_llm_robust(system_prompt, user_prompt, client, generation_model,
                    json_mode=False, temperature=0.2, max_tokens=None,
                    timeout=180):
    """
    The single chat-completion call in the system.

    Every LLM interaction — the planner's DAG, the Researcher's synthesis, the
    Summarizer's reduction, the Writer's draft — arrives here. That is the point
    of the design: one place to add retries, one place to normalise reasoning
    output, one place to swap providers.

    Args:
        system_prompt (str):    role and constraints.
        user_prompt (str):      the task.
        client:                 credential holder; base_url selects the provider.
        generation_model (str): model ID. Super for the planner, Nano for agents.
        json_mode (bool):       request a JSON object. Falls back gracefully on
                                endpoints that reject `response_format`.
        temperature (float):    0.2 by default. Low, because every call in this
                                engine is extraction or transformation, not
                                open-ended generation.
        max_tokens (int|None):  None lets the endpoint decide.
        timeout (int):          per-attempt socket timeout in seconds.

    Returns:
        str: response text, reasoning blocks removed.

    Raises:
        RetryableAPIError: after 5 failed attempts on 429/5xx.
        FatalAPIError:     immediately on 4xx that retrying cannot fix.
    """
    import requests as _req

    endpoint, headers = _client_endpoint(client, "/chat/completions")

    payload = {
        "model": generation_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    logging.info(f"[LLM] {generation_model} | json_mode={json_mode}")

    try:
        r = _req.post(endpoint, headers=headers, json=payload, timeout=timeout)
    except _req.exceptions.Timeout:
        raise RetryableAPIError(f"Request to {generation_model} timed out after {timeout}s.")
    except _req.exceptions.ConnectionError as e:
        raise RetryableAPIError(f"Connection error contacting {generation_model}: {e}")

    # Not every OpenAI-compatible endpoint implements `response_format`. When
    # one rejects it, drop the parameter and retry once — the prompt already
    # demands JSON, and extract_json() will cope with whatever shape comes back.
    if r.status_code == 400 and json_mode:
        logging.warning("[LLM] Endpoint rejected response_format; retrying without it.")
        payload.pop("response_format", None)
        try:
            r = _req.post(endpoint, headers=headers, json=payload, timeout=timeout)
        except _req.exceptions.RequestException as e:
            raise RetryableAPIError(f"Retry without response_format failed: {e}")

    if r.status_code != 200:
        raise _classify_http(r.status_code, r.text)

    data = r.json()
    message = data["choices"][0]["message"]

    content = (message.get("content") or "").strip()
    if not content:
        # Reasoning models put the answer here when `content` comes back empty.
        content = (message.get("reasoning_content") or "").strip()

    if not content:
        raise RetryableAPIError(
            f"{generation_model} returned an empty response. "
            f"finish_reason={data['choices'][0].get('finish_reason')}"
        )

    return strip_reasoning(content)


# =============================================================================
# SECTION D — EMBEDDINGS
#
# The payload differs by provider, and the difference is not cosmetic.
#
# OpenAI accepts {model, input} and rejects unknown keys with HTTP 400.
# NVIDIA's retrieval embedders are asymmetric — they encode a question and a
# document differently — and require `input_type` to say which is which.
# Sending `input_type` to OpenAI is a 400; omitting it on NVIDIA is a 400.
#
# Hence the branch below. It keys off the model name, so callers never have to
# know which provider they are on.
# =============================================================================

@retry(retry=retry_if_exception_type(RetryableAPIError),
       wait=wait_random_exponential(min=2, max=30),
       stop=stop_after_attempt(4),
       reraise=True)
def get_embedding(text, client, embedding_model, input_type="query"):
    """
    Embed a single string.

    Args:
        text (str):             text to embed.
        client:                 credential holder. MUST belong to the same
                                provider that built the index being queried.
        embedding_model (str):  model ID; also selects the payload shape.
        input_type (str):       "query" or "passage". NVIDIA only. Retrieval at
                                run time is always "query"; ingestion used
                                "passage".

    Returns:
        list[float]: the embedding vector.
    """
    import requests as _req

    text = (text or "").replace("\n", " ")
    endpoint, headers = _client_endpoint(client, "/embeddings")

    payload = {"model": embedding_model, "input": [text]}

    # NVIDIA retrieval embedders need to be told which side of the pair this is.
    if embedding_model.lower().startswith("nvidia/"):
        payload["input_type"] = input_type
        payload["truncate"]   = "END"

    try:
        r = _req.post(endpoint, headers=headers, json=payload, timeout=45)
    except _req.exceptions.Timeout:
        raise RetryableAPIError("Embedding request timed out after 45s.")
    except _req.exceptions.ConnectionError as e:
        raise RetryableAPIError(f"Connection error during embedding: {e}")

    if r.status_code != 200:
        err = _classify_http(r.status_code, r.text)
        # The most common misconfiguration in this notebook, named explicitly.
        if r.status_code == 400 and "input_type" in (r.text or ""):
            raise FatalAPIError(
                f"Embedding endpoint rejected the payload for '{embedding_model}'. "
                f"This usually means the embedding client and the embedding model "
                f"belong to different providers — an OpenAI client cannot serve an "
                f"nvidia/* model, and vice versa. Original: {r.text[:200]}"
            )
        raise err

    return r.json()["data"][0]["embedding"]


# =============================================================================
# SECTION E — MODEL CONTEXT PROTOCOL ENVELOPE
#
# Every agent receives and returns the same envelope. It is a small thing, but
# it is what lets the Foreman treat all six registry entries identically: it
# never has to know whether it is calling the Librarian or the Writer, only
# that the thing it called returns {sender, content, metadata}.
# =============================================================================

def create_mcp_message(sender, content, metadata=None):
    """
    Wrap a payload in the engine's standard inter-agent envelope.

    Args:
        sender (str):     originating component, e.g. "Engine" or "Researcher".
        content:          the payload — dict for structured agents, str for
                          the Writer's prose.
        metadata (dict):  optional provenance.

    Returns:
        dict: {protocol_version, sender, content, metadata}
    """
    return {
        "protocol_version": "2.0 (Context Engine)",
        "sender"          : sender,
        "content"         : content,
        "metadata"        : metadata or {},
    }


# =============================================================================
# SECTION F — VECTOR RETRIEVAL
# =============================================================================

def query_pinecone(query_text, namespace, top_k, index, client, embedding_model):
    """
    Embed a query and search one Pinecone namespace.

    Args:
        query_text (str):      natural-language query.
        namespace (str):       physical namespace — "ContextLibrary" for
                               blueprints, "KnowledgeStore" for documents.
        top_k (int):           matches to return. 1 for blueprints (there is
                               one right answer), 3 for knowledge (synthesis
                               wants corroboration).
        index:                 Pinecone Index handle.
        client:                embedding credential holder.
        embedding_model (str): must match the model the index was built with.

    Returns:
        list: Pinecone match objects, each carrying id, score, and metadata.
    """
    logging.info(f"[Pinecone] querying namespace '{namespace}' (top_k={top_k})")
    try:
        vector = get_embedding(query_text, client=client,
                               embedding_model=embedding_model,
                               input_type="query")
        response = index.query(
            vector          = vector,
            namespace       = namespace,
            top_k           = top_k,
            include_metadata= True,
        )
        matches = response["matches"]
        logging.info(f"[Pinecone] {len(matches)} match(es) returned.")
        return matches
    except Exception as e:
        logging.error(f"[Pinecone] query failed on namespace '{namespace}': {e}")
        raise


# =============================================================================
# SECTION G — TOKEN ACCOUNTING
#
# An honest caveat: tiktoken implements OpenAI's BPE vocabularies. Nemotron uses
# a different tokenizer, so these numbers are an estimate, not a bill.
#
# They are still the right thing to record. The trace uses token counts to show
# the Summarizer earning its place in the DAG — a node that consumes 4,000
# tokens and emits 400 has removed 3,600 tokens from every downstream prompt.
# That ratio is what matters, and it survives a change of tokenizer.
# =============================================================================

def count_tokens(text, model="gpt-4o"):
    """
    Estimate the token count of a string.

    Args:
        text (str):   text to measure.
        model (str):  vocabulary hint. Unknown models fall back to cl100k_base.

    Returns:
        int: estimated tokens. Never raises — accounting must not break a run.
    """
    try:
        import tiktoken
        try:
            encoding = tiktoken.encoding_for_model(model)
        except Exception:
            encoding = tiktoken.get_encoding("cl100k_base")
        return len(encoding.encode(str(text)))
    except Exception:
        # Last-resort heuristic: English averages ~4 characters per token.
        return max(1, len(str(text)) // 4)


# =============================================================================
# SECTION H — INPUT SANITISATION
#
# A regular-expression screen for prompt-injection phrasing. It runs in two
# distinct places, and the distinction is the interesting part:
#
#   1. Harness Gate 1, on the user's goal, before any model is called.
#   2. Inside agent_researcher, on every chunk retrieved from Pinecone,
#      before those chunks are pasted into a prompt.
#
# The second is the one people forget. Your vector store is an untrusted input
# channel: a document ingested six months ago can carry an instruction that
# only detonates when a retrieval happens to surface it. Screening the goal and
# not the retrieved text defends the front door and leaves the loading bay open.
#
# ON PRECISION
# ------------
# These patterns are deliberately blunt and they over-trigger. "act as" will
# match a contract clause reading "this schedule shall act as an addendum",
# and that chunk gets dropped. That is the correct default for a teaching
# system — a visible false positive is a lesson, a missed injection is not —
# but it is a real trade-off, and in production you would tighten these
# patterns and log every rejection for review rather than dropping silently.
#
# The list is a module-level constant so you can edit it without touching the
# function.
# =============================================================================

INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"ignore all prior commands",
    r"ignore all instructions",
    r"disregard (the )?(above|previous|prior)",
    r"you are now in.*mode",
    r"act as",
    r"ignore any legal advice",
    r"print your (system )?(prompt|instructions)",
    r"reveal your (system )?(prompt|instructions)",
    r"sudo|apt-get|yum|pip install",
]


def helper_sanitize_input(text):
    """
    Screen text for prompt-injection phrasing.

    Args:
        text (str): goal text, or a chunk retrieved from the vector store.

    Returns:
        str: the text unchanged, when it passes.

    Raises:
        ValueError: when a pattern matches. Callers decide what that means —
                    Gate 1 vetoes the whole run; the Researcher drops the one
                    chunk and continues with the rest.
    """
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text or "", re.IGNORECASE):
            logging.warning(f"[Sanitizer] pattern matched: '{pattern}'")
            raise ValueError(
                f"Input sanitization failed — matched pattern: '{pattern}'"
            )
    logging.info("[Sanitizer] passed.")
    return text


# =============================================================================
# SECTION I — CONTENT MODERATION
#
# The one call in the engine that has no NVIDIA equivalent. NIM publishes no
# moderation endpoint, so Gate 1's moderation sub-check reaches out to
# api.openai.com even on a run where every generated token came from NIM.
#
# FAIL-OPEN, DELIBERATELY
# -----------------------
# Infrastructure failures return "not flagged" rather than vetoing. A network
# blip should not silently reject every goal a user submits — that is an outage
# disguised as a policy decision, and it is very hard to diagnose from the
# outside.
#
# The exposure this creates is bounded: sanitisation and the business-rules
# check at Gate 1 do not depend on the network, and both still run. In a
# regulated deployment you would invert this — fail closed, alert, and require
# an operator to clear the block. That is a policy choice, and it belongs in
# the open, which is why it is a paragraph here rather than a bare
# `except: pass`.
# =============================================================================

def helper_moderate_content(text_to_moderate, client):
    """
    Screen text against the OpenAI moderation endpoint.

    Args:
        text_to_moderate (str): text to screen.
        client:                 OpenAI client. May be None.

    Returns:
        dict: {flagged: bool, categories: dict, scores: dict, available: bool}

              `available` is False whenever the verdict is a fail-open default
              rather than a real answer, so callers and the audit trail can
              tell "clean" apart from "unchecked".
    """
    import os as _os
    import requests as _req

    unavailable = {"flagged": False, "categories": {}, "scores": {}, "available": False}

    if client is None:
        logging.warning("[Moderation] no OpenAI client configured — skipping.")
        return unavailable

    api_key = _os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        try:
            api_key = client.api_key
        except Exception:
            api_key = ""
    if not api_key:
        logging.warning("[Moderation] no API key available — skipping.")
        return unavailable

    try:
        r = _req.post(
            "https://api.openai.com/v1/moderations",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type" : "application/json"},
            json={"input": text_to_moderate},
            timeout=20,
        )
        if r.status_code == 200:
            result = r.json()["results"][0]
            report = {
                "flagged"   : result["flagged"],
                "categories": result["categories"],
                "scores"    : result["category_scores"],
                "available" : True,
            }
            if report["flagged"]:
                hits = [c for c, v in report["categories"].items() if v]
                logging.warning(f"[Moderation] FLAGGED: {hits}")
            else:
                logging.info("[Moderation] passed.")
            return report

        logging.warning(f"[Moderation] HTTP {r.status_code} — failing open.")
        return unavailable

    except Exception as e:
        logging.warning(f"[Moderation] {type(e).__name__}: {e} — failing open.")
        return unavailable


logging.info("Helper functions loaded (NIM edition, raw HTTP transport).")
