package com.ds.cockpit.screen.system.service.chatbi.impl;

import cn.hutool.core.lang.UUID;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIFeedbackRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIRequest;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBISessionVO;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ChatBIStreamEvent;
import com.ds.cockpit.screen.common.core.domain.entity.vo.chatbi.ToolCallResponse;
import com.ds.cockpit.screen.system.service.chatbi.ChatBIConversationStore;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

import javax.annotation.PostConstruct;
import javax.annotation.Resource;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.Collections;
import java.util.List;

@Repository
public class JdbcChatBIConversationStore implements ChatBIConversationStore {
    private static final Logger log = LoggerFactory.getLogger(JdbcChatBIConversationStore.class);
    private static final int MAX_RAW_BODY_LENGTH = 20000;

    @Resource
    private JdbcTemplate jdbcTemplate;

    @PostConstruct
    public void initSchema() {
        try {
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_sessions (" +
                    "session_id VARCHAR(64) PRIMARY KEY," +
                    "title VARCHAR(255) NOT NULL DEFAULT '新对话'," +
                    "user_id VARCHAR(128)," +
                    "user_name VARCHAR(128)," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP," +
                    "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" +
                    ")");
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_messages (" +
                    "message_id VARCHAR(64) PRIMARY KEY," +
                    "session_id VARCHAR(64) NOT NULL REFERENCES chatbi_sessions(session_id) ON DELETE CASCADE," +
                    "user_id VARCHAR(128)," +
                    "user_name VARCHAR(128)," +
                    "question TEXT NOT NULL," +
                    "answer TEXT," +
                    "answer_mode VARCHAR(32) NOT NULL DEFAULT 'quick'," +
                    "intent VARCHAR(64)," +
                    "status VARCHAR(32) NOT NULL DEFAULT 'prepared'," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP," +
                    "updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" +
                    ")");
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_message_events (" +
                    "event_id BIGSERIAL PRIMARY KEY," +
                    "session_id VARCHAR(64) NOT NULL," +
                    "message_id VARCHAR(64) NOT NULL REFERENCES chatbi_messages(message_id) ON DELETE CASCADE," +
                    "event_seq INTEGER NOT NULL," +
                    "event_type VARCHAR(64) NOT NULL," +
                    "node_name VARCHAR(128)," +
                    "times_text VARCHAR(64)," +
                    "message TEXT," +
                    "is_show VARCHAR(8)," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" +
                    ")");
            jdbcTemplate.execute("CREATE INDEX IF NOT EXISTS idx_chatbi_message_events_msg_seq ON chatbi_message_events(message_id, event_seq)");
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_tool_calls (" +
                    "call_id VARCHAR(64) PRIMARY KEY," +
                    "session_id VARCHAR(64) NOT NULL," +
                    "message_id VARCHAR(64) NOT NULL REFERENCES chatbi_messages(message_id) ON DELETE CASCADE," +
                    "tool_name VARCHAR(128) NOT NULL," +
                    "intent VARCHAR(64) NOT NULL," +
                    "success BOOLEAN NOT NULL DEFAULT FALSE," +
                    "source_status VARCHAR(64)," +
                    "message TEXT," +
                    "raw_body TEXT," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" +
                    ")");
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_feedback (" +
                    "feedback_id BIGSERIAL PRIMARY KEY," +
                    "session_id VARCHAR(64)," +
                    "message_id VARCHAR(64)," +
                    "user_id VARCHAR(128)," +
                    "rating VARCHAR(32)," +
                    "reason TEXT," +
                    "comment TEXT," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" +
                    ")");
            jdbcTemplate.execute("CREATE TABLE IF NOT EXISTS chatbi_audit_logs (" +
                    "audit_id BIGSERIAL PRIMARY KEY," +
                    "session_id VARCHAR(64)," +
                    "message_id VARCHAR(64)," +
                    "user_id VARCHAR(128)," +
                    "action VARCHAR(128) NOT NULL," +
                    "detail TEXT," +
                    "created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP" +
                    ")");
        } catch (Exception ex) {
            log.warn("ChatBI schema init skipped: {}", ex.getMessage());
        }
    }

