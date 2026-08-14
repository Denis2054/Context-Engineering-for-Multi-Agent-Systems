# lc_helpers.py
# =============================================================================
# Universal Context Engine — LangChain Edition
# The primitives: model, embeddings, vector stores, retrievers, guardrails,
# and token accounting.
#
# Replaces: helpers.py
#
#   call_llm_robust()        -> ChatOpenAI(...).with_retry()
#   get_embedding()          -> OpenAIEmbeddings(...)
#   query_pinecone()         -> PineconeVectorStore(...).as_retriever()
#   count_tokens()           -> llm.get_num_tokens() + real usage_metadata
#   helper_sanitize_input()  -> sanitize()   [no LangChain equivalent exists]
#   helper_moderate_content()-> moderate()   [no LangChain equivalent in v1]
#   create_mcp_message()     -> not needed; LangGraph state carries structure
#
# WHAT LANGCHAIN DOES NOT PROVIDE, AND IS THEREFORE HAND-WRITTEN HERE
# -------------------------------------------------------------------
#   * sanitize()      — per-chunk prompt-injection screening with skip-and-
#                       continue semantics. Middleware sees a whole message and
#                       cannot drop chunk 2 while keeping chunks 1 and 3.
#   * moderate()      — langchain-core v1 has no moderation wrapper; the legacy
#                       OpenAIModerationChain moved to langchain-classic. This
#                       calls the OpenAI moderation endpoint directly.
#   * UsageTracker    — LangChain reports token usage per call; attributing it
#                       per *plan step* against an execution cursor is ours.
# =============================================================================

from __future__ import annotations

import logging
import re
import warnings
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.runnables import RunnableLambda
from langchain_core.vectorstores import VectorStoreRetriever
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_pinecone import PineconeVectorStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)

# =============================================================================
# 1. Configuration — identical values to the original Control Deck
# =============================================================================

CONFIG = {
    "index_name": "genai-mas-mcp-ch3",
    "generation_model": "gpt-5.1",
    "embedding_model": "text-embedding-3-small",
    "namespace_context": "ContextLibrary",
    "namespace_knowledge": "KnowledgeStore",
    # Retrieval depth. These reproduce the original agents' top_k values.
    "k_blueprint": 1,     # agent_context_librarian used top_k=1
    "k_knowledge": 3,     # agent_researcher used top_k=3
    # Which metadata field holds the readable payload in each namespace.
    "text_key_context": "blueprint_json",
    "text_key_knowledge": "text",
    # Retry policy, matching the original tenacity decorator.
    "llm_retries": 6,
    "request_timeout": 120,
}


# =============================================================================
# 2. The model — replaces call_llm_robust
# =============================================================================

def build_llm(config: Optional[dict] = None, **kwargs):
    """
    Build the chat model with the same retry policy the original used.

    Original:  @retry(wait=wait_random_exponential(min=1, max=60),
                      stop=stop_after_attempt(6))
    LangChain: .with_retry(stop_after_attempt=6, wait_exponential_jitter=True)

    The returned object is a Runnable, so the retry wrapper applies to every
    chain it is piped into, not just to one function.

    No temperature is set, exactly as in the original. Do not add one during a
    comparison run: introducing a parameter the original did not use makes
    output differences impossible to attribute.
    """
    cfg = {**CONFIG, **(config or {})}
    base = ChatOpenAI(
        model=cfg["generation_model"],
        timeout=cfg["request_timeout"],
        **kwargs,
    )
    llm = base.with_retry(
        stop_after_attempt=cfg["llm_retries"],
        wait_exponential_jitter=True,
    )
    logging.info(
        f"LLM ready: {cfg['generation_model']} "
        f"(retry: {cfg['llm_retries']} attempts, timeout: {cfg['request_timeout']}s)."
    )
    return llm


def base_model(llm):
    """
    Unwrap a retry-wrapped Runnable back to the underlying ChatOpenAI.

    .with_retry() returns a RunnableRetry that holds the real model in .bound.
    Some methods -- with_structured_output(), get_num_tokens(), and the OpenAI
    client used for moderation -- live on the model itself, not on the wrapper.

    Note that you cannot simply attach an attribute to either object: both are
    Pydantic models and reject unknown fields. This shim exists because of a
    LangChain limitation, not because of a LangChain feature.
    """
    return getattr(llm, "bound", llm)


