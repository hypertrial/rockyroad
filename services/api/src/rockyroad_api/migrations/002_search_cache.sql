CREATE TABLE IF NOT EXISTS search_cache (
    cache_key TEXT PRIMARY KEY,
    query TEXT NOT NULL,
    payload JSON NOT NULL,
    created_at TIMESTAMP NOT NULL
);
