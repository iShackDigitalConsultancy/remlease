import re

CLAUSE_PATTERN = re.compile(
    r'(?:^|\n)(?='
    r'\d+\.\d+|'          # 12.1  / 1.2.3
    r'\d+\.|'             # 1.
    r'\([a-zA-Z]\)|'      # (a)
    r'WHEREAS|'           # WHEREAS
    r'NOW,?\s+THEREFORE|' # NOW THEREFORE
    r'SCHEDULE|'          # SCHEDULE
    r'ANNEXURE|'
    r'[A-Z]{4,}\s*:)'     # ALL CAPS HEADING:
)

def smart_chunk(text: str, page_num: int, max_chars: int = 900, overlap: int = 150):
    """Split text on legal clause boundaries with character-length cap."""
    raw_splits = CLAUSE_PATTERN.split(text)
    splits = [s.strip() for s in raw_splits if s and s.strip()]
    if not splits:
        splits = [text]

    chunks = []
    buffer = ""
    for split in splits:
        if len(buffer) + len(split) <= max_chars:
            buffer += ("\n" if buffer else "") + split
        else:
            if buffer:
                chunks.append({"text": buffer, "page": page_num})
            # Start new buffer with overlap from previous
            buffer = buffer[-overlap:] + "\n" + split if buffer else split
    if buffer:
        chunks.append({"text": buffer, "page": page_num})
    return chunks
