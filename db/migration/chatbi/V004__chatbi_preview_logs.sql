CREATE TABLE IF NOT EXISTS chatbi_preview_logs (
    preview_id VARCHAR(128) PRIMARY KEY,
    agent_id VARCHAR(64),
    node_type VARCHAR(64),
    provider_id VARCHAR(64),
    model_id VARCHAR(128),
    prompt_version_id VARCHAR(128),
    status VARCHAR(32) NOT NULL,
    input_tokens INTEGER,
    output_tokens INTEGER,
    latency_ms INTEGER,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
