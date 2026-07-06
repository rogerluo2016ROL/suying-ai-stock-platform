package com.ds.cockpit.screen.system.service.chatbi.impl;

import cn.hutool.core.lang.UUID;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.PlatformUserBinding;
import com.ds.cockpit.screen.system.service.chatbi.PlatformIdentityService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

@Service
public class JdbcPlatformIdentityService implements PlatformIdentityService {
    private static final Logger log = LoggerFactory.getLogger(JdbcPlatformIdentityService.class);

    @Resource
    private JdbcTemplate jdbcTemplate;

    @PostConstruct
    public void initSchema() {
        try {
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_platform_user_bindings (" +
                    "binding_id VARCHAR(128) PRIMARY KEY," +
                    "platform VARCHAR(32) NOT NULL," +
                    "tenant_id VARCHAR(128) NOT NULL DEFAULT ''," +
                    "platform_user_id VARCHAR(128) NOT NULL," +
                    "internal_user_id VARCHAR(128) NOT NULL," +
                    "display_name VARCHAR(128)," +
                    "roles TEXT," +
                    "permissions TEXT," +
                    "status VARCHAR(32) NOT NULL DEFAULT 'active'," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP," +
                    "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP," +
                    "UNIQUE(platform, tenant_id, platform_user_id)" +
                    ")");
            jdbcTemplate.execute("CREATE INDEX IF NOT EXISTS idx_chatbi_platform_bindings_internal_user ON chatbi_platform_user_bindings(internal_user_id)");
        } catch (Exception ex) {
            log.warn("ChatBI platform identity schema init skipped: {}", ex.getMessage());
        }
    }

    @Override
    public PlatformUserBinding bind(Map<String, Object> request) {
        String platform = normalizePlatform(text(request, "platform", "feishu"));
        String platformUserId = text(request, "platform_user_id", text(request, "platformUserId", ""));
        String tenantId = text(request, "tenant_id", text(request, "tenantId", ""));
        if (platformUserId.length() == 0) {
            throw new IllegalArgumentException("platform_user_id 不能为空");
        }
        String internalUserId = text(request, "internal_user_id", text(request, "internalUserId", defaultInternalUserId(platform, tenantId, platformUserId)));
        String bindingId = text(request, "binding_id", platform + "_" + tenantId + "_" + platformUserId);
        String displayName = text(request, "display_name", text(request, "displayName", platformUserId));
        String roles = csvText(request.get("roles"), "analyst");
        String permissions = csvText(request.get("permissions"), "chatbi.basic");

        jdbcTemplate.update("INSERT INTO chatbi_platform_user_bindings(binding_id, platform, tenant_id, platform_user_id, internal_user_id, display_name, roles, permissions, status, updated_at) " +
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', CURRENT_TIMESTAMP) " +
                        "ON CONFLICT (platform, tenant_id, platform_user_id) DO UPDATE SET internal_user_id = EXCLUDED.internal_user_id, display_name = EXCLUDED.display_name, roles = EXCLUDED.roles, permissions = EXCLUDED.permissions, status = 'active', updated_at = CURRENT_TIMESTAMP",
                bindingId, platform, tenantId, platformUserId, internalUserId, displayName, roles, permissions);
        return find(platform, tenantId, platformUserId);
    }

    @Override
    public Map<String, Object> resolve(Map<String, Object> request) {
        String platform = normalizePlatform(text(request, "platform", "feishu"));
        String platformUserId = text(request, "platform_user_id", text(request, "platformUserId", ""));
        String tenantId = text(request, "tenant_id", text(request, "tenantId", ""));
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("platform", platform);
        result.put("platform_user_id", platformUserId);
        result.put("tenant_id", tenantId);
        if (platformUserId.length() == 0) {
            result.put("status", "missing_identity");
            result.put("message", "缺少 platform_user_id，不能解析平台身份。");
            return result;
        }
        PlatformUserBinding binding = find(platform, tenantId, platformUserId);
        if (binding == null) {
            if (bool(request, "auto_bind", false)) {
                binding = bind(request);
            } else {
                result.put("status", "unbound");
                result.put("internal_user_id", "");
                result.put("message", "平台用户尚未绑定内部用户。");
                return result;
            }
        }
        result.put("status", "bound");
        result.put("internal_user_id", binding.getInternalUserId());
        result.put("display_name", binding.getDisplayName());
        result.put("roles", binding.getRoles());
        result.put("permissions", binding.getPermissions());
        result.put("binding", binding);
        return result;
    }

