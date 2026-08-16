# =============================================================================
# utils_nim.py  —  Setup, Secrets, Clients, and Pre-flight Diagnostics
# Universal Context Engine — DAG Edition · NIM
#
# Copyright 2025-2026, Denis Rothman
#
# ROLE IN THE SYSTEM
# ------------------
# This is the only module that touches the outside world before the engine
# starts: it installs packages, reads credentials, builds the three clients,
# and runs the two pre-flight checks that stop a run from failing silently.
#
# It is deliberately the lowest layer. It imports nothing from the engine, so
# it can be imported and executed before any other module exists on disk.
#
# WHAT IT PROVIDES
# ----------------
#   install_dependencies()        pip installs, quiet, pinned
#   initialize_nim_clients()      -> (nim_client, openai_client, pinecone_client)
#   verify_nim_connectivity()     1-token probe of both NIM models
#   list_nim_models()             ask NIM which model IDs are actually live
#   resolve_embedding_backend()   picks index + embedding model + dimension
#   check_index()                 confirms the Pinecone index is usable
#
# THE TWO CLIENTS, AND WHY THERE ARE TWO
# --------------------------------------
# `nim_client` and `openai_client` are both `openai.OpenAI` objects. They differ
# only in `base_url` and `api_key`. NVIDIA exposes an OpenAI-compatible REST
# surface, so one SDK — and, in this codebase, one raw-HTTP helper — drives both.
#
#   nim_client     -> https://integrate.api.nvidia.com/v1   (all LLM inference)
#   openai_client  -> https://api.openai.com/v1             (moderation, and
#                                                            embeddings if the
#                                                            index was built
#                                                            with OpenAI vectors)
#
# Moderation is the one call that cannot move: NVIDIA publishes no equivalent of
# OpenAI's `/moderations` endpoint, so Gate 1 keeps an OpenAI dependency even
# when every token of generation is running on NIM.
#
# SECRETS
# -------
# Resolution order is Colab Secrets -> environment variable -> interactive
# prompt. That order lets the identical module run in Colab, in a container,
# and on a laptop without edits.
#
#   NVIDIA_API_KEY    required, must start with "nvapi-"
#   API_KEY           OpenAI key (moderation, and OpenAI embeddings)
#   PINECONE_API_KEY  required
# =============================================================================

import os
import subprocess
import sys


# =============================================================================
# SECTION A — MODEL CONSTANTS
#
# Two models, chosen for two different jobs. This split is the single most
# consequential configuration decision in the NIM edition.
#
# NIM_PLANNER_MODEL — Nemotron Super
#   Called exactly once per run, by planner(). It must emit a syntactically
#   valid JSON DAG whose agent names and input keys match the registry exactly.
#   That is a hard structured-output task, and it is worth paying for a large
#   model to get it right, because a malformed plan wastes every downstream
#   call. A large mixture-of-experts model with a long context window is the
#   right shape here: the capabilities block it must read is ~2k tokens.
#
# NIM_AGENT_MODEL — Nemotron Nano Omni
#   Called once per DAG node. Each call is narrow and self-contained:
#   summarise this text, synthesise these three chunks, apply this blueprint.
#   A sparse 30B model activating ~3B parameters per token gives most of the
#   quality at a fraction of the latency, and latency is what dominates
#   wall-clock time when four nodes run concurrently.
#
# Model IDs drift. Run list_nim_models() to see what your key can actually
# reach today, and override these constants in the notebook if an ID has moved.
# =============================================================================

NIM_BASE_URL        = "https://integrate.api.nvidia.com/v1"
NIM_PLANNER_MODEL   = "nvidia/nemotron-3-super-120b-a12b"
NIM_AGENT_MODEL     = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
NIM_EMBEDDING_MODEL = "nvidia/nv-embedqa-e5-v5"

OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"

# Vector width per embedding model. A Pinecone index is created with a fixed
# dimension, so this table is what makes the "wrong index" failure detectable
# before a run instead of after it.
EMBEDDING_DIMS = {
    "text-embedding-3-small"   : 1536,
    "text-embedding-3-large"   : 3072,
    "nvidia/nv-embedqa-e5-v5"  : 1024,
}

# Concurrency cap for the Foreman's asyncio semaphore.
#
# The NIM free tier allows roughly 40 requests per minute. Four concurrent
# in-flight requests, each taking a few seconds, sits comfortably under that.
# Raise this to 8 or 16 on a paid tier; nothing else in the codebase changes.
NIM_MAX_CONCURRENT = 4


