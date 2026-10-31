-- Initialize PostgreSQL database with pgvector extension for BoardBridge
CREATE EXTENSION IF NOT EXISTS vector;

-- Verification query (logged during container initialization)
SELECT extversion FROM pg_extension WHERE extname = 'vector';

