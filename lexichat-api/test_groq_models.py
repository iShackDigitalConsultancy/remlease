import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

try:
    completion = client.chat.completions.create(
        model='llama3-8b-8192',
        messages=[{'role': 'user', 'content': 'test'}]
    )
    print("llama3-8b-8192 works!")
except Exception as e:
    print(f"Error: {e}")
