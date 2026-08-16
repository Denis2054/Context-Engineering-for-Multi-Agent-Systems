# =============================================================================
# adapters_nim.py  —  The Storage Contract and its Pinecone Implementation
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# The engine, the Foreman, and the registry never import `pinecone`. They hold
# an adapter and call methods on it. Swapping the storage backend is therefore
# a construction-time decision — one argument at one call site — rather than a
# refactor that reaches into every agent.
#
# THE FOUR PROMISES
# -----------------
#   search_meaning(query, namespace, top_k)  semantic vector search
#   search_exact(filter, namespace)          structured metadata filter
#   read_state(key)                          read durable state
#   write_state(key, value)                  write durable state
#
# PineconeAdapter implements the first. The other three raise
# NotImplementedError with a message naming exactly what would be required to
# fulfil them.
#
# WHY DECLARE PROMISES YOU HAVE NOT KEPT
# --------------------------------------
# Because the alternative is worse. Two options were available for the three
# unimplemented methods: leave them off the interface, or declare them and
# raise. Leaving them off means a future OracleAdapter invents its own names
# and nothing composes. Declaring them means the contract is visible now, and
# any code path that reaches for a capability this backend lacks fails loudly,
# at the call, with a message that says what to wire in.
#
# `read_state` and `write_state` matter more than they look. Today the Foreman
# keeps completed node outputs in a dict, which is fine while everything runs
# in one process. The moment a node runs on another machine, that dict has to
# become a state of record. The seam is already named; only the implementation
# is missing.
# =============================================================================

import logging
from abc import ABC, abstractmethod


# =============================================================================
# SECTION A — THE CONTRACT
#
# Abstract methods, so a subclass that forgets one fails at instantiation
# rather than three nodes into a run.
# =============================================================================

class StorageAdapterBase(ABC):
    """
    The storage contract every adapter must fulfil.

    Concrete adapters map these four methods onto whatever they wrap — a vector
    database, a relational database, a document store, or a composition of
    several.
    """

    @abstractmethod
    def search_meaning(self, query: str, namespace: str, top_k: int = 5) -> list:
        """
        Semantic vector search.

        Returns:
            list[dict]: [{"text": str, "score": float, "metadata": dict}, ...]
        """
        ...

    @abstractmethod
    def search_exact(self, filter: dict, namespace: str) -> list:
        """
        Structured metadata filter — exact key/value match, no embedding.

        The capability semantic search cannot provide. "Every NDA signed in
        2024" is a filter, not a similarity query, and asking an embedding
        model to approximate it produces plausible wrong answers.
        """
        ...

    @abstractmethod
    def read_state(self, key: str):
        """Read a durable value that must outlive a single run_dag() call."""
        ...

    @abstractmethod
    def write_state(self, key: str, value) -> None:
        """Write a durable value that must outlive a single run_dag() call."""
        ...


# =============================================================================
# SECTION B — PINECONE IMPLEMENTATION
# =============================================================================

