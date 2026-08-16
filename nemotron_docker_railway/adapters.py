# =============================================================================
# adapters.py  —  Storage Adapter Interface + Pinecone Implementation
# commons/dag_engine/adapters.py
#
# Copyright 2025-2026, Denis Rothman
#
# WHAT THIS FILE DOES:
#   Defines the four-promise storage contract (StorageAdapterBase) and
#   provides PineconeAdapter as the Phase 1 implementation.
#
#   The engine, agents, and registry never import from pinecone directly.
#   They call adapter methods. This means swapping the storage backend
#   is a construction-time decision — one argument at the call site,
#   zero changes to the engine.
#
# THE FOUR PROMISES:
#   1. search_meaning(query, namespace, top_k)  — semantic vector search
#   2. search_exact(filter, namespace)           — structured metadata filter
#   3. read_state(key)                           — read durable state
#   4. write_state(key, value)                   — write durable state
#
# PHASE 1 STATUS:
#   PineconeAdapter implements promise 1 only.
#   Promises 2, 3, and 4 raise NotImplementedError with descriptive messages
#   that name exactly what is needed to fulfil them.
#   This is intentional — the system fails loudly if something tries to use
#   capabilities that don't exist yet, rather than silently doing nothing.
#
# FUTURE ADAPTERS (drop-in replacements — implement all four promises):
#   - OracleAdapter      : search_exact via SQL, read/write_state via AQ
#   - CouchDBAdapter     : read/write_state via document store
#   - MilvusAdapter      : search_meaning via Milvus, for self-hosted vector DB
#   - HybridAdapter      : compose two adapters (e.g. Pinecone + Postgres)
#
# RELATIONSHIP TO OTHER FILES:
#   - Imported by: engine.py, registry.py, agents.py
#   - Wraps:       helpers.py → query_pinecone(), get_embedding()
# =============================================================================

import logging
from abc import ABC, abstractmethod


# =============================================================================
# SECTION A — THE CONTRACT  (StorageAdapterBase)
# All four promises declared as abstract methods.
# Any concrete adapter that fails to implement all four raises TypeError
# at instantiation time — not at runtime when a node tries to use it.
# =============================================================================

class StorageAdapterBase(ABC):
    """
    The storage contract every adapter must fulfil.

    Agents and the engine call these four methods.
    The adapter is responsible for mapping them to whatever
    backend it wraps — vector DB, relational DB, document store,
    or any combination.
    """

    @abstractmethod
    def search_meaning(self, query: str, namespace: str, top_k: int = 5) -> list:
        """
        Semantic vector search — find the top_k most relevant chunks
        for the given natural-language query in the specified namespace.

        Args:
            query (str):      Natural-language search query.
            namespace (str):  The namespace / collection to search.
            top_k (int):      Maximum number of results to return.

        Returns:
            list[dict]: Each dict has at minimum:
                        {"text": str, "score": float, "metadata": dict}
        """
        ...

    @abstractmethod
    def search_exact(self, filter: dict, namespace: str) -> list:
        """
        Structured metadata filter — find all chunks matching an exact
        key-value filter (e.g. {"document_type": "NDA", "year": 2024}).

        Args:
            filter (dict):    Metadata key-value pairs to match exactly.
            namespace (str):  The namespace / collection to search.

        Returns:
            list[dict]: Matching chunks, same shape as search_meaning results.
        """
        ...

    @abstractmethod
    def read_state(self, key: str):
        """
        Read a durable state value by key.

        Used for inter-execution persistence — results that must survive
        beyond a single run_dag() call, be audited, or be read by another
        worker or engine instance.

        Args:
            key (str): The state key.

        Returns:
            The stored value, or None if the key does not exist.
        """
        ...

    @abstractmethod
    def write_state(self, key: str, value) -> None:
        """
        Write a durable state value by key.

        Args:
            key (str):   The state key.
            value:       Any JSON-serialisable value.
        """
        ...


# =============================================================================
# SECTION B — PINECONE ADAPTER
# Implements search_meaning only.
# The other three promises raise NotImplementedError with precise messages.
# =============================================================================