# =============================================================================
# SECTION B — SECRET RESOLUTION
#
# Three sources, tried in order. The point is portability: the same file runs
# unmodified in Colab, in Docker, and in a local shell.
# =============================================================================

def _get_secret(name: str, required: bool = True):
    """
    Resolve a credential from Colab Secrets, then the environment, then stdin.

    Args:
        name (str):      Secret name, e.g. "NVIDIA_API_KEY".
        required (bool): If True, prompt interactively when nothing is found.
                         If False, return None instead of prompting.

    Returns:
        str | None: The secret value, whitespace-stripped, or None.
    """
    # 1. Colab Secrets (the key icon in the left sidebar).
    try:
        from google.colab import userdata          # noqa: F401
        try:
            value = userdata.get(name)
            if value:
                # Colab occasionally returns a trailing newline on pasted keys,
                # which produces a baffling 401. Strip it here, once.
                return value.strip().splitlines()[0]
        except Exception:
            pass
    except ImportError:
        pass

    # 2. Environment variable — the container / CI path.
    value = os.environ.get(name)
    if value:
        return value.strip()

    # 3. Interactive prompt — the laptop path.
    if required:
        try:
            from getpass import getpass
            value = getpass(f"Enter {name}: ").strip()
            if value:
                os.environ[name] = value
                return value
        except Exception:
            pass

    return None


# =============================================================================
# SECTION C — DEPENDENCY INSTALLATION
# =============================================================================

def install_dependencies(verbose: bool = True) -> bool:
    """
    Install the runtime dependencies.

    The list is short because the engine talks to every API over raw HTTP
    rather than through vendor SDKs. `openai` is installed only so that the
    client objects can carry `base_url` and `api_key` in a familiar shape;
    no SDK call path is used for chat, embeddings, or moderation.

        requests      every outbound API call
        pinecone      vector store client
        tiktoken      token accounting for the trace
        tenacity      exponential backoff on 429 / 5xx
        nest_asyncio  lets asyncio.run() work inside a notebook's live loop

    Returns:
        bool: True if every install succeeded.
    """
    if verbose:
        print("Installing dependencies...")

    packages = [
        # A FLOOR, NOT A PIN — and the reason is worth knowing.
        #
        # openai < 1.55.3 passes `proxies=` to httpx.Client. httpx 0.28 removed
        # that argument, so the two together raise at construction time:
        #
        #   Client.__init__() got an unexpected keyword argument 'proxies'
        #
        # Colab ships a recent httpx, so pinning an exact old openai version
        # DOWNGRADES a working environment into a broken one. A floor pins the
        # fix without freezing the SDK. (initialize_nim_clients() also falls
        # back to a plain credential object if construction fails anyway.)
        "openai>=1.55.3",
        "pinecone==7.0.0",
        "tenacity==9.0.0",
        "tiktoken==0.8.0",
        "nest_asyncio==1.6.0",
        "requests",
        "tqdm==4.67.1",
    ]

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", *packages, "--quiet"],
            check=True,
        )
        if verbose:
            print("All packages installed.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Installation failed: {e}")
        print("Read the pip output above before continuing.")
        return False


# =============================================================================
# SECTION D — CLIENT INITIALISATION
#
# A "client" in this codebase is nothing more than a container for a base URL
# and an API key. helpers_nim.py reads those two attributes off it and issues
# raw HTTP itself; no SDK method is ever called on these objects.
#
# That fact is what makes the fallback below both possible and correct. The
# openai SDK is constructed when it can be, because a real client object is
# what most readers expect to see — but when the installed SDK and httpx
# disagree (see the openai floor in install_dependencies), a five-line stand-in
# carries the same two attributes and the engine cannot tell the difference.
#
# The alternative — letting a dependency the engine does not use take down
# initialisation — is the failure this exists to prevent.
# =============================================================================

class APICredentials:
    """
    A minimal stand-in for an SDK client object.

    Carries exactly what helpers_nim.py reads: `.base_url` and `.api_key`.
    Used when the installed openai SDK cannot be constructed, which happens on
    version-skewed environments and would otherwise be fatal for no reason.
    """

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.api_key  = api_key

    def __repr__(self):
        tail = self.api_key[-4:] if self.api_key else "????"
        return f"APICredentials(base_url={self.base_url!r}, api_key=***{tail})"


