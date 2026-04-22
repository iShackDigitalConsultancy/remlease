from dependencies import vo
from typing import List
import time

def get_embedding(text: str):
    return vo.embed([text], model="voyage-law-2").embeddings[0]

def get_embeddings(texts: List[str]):
    all_embeddings = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i+50]
        result = vo.embed(batch, model="voyage-law-2")
        all_embeddings.extend(result.embeddings)
        if i + 50 < len(texts):
            time.sleep(2)
    return all_embeddings
