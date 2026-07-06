-- ChatBI model, prompt, report template, and agent configuration tables.

CREATE TABLE IF NOT EXISTS chatbi_model_providers (
  provider_id VARCHAR(64) PRIMARY KEY,
  provider_name VARCHAR(128) NOT NULL,
  provider_type VARCHAR(64) NOT NULL,
  base_url TEXT,
  api_key_ref VARCHAR(128),
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  timeout_seconds INTEGER NOT NULL DEFAULT 30,
  rate_limit_qpm INTEGER NOT NULL DEFAULT 60,
  created_by VARCHAR(128),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_model_versions (
  model_id VARCHAR(128) PRIMARY KEY,
  provider_id VARCHAR(64) NOT NULL REFERENCES chatbi_model_providers(provider_id) ON DELETE CASCADE,
  model_name VARCHAR(128) NOT NULL,
  context_window INTEGER,
  max_output_tokens INTEGER,
  cost_input_per_1k NUMERIC(18, 8),
  cost_output_per_1k NUMERIC(18, 8),
  fallback_order INTEGER NOT NULL DEFAULT 100,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_agents (
  agent_id VARCHAR(64) PRIMARY KEY,
  agent_name VARCHAR(128) NOT NULL,
  agent_type VARCHAR(64) NOT NULL,
  default_model_id VARCHAR(128),
  fallback_model_ids TEXT,
  default_prompt_version_id VARCHAR(128),
  default_report_template_version_id VARCHAR(128),
  tool_scope TEXT,
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_agent_model_bindings (
  binding_id VARCHAR(128) PRIMARY KEY,
  agent_id VARCHAR(64) NOT NULL REFERENCES chatbi_agents(agent_id) ON DELETE CASCADE,
  node_type VARCHAR(64) NOT NULL,
  primary_model_id VARCHAR(128),
  fallback_model_ids TEXT,
  prompt_version_id VARCHAR(128),
  temperature NUMERIC(6, 3) NOT NULL DEFAULT 0.2,
  max_output_tokens INTEGER NOT NULL DEFAULT 1200,
  timeout_seconds INTEGER NOT NULL DEFAULT 30,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_by VARCHAR(128),
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT chk_chatbi_node_type CHECK (node_type IN (
    'intent_recognition',
    'query_planning',
    'data_query_assist',
    'evidence_extraction',
    'answer_generation',
    'report_generation'
  ))
);

CREATE TABLE IF NOT EXISTS chatbi_agent_tools (
  id BIGSERIAL PRIMARY KEY,
  agent_id VARCHAR(64) NOT NULL REFERENCES chatbi_agents(agent_id) ON DELETE CASCADE,
  tool_name VARCHAR(128) NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_prompt_versions (
  prompt_version_id VARCHAR(128) PRIMARY KEY,
  prompt_id VARCHAR(64) NOT NULL,
  version VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  system_prompt TEXT,
  task_prompt TEXT,
  output_schema TEXT,
  risk_rules TEXT,
  allowed_tools TEXT,
  change_note TEXT,
  created_by VARCHAR(128),
  published_by VARCHAR(128),
  published_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(prompt_id, version)
);

CREATE TABLE IF NOT EXISTS chatbi_report_templates (
  template_id VARCHAR(64) PRIMARY KEY,
  template_name VARCHAR(128) NOT NULL,
  template_type VARCHAR(64) NOT NULL DEFAULT 'research_report',
  status VARCHAR(32) NOT NULL DEFAULT 'active',
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chatbi_report_template_versions (
  template_version_id VARCHAR(128) PRIMARY KEY,
  template_id VARCHAR(64) NOT NULL REFERENCES chatbi_report_templates(template_id) ON DELETE CASCADE,
  version VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL DEFAULT 'draft',
  format VARCHAR(32) NOT NULL DEFAULT 'markdown',
  sections TEXT,
  required_data TEXT,
  optional_data TEXT,
  style_config TEXT,
  change_note TEXT,
  created_by VARCHAR(128),
  published_by VARCHAR(128),
  published_at TIMESTAMP,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(template_id, version)
);

CREATE TABLE IF NOT EXISTS chatbi_render_logs (
  render_id VARCHAR(128) PRIMARY KEY,
  template_version_id VARCHAR(128),
  session_id VARCHAR(64),
  message_id VARCHAR(64),
  status VARCHAR(32) NOT NULL,
  error_message TEXT,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

