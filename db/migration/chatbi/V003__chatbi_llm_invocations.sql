-- ChatBI LLM gateway invocation audit.

CREATE TABLE IF NOT EXISTS chatbi_llm_invocations (
  invocation_id VARCHAR(128) PRIMARY KEY,
  session_id VARCHAR(64),
  message_id VARCHAR(64),
  agent_id VARCHAR(64),
  node_type VARCHAR(64),
  provider_id VARCHAR(64),
  model_id VARCHAR(128),
  status VARCHAR(32) NOT NULL,
  input_tokens INTEGER,
  output_tokens INTEGER,
  fallback_reason TEXT,
  error_message TEXT,
  latency_ms INTEGER,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

