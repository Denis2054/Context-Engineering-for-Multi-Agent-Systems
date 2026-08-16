# =============================================================================
# utils.py  —  Setup, Client Initialisation, and NIM Support
# =============================================================================

import os
import subprocess
import sys

NIM_PLANNER_MODEL   = "nvidia/nemotron-3-super-120b-a12b"
NIM_AGENT_MODEL     = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning"
NIM_EMBEDDING_MODEL = "nvidia/nv-embedqa-e5-v5"

NIM_MAX_CONCURRENT = 4

def install_dependencies():
    print("🚀 Skipping programmatic pip install in Docker. Dependencies managed by requirements.txt.")

def initialize_clients():
    """Path A — Original OpenAI Client"""
    from openai import OpenAI
    from pinecone import Pinecone

    print("\n🔑 Initializing API clients (OpenAI path)...")
    try:
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not found.")
            
        openai_client = OpenAI(api_key=openai_api_key)
        print("   - OpenAI client initialized.")

        pinecone_api_key = os.environ.get("PINECONE_API_KEY")
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY environment variable not found.")
            
        pinecone_client  = Pinecone(api_key=pinecone_api_key)
        print("   - Pinecone client initialized.")

        print("✅ Clients initialized successfully (OpenAI path).")
        return openai_client, pinecone_client

    except Exception as e:
        print(f"🛑 An error occurred during client initialization: {e}")
        return None, None

def initialize_nim_clients():
    """Path B — NIM (NVIDIA Inference Microservices) + Pinecone."""
    from openai import OpenAI
    from pinecone import Pinecone

    print("\n🚀 Initializing API clients (NIM path)...")
    try:
        # ── NIM LLM client ────────────────────────────────────────────────────
        nvidia_api_key = os.environ.get("NVIDIA_API_KEY")

        assert nvidia_api_key and nvidia_api_key.startswith("nvapi-"), (
            "NVIDIA_API_KEY must start with 'nvapi-'. Make sure you pass it in your docker run command."
        )

        nim_client = OpenAI(
            base_url = "https://integrate.api.nvidia.com/v1",
            api_key  = nvidia_api_key,
        )
        print(f"   - NIM client initialized.")
        print(f"     Planner model : {NIM_PLANNER_MODEL}")
        print(f"     Agent model   : {NIM_AGENT_MODEL}")
        print(f"     Rate limit    : 40 RPM (free tier)")
        print(f"     Max concurrent: {NIM_MAX_CONCURRENT} agent nodes")

        # ── OpenAI client — embeddings only ──────────────────────────────────
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable not found. Required for embeddings.")
            
        openai_client = OpenAI(api_key=openai_api_key)
        print("   - OpenAI client initialized (embeddings only).")

        # ── Pinecone client ───────────────────────────────────────────────────
        pinecone_api_key = os.environ.get("PINECONE_API_KEY")
        if not pinecone_api_key:
            raise ValueError("PINECONE_API_KEY environment variable not found.")
            
        pinecone_client  = Pinecone(api_key=pinecone_api_key)
        print("   - Pinecone client initialized.")

        print("\n✅ NIM path ready.")
        return nim_client, openai_client, pinecone_client

    except Exception as e:
        print(f"🛑 Error during NIM client initialization: {e}")
        return None, None, None

def verify_nim_connectivity(nim_client, verbose=True):
    # Standard connectivity check remains unchanged...
    import requests as _req
    
    print("🔍 Verifying NIM connectivity...")
    try:
        api_key = nim_client.api_key
        base_url = str(nim_client.base_url)
    except Exception:
        return False
        
    endpoint = base_url.rstrip("/") + "/chat/completions"
    headers  = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type" : "application/json",
    }
    probe_payload = {
        "messages"   : [{"role": "user", "content": "Reply ready"}],
        "max_tokens" : 10,
        "temperature": 0.0,
        "model": NIM_PLANNER_MODEL
    }

    try:
        r = _req.post(endpoint, headers=headers, json=probe_payload, timeout=10)
        if r.status_code == 200:
            print("✅ NIM connectivity verified.")
            return True
        else:
            print(f"🛑 NIM connectivity check FAILED: {r.status_code} {r.text[:100]}")
            return False
    except Exception as e:
        print(f"🛑 NIM connectivity check FAILED: {e}")
        return False