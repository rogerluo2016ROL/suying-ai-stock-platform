-- ═══════════════════════════════════════════════════════════════
-- 数据质量修复脚本 — 一次性清理 + 约束加固
--
-- 用法: psql -U kronos -d kronos -f services/sql/data_quality_fix.sql
-- 安全: 所有操作使用事务 + ON CONFLICT/IF NOT EXISTS，可重复执行
-- ═══════════════════════════════════════════════════════════════

BEGIN;

-- ──────────────────────────────────────────────────────────────
-- 1. 修复 daily_kline.change_pct 空值
--    用当前收盘价与前一日收盘价的涨跌幅回填
-- ──────────────────────────────────────────────────────────────
\echo '--- [1/6] Fix daily_kline.change_pct NULLs ---'

WITH null_count AS (
    SELECT COUNT(*) AS cnt FROM daily_kline WHERE change_pct IS NULL
)
SELECT 'daily_kline.change_pct NULLs before fix: ' || cnt::TEXT FROM null_count;

UPDATE daily_kline d1 SET change_pct =
    CASE
        WHEN d2.close > 0 THEN (d1.close - d2.close) / d2.close * 100
        ELSE NULL
    END
FROM daily_kline d2
WHERE d1.change_pct IS NULL
  AND d2.code = d1.code
  AND d2.trade_date = (
      SELECT MAX(trade_date)
      FROM daily_kline
      WHERE code = d1.code AND trade_date < d1.trade_date
  )
  AND d2.close > 0;

WITH null_count AS (
    SELECT COUNT(*) AS cnt FROM daily_kline WHERE change_pct IS NULL
)
SELECT 'daily_kline.change_pct NULLs after fix: ' || cnt::TEXT FROM null_count;


-- ──────────────────────────────────────────────────────────────
-- 2. 为 cb_daily 添加 CHECK 约束
--    先标记异常行 (不删除，仅统计)，再添加约束
-- ──────────────────────────────────────────────────────────────
\echo '--- [2/6] Add cb_daily CHECK constraint ---'

-- 统计异常行
SELECT 'cb_daily rows with close<=0: ' || COUNT(*)::TEXT
FROM cb_daily WHERE close <= 0 OR close IS NULL;

SELECT 'cb_daily rows with amount<0: ' || COUNT(*)::TEXT
FROM cb_daily WHERE amount < 0;

SELECT 'cb_daily rows with amount IS NULL: ' || COUNT(*)::TEXT
FROM cb_daily WHERE amount IS NULL;

-- 将异常 amount 的 NULL 设为 0 (避免约束阻塞)
UPDATE cb_daily SET amount = 0 WHERE amount IS NULL;

-- 添加约束 (IF NOT EXISTS 语法由 DO 块实现)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_cb_daily_valid' AND conrelid = 'cb_daily'::regclass
    ) THEN
        ALTER TABLE cb_daily ADD CONSTRAINT chk_cb_daily_valid
            CHECK (close > 0 AND amount >= 0);
    END IF;
END $$;


-- ──────────────────────────────────────────────────────────────
-- 3. stk_mins 去重 (保留 ctid 最大的一条)
--    stk_mins 使用 SERIAL id 而非 ctid，此处用 MAX(id) 去重
-- ──────────────────────────────────────────────────────────────
\echo '--- [3/6] stk_mins deduplication ---'

SELECT 'stk_mins duplicate rows: ' || COUNT(*)::TEXT
FROM (
    SELECT code, trade_time, freq, COUNT(*) - 1 AS dup_count
    FROM stk_mins
    GROUP BY code, trade_time, freq
    HAVING COUNT(*) > 1
) dups;

DELETE FROM stk_mins a
USING stk_mins b
WHERE a.code = b.code
  AND a.trade_time = b.trade_time
  AND a.freq = b.freq
  AND a.id < b.id;

SELECT 'stk_mins total rows after dedup: ' || COUNT(*)::TEXT FROM stk_mins;


