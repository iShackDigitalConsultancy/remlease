from config.model_versions import VOYAGE_EMBEDDING_MODEL
from dependencies import vo
from typing import List
import time

def get_embedding(text: str):
    return vo.embed([text], model=VOYAGE_EMBEDDING_MODEL).embeddings[0]

def get_embeddings(texts: List[str]):
    all_embeddings = []
    for i in range(0, len(texts), 50):
        batch = texts[i:i+50]
        result = vo.embed(batch, model=VOYAGE_EMBEDDING_MODEL)
        all_embeddings.extend(result.embeddings)
        if i + 50 < len(texts):
            time.sleep(2)
    return all_embeddings