def _make_client(base_url: str, api_key: str, label: str, verbose: bool = True):
    """
    Build a client object, preferring the openai SDK and degrading gracefully.

    Args:
        base_url (str): endpoint root.
        api_key (str):  credential.
        label (str):    name used in the fallback warning.
        verbose (bool): print which path was taken.

    Returns:
        openai.OpenAI | APICredentials — indistinguishable to this engine.
    """
    try:
        from openai import OpenAI
        return OpenAI(base_url=base_url, api_key=api_key)
    except Exception as e:
        # The common case is the openai/httpx `proxies` incompatibility. A pip
        # upgrade does not fix a kernel that has already imported the broken
        # module, so falling back here avoids forcing a runtime restart.
        if verbose:
            print(f"  NOTE  openai SDK unusable for {label} ({type(e).__name__}: {e}).")
            print(f"        Falling back to a plain credential object. The engine")
            print(f"        talks raw HTTP, so this changes nothing functionally.")
        return APICredentials(base_url, api_key)


def initialize_nim_clients(verbose: bool = True):
    """
    Build the three clients the engine needs.

    Returns:
        tuple: (nim_client, openai_client, pinecone_client)

        nim_client       OpenAI-compatible client pointed at NVIDIA NIM.
                         Carries every planner and agent call.
        openai_client    Standard OpenAI client. Carries the moderation call,
                         and the embedding call when the index holds OpenAI
                         vectors. May be None if no OpenAI key is available —
                         the engine degrades rather than refusing to start.
        pinecone_client  Pinecone control-plane client. `pc.Index(name)` gives
                         the data-plane handle the adapter wraps.

    Any client that cannot be built comes back as None with its own diagnostic;
    a failure in one never suppresses the other two.
    """
    # No top-level SDK imports here on purpose. `_make_client` imports openai
    # lazily and falls back if it is unusable, and Pinecone is imported inside
    # its own try block below — so an unimportable dependency degrades one
    # client instead of aborting the function before anything is attempted.

    if verbose:
        print("Initializing clients (NIM path)...")

    # Each client is built in its own try block. An earlier version wrapped all
    # three in one, which meant a failure constructing the NIM client returned
    # (None, None, None) and the notebook's next assertion blamed Pinecone for
    # a problem it had nothing to do with. Independent failures should produce
    # independent diagnostics.
    nim_client = openai_client = pinecone_client = None
    failures = []

    # ---- NIM: all LLM inference -----------------------------------------
    try:
        nvidia_api_key = _get_secret("NVIDIA_API_KEY")
        if not nvidia_api_key:
            raise RuntimeError("NVIDIA_API_KEY not found in Colab Secrets or the environment.")
        if not nvidia_api_key.startswith("nvapi-"):
            raise RuntimeError(
                "NVIDIA_API_KEY does not start with 'nvapi-'. "
                "Free keys are issued at https://build.nvidia.com"
            )

        nim_client = _make_client(NIM_BASE_URL, nvidia_api_key, "NIM", verbose)
        if verbose:
            print(f"  NIM client        {NIM_BASE_URL}")
            print(f"    planner model   {NIM_PLANNER_MODEL}")
            print(f"    agent model     {NIM_AGENT_MODEL}")
            print(f"    concurrency cap {NIM_MAX_CONCURRENT}")
    except Exception as e:
        failures.append(f"NIM client: {e}")
        print(f"  FAIL  NIM client — {e}")

    # ---- OpenAI: moderation, and embeddings on the hybrid path -----------
    # Not fatal if absent. Gate 1 keeps sanitisation and business rules;
    # only the moderation sub-check degrades to a pass-through.
    try:
        openai_api_key = _get_secret("API_KEY", required=False) \
                         or _get_secret("OPENAI_API_KEY", required=False)
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
            openai_client = _make_client("https://api.openai.com/v1",
                                         openai_api_key, "OpenAI", verbose)
            if verbose:
                print("  OpenAI client     api.openai.com "
                      "(moderation + OpenAI embeddings)")
        else:
            if verbose:
                print("  OpenAI client     NOT configured")
                print("    Moderation will pass through. Sanitisation and")
                print("    business rules at Gate 1 still apply.")
    except Exception as e:
        print(f"  WARN  OpenAI client — {e} (continuing without it)")

    # ---- Pinecone: the knowledge store -----------------------------------
    try:
        from pinecone import Pinecone
        pinecone_api_key = _get_secret("PINECONE_API_KEY")
        if not pinecone_api_key:
            raise RuntimeError("PINECONE_API_KEY not found in Colab Secrets or the environment.")
        pinecone_client = Pinecone(api_key=pinecone_api_key)
        if verbose:
            print("  Pinecone client   connected")
    except Exception as e:
        failures.append(f"Pinecone client: {e}")
        print(f"  FAIL  Pinecone client — {e}")

    if verbose:
        print()
        print("Ready." if not failures
              else f"{len(failures)} client(s) failed — see above.")

    return nim_client, openai_client, pinecone_client


