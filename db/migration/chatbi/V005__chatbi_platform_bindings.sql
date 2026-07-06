CREATE TABLE IF NOT EXISTS chatbi_platform_user_bindings (
    binding_id VARCHAR(128) PRIMARY KEY,
    platform VARCHAR(32) NOT NULL,
    tenant_id VARCHAR(128) NOT NULL DEFAULT '',
    platform_user_id VARCHAR(128) NOT NULL,
    internal_user_id VARCHAR(128) NOT NULL,
    display_name VARCHAR(128),
    roles TEXT,
    permissions TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(platform, tenant_id, platform_user_id)
);

CREATE INDEX IF NOT EXISTS idx_chatbi_platform_bindings_internal_user
    ON chatbi_platform_user_bindings(internal_user_id);
