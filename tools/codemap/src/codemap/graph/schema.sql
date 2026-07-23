-- Deeply Understand (codemap) SQLite schema
-- SSOT: docs/design/deeply-understand/03-data-model.md §1
-- ADR-021

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ============================================================
-- files：文件级元数据 + 双指纹（内容/结构）
-- ============================================================
CREATE TABLE IF NOT EXISTS files (
    path            TEXT PRIMARY KEY,        -- 仓库相对路径，如 src/auth/login.py
    language        TEXT,                    -- python / javascript / typescript / sql / yaml / json / java / markdown / unknown
    category        TEXT,                    -- code / config / docs / infra / data / script / markup
    line_count      INTEGER,
    content_hash    TEXT,                    -- sha256(文件字节) — 内容指纹
    structure_hash  TEXT,                    -- sha256(规范化后的 symbols+imports 摘要) — 结构指纹
    analyzed_at     TEXT                     -- ISO8601，最后一次提取时间
);
CREATE INDEX IF NOT EXISTS idx_files_content_hash   ON files(content_hash);
CREATE INDEX IF NOT EXISTS idx_files_structure_hash ON files(structure_hash);
CREATE INDEX IF NOT EXISTS idx_files_language       ON files(language);

-- ============================================================
-- nodes：图谱节点（文件级 + 符号级）
-- ============================================================
CREATE TABLE IF NOT EXISTS nodes (
    id          TEXT PRIMARY KEY,            -- 类型前缀 + 定位，见 03 §2 命名约定
    type        TEXT NOT NULL,               -- file/function/class/method/module/config/document/schema/service
    name        TEXT NOT NULL,
    file_path   TEXT REFERENCES files(path), -- 所属文件（file 节点 = 自己路径）
    signature   TEXT,                        -- 符号签名（函数 def 行 / class 基类），file 节点为 NULL
    start_line  INTEGER,                     -- 符号起始行（file 节点为 NULL）
    end_line    INTEGER,
    complexity  TEXT,                        -- simple / moderate / complex
    summary     TEXT                         -- 可选：LLM 生成的一句话摘要
    -- embedding 不内联：用单独 embeddings 表（见 06 §3.1），避免 nodes 膨胀 + 模型切换只清 embeddings
);
CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
CREATE INDEX IF NOT EXISTS idx_nodes_type      ON nodes(type);
CREATE INDEX IF NOT EXISTS idx_nodes_name      ON nodes(name);

-- ============================================================
-- edges：图谱边（带类型 + 权重）
-- ============================================================
CREATE TABLE IF NOT EXISTS edges (
    src     TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    dst     TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    type    TEXT NOT NULL,                   -- imports/calls/contains/inherits/depends_on/tested_by/configures
    weight  REAL DEFAULT 0.5,                -- 权重约定见 03 §3
    detail  TEXT,                            -- 如 import 的具体符号 "from x import a,b"
    PRIMARY KEY (src, dst, type)
);
CREATE INDEX IF NOT EXISTS idx_edges_src  ON edges(src);
CREATE INDEX IF NOT EXISTS idx_edges_dst  ON edges(dst);   -- 反向查询（影响分析用）
CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(type);

-- ============================================================
-- meta：图谱级元数据
-- ============================================================
CREATE TABLE IF NOT EXISTS meta (
    key     TEXT PRIMARY KEY,                -- git_commit / analyzed_at / version / lang_coverage / node_count
    value   TEXT
);

-- ============================================================
-- nodes_fts：全文检索（name + summary），降级回退路径（见 06 §3）
-- ============================================================
CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts USING fts5(
    name, summary, content='nodes', content_rowid='rowid', tokenize='unicode61'
);

-- ============================================================
-- embeddings：语义向量（可选，D3，见 06 §3.1）
-- ============================================================
CREATE TABLE IF NOT EXISTS embeddings (
    node_id   TEXT PRIMARY KEY REFERENCES nodes(id),
    model     TEXT NOT NULL,
    vector    BLOB NOT NULL,
    dim       INTEGER NOT NULL,
    built_at  TEXT
);
CREATE INDEX IF NOT EXISTS idx_emb_model ON embeddings(model);