# =============================================================================
# SECTION E — CONNECTIVITY PROBE
#
# Every call in this codebase goes out over raw HTTP, and so does this probe.
# That is deliberate: if the probe used the SDK and the engine did not, a green
# probe would not prove the engine can reach anything.
# =============================================================================

def verify_nim_connectivity(nim_client, verbose: bool = True) -> bool:
    """
    Send a 1-token probe to both NIM models and report precisely what happened.

    Roughly 20 tokens total. Safe to run as often as you like, and worth running
    before every session — an expired key surfaces here in two seconds instead
    of halfway through an eight-node DAG.

    Args:
        nim_client: client from initialize_nim_clients(); only its base_url
                    and api_key are read.
        verbose:    print per-model detail.

    Returns:
        bool: True only if both models returned HTTP 200.
    """
    import requests as _req

    print("Verifying NIM connectivity (raw HTTP)...")
    print()

    try:
        import openai as _oai
        print(f"  openai SDK      {_oai.__version__}")
    except Exception:
        print("  openai SDK      not installed")

    try:
        api_key = nim_client.api_key
        shown = api_key[:12] + "..." + api_key[-4:] if len(api_key) > 16 else "too short"
    except Exception:
        api_key, shown = None, "unreadable"
    print(f"  NVIDIA_API_KEY  {shown}")

    try:
        base_url = str(nim_client.base_url).rstrip("/")
    except Exception:
        base_url = NIM_BASE_URL
    print(f"  base URL        {base_url}")
    print()

    endpoint = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type" : "application/json",
    }
    probe = {
        "messages"   : [{"role": "user", "content": "Reply with exactly one word: ready"}],
        "max_tokens" : 64,
        "temperature": 0.0,
    }

    # Failure modes worth naming individually. A bare "request failed" sends
    # the reader to the wrong fix; each of these has a different remedy.
    hints = {
        401: "Key invalid or expired. Regenerate at https://build.nvidia.com",
        402: "Credits exhausted. Check your balance at https://build.nvidia.com",
        404: "Model ID not found. Run list_nim_models() to see live IDs.",
        429: "Rate limited (free tier is ~40 RPM). Wait 60s and retry.",
    }

    results = {}
    for label, model in [("planner (Super)", NIM_PLANNER_MODEL),
                         ("agents  (Nano) ", NIM_AGENT_MODEL)]:
        try:
            r = _req.post(endpoint, headers=headers,
                          json={**probe, "model": model}, timeout=30)
            if r.status_code == 200:
                data = r.json()
                msg = data["choices"][0]["message"]
                # Reasoning models sometimes leave `content` empty and put the
                # text in `reasoning_content`. Both count as a live endpoint.
                text = (msg.get("content") or "").strip()
                if not text:
                    text = ((msg.get("reasoning_content") or "")[:40] + " [reasoning]").strip()
                used = data.get("usage", {}).get("total_tokens", "?")
                results[label] = True
                if verbose:
                    print(f"  OK    {label}  '{text}'  [{used} tokens]")
            else:
                results[label] = False
                print(f"  FAIL  {label}  HTTP {r.status_code}")
                print(f"        {hints.get(r.status_code, r.text[:200])}")
        except _req.exceptions.Timeout:
            results[label] = False
            print(f"  FAIL  {label}  timeout after 30s — NIM may be under load")
        except _req.exceptions.ConnectionError:
            results[label] = False
            print(f"  FAIL  {label}  connection error — check network access")
        except Exception as e:
            results[label] = False
            print(f"  FAIL  {label}  {type(e).__name__}: {e}")

    print()
    ok = bool(results) and all(results.values())
    print("NIM connectivity verified." if ok
          else "NIM connectivity check FAILED — see above.")
    return ok


