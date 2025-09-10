# utils.py

import os
import subprocess
import sys

def install_dependencies():
    """
    Installs all the required pip packages with specific versions.
    """
    print("🚀 Installing required packages...")
    try:
        # Using subprocess to run pip commands
        subprocess.run([sys.executable, "-m", "pip", "install", "tqdm==4.67.1", "--upgrade", "--quiet"], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "openai==1.104.2", "pinecone==7.0.0", "tenacity==8.3.0", "--quiet"], check=True)
        print("✅ All packages installed successfully.")
    except subprocess.CalledProcessError as e:
        print(f"🛑 Error during installation: {e}")

from openai import OpenAI
from pinecone import Pinecone, ServerlessSpec
from google.colab import userdata

def initialize_clients():
    """
    Loads API keys from Colab Secrets and initializes OpenAI and Pinecone clients.
    Returns the initialized clients.
    """
    print("\n🔑 Initializing API clients...")
    try:
        # Load OpenAI API Key
        os.environ["OPENAI_API_KEY"] = userdata.get("API_KEY")
        openai_client = OpenAI()
        print("   - OpenAI client initialized.")

        # Load Pinecone API Key and initialize client
        pinecone_api_key = userdata.get('PINECONE_API_KEY')
        pinecone_client = Pinecone(api_key=pinecone_api_key)
        print("   - Pinecone client initialized.")

        print("✅ Clients initialized successfully.")
        return openai_client, pinecone_client

    except userdata.SecretNotFoundError as e:
        print(f"🛑 Secret not found: {e}. Please add the required API keys to Colab Secrets.")
        return None, None
    except Exception as e:
        print(f"An error occurred during client initialization: {e}")
        return None, None
