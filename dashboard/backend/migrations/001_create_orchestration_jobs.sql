-- 001_create_orchestration_jobs.sql
-- Orchestration jobs table — persistent state for chat-triggered multi-agent pipelines.
-- Replaces the old fire-and-forget chat-bridge pattern with a durable queue that
-- survives process restarts, supports checkpoints, and gives the dashboard a
-- live view of progress.

CREATE TABLE IF NOT EXISTS orchestration_jobs (
    id TEXT PRIMARY KEY,
    agent TEXT NOT NULL,
    prompt TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'start',
    stage_result TEXT,
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, running, success, failed, cancelled
    error TEXT,
    telegram_chat_id TEXT,
    telegram_message_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_orchestration_jobs_status ON orchestration_jobs(status);
CREATE INDEX IF NOT EXISTS idx_orchestration_jobs_created ON orchestration_jobs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_orchestration_jobs_agent ON orchestration_jobs(agent);