    @Override
    public ChatBISessionVO saveSession(ChatBISessionVO session, ChatBIRequest request) {
        try {
            jdbcTemplate.update("INSERT INTO chatbi_sessions(session_id, title, user_id, user_name, created_at, updated_at) " +
                            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) " +
                            "ON CONFLICT (session_id) DO UPDATE SET updated_at = CURRENT_TIMESTAMP, user_id = COALESCE(EXCLUDED.user_id, chatbi_sessions.user_id), user_name = COALESCE(EXCLUDED.user_name, chatbi_sessions.user_name)",
                    session.getSessionId(), session.getTitle(), request == null ? null : request.getUserId(), request == null ? null : request.getUserName());
        } catch (Exception ex) {
            log.warn("ChatBI saveSession skipped: {}", ex.getMessage());
        }
        return session;
    }

    @Override
    public ChatBISessionVO findSession(String sessionId) {
        try {
            List<ChatBISessionVO> rows = jdbcTemplate.query("SELECT session_id, title, created_at, updated_at FROM chatbi_sessions WHERE session_id = ?",
                    (rs, rowNum) -> {
                        ChatBISessionVO vo = new ChatBISessionVO();
                        vo.setId(rs.getString("session_id"));
                        vo.setSessionId(rs.getString("session_id"));
                        vo.setTitle(rs.getString("title"));
                        vo.setCreatedAt(toText(rs.getTimestamp("created_at")));
                        vo.setUpdatedAt(toText(rs.getTimestamp("updated_at")));
                        return vo;
                    }, sessionId);
            return rows.isEmpty() ? null : rows.get(0);
        } catch (Exception ex) {
            log.warn("ChatBI findSession skipped: {}", ex.getMessage());
            return null;
        }
    }

    @Override
    public List<ChatBISessionVO> listSessions() {
        try {
            return jdbcTemplate.query("SELECT session_id, title, created_at, updated_at FROM chatbi_sessions ORDER BY updated_at DESC LIMIT 50",
                    (rs, rowNum) -> {
                        ChatBISessionVO vo = new ChatBISessionVO();
                        vo.setId(rs.getString("session_id"));
                        vo.setSessionId(rs.getString("session_id"));
                        vo.setTitle(rs.getString("title"));
                        vo.setCreatedAt(toText(rs.getTimestamp("created_at")));
                        vo.setUpdatedAt(toText(rs.getTimestamp("updated_at")));
                        return vo;
                    });
        } catch (Exception ex) {
            log.warn("ChatBI listSessions skipped: {}", ex.getMessage());
            return Collections.emptyList();
        }
    }

    @Override
    public void savePreparedMessage(String sessionId, String messageId, ChatBIRequest request) {
        try {
            jdbcTemplate.update("INSERT INTO chatbi_messages(message_id, session_id, user_id, user_name, question, answer_mode, status, created_at, updated_at) " +
                            "VALUES (?, ?, ?, ?, ?, ?, 'prepared', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP) " +
                            "ON CONFLICT (message_id) DO UPDATE SET question = EXCLUDED.question, answer_mode = EXCLUDED.answer_mode, updated_at = CURRENT_TIMESTAMP",
                    messageId, sessionId, request.getUserId(), request.getUserName(), request.normalizedQuestion(), request.normalizedAnswerMode());
            String title = titleFromQuestion(request.normalizedQuestion());
            jdbcTemplate.update("UPDATE chatbi_sessions SET title = CASE WHEN title = '新对话' OR title = '历史会话' THEN ? ELSE title END, updated_at = CURRENT_TIMESTAMP WHERE session_id = ?",
                    title, sessionId);
        } catch (Exception ex) {
            log.warn("ChatBI savePreparedMessage skipped: {}", ex.getMessage());
        }
    }

    @Override
    public void saveCompletedMessage(String sessionId, String messageId, String answer, String intent) {
        try {
            jdbcTemplate.update("UPDATE chatbi_messages SET answer = ?, intent = ?, status = 'completed', updated_at = CURRENT_TIMESTAMP WHERE message_id = ?",
                    answer, intent, messageId);
            jdbcTemplate.update("UPDATE chatbi_sessions SET updated_at = CURRENT_TIMESTAMP WHERE session_id = ?", sessionId);
        } catch (Exception ex) {
            log.warn("ChatBI saveCompletedMessage skipped: {}", ex.getMessage());
        }
    }

    @Override
    public void saveEvent(String sessionId, String messageId, int eventSeq, ChatBIStreamEvent event) {
        try {
            jdbcTemplate.update("INSERT INTO chatbi_message_events(session_id, message_id, event_seq, event_type, node_name, times_text, message, is_show) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    sessionId, messageId, eventSeq, event.getType(), event.getNode(), event.getTimes(), event.getMessage(), event.getIsShow());
        } catch (Exception ex) {
            log.warn("ChatBI saveEvent skipped: {}", ex.getMessage());
        }
    }

    @Override
    public void saveToolCall(String sessionId, String messageId, String intent, ToolCallResponse response) {
        try {
            jdbcTemplate.update("INSERT INTO chatbi_tool_calls(call_id, session_id, message_id, tool_name, intent, success, source_status, message, raw_body) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    UUID.randomUUID().toString(), sessionId, messageId, "screener", intent, response.isSuccess(), response.getSourceStatus(), response.getMessage(), truncate(response.getRawBody(), MAX_RAW_BODY_LENGTH));
        } catch (Exception ex) {
            log.warn("ChatBI saveToolCall skipped: {}", ex.getMessage());
        }
    }

    @Override
    public void saveFeedback(ChatBIFeedbackRequest request) {
        try {
            jdbcTemplate.update("INSERT INTO chatbi_feedback(session_id, message_id, user_id, rating, reason, comment) VALUES (?, ?, ?, ?, ?, ?)",
                    request.getSessionId(), request.getMessageId(), request.getUserId(), request.getRating(), request.getReason(), request.getComment());
        } catch (Exception ex) {
            log.warn("ChatBI saveFeedback skipped: {}", ex.getMessage());
        }
    }

    private String titleFromQuestion(String question) {
        if (question == null || question.trim().length() == 0) {
            return "新对话";
        }
        String normalized = question.trim();
        return normalized.length() <= 24 ? normalized : normalized.substring(0, 24);
    }

    private String toText(Timestamp timestamp) {
        return timestamp == null ? LocalDateTime.now().toString() : timestamp.toLocalDateTime().toString();
    }

    private String truncate(String text, int maxLength) {
        if (text == null || text.length() <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength);
    }
}

