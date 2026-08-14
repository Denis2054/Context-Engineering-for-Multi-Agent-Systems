# lc_utils.py
# =============================================================================
# Universal Context Engine — LangChain Edition
# Installation, credentials, and index diagnostics.
#
# Replaces: utils.py
#
# Difference from the original: the original built an `openai.OpenAI` client and
# a `pinecone.Pinecone` client and passed them around by hand. LangChain reads
# credentials from environment variables and builds its own clients, so all this
# module does is move the Colab Secrets into os.environ.
#
# HONEST NOTE ON THE DEPENDENCY SURFACE
# -------------------------------------
# check_index() below imports the Pinecone SDK directly. It is an administrative
# diagnostic, not part of the engine's runtime path — no LangChain abstraction
# exposes describe_index_stats(). It is declared here rather than hidden.
# =============================================================================

from __future__ import annotations

import logging
import os
import subprocess
import sys
from typing import Iterable, Optional, Sequence, Tuple

# Package versions. LangChain moves fast; pin a major range so a notebook that
# works today still works next month. These pins are mirrored in
# requirements.txt — change both together.
PACKAGES = [
    "langchain>=1.0,<2.0",          # create_agent (Route B)
    "langchain-core>=1.0,<2.0",     # Runnables, prompts, tools, documents
    "langchain-openai>=1.0,<2.0",   # ChatOpenAI, OpenAIEmbeddings
    "langchain-pinecone>=0.2,<1.0", # PineconeVectorStore
    "langgraph>=1.0,<2.0",          # StateGraph orchestration
    "pydantic>=2.0,<3.0",           # the Plan schema
    "openai>=1.0,<3.0",             # moderation endpoint fallback (see lc_helpers)
    "pinecone>=5.0,<8.0",           # check_index() only
    "markdown>=3.4",                # the trace dashboard only
]

# The values the engine expects to find in Pinecone. Mirrored in
# lc_helpers.CONFIG; kept here so the pre-flight check can run before the
# engine is built.
EXPECTED_INDEX = "genai-mas-mcp-ch3"
EXPECTED_DIMENSION = 1536           # text-embedding-3-small
EXPECTED_NAMESPACES = ("ContextLibrary", "KnowledgeStore")


# =============================================================================
# 1. Installation
# =============================================================================

def install_dependencies(extra: Optional[Iterable[str]] = None,
                         quiet: bool = True) -> bool:
    """
    Install every package the LangChain engine needs.

    Returns True on success, False on failure. The failure branch prints pip's
    own stderr rather than swallowing it, because a silent install failure
    surfaces later as an ImportError three cells away from its cause.
    """
    pkgs = list(PACKAGES) + list(extra or [])
    print(f"Installing {len(pkgs)} packages...")
    cmd = [sys.executable, "-m", "pip", "install", *pkgs]
    if quiet:
        cmd.append("--quiet")
    try:
        subprocess.run(cmd, check=True, capture_output=quiet, text=True)
        print("All packages installed successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Installation FAILED (exit code {e.returncode}).")
        if e.stderr:
            print(e.stderr[-2000:])
        return False


# =============================================================================
# 2. LangSmith — validated, never merely assumed
#
# LangSmith is optional. The failure mode worth engineering against is a key
# that EXISTS but is not USABLE: expired, revoked, or issued for a different
# workspace. Setting LANGSMITH_TRACING=true on the strength of the secret merely
# being present produces a 403 on every trace flush:
#
#   WARNING:langsmith.client:Failed to send compressed multipart ingest:
#   ... HTTPError('403 Client Error: Forbidden ...')
#
# That is log noise, wasted latency on retries, and — in a delivered notebook —
# indistinguishable from a broken build. So the key is exercised once, against a
# cheap authenticated endpoint, before tracing is switched on.
# =============================================================================

