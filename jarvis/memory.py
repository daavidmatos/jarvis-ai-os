from jarvis.db import Database

class MemoryEngine:
    def __init__(self, db: Database): self.db=db
    def retrieve(self, query: str, limit: int=6) -> list[dict]: return self.db.search_memories(query,limit)
    def remember(self, content: str, kind: str="semantic", importance: int=50): return self.db.add_memory(kind,content,importance)
    def context_text(self, query: str) -> str:
        rows=self.retrieve(query)
        return "\n".join(f"- [{m['kind']}] {m['content']}" for m in rows)