-- ──────────────────────────────────────────────────────────────
-- 4. cb_factor 添加 RSI 合法范围约束 (0-100)
-- ──────────────────────────────────────────────────────────────
\echo '--- [4/6] Add cb_factor RSI constraint ---'

-- 统计越界值
SELECT 'rsi_6 out of [0,100]: ' || COUNT(*)::TEXT
FROM cb_factor WHERE rsi_6 IS NOT NULL AND (rsi_6 < 0 OR rsi_6 > 100);

SELECT 'rsi_12 out of [0,100]: ' || COUNT(*)::TEXT
FROM cb_factor WHERE rsi_12 IS NOT NULL AND (rsi_12 < 0 OR rsi_12 > 100);

SELECT 'rsi_24 out of [0,100]: ' || COUNT(*)::TEXT
FROM cb_factor WHERE rsi_24 IS NOT NULL AND (rsi_24 < 0 OR rsi_24 > 100);

-- 将越界值裁剪到 [0, 100]
UPDATE cb_factor SET rsi_6 = 0 WHERE rsi_6 < 0;
UPDATE cb_factor SET rsi_6 = 100 WHERE rsi_6 > 100;
UPDATE cb_factor SET rsi_12 = 0 WHERE rsi_12 < 0;
UPDATE cb_factor SET rsi_12 = 100 WHERE rsi_12 > 100;
UPDATE cb_factor SET rsi_24 = 0 WHERE rsi_24 < 0;
UPDATE cb_factor SET rsi_24 = 100 WHERE rsi_24 > 100;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_rsi_range' AND conrelid = 'cb_factor'::regclass
    ) THEN
        ALTER TABLE cb_factor ADD CONSTRAINT chk_rsi_range
            CHECK (rsi_6 BETWEEN 0 AND 100
               AND rsi_12 BETWEEN 0 AND 100
               AND rsi_24 BETWEEN 0 AND 100);
    END IF;
END $$;


-- ──────────────────────────────────────────────────────────────
-- 5. ths_daily 清理 + NOT NULL 约束
--    删除 change_pct 为 NULL 的行，再设 NOT NULL
-- ──────────────────────────────────────────────────────────────
\echo '--- [5/6] Clean ths_daily + add NOT NULL ---'

SELECT 'ths_daily rows with change_pct IS NULL: ' || COUNT(*)::TEXT
FROM ths_daily WHERE change_pct IS NULL;

-- 也检查 pct_change 列 (两个列名可能混用)
SELECT 'ths_daily rows with pct_change IS NULL: ' || COUNT(*)::TEXT
FROM ths_daily WHERE pct_change IS NULL;

-- 删除 change_pct 为 NULL 的行
DELETE FROM ths_daily WHERE change_pct IS NULL;

-- 设置 NOT NULL 约束 (先检查是否已有约束)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_attribute a ON a.attnum = ANY(c.conkey)
        WHERE c.conname LIKE '%change_pct%'
          AND c.conrelid = 'ths_daily'::regclass
          AND c.contype = 'n'
    ) THEN
        ALTER TABLE ths_daily ALTER COLUMN change_pct SET NOT NULL;
    END IF;
END $$;


-- ──────────────────────────────────────────────────────────────
-- 6. 创建 ths_concept_map 表 (同花顺概念-成分股映射)
--    用于 ths_concept_map 每月自动同步
-- ──────────────────────────────────────────────────────────────
\echo '--- [6/6] Create ths_concept_map table ---'

CREATE TABLE IF NOT EXISTS ths_concept_map (
    id SERIAL PRIMARY KEY,
    ts_code TEXT NOT NULL,
    concept_name TEXT NOT NULL,
    concept_code TEXT NOT NULL,
    trade_date DATE NOT NULL DEFAULT CURRENT_DATE,
    UNIQUE(ts_code, concept_name)
);
CREATE INDEX IF NOT EXISTS idx_ths_concept_map_code ON ths_concept_map(ts_code);
CREATE INDEX IF NOT EXISTS idx_ths_concept_map_concept ON ths_concept_map(concept_name);

COMMIT;

\echo '=== Data quality fix completed ==='