def _validate_langsmith(api_key: str) -> Tuple[bool, Optional[str]]:
    """
    Return (usable, reason). Makes one authenticated read against /sessions.

    A bad key fails in well under a second, so this costs nothing measurable at
    start-up and removes a warning that would otherwise repeat on every run.
    """
    try:
        from langsmith import Client
    except ImportError:
        return False, "the 'langsmith' package is not installed"
    try:
        next(iter(Client(api_key=api_key).list_projects(limit=1)), None)
        return True, None
    except Exception as e:
        detail = str(e).splitlines()[0] if str(e) else ""
        return False, f"{type(e).__name__}: {detail[:160]}"


def disable_langsmith(quiet: bool = False) -> None:
    """
    Turn tracing off and stop the client from emitting warnings.

    Both the current and the legacy environment variables are cleared: a stale
    LANGCHAIN_TRACING_V2 left in the environment re-enables tracing on its own.

    Call this at any point to silence LangSmith mid-session. Note that LangChain
    caches its tracer on first use, so if a run has already been traced you must
    restart the runtime for this to take full effect.
    """
    os.environ["LANGSMITH_TRACING"] = "false"
    os.environ["LANGCHAIN_TRACING_V2"] = "false"
    os.environ.pop("LANGSMITH_API_KEY", None)
    os.environ.pop("LANGCHAIN_API_KEY", None)
    # Once tracing is deliberately off, anything this logger emits is spurious.
    logging.getLogger("langsmith.client").setLevel(logging.ERROR)
    if not quiet:
        print("   - LangSmith tracing disabled.")


# =============================================================================
# 3. Credentials
# =============================================================================

def initialize_environment(
    openai_secret: str = "API_KEY",
    pinecone_secret: str = "PINECONE_API_KEY",
    langsmith_secret: str = "LANGSMITH_API_KEY",
    langsmith_project: str = "universal-context-engine-langchain",
) -> bool:
    """
    Load API keys from Colab Secrets into environment variables.

    LangChain reads OPENAI_API_KEY and PINECONE_API_KEY implicitly, so nothing
    else has to be passed around. Returns True on success.

    The secret names default to the same ones the original notebook used, so an
    existing Colab setup works unchanged. Outside Colab, the function falls back
    to environment variables that are already set.
    """
    print("Initializing environment...")
    try:
        from google.colab import userdata  # noqa: F401
        get = userdata.get
        in_colab = True
    except Exception:
        def get(key):
            return os.environ.get(key)
        in_colab = False
        print("   - Not running in Colab: falling back to existing env vars.")

    try:
        openai_key = get(openai_secret)
        if not openai_key:
            raise ValueError(f"Secret '{openai_secret}' is empty or missing.")
        os.environ["OPENAI_API_KEY"] = openai_key
        print("   - OPENAI_API_KEY set.")

        pinecone_key = get(pinecone_secret)
        if not pinecone_key:
            raise ValueError(f"Secret '{pinecone_secret}' is empty or missing.")
        os.environ["PINECONE_API_KEY"] = pinecone_key
        print("   - PINECONE_API_KEY set.")

        # LangSmith tracing is optional, and is enabled only if the key is
        # proven to work. A present-but-unusable key is worse than no key: it
        # produces a 403 warning on every trace flush without adding anything.
        try:
            ls_key = get(langsmith_secret)
        except Exception:
            ls_key = None

        if not ls_key:
            disable_langsmith(quiet=True)
            print("   - LangSmith not configured (optional). Local tracing only.")
        else:
            usable, reason = _validate_langsmith(ls_key)
            if usable:
                os.environ["LANGSMITH_API_KEY"] = ls_key
                os.environ["LANGSMITH_TRACING"] = "true"
                os.environ["LANGSMITH_PROJECT"] = langsmith_project
                print(f"   - LangSmith key verified. Tracing enabled "
                      f"(project: {langsmith_project}).")
            else:
                disable_langsmith(quiet=True)
                print("   - LangSmith key present but NOT usable — tracing disabled.")
                print(f"     Reason: {reason}")
                print("     A 403 means the key is expired, revoked, or belongs to "
                      "another workspace.")
                print("     Nothing else is affected: the engine's own trace and the "
                      "HTML dashboard")
                print("     do not depend on LangSmith. Remove the secret, or replace "
                      "it, to clear this.")

        print("Environment ready.")
        return True

    except Exception as e:
        print(f"Setup failed: {e}")
        if in_colab:
            print("   Add your keys under the key icon in the Colab sidebar:")
            print(f"     {openai_secret}      = your OpenAI key")
            print(f"     {pinecone_secret}    = your Pinecone key")
            print(f"     {langsmith_secret}   = your LangSmith key (optional)")
        else:
            print("   Export them before launching, e.g.:")
            print(f"     export {openai_secret}=sk-...")
            print(f"     export {pinecone_secret}=pcsk_...")
        return False


