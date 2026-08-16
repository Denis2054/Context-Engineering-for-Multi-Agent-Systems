import logging
import re
import tiktoken

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def call_llm_robust(system_prompt, user_prompt, client, generation_model, json_mode=False):
    import requests as _req
    logging.info("Attempting to call LLM (raw HTTP)...")
    try:
        base_url = str(client.base_url).rstrip("/")
        api_key  = client.api_key
        endpoint = f"{base_url}/chat/completions"
        headers  = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {
            "model": generation_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if json_mode: payload["response_format"] = {"type": "json_object"}
        r = _req.post(endpoint, headers=headers, json=payload, timeout=120)
        
        if r.status_code == 200:
            data = r.json()
            content = data["choices"][0]["message"].get("content") or data["choices"][0]["message"].get("reasoning_content") or ""
            return content.strip()
        else:
            raise Exception(f"HTTP {r.status_code}: {r.text[:400]}")
    except Exception as e:
        logging.error(f"LLM Error: {e}")
        raise e

def get_embedding(text, client, embedding_model):
    import requests as _req
    import os
    text = text.replace("\n", " ")
    try:
        # FIX: Dual-Provider Routing
        # If the model is an OpenAI model, bypass NIM and route directly to OpenAI
        if "text-embedding" in embedding_model:
            base_url = "https://api.openai.com/v1"
            api_key  = os.environ.get("OPENAI_API_KEY")
            payload  = {"model": embedding_model, "input": text}
        else:
            base_url = str(client.base_url).rstrip("/")
            api_key  = client.api_key
            payload  = {"model": embedding_model, "input": [text], "input_type": "query"}

        endpoint = f"{base_url}/embeddings"
        headers  = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        
        r = _req.post(endpoint, headers=headers, json=payload, timeout=30)
        if r.status_code == 200:
            return r.json()["data"][0]["embedding"]
        else:
            raise Exception(f"HTTP {r.status_code}: {r.text[:400]}")
    except Exception as e:
        logging.error(f"Embedding error: {e}")
        raise e

def create_mcp_message(sender, content, metadata=None):
    return {"protocol_version": "2.0", "sender": sender, "content": content, "metadata": metadata or {}}

def query_pinecone(query_text, namespace, top_k, index, client, embedding_model):
    logging.info(f"Querying Pinecone namespace '{namespace}'...")
    query_embedding = get_embedding(query_text, client=client, embedding_model=embedding_model)
    response = index.query(vector=query_embedding, namespace=namespace, top_k=top_k, include_metadata=True)
    return response['matches']

def count_tokens(text, model="gpt-5.1"):
    try: encoding = tiktoken.encoding_for_model(model)
    except: encoding = tiktoken.get_encoding("cl100k_base")
    return len(encoding.encode(text))

def helper_sanitize_input(text):
    patterns = [r"ignore previous instructions", r"ignore all prior commands", r"you are now in.*mode", r"act as", r"ignore any legal advice", r"sudo|apt-get|yum|pip install"]
    for p in patterns:
        if re.search(p, text, re.IGNORECASE): raise ValueError("Threat detected.")
    return text

def helper_moderate_content(text, client):
    import requests as _req
    import os
    try:
        api_key = os.environ.get("OPENAI_API_KEY")
        r = _req.post("https://api.openai.com/v1/moderations", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"input": text}, timeout=15)
        if r.status_code == 200:
            res = r.json()["results"][0]
            return {"flagged": res["flagged"], "categories": res["categories"], "scores": res["category_scores"]}
        return {"flagged": False, "categories": {}, "scores": {}}
    except:
        return {"flagged": False, "categories": {}, "scores": {}}