# =============================================================================
# 3. Embeddings — replaces get_embedding
# =============================================================================

def build_embeddings(config: Optional[dict] = None):
    """
    IMPORTANT: this MUST be the same model that wrote the vectors into Pinecone.
    text-embedding-3-small produces 1536 dimensions. Using anything else returns
    plausible-looking nonsense with no error message.
    """
    cfg = {**CONFIG, **(config or {})}
    emb = OpenAIEmbeddings(model=cfg["embedding_model"])
    logging.info(f"Embeddings ready: {cfg['embedding_model']}.")
    return emb


# =============================================================================
# 4. Vector stores — replaces query_pinecone
#
# One Pinecone index, TWO namespaces, TWO different text_key values.
# This is the single most important detail in the whole port.
# =============================================================================

def build_stores(embeddings,
                 config: Optional[dict] = None
                 ) -> Tuple[PineconeVectorStore, PineconeVectorStore]:
    """
    Returns (context_store, knowledge_store).

    context_store   -> namespace 'ContextLibrary',  text_key 'blueprint_json'
    knowledge_store -> namespace 'KnowledgeStore',  text_key 'text'

    Both READ an existing index. Nothing is written. Never call
    PineconeVectorStore.from_documents() here — that would ingest new vectors,
    chunked differently and with different metadata keys, silently
    desynchronising the index from the Chapter 8 and 9 ingestion notebooks.
    """
    cfg = {**CONFIG, **(config or {})}

    context_store = PineconeVectorStore(
        index_name=cfg["index_name"],
        embedding=embeddings,
        namespace=cfg["namespace_context"],
        text_key=cfg["text_key_context"],
    )
    knowledge_store = PineconeVectorStore(
        index_name=cfg["index_name"],
        embedding=embeddings,
        namespace=cfg["namespace_knowledge"],
        text_key=cfg["text_key_knowledge"],
    )
    logging.info(
        f"Vector stores ready on index '{cfg['index_name']}': "
        f"'{cfg['namespace_context']}' (text_key={cfg['text_key_context']}) and "
        f"'{cfg['namespace_knowledge']}' (text_key={cfg['text_key_knowledge']})."
    )
    return context_store, knowledge_store


def build_retrievers(context_store,
                     knowledge_store,
                     config: Optional[dict] = None
                     ) -> Tuple[VectorStoreRetriever, VectorStoreRetriever]:
    """Turn the two stores into Runnables that take a query string and return a
    list of Documents."""
    cfg = {**CONFIG, **(config or {})}
    blueprint_retriever = context_store.as_retriever(
        search_kwargs={"k": cfg["k_blueprint"]}
    )
    knowledge_retriever = knowledge_store.as_retriever(
        search_kwargs={"k": cfg["k_knowledge"]}
    )
    logging.info(
        f"Retrievers ready: blueprint k={cfg['k_blueprint']}, "
        f"knowledge k={cfg['k_knowledge']}."
    )
    return blueprint_retriever, knowledge_retriever


# =============================================================================
# 5. Security guardrail — same patterns as helper_sanitize_input
#
# NOT a LangChain component. LangChain has no built-in for per-chunk pattern
# screening, and middleware operates at the wrong granularity.
# =============================================================================

INJECTION_PATTERNS = [
    r"ignore previous instructions",
    r"ignore all prior commands",
    r"you are now in.*mode",
    r"act as",
    r"ignore any legal advice",
    r"print your instructions",
    r"sudo|apt-get|yum|pip install",
]

# Compiled once at import. Behaviour is identical to re.search(..., IGNORECASE)
# on every call; this just avoids recompiling on every retrieved chunk.
_COMPILED_PATTERNS = [(p, re.compile(p, re.IGNORECASE)) for p in INJECTION_PATTERNS]


