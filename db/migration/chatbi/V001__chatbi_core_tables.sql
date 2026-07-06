-- ChatBI core persistence tables.
-- These tables are intentionally independent from legacy RuoYi AI history
-- tables so the standalone mobile ChatBI can run without the old Dify schema.

CREATE TABLE IF NOT EXISTS chatbi_sessions (
  session_id VARCHAR(64) PRIMARY KEY,
  title VARCHAR(255) NOT NULL DEFAULT '新对话',
  user_id VARCHAR(128),
  user_name VARCHAR(128),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_messages (
  message_id VARCHAR(64) PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL REFERENCES chatbi_sessions(session_id) ON DELETE CASCADE,
  user_id VARCHAR(128),
  user_name VARCHAR(128),
  question TEXT NOT NULL,
  answer TEXT,
  answer_mode VARCHAR(32) NOT NULL DEFAULT 'quick',
  intent VARCHAR(64),
  status VARCHAR(32) NOT NULL DEFAULT 'prepared',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_message_events (
  event_id BIGSERIAL PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL,
  message_id VARCHAR(64) NOT NULL REFERENCES chatbi_messages(message_id) ON DELETE CASCADE,
  event_seq INTEGER NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  node_name VARCHAR(128),
  times_text VARCHAR(64),
  message TEXT,
  is_show VARCHAR(8),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_chatbi_message_events_msg_seq
  ON chatbi_message_events(message_id, event_seq);

CREATE TABLE IF NOT EXISTS chatbi_tool_calls (
  call_id VARCHAR(64) PRIMARY KEY,
  session_id VARCHAR(64) NOT NULL,
  message_id VARCHAR(64) NOT NULL REFERENCES chatbi_messages(message_id) ON DELETE CASCADE,
  tool_name VARCHAR(128) NOT NULL,
  intent VARCHAR(64) NOT NULL,
  success BOOLEAN NOT NULL DEFAULT FALSE,
  source_status VARCHAR(64),
  message TEXT,
  raw_body TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_feedback (
  feedback_id BIGSERIAL PRIMARY KEY,
  session_id VARCHAR(64),
  message_id VARCHAR(64),
  user_id VARCHAR(128),
  rating VARCHAR(32),
  reason TEXT,
  comment TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_audit_logs (
  audit_id BIGSERIAL PRIMARY KEY,
  session_id VARCHAR(64),
  message_id VARCHAR(64),
  user_id VARCHAR(128),
  action VARCHAR(128) NOT NULL,
  detail TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

