from pydantic import BaseModel


class Settings(BaseModel):
    max_files_per_side: int = 150
    max_file_size_mb: int = 40
    semantic_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    semantic_chunk_size: int = 32
    top_mismatches_limit: int = 7000
    cache_ttl_seconds: int = 3600
    max_cached_results: int = 200
    allowed_suffixes: tuple[str, ...] = (
        ".docx",
        ".pdf",
        ".txt",
        ".xlsx",
        ".png",
        ".jpg",
        ".jpeg",
    )


settings = Settings()