class PineconeAdapter(StorageAdapterBase):
    """
    Phase 1 storage adapter — wraps Pinecone for semantic search.

    Construction:
        adapter = PineconeAdapter(
            client         = openai_client,
            index          = pc.Index(index_name),
            embedding_model = "text-embedding-3-small",
            namespaces     = {
                "General"   : {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
                "Legal"     : {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
                "Marketing" : {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
            }
        )

    The `namespaces` dict maps domain names to their Pinecone namespace
    names for context and knowledge queries. All domains currently share
    the same physical namespaces in the free-tier Pinecone index —
    the adapter accepts the logical domain name and resolves it.
    """

    def __init__(self, client, index, embedding_model: str, namespaces: dict):
        """
        Args:
            client:             OpenAI-compatible client for embedding calls.
            index:              Pinecone Index object (pc.Index(index_name)).
            embedding_model:    Model name used for embedding queries.
            namespaces (dict):  Logical domain → physical namespace mapping.
                                See class docstring for the expected shape.
        """
        self._client          = client
        self._index           = index
        self._embedding_model = embedding_model
        self._namespaces      = namespaces

        logging.info(
            f"[PineconeAdapter] Initialised. "
            f"Embedding model: {embedding_model}. "
            f"Domains registered: {sorted(namespaces.keys())}"
        )

    # ------------------------------------------------------------------
    # PROMISE 1  —  search_meaning  (IMPLEMENTED)
    # ------------------------------------------------------------------

    def search_meaning(self, query: str, namespace: str, top_k: int = 5) -> list:
        """
        Semantic vector search via Pinecone.

        Embeds the query using the configured embedding model, queries the
        Pinecone index in the specified namespace, and returns the top_k
        most relevant chunks as a list of dicts.

        Args:
            query (str):      Natural-language search query.
            namespace (str):  Physical Pinecone namespace name
                              (e.g. "KnowledgeStore" or "ContextLibrary").
                              Use resolve_namespace() to map logical names first.
            top_k (int):      Maximum results to return.

        Returns:
            list[dict]: [{"text": str, "score": float, "metadata": dict}, ...]
        """
        from helpers import query_pinecone

        logging.info(
            f"[PineconeAdapter] search_meaning | "
            f"namespace={namespace} | top_k={top_k} | "
            f"query='{query[:60]}{'...' if len(query) > 60 else ''}'"
        )

        raw_results = query_pinecone(
            client          = self._client,
            index           = self._index,
            query           = query,
            namespace       = namespace,
            top_k           = top_k,
            embedding_model = self._embedding_model,
        )

        # Normalise to a consistent shape regardless of Pinecone SDK version
        normalised = []
        for match in raw_results:
            normalised.append({
                "text"     : match.get("metadata", {}).get("text", ""),
                "score"    : match.get("score", 0.0),
                "metadata" : match.get("metadata", {}),
            })

        logging.info(
            f"[PineconeAdapter] search_meaning returned {len(normalised)} result(s)."
        )
        return normalised

    # ------------------------------------------------------------------
    # PROMISE 2  —  search_exact  (NOT IMPLEMENTED — stub)
    # ------------------------------------------------------------------

    def search_exact(self, filter: dict, namespace: str) -> list:
        """
        NOT IMPLEMENTED in PineconeAdapter (Phase 1).

        Pinecone's free tier does not support metadata filtering queries.
        Exact structured search requires one of:
            - Pinecone paid tier (metadata filter via `filter=` parameter)
            - A relational adapter (OracleAdapter, PostgresAdapter)

        Raises:
            NotImplementedError: Always. Intentional — fails loudly.
        """
        raise NotImplementedError(
            "PineconeAdapter.search_exact() is not implemented. "
            "Pinecone free tier does not support metadata filtering. "
            "To enable exact search, either:\n"
            "  (a) Upgrade to Pinecone paid tier and implement filter= queries, or\n"
            "  (b) Wire a relational adapter (OracleAdapter, PostgresAdapter) "
            "that implements this method via SQL WHERE clauses.\n"
            f"Attempted filter: {filter} | namespace: {namespace}"
        )

    # ------------------------------------------------------------------
    # PROMISE 3  —  read_state  (NOT IMPLEMENTED — stub)
    # ------------------------------------------------------------------

    def read_state(self, key: str):
        """
        NOT IMPLEMENTED in PineconeAdapter (Phase 1).

        Pinecone is a vector store — it has no key-value state API.
        Durable state requires a separate store. Options:
            - PostgresAdapter  : read via SELECT WHERE key = $1
            - CouchDBAdapter   : read via document GET
            - OracleAdapter    : read via AQ dequeue or table SELECT

        Raises:
            NotImplementedError: Always. Intentional — fails loudly.
        """
        raise NotImplementedError(
            "PineconeAdapter.read_state() is not implemented. "
            "PineconeAdapter does not support durable state persistence. "
            "State of record requires a stateful adapter. "
            "Wire a PostgresAdapter, CouchDBAdapter, or OracleAdapter "
            "that implements read_state() before Stage 4 (worker queue).\n"
            f"Attempted key: '{key}'"
        )

    # ------------------------------------------------------------------
    # PROMISE 4  —  write_state  (NOT IMPLEMENTED — stub)
    # ------------------------------------------------------------------

    def write_state(self, key: str, value) -> None:
        """
        NOT IMPLEMENTED in PineconeAdapter (Phase 1).

        Same constraint as read_state — Pinecone has no state API.

        Raises:
            NotImplementedError: Always. Intentional — fails loudly.
        """
        raise NotImplementedError(
            "PineconeAdapter.write_state() is not implemented. "
            "PineconeAdapter does not support durable state persistence. "
            "State of record requires a stateful adapter. "
            "Wire a PostgresAdapter, CouchDBAdapter, or OracleAdapter "
            "that implements write_state() before Stage 4 (worker queue).\n"
            f"Attempted key: '{key}' | value type: {type(value).__name__}"
        )

    # ------------------------------------------------------------------
    # UTILITY  —  resolve_namespace
    # Maps a logical (domain, role) pair to a physical Pinecone namespace.
    # ------------------------------------------------------------------

    def resolve_namespace(self, domain: str, role: str = "knowledge") -> str:
        """
        Map a logical domain name and role to a physical Pinecone namespace.

        Args:
            domain (str): Logical domain name ("General", "Legal", "Marketing").
            role (str):   "knowledge" (KnowledgeStore) or "context" (ContextLibrary).

        Returns:
            str: Physical Pinecone namespace name.

        Raises:
            KeyError: If the domain is not registered in the namespace map.
            KeyError: If the role is not "knowledge" or "context".
        """
        if domain not in self._namespaces:
            raise KeyError(
                f"Domain '{domain}' is not registered in PineconeAdapter. "
                f"Registered domains: {sorted(self._namespaces.keys())}. "
                f"Add it to the namespaces dict at construction time."
            )

        domain_map = self._namespaces[domain]

        if role not in domain_map:
            raise KeyError(
                f"Role '{role}' not found for domain '{domain}'. "
                f"Available roles: {sorted(domain_map.keys())}."
            )

        resolved = domain_map[role]
        logging.debug(
            f"[PineconeAdapter] resolve_namespace: "
            f"domain={domain} | role={role} → {resolved}"
        )
        return resolved

    # ------------------------------------------------------------------
    # UTILITY  —  describe
    # Returns a human-readable summary of this adapter's capabilities.
    # Used by the harness audit log and docx documentation generator.
    # ------------------------------------------------------------------

    def describe(self) -> dict:
        """
        Return a structured description of this adapter's capabilities.
        Used in audit logs and documentation generation.
        """
        return {
            "adapter"         : "PineconeAdapter",
            "phase"           : 1,
            "search_meaning"  : "implemented",
            "search_exact"    : "not implemented — Pinecone free tier limitation",
            "read_state"      : "not implemented — requires stateful adapter",
            "write_state"     : "not implemented — requires stateful adapter",
            "embedding_model" : self._embedding_model,
            "domains"         : sorted(self._namespaces.keys()),
        }