class PineconeAdapter(StorageAdapterBase):
    """
    Semantic search over Pinecone, plus logical-to-physical namespace mapping.

    Construction:

        adapter = PineconeAdapter(
            client          = embedding_client,   # MUST match the index vectors
            index           = pc.Index(INDEX_NAME),
            embedding_model = "text-embedding-3-small",
            namespaces      = {
                "General"  : {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
                "Legal"    : {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
                "Marketing": {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
            },
        )

    ON `client`
    -----------
    This is the single most consequential argument in the notebook, and the one
    most easily set wrong, because setting it wrong produces no exception.

    The client determines which provider embeds the query. The index determines
    which provider embedded the documents. If those disagree, one of two things
    happens: the dimensions differ and Pinecone rejects the query, or the
    dimensions coincide and you receive similarity scores computed between two
    unrelated vector spaces — retrieval that looks like it worked and is
    meaningless.

    Pass the OpenAI client for an OpenAI-embedded index; the NIM client for an
    NVIDIA-embedded one. `utils_nim.resolve_embedding_backend()` returns the
    matching triple so the choice is made once.

    ON `namespaces`
    ---------------
    A logical domain maps to a physical namespace. In this deployment all three
    domains share ContextLibrary and KnowledgeStore, which is what a free-tier
    index allows. The indirection still earns its place: giving Legal its own
    physically isolated namespace later is an edit to this dict, not to the
    agents that read from it.
    """

    def __init__(self, client, index, embedding_model: str, namespaces: dict):
        """
        Args:
            client:                 embedding credential holder; must match the
                                    provider that built the index.
            index:                  Pinecone Index handle, pc.Index(name).
            embedding_model (str):  must match the model the index was built with.
            namespaces (dict):      domain -> {"context": ns, "knowledge": ns}.
        """
        self._client          = client
        self._index           = index
        self._embedding_model = embedding_model
        self._namespaces      = namespaces

        logging.info(
            f"[PineconeAdapter] initialised. "
            f"embedding_model={embedding_model} "
            f"domains={sorted(namespaces.keys())}"
        )

    # ------------------------------------------------------------------
    # PROMISE 1 — search_meaning  (implemented)
    # ------------------------------------------------------------------

    def search_meaning(self, query: str, namespace: str, top_k: int = 5) -> list:
        """
        Embed a query and return the top_k nearest chunks from one namespace.

        Args:
            query (str):     natural-language query.
            namespace (str): PHYSICAL namespace name. Call resolve_namespace()
                             first if you are holding a logical domain name.
            top_k (int):     maximum matches.

        Returns:
            list[dict]: [{"text": str, "score": float, "metadata": dict}, ...]
                        normalised, so callers are insulated from Pinecone SDK
                        response-shape changes.
        """
        from helpers import query_pinecone

        preview = query[:60] + ("..." if len(query) > 60 else "")
        logging.info(
            f"[PineconeAdapter] search_meaning ns={namespace} "
            f"top_k={top_k} query='{preview}'"
        )

        raw = query_pinecone(
            query_text      = query,
            namespace       = namespace,
            top_k           = top_k,
            index           = self._index,
            client          = self._client,
            embedding_model = self._embedding_model,
        )

        normalised = [
            {
                "text"    : m.get("metadata", {}).get("text", ""),
                "score"   : m.get("score", 0.0),
                "metadata": m.get("metadata", {}),
            }
            for m in raw
        ]
        logging.info(f"[PineconeAdapter] {len(normalised)} result(s).")
        return normalised

    # ------------------------------------------------------------------
    # PROMISE 2 — search_exact  (declared, not implemented)
    # ------------------------------------------------------------------

    def search_exact(self, filter: dict, namespace: str) -> list:
        """
        Not implemented for Pinecone free tier.

        Raises:
            NotImplementedError: always, with the two routes to fixing it.
        """
        raise NotImplementedError(
            "PineconeAdapter.search_exact() is not implemented.\n"
            "The Pinecone free tier does not support metadata filter queries.\n"
            "Two routes forward:\n"
            "  (a) a paid Pinecone tier, and pass filter= to index.query()\n"
            "  (b) a relational adapter that implements this via SQL WHERE\n"
            f"Attempted filter: {filter} | namespace: {namespace}"
        )

    # ------------------------------------------------------------------
    # PROMISE 3 — read_state  (declared, not implemented)
    # ------------------------------------------------------------------

    def read_state(self, key: str):
        """
        Not implemented. Pinecone is a vector store with no key/value API.

        Raises:
            NotImplementedError: always.
        """
        raise NotImplementedError(
            "PineconeAdapter.read_state() is not implemented.\n"
            "Pinecone stores vectors; it has no durable key/value surface.\n"
            "Distributed execution needs a state of record — Postgres, CouchDB,\n"
            "or Oracle AQ — before node outputs can outlive a single process.\n"
            f"Attempted key: '{key}'"
        )

    # ------------------------------------------------------------------
    # PROMISE 4 — write_state  (declared, not implemented)
    # ------------------------------------------------------------------

    def write_state(self, key: str, value) -> None:
        """
        Not implemented. Same constraint as read_state.

        Raises:
            NotImplementedError: always.
        """
        raise NotImplementedError(
            "PineconeAdapter.write_state() is not implemented.\n"
            "Pinecone stores vectors; it has no durable key/value surface.\n"
            f"Attempted key: '{key}' | value type: {type(value).__name__}"
        )

    # ------------------------------------------------------------------
    # UTILITY — resolve_namespace
    # ------------------------------------------------------------------

    def resolve_namespace(self, domain: str, role: str = "knowledge") -> str:
        """
        Map a logical (domain, role) pair to a physical namespace.

        Called by the registry when it builds an agent handler, which is why an
        agent function never contains a namespace string. Routing is
        configuration; the agent is code.

        Args:
            domain (str): "General", "Legal", "Marketing".
            role (str):   "knowledge" or "context".

        Returns:
            str: the physical namespace name.

        Raises:
            KeyError: unknown domain or role, naming what is registered.
        """
        if domain not in self._namespaces:
            raise KeyError(
                f"Domain '{domain}' is not registered with this adapter. "
                f"Registered: {sorted(self._namespaces.keys())}. "
                f"Add it to the namespaces dict at construction time."
            )

        domain_map = self._namespaces[domain]
        if role not in domain_map:
            raise KeyError(
                f"Role '{role}' not defined for domain '{domain}'. "
                f"Available: {sorted(domain_map.keys())}."
            )

        resolved = domain_map[role]
        logging.debug(
            f"[PineconeAdapter] resolve_namespace {domain}/{role} -> {resolved}"
        )
        return resolved

    # ------------------------------------------------------------------
    # UTILITY — describe
    # ------------------------------------------------------------------

    def describe(self) -> dict:
        """
        Machine-readable capability summary, for audit logs and the dashboard.

        Reporting the three unimplemented promises by name is the point: an
        auditor reading this can see what the system cannot do without reading
        the source.
        """
        return {
            "adapter"        : "PineconeAdapter",
            "search_meaning" : "implemented",
            "search_exact"   : "not implemented — Pinecone free tier limitation",
            "read_state"     : "not implemented — requires a stateful adapter",
            "write_state"    : "not implemented — requires a stateful adapter",
            "embedding_model": self._embedding_model,
            "domains"        : sorted(self._namespaces.keys()),
        }