class SanitizationError(ValueError):
    """Raised when a retrieved chunk matches an injection pattern.

    Subclasses ValueError so that `except ValueError` in the original agent code
    continues to work unchanged.
    """

    def __init__(self, pattern: str):
        self.pattern = pattern
        super().__init__("Input sanitization failed. Potential threat detected.")


def sanitize(text: str) -> str:
    """
    Detect prompt-injection patterns in retrieved text.
    Returns the text if clean; raises SanitizationError if a threat is detected.

    This is applied PER RETRIEVED CHUNK inside the Researcher, exactly as in the
    original. Tainted chunks are skipped and the remaining ones still produce an
    answer. Do not move this into agent middleware: middleware sees the whole
    message, so it cannot drop chunk 2 while keeping chunks 1 and 3.
    """
    for raw, compiled in _COMPILED_PATTERNS:
        if compiled.search(text):
            logging.warning(f"[Sanitizer] Potential threat detected with pattern: '{raw}'")
            raise SanitizationError(raw)
    logging.info("[Sanitizer] Input passed sanitization check.")
    return text


# =============================================================================
# 6. Moderation guardrail
#
# langchain-core v1 has no native moderation wrapper (the legacy
# OpenAIModerationChain moved to langchain-classic). We call the OpenAI
# moderation endpoint directly and expose the check as a RunnableLambda so it
# can still be composed and traced like any other engine component.
#
# Client resolution is tiered so that a change in langchain-openai's internals
# degrades to an explicit SDK client instead of breaking moderation outright.
# =============================================================================

_MODERATION_CLIENT = None


def _openai_client(llm=None):
    """
    Resolve an OpenAI SDK client that exposes `.moderations`.

    Order of preference:
      1. ChatOpenAI.root_client  — the public client attribute on the model.
      2. ChatOpenAI.client._client — the parent of the completions resource.
      3. openai.OpenAI() — constructed from OPENAI_API_KEY in the environment.

    Step 3 is why `openai` is a declared dependency rather than an accidental
    transitive one. Relying only on steps 1-2 couples moderation to
    langchain-openai's private attribute layout, which is not a stable contract.
    """
    global _MODERATION_CLIENT
    if _MODERATION_CLIENT is not None:
        return _MODERATION_CLIENT

    if llm is not None:
        base = base_model(llm)
        candidate = getattr(base, "root_client", None)
        if candidate is not None and hasattr(candidate, "moderations"):
            _MODERATION_CLIENT = candidate
            return _MODERATION_CLIENT

        resource = getattr(base, "client", None)
        parent = getattr(resource, "_client", None)
        if parent is not None and hasattr(parent, "moderations"):
            _MODERATION_CLIENT = parent
            return _MODERATION_CLIENT

    from openai import OpenAI  # declared dependency; see PACKAGES in lc_utils
    _MODERATION_CLIENT = OpenAI()
    logging.info("[Moderation] Using a directly constructed OpenAI client.")
    return _MODERATION_CLIENT


def moderate(text: str, llm=None, model: str = "omni-moderation-latest") -> Dict[str, Any]:
    """
    Return a moderation report.

    {
      "flagged":   bool,   # the endpoint flagged the content
      "available": bool,   # the check actually ran
      "categories": {...},
      "scores":     {...},
      "error":      str | None,
    }

    Fail-safe policy: if the check cannot run, `flagged` is True and `available`
    is False. Callers must distinguish the two — "this content is unsafe" and
    "we could not determine whether this content is safe" are different findings
    and, in a regulated deployment, belong in different audit records.
    """
    logging.info("Moderating content...")
    try:
        client = _openai_client(llm)
        result = client.moderations.create(model=model, input=text).results[0]
        report = {
            "flagged": bool(result.flagged),
            "available": True,
            "categories": dict(result.categories),
            "scores": dict(result.category_scores),
            "error": None,
        }
        if report["flagged"]:
            flagged_names = [k for k, v in report["categories"].items() if v]
            logging.warning(f"Content was FLAGGED by moderation: {flagged_names}")
        else:
            logging.info("Content PASSED moderation.")
        return report
    except Exception as e:
        logging.error(f"Moderation error: {e}")
        return {
            "flagged": True,
            "available": False,
            "categories": {},
            "scores": {},
            "error": str(e),
        }