    @Override
    public List<PlatformUserBinding> bindings(String platform, String tenantId) {
        String normalizedPlatform = platform == null || platform.trim().length() == 0 ? "" : normalizePlatform(platform);
        if (normalizedPlatform.length() > 0 && tenantId != null && tenantId.trim().length() > 0) {
            return rows("SELECT * FROM chatbi_platform_user_bindings WHERE platform = ? AND tenant_id = ? ORDER BY updated_at DESC", normalizedPlatform, tenantId.trim());
        }
        if (normalizedPlatform.length() > 0) {
            return rows("SELECT * FROM chatbi_platform_user_bindings WHERE platform = ? ORDER BY updated_at DESC", normalizedPlatform);
        }
        return rows("SELECT * FROM chatbi_platform_user_bindings ORDER BY updated_at DESC LIMIT 100");
    }

    private PlatformUserBinding find(String platform, String tenantId, String platformUserId) {
        List<PlatformUserBinding> rows = rows("SELECT * FROM chatbi_platform_user_bindings WHERE platform = ? AND tenant_id = ? AND platform_user_id = ? AND status = 'active'", platform, tenantId, platformUserId);
        return rows.isEmpty() ? null : rows.get(0);
    }

    private List<PlatformUserBinding> rows(String sql, Object... args) {
        List<Map<String, Object>> rows = jdbcTemplate.queryForList(sql, args);
        List<PlatformUserBinding> result = new ArrayList<>();
        for (Map<String, Object> row : rows) {
            result.add(toBinding(row));
        }
        return result;
    }

    private PlatformUserBinding toBinding(Map<String, Object> row) {
        PlatformUserBinding binding = new PlatformUserBinding();
        binding.setBindingId(string(row.get("binding_id")));
        binding.setPlatform(string(row.get("platform")));
        binding.setTenantId(string(row.get("tenant_id")));
        binding.setPlatformUserId(string(row.get("platform_user_id")));
        binding.setInternalUserId(string(row.get("internal_user_id")));
        binding.setDisplayName(string(row.get("display_name")));
        binding.setRoles(splitCsv(string(row.get("roles"))));
        binding.setPermissions(splitCsv(string(row.get("permissions"))));
        binding.setStatus(string(row.get("status")));
        return binding;
    }

    private String normalizePlatform(String platform) {
        String value = platform == null ? "" : platform.trim().toLowerCase();
        if ("wechat_work".equals(value) || "wework".equals(value) || "wxwork".equals(value)) {
            value = "wecom";
        }
        if (!"feishu".equals(value) && !"dingtalk".equals(value) && !"wecom".equals(value)) {
            throw new IllegalArgumentException("暂不支持的平台：" + platform);
        }
        return value;
    }

    private String defaultInternalUserId(String platform, String tenantId, String platformUserId) {
        String seed = platform + ":" + tenantId + ":" + platformUserId;
        return "u_" + Integer.toHexString(seed.hashCode()).replace("-", "0");
    }

    private String text(Map<String, Object> request, String key, String defaultValue) {
        Object value = request.get(key);
        if (value == null || String.valueOf(value).trim().length() == 0) {
            return defaultValue;
        }
        return String.valueOf(value).trim();
    }

    private String csvText(Object value, String defaultValue) {
        if (value == null) {
            return defaultValue;
        }
        if (value instanceof List) {
            StringBuilder builder = new StringBuilder();
            for (Object item : (List<?>) value) {
                String text = item == null ? "" : String.valueOf(item).trim();
                if (text.length() == 0) {
                    continue;
                }
                if (builder.length() > 0) {
                    builder.append(",");
                }
                builder.append(text);
            }
            return builder.length() == 0 ? defaultValue : builder.toString();
        }
        String text = String.valueOf(value).trim();
        return text.length() == 0 ? defaultValue : text;
    }

    private List<String> splitCsv(String value) {
        if (value == null || value.trim().length() == 0) {
            return new ArrayList<>();
        }
        List<String> result = new ArrayList<>();
        for (String item : Arrays.asList(value.split(","))) {
            String text = item.trim();
            if (text.length() > 0) {
                result.add(text);
            }
        }
        return result;
    }

    private boolean bool(Map<String, Object> request, String key, boolean defaultValue) {
        Object value = request.get(key);
        return value == null ? defaultValue : Boolean.parseBoolean(String.valueOf(value));
    }

    private String string(Object value) {
        return value == null ? "" : String.valueOf(value);
    }
}