# =============================================================================
# 4. Pre-flight index diagnostic
# =============================================================================

def check_index(index_name: str = EXPECTED_INDEX,
                namespaces: Sequence[str] = EXPECTED_NAMESPACES,
                expected_dimension: int = EXPECTED_DIMENSION) -> bool:
    """
    Confirm the index exists, has the expected dimension, and that both
    namespaces contain vectors. Returns True only if all three hold.

    This is the cheapest possible way to catch the two failure modes that
    otherwise waste a full run: an unpopulated namespace (zero documents, no
    error) and a dimension mismatch (irrelevant answers, no error).

    Uses the Pinecone SDK directly because this is an administrative check, not
    part of the engine's runtime path.
    """
    try:
        from pinecone import Pinecone
    except ImportError:
        print("The 'pinecone' package is not installed. Run install_dependencies() first.")
        return False

    try:
        pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
        stats = pc.Index(index_name).describe_index_stats()
    except KeyError:
        print("PINECONE_API_KEY is not set. Run initialize_environment() first.")
        return False
    except Exception as e:
        print(f"Could not inspect index '{index_name}': {e}")
        return False

    dimension = stats.get("dimension")
    total = stats.get("total_vector_count")
    print(f"Index '{index_name}' — dimension {dimension}, total vectors {total}")

    ok = True
    if dimension is not None and dimension != expected_dimension:
        print(f"   [FAIL ] dimension is {dimension}, expected {expected_dimension} "
              f"(text-embedding-3-small). This index was written with a different "
              f"embedding model and cannot be read by this engine.")
        ok = False

    ns_stats = stats.get("namespaces", {}) or {}
    engine_total = 0
    for name in namespaces:
        count = (ns_stats.get(name) or {}).get("vector_count", 0)
        engine_total += count
        mark = "OK   " if count else "EMPTY"
        print(f"   [{mark}] namespace '{name}': {count} vectors")
        if not count:
            ok = False

    # Account for every remaining vector. An index whose reported total is far
    # larger than the two namespaces the engine reads is normal -- earlier
    # chapters write elsewhere in the same index -- but an unexplained
    # difference invites exactly the wrong question in a review, so name it.
    others = {n: (v or {}).get("vector_count", 0)
              for n, v in ns_stats.items() if n not in namespaces}
    other_total = sum(others.values())
    if other_total:
        print(f"   [INFO ] {engine_total} vector(s) in the two engine namespaces; "
              f"{other_total} elsewhere in this index, not read by this engine:")
        for n, c in sorted(others.items(), key=lambda kv: -kv[1]):
            print(f"            - '{n or '(default)'}': {c} vectors")

    # A ContextLibrary this small cannot support meaningful k=1 retrieval.
    blueprint_ns = namespaces[0] if namespaces else None
    blueprint_count = (ns_stats.get(blueprint_ns) or {}).get("vector_count", 0)
    if 0 < blueprint_count < 5:
        print(f"   [WARN ] only {blueprint_count} blueprint(s) in "
              f"'{blueprint_ns}'. The Librarian retrieves at k=1, so with a "
              f"library this small the blueprint it returns may not match the "
              f"requested intent. Run lc_helpers.blueprint_diagnostics() to see "
              f"the actual scores before demonstrating this engine.")

    if not ok:
        print("\n   Populate the index before running the engine:")
        print("     1. Chapter08/Data_Ingestion.ipynb            (legal data)")
        print("     2. Chapter09/Data_Ingestion_Marketing.ipynb  with clear_index=False")
        print("   The second must append, not replace, or the legal namespace is lost.")
    return ok