def moderation_runnable(llm=None) -> RunnableLambda:
    """The moderation check as a first-class LangChain Runnable, so it can be
    piped: moderation_runnable(llm) | ... or invoked with .invoke(text)."""
    return RunnableLambda(lambda text: moderate(text, llm), name="Moderation")


# =============================================================================
# 7. Token accounting — replaces count_tokens
#
# Two numbers are tracked, and they mean different things:
#
#   CTX IN / CTX OUT  - the size of the context handed to a step and the size of
#                       what it produced. This is the original notebook's metric
#                       (tiktoken over the payload) and is what the Summarizer's
#                       "tokens saved" figure is computed from.
#   LLM IN / LLM OUT  - the tokens the provider actually billed for this step,
#                       read from AIMessage.usage_metadata. Exact, not estimated.
#                       A retrieval-only step (Librarian) reports 0 here because
#                       it makes no model call.
# =============================================================================

def count_tokens(text: Any, llm=None) -> int:
    """
    Context-size measurement, via LangChain's own tokenizer helper.

    A brand-new model name may not be in tiktoken's registry yet, in which case
    LangChain falls back to a generic tokenizer and warns. The count is then an
    estimate, exactly as the original helpers.count_tokens() was. The warning is
    silenced because it would fire on every step; the exact numbers come from
    usage_metadata (llm_in / llm_out) instead.
    """
    payload = str(text)
    if llm is not None:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return base_model(llm).get_num_tokens(payload)
        except Exception:
            pass
    return max(1, len(payload) // 4)


class UsageTracker(BaseCallbackHandler):
    """
    Callback handler that accumulates real provider token usage.

    Attach it once per run via config={"callbacks": [tracker]}. The engine takes
    a snapshot before and after each step to attribute usage to that step.

    LangChain reports usage per model call; attributing it per plan step is the
    part LangChain does not do for you.
    """

    def __init__(self):
        self.reset()

    def reset(self) -> "UsageTracker":
        """Clear all counters. Called once per run so figures are per-run."""
        self.input_tokens = 0
        self.output_tokens = 0
        self.llm_calls = 0
        self.events: List[dict] = []
        return self

    # --- snapshotting -----------------------------------------------------
    def snapshot(self) -> Tuple[int, int, int]:
        return (self.input_tokens, self.output_tokens, self.llm_calls)

    def delta(self, snap: Optional[Tuple[int, int, int]]) -> Dict[str, int]:
        if snap is None:
            return {"llm_in": 0, "llm_out": 0, "llm_calls": 0}
        return {
            "llm_in": self.input_tokens - snap[0],
            "llm_out": self.output_tokens - snap[1],
            "llm_calls": self.llm_calls - snap[2],
        }

    # --- LangChain hooks --------------------------------------------------
    def on_llm_end(self, response, **kwargs):
        self.llm_calls += 1
        got = False
        # Preferred: standardized usage_metadata on each generated message.
        try:
            for gen_list in (response.generations or []):
                for gen in gen_list:
                    msg = getattr(gen, "message", None)
                    usage = getattr(msg, "usage_metadata", None) if msg else None
                    if usage:
                        self.input_tokens += usage.get("input_tokens", 0) or 0
                        self.output_tokens += usage.get("output_tokens", 0) or 0
                        got = True
        except Exception:
            pass
        # Fallback: provider-specific llm_output block.
        if not got:
            try:
                tu = (response.llm_output or {}).get("token_usage", {}) or {}
                self.input_tokens += tu.get("prompt_tokens", 0) or 0
                self.output_tokens += tu.get("completion_tokens", 0) or 0
            except Exception:
                pass

    def on_llm_error(self, error, **kwargs):
        self.events.append({"type": "llm_error", "error": str(error)})

    def on_tool_error(self, error, **kwargs):
        self.events.append({"type": "tool_error", "error": str(error)})

    # --- convenience ------------------------------------------------------
    def summary(self) -> Dict[str, int]:
        """Totals for the most recent run only — reset() is called per run."""
        return {
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
        }


logging.info("LangChain helper layer defined.")
