import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# --- Cleaned up imports without _nim ---
import utils
from engine import context_engine
from registry import AGENT_TOOLKIT
from harness import Harness
from adapters import PineconeAdapter

app = FastAPI(title="Universal Context Engine API")

print("🚀 Initializing Engine Services...")

try:
    # 1. Initialize clients using the actual function from your utils.py
    nim_client, openai_client, pinecone_client = utils.initialize_nim_clients()
    
    if not nim_client:
        raise RuntimeError("Failed to initialize NIM clients. Check your API keys in the Docker run command.")

    # 2. Initialize the Pinecone Adapter exactly as you did in the notebook
    INDEX_NAME = "genai-mas-mcp-ch3" # Update this if your Pinecone index is named differently
    NAMESPACE_MAP = {
        "General"   : {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
        "Legal"     : {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
        "Marketing" : {"context": "ContextLibrary", "knowledge": "KnowledgeStore"},
    }
    
    pinecone_adapter = PineconeAdapter(
        client          = openai_client,
        index           = pinecone_client.Index(INDEX_NAME),
        embedding_model = "text-embedding-3-small",
        namespaces      = NAMESPACE_MAP,
    )
    
    # 3. Initialize the Harness (Gates 1 & 2)
    gate = Harness(client=openai_client) 
    
    print("✅ Services initialized successfully.")
except Exception as e:
    print(f"❌ Error during service initialization: {e}")
    raise e

# --- API Endpoints ---
class GoalRequest(BaseModel):
    goal: str
    moderation_active: bool = True

@app.post("/execute")
def execute_task(request: GoalRequest):
    try:
        print(f"🎯 Received goal: {request.goal}")
        
        # Trigger the engine with all the NIM parameters
        result, trace = context_engine(
            goal=request.goal,
            client=nim_client,
            adapter=pinecone_adapter,
            generation_model=utils.NIM_PLANNER_MODEL,
            embedding_model="text-embedding-3-small",
            registry=AGENT_TOOLKIT,
            harness=gate,
            agent_model=utils.NIM_AGENT_MODEL
        )
        
        return {
            "status": "success", 
            "output": result, 
            "trace_summary": trace.summary()
        }
        
    except Exception as e:
        print(f"Error processing task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}