def list_nim_models(nim_client, contains: str = "nemotron", limit: int = 40):
    """
    Ask the NIM endpoint which model IDs your key can reach.

    Model IDs move between preview and general availability, and names change.
    Rather than trusting the constants at the top of this file, call this and
    read the answer from the endpoint itself.

    Args:
        nim_client: client from initialize_nim_clients().
        contains:   case-insensitive substring filter. Pass "" for everything.
        limit:      maximum IDs to print.

    Returns:
        list[str]: matching model IDs, sorted.
    """
    import requests as _req

    base_url = str(nim_client.base_url).rstrip("/")
    try:
        r = _req.get(f"{base_url}/models",
                     headers={"Authorization": f"Bearer {nim_client.api_key}"},
                     timeout=30)
        r.raise_for_status()
        ids = sorted(m["id"] for m in r.json().get("data", []))
    except Exception as e:
        print(f"Could not list models: {e}")
        return []

    needle = (contains or "").lower()
    hits = [i for i in ids if needle in i.lower()]
    print(f"{len(hits)} of {len(ids)} model(s) match '{contains}':")
    for i in hits[:limit]:
        print(f"  {i}")
    if len(hits) > limit:
        print(f"  ... and {len(hits) - limit} more")
    return hits


# =============================================================================
# SECTION F — EMBEDDING BACKEND RESOLUTION
#
# This is the fork in the road for the NIM edition, and it is worth being
# explicit about because getting it wrong produces no error at all — just
# retrieval that returns confident nonsense.
#
# A Pinecone index stores vectors of a fixed width, produced by one specific
# embedding model. Query vectors must come from the *same* model. Query an
# OpenAI-embedded index with NVIDIA vectors and one of two things happens:
# the dimensions differ and Pinecone rejects the query, or the dimensions
# happen to match and you get similarity scores computed across two unrelated
# coordinate systems. The second failure is the dangerous one.
#
#   "openai"  Query the index built by Chapter08 and Chapter09 ingestion.
#             1536-dim OpenAI vectors. Nothing to re-ingest. LLM inference is
#             still 100% NIM; only the embedding call touches OpenAI.
#
#   "nvidia"  Query an index you have re-ingested with NVIDIA vectors.
#             1024-dim. Removes the last inference dependency on OpenAI, at
#             the cost of rebuilding the index.
# =============================================================================

def resolve_embedding_backend(backend: str = "openai",
                              openai_index: str = "genai-mas-mcp-ch3",
                              nvidia_index: str = "genai-mas-mcp-nim") -> dict:
    """
    Turn a one-word backend choice into a consistent configuration bundle.

    Args:
        backend (str):      "openai" or "nvidia".
        openai_index (str): index holding OpenAI-embedded vectors.
        nvidia_index (str): index holding NVIDIA-embedded vectors.

    Returns:
        dict: {backend, index_name, embedding_model, dimension, client_role}

              client_role is "openai" or "nim" and tells the notebook which
              client object to hand to the PineconeAdapter. The adapter's
              embedding client and the index contents must agree.

    Raises:
        ValueError: on an unrecognised backend.
    """
    backend = (backend or "").strip().lower()

    if backend == "openai":
        model = OPENAI_EMBEDDING_MODEL
        return {
            "backend"        : "openai",
            "index_name"     : openai_index,
            "embedding_model": model,
            "dimension"      : EMBEDDING_DIMS[model],
            "client_role"    : "openai",
            "note"           : ("Matches the index produced by Chapter08 and "
                                "Chapter09 ingestion. No re-indexing required."),
        }

    if backend == "nvidia":
        model = NIM_EMBEDDING_MODEL
        return {
            "backend"        : "nvidia",
            "index_name"     : nvidia_index,
            "embedding_model": model,
            "dimension"      : EMBEDDING_DIMS[model],
            "client_role"    : "nim",
            "note"           : ("Requires an index re-ingested with NVIDIA "
                                "vectors. Chapter08/09 output will NOT work."),
        }

    raise ValueError(
        f"Unknown embedding backend '{backend}'. Use 'openai' or 'nvidia'."
    )


# =============================================================================
# SECTION G — INDEX PRE-FLIGHT
#
# Two failure modes cost a full run and report nothing:
#
#   1. An empty namespace returns zero matches, and zero matches is not an
#      error. The Researcher reports "no data found", the Writer writes around
#      the hole, and the dashboard is green.
#   2. A dimension mismatch either throws deep inside Pinecone or, worse,
#      silently returns the nearest vectors in a coordinate system that means
#      nothing.
#
# One metadata request rules out both.
# =============================================================================

def _field(obj, name: str, default=None):
    """
    Read a field from an object that may be a dict, a model, or neither.

    SDK responses drift between plain dicts and typed model objects across
    major versions. Rather than pinning a version to keep one access style
    valid, try mapping access, then attribute access, then give up quietly.
    """
    if obj is None:
        return default
    try:
        if hasattr(obj, "get"):
            value = obj.get(name, None)
            if value is not None:
                return value
    except Exception:
        pass
    return getattr(obj, name, default)


def check_index(pinecone_client, index_name: str, expected_dim: int,
                required_namespaces=("ContextLibrary", "KnowledgeStore")) -> bool:
    """
    Confirm the index exists, has the right dimension, and is populated.

    Args:
        pinecone_client:     client from initialize_nim_clients().
        index_name (str):    index to inspect.
        expected_dim (int):  dimension implied by the chosen embedding model.
        required_namespaces: namespaces that must contain at least one vector.

    Returns:
        bool: True if the index is safe to query.

    Blocking conditions are exactly two: dimension mismatch, and an empty or
    missing required namespace. Everything else is printed as advice.
    """
    print(f"Pre-flight: inspecting index '{index_name}'...")
    print()

    # ---- Does the index exist at all? -----------------------------------
    # The Pinecone SDK has returned several different shapes across major
    # versions: a list of strings, a list of dicts, a list of model objects,
    # and an IndexList exposing .names(). Rather than pinning a version, read
    # whichever shape arrives.
    try:
        raw = pinecone_client.list_indexes()
        if hasattr(raw, "names"):
            names = list(raw.names())
        else:
            names = [_field(item, "name") for item in raw]
        names = [n for n in names if n]
    except Exception as e:
        print(f"  FAIL  could not list indexes: {e}")
        return False

    if index_name not in names:
        print(f"  FAIL  index '{index_name}' does not exist.")
        print(f"        Indexes on this key: {names or '(none)'}")
        print( "        Run the Chapter08 and Chapter09 ingestion notebooks first.")
        return False

    # ---- Dimension and namespace occupancy ------------------------------
    try:
        index = pinecone_client.Index(index_name)
        stats = index.describe_index_stats()
    except Exception as e:
        print(f"  FAIL  could not read index stats: {e}")
        return False

    dim   = _field(stats, "dimension")
    total = _field(stats, "total_vector_count", 0)
    ns    = _field(stats, "namespaces", {}) or {}

    print(f"  dimension        {dim}")
    print(f"  total vectors    {total}")
    print(f"  namespaces       {sorted(ns.keys()) or '(none)'}")
    print()

    ok = True

    if dim != expected_dim:
        ok = False
        print(f"  FAIL  dimension mismatch: index is {dim}, "
              f"embedding model produces {expected_dim}.")
        print( "        The index and the embedding model disagree. Either")
        print( "        switch EMBEDDING_BACKEND, or point INDEX_NAME at the")
        print( "        index that matches your embedding model.")

    for name in required_namespaces:
        entry = ns.get(name) if hasattr(ns, "get") else None
        count = _field(entry, "vector_count", 0) if entry is not None else 0
        if count > 0:
            print(f"  OK    namespace '{name}' holds {count} vector(s)")
        else:
            ok = False
            print(f"  FAIL  namespace '{name}' is empty or missing.")
            if name == "ContextLibrary":
                print( "        Blueprints live here. The Librarian will return")
                print( "        a neutral default and the Writer will lose its")
                print( "        style contract.")
            if name == "KnowledgeStore":
                print( "        Source documents live here. Every Researcher")
                print( "        node will report 'no data found'.")
            print( "        Fix: run Chapter08/Data_Ingestion.ipynb, then")
            print( "        Chapter09/Data_Ingestion_Marketing.ipynb with")
            print( "        clear_index=False so marketing appends to legal.")

    print()
    print("Index ready." if ok else "Index NOT ready — fix the failures above.")
    return ok
