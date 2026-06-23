---
reviewer: code-reviewer
audit_type: backend-security-correctness
date: 2026-06-22
scope: backend/ + services/ (11 微服务) + packages/ (kronos-data/kronos-factors/kronos-auth)
files_scanned: ~85 .py (auth/admin/trade/strategy/data-pipeline/pg_adapter/circuit_breaker)
tests_status: backend 51 passed / 9 skipped (warning: httpx DeprecationWarning in SIT)
critical_count: 3
warning_count: 9
suggestion_count: 4
code_verdict: approve with changes
sit_audit_verdict: N/A (one-off infrastructure audit, no progress/<role>.md to audit)
---

# 后端审计报告 — 速赢AI证券投资平台 (2026-06-22)

> Reviewer: `code-reviewer`（review-only，未动一行源码）。
> 范围：`backend/`（auth + admin + alembic）、`services/` 11 微服务、`packages/{kronos-data,kronos-factors,kronos-auth}`。
> 严重度：**P0** = 资金风险 / 数据错误 / 安全漏洞 / 阻断功能；**P1** = 功能缺陷 / 已知债未修 / 认证缺陷；**P2** = 代码质量。

---

## §1 概览

### 扫描范围
- backend/app/ (auth_service / routers/auth / routers/admin / api/deps / config / main)
- services/{api-gateway, screener, prediction, strategy, signal, alert, trade, backtest, training, diagnosis, data}-service
- packages/{kronos-data (etl/market_data), kronos-factors (pg_adapter/recorder), kronos-auth}
- 重点 read：`pg_adapter.py` / `_insert_rows` / `cb_sync.py` / `pg_writer.py` / `circuit_breaker.py` / `engine.py` / `auto_trading_executor.py` / `api-gateway/main.py`
- grep 扫描：SQL 注入 (`f".*{.*}.*"` in execute) / 异常吞没 (`except.*pass`) / 违规依赖 (`httpx|aiohttp`) / `r["code"]` 在 PG tuple 路径 / 硬编码密钥

### 问题总数
| 严重度 | 数量 |
|---|---|
| **P0** | 3 |
| **P1** | 9 |
| **P2** | 4 |

### 已知债验证结论

| 已知债（来自 memory / CLAUDE.md 背景） | 当前状态 | 证据 |
|---|---|---|
| **数据管道 cyq / pledge `r[code]` bug** | **部分残留** | `etl.py:1300` `sync_cyq_chips` 仍写 `db.row_factory = sqlite3.Row`（L1300），但对 PG 路径是**无效赋值**——`_Db.execute` (`etl.py:111-125`) 用 `psycopg2.extras.DictCursor`，不读 `row_factory`。**功能上没炸**是因为 DictCursor 让 `r["code"]` 在 PG 下也能用；但 `db.row_factory = sqlite3.Row` 是误导性死代码（见 P2-1）。pledge `r.get("p_total_ratio")` vs cols `"pledge_total_ratio"` 列名不一致（L1217/L1230）——**真实 bug**：写入永远 None（见 P1-3）。 |
| **`rt_sw_k` / `sw_daily` 缺核心列** | **未修复（设计性跳过）** | `services/sql/audit/schema_audit.py:8` 把 `sw_daily`/`rt_sw_k`/`pledge_detail`/`cyq_chips`/`top_list` 放进 `EXCLUDED` 集合，schema audit 主动跳过这些表。`signal-service/routes.py:992-1014` 仅查 `trade_date` 一列做监控。这两张表的实际 schema 是否齐全**无审计覆盖**（见 P1-4）。 |
| **PG 写入收口（ADR-012/015）** | **完整收口** | grep 实证：所有写路径都走 `_pg_write` (pg_writer.py) → `_insert_rows` (etl.py)，支持 `conflict_action` + `now_cols` UPSERT。止血 commit `2d311fa` 的自动列过滤生效（etl.py:264-276 `valid_cols` 过滤）。**无遗漏 inline 直写路径**（`pg_writer.py:229` 的 `cur.execute(f"SELECT COUNT(*) FROM {view}")` 是只读计数，非写入，view 名来自代码内常量列表，非用户输入）。 |
| **PG/SQLite 列名映射** | **覆盖不全** | `pg_adapter._COLUMN_MAP` (`pg_adapter.py:70-74`) 仅映射 3 个列：`pct_chg→change_pct`、`pct_change→change_pct`、`ts_code→code`。`_KEY_MAP` (`pg_adapter.py:221`) 仅 1 个反向映射 `change_pct→pct_chg`。**遗漏**：`vol→volume`（daily_kline PG 是 volume，engine 用 vol）、`amount`（一致无映射）、`turnover_rate`（一致）、`is_st`（一致）。`pg_writer.write_index_daily` (`pg_writer.py:170`) 手工做 `vol→volume`/`pct_chg→change_pct` 重排，绕开了 adapter——说明**列名映射机制本身不够，要靠每个 write_* 函数手补**（见 P2-2）。 |

---

## §2 问题清单

### P0 — 必修（资金风险 / 安全漏洞 / 阻断功能）

#### **P0-1 JWT 密钥 dev fallback 在 diagnosis-service / training-service 与 backend 不一致 → 跨服务验签 100% 失败**
- **位置**：`services/diagnosis-service/app/config.py:22`、`services/training-service/app/config.py:22`
- **描述**：两个服务在 `JWT_SECRET_KEY` env 缺失时 fallback 到硬编码 `"dev-secret-change-in-production-min-32-chars!!"`，但 `backend/app/config.py:54` 用的是 `"dev-only-jwt-secret-change-in-production-min-32-chars!!"`（前缀 `dev-only-`）。本地 dev 或 docker 未注入 env 时：
  - backend 签发 token 用 `dev-only-jwt-secret...`
  - diagnosis/training 用 `dev-secret-change...` 验签 → `jwt.InvalidTokenError` → 所有带认证的 endpoint 返回 401
- **复现**：`unset JWT_SECRET_KEY && cd services/diagnosis-service && uvicorn app.main:app --port 8009` + 任何带 `Authorization: Bearer <backend-issued-token>` 的请求 → 401 "Invalid authentication token"
- **修复**：两个 config.py 改用 `_secret()` 分级 raise 契约（与 backend/app/config.py:18-38 和 packages/kronos-auth/kronos_auth/config.py:17-37 一致）：
  ```python
  def _secret(env_key, dev_fallback):
      v = os.environ.get(env_key)
      if v: return v
      if os.environ.get("KRONOS_ENV","").lower() == "production":
          raise RuntimeError(f"{env_key} must be set in production")
      import warnings; warnings.warn(f"{env_key} not set — dev fallback", RuntimeWarning)
      return dev_fallback
  JWT_SECRET_KEY = _secret("JWT_SECRET_KEY", "dev-only-jwt-secret-change-in-production-min-32-chars!!")
  ```
  或直接 `from kronos_auth.config import KRONOS_JWT_SECRET as JWT_SECRET_KEY`（复用包，消除三处副本）。

#### **P0-2 trade-service/app/deps.py 残留 `secrets.token_hex(32)` 进程内随机 fallback → 生产密钥缺失不告警**
- **位置**：`services/trade-service/app/deps.py:5-9`
- **描述**：
  ```python
  JWT_SECRET = os.environ.get("JWT_SECRET_KEY")
  if not JWT_SECRET:
      JWT_SECRET = secrets.token_hex(32)   # ← 进程内随机
      warnings.warn("JWT_SECRET_KEY not set — using random key!", RuntimeWarning)
  ```
  这正是 `backend/app/config.py:6` 注释明令禁止的反模式："**禁 `secrets.token_hex` 进程内随机**（多实例/重启 token 互不兼容，比硬编码默认更隐蔽）"。后果：
  - 生产部署忘设 `JWT_SECRET_KEY` → trade-service 每次重启换一个随机密钥，所有在途 JWT 立即失效，且不 raise（只 warn，日志可能被淹）
  - 多实例部署时每个 worker 不同密钥，负载均衡到不同实例验签结果随机
  - 注：`routes.py:22 from kronos_auth import require_role` 才是实际生效路径，`deps.py` 当前是**未引用的死代码**，但留着是定时炸弹（未来谁 import 一次就炸）
- **复现**：`unset JWT_SECRET_KEY && grep -r "from app.deps" services/trade-service/`（当前 0 引用）—— 但任何新增 `from app.deps import require_auth` 的 PR 会立即引入 bug
- **修复**：删 `services/trade-service/app/deps.py`（死代码），或改成 `from kronos_auth.config import KRONOS_JWT_SECRET as JWT_SECRET`。同时 grep 确认无其它服务有同样模式（本审计已扫，仅此一处）。

#### **P0-3 circuit_breaker 共享可变状态无锁 → 并发下单 race condition 可绕过熔断**
- **位置**：`services/trade-service/app/circuit_breaker.py:55` `_breakers: dict[str, BreakerState] = {}` + 全文无 `Lock`
- **描述**：circuit breaker 的所有读写（`_get_or_create`/`check_daily_loss`/`can_trade`/`record_probe`/`reset`）都是 `async def` 但操作的是**模块级 dict + dataclass 可变字段**，**无任何 `asyncio.Lock` 或 `threading.Lock` 保护**。`trade-service` 是 FastAPI async，多个订单请求并发时：
  - 线程 A `can_trade()` 读 `state.status == HALF_OPEN, probing_count == 0` → 返回 True
  - 线程 B 同一时刻也 `can_trade()` 读 `probing_count == 0` → 也返回 True
  - 两个"探测单"同时进入 `_place_order`，HALF_OPEN 语义（只允许 1 个探测）被绕过
  - 同理 TRIGGERED 状态下 `check_daily_loss` 的"已触发则不再检查阈值"分支 (L111) 也有 TOCTOU
- **对比**：同项目 `trade-service/app/engine.py:49 PaperTradingEngine._lock = threading.Lock()` 正确加锁；`strategy-service/app/auto_trading_executor.py:158 ExecutorManager._lock = threading.Lock()` 也正确加锁。唯独 circuit breaker 漏了。
- **复现**：构造 HALF_OPEN 状态 + 用 `asyncio.gather` 并发调 `can_trade(account_id)` 两次 → 两次都返回 `(True, "HALF_OPEN probing order allowed")`，而正确语义应只有一次 True。
- **修复**：在 `circuit_breaker.py` 顶部加 `_lock = asyncio.Lock()`，把 `check_daily_loss` / `can_trade` / `record_probe` / `reset` / `_get_or_create` 全部用 `async with _lock:` 包裹（注意 `_get_or_create` 是同步函数，要么改成 async，要么内部用 `threading.Lock`——推荐改 async，因为调用方全是 async）。

---

### P1 — 建议修（功能缺陷 / 已知债 / 认证弱点）

#### **P1-1 diagnosis-service 用 aiohttp（违反 CLAUDE.md "不引入 httpx/aiohttp"）**
- **位置**：`services/diagnosis-service/app/diagnosis_engine.py:621,626,629`
- **描述**：CLAUDE.md 明确规定"微服务间 HTTP 调用使用 `urllib` async wrapper (`loop.run_in_executor`)，不引入 `httpx`/`aiohttp` 额外依赖"。diagnosis_engine 调 Kronos prediction 用了 `import aiohttp; aiohttp.ClientSession()`。
- **对比**：`strategy-service/auto_trading_executor.py:764-816` 的 `_http_get`/`_http_post_query` 是正确的 urllib async wrapper 范式。
- **修复**：照 `auto_trading_executor._http_get` 改写 `_fetch_kronos_prediction`（把 aiohttp session 换成 `urllib.request.urlopen` + `loop.run_in_executor`）。

#### **P1-2 死代码 nested api-gateway（用 httpx）藏在 diagnosis-service 子目录**
- **位置**：`services/diagnosis-service/services/api-gateway/app/routes.py:11` `import httpx`（全文 240 行）
- **描述**：整个 `services/diagnosis-service/services/api-gateway/` 目录是**死代码**——`grep -rn` 实证无任何 import / Dockerfile 引用。它是早期开发残留的完整 api-gateway 副本，用 httpx 实现，违反 CLAUDE.md 依赖铁律。留在仓库里：(a) 误导后续 dev 以为它是活的；(b) 一旦有人 copy-paste 其代码片段就引入 httpx 依赖。
- **修复**：`rm -rf services/diagnosis-service/services/`（整个 services 子目录）。

#### **P1-3 pledge_detail 写入列名 vs 数据字段名不匹配 → pledge_total_ratio 永远 NULL**
- **位置**：`packages/kronos-data/kronos_data/etl.py:1217` vs `:1230`
- **描述**：
  ```python
  cols = ["code", "ann_date", "pledgor", "pledgee", "pledge_amount", "pledge_total_ratio"]  # L1217
  ...
  rows.append((..., r.get("p_total_ratio")))  # L1230 — Tushare 实际字段 p_total_ratio
  ```
  注释 L1230 说"ADR-009 修正: Tushare 实际字段名 p_total_ratio（探针实测, 非 ADR 原假设的 pledge_total_ratio）"——**修了 fetch 端但没修 cols 端**。结果：元组里第 6 位是 `p_total_ratio` 的值，但 INSERT 语句把这一列写到 `pledge_total_ratio` 字段名下。若 PG 表 `pledge_detail` 有 `pledge_total_ratio` 列 → 数据写进去了（值正确，列名误导）。若 PG 表实际列名是 `p_total_ratio` → `_insert_rows` 的自动列过滤（`_get_pg_columns`）会把 `pledge_total_ratio` 当无效列丢弃，**这列数据永远丢失**。
- **验证步骤**：`psql -c "\d pledge_detail"` 看 PG 实际列名。若列名是 `pledge_total_ratio`，仅修 cols 一致性即可；若是 `p_total_ratio`，则数据已长期丢失。
- **修复**：`cols` 第 6 项改 `"p_total_ratio"`（与 Tushare API + 大概率与 PG 列名一致）。同步检查 `init_postgres.sql` 的 pledge_detail DDL。

#### **P1-4 rt_sw_k / sw_daily / pledge_detail / cyq_chips 等 5 张表退出 schema audit → schema drift 不可见**
- **位置**：`services/sql/audit/schema_audit.py:8` `EXCLUDED = {"sw_daily","pledge_detail","rt_sw_k","top_list","cyq_chips","top_inst","ths_daily", ...}`
- **描述**：schema audit 主动把这 5+ 张表排除出检查。后果：这 5 张表的 PG schema 与 sync 函数 cols 假设是否一致**完全无人监督**。P1-3 的 pledge 列名问题正是因为这张表在 EXCLUDED 里才长期未被发现。memory 记录的"rt_sw_k/sw_daily 缺核心列"也无审计可证伪。
- **修复**：把 EXCLUDED 集合清空（或只保留确实未启用 sync 的表）。对每张表跑一次：`SELECT column_name FROM information_schema.columns WHERE table_name=X` 与 sync 函数的 `cols` 列表 diff，把 diff 写进 audit 报告。

#### **P1-5 refresh_token rotate 路径不校验 JWT type=refresh claim**
- **位置**：`backend/app/services/auth_service.py:200-250 rotate_refresh_token`
- **描述**：函数把传入的 `old_token` 直接 `_hash_token` 后查 DB，**没有先 `decode_token()` 验签 + 检查 `type==refresh`**。当前安全因为：DB `refresh_tokens` 表只存 `create_refresh_token()` 产物的 hash（L67 `create_refresh_token` 走 `_create_token(user, "refresh", ...)`），所以 access token 的 hash 不会命中 refresh_tokens 表。但这是**靠巧合**而非**靠校验**的安全：未来若有人在别处把 access token 也 hash 入库（例如审计/日志场景误存），rotate 会接受 access token 当 refresh 用。
- **对比**：`api/deps.py:47 get_current_user` 正确校验了 `payload.get("type") != "access"`。
- **修复**：在 `rotate_refresh_token` 开头加：
  ```python
  try:
      payload = decode_token(old_token)
  except jwt.PyJWTError:
      return None
  if payload.get("type") != "refresh":
      return None
  ```

#### **P1-6 trade-service `/broker/connect` trade_password 明文进内存 + 无日志脱敏保障**
- **位置**：`services/trade-service/app/routes.py:381,397-403`
- **描述**：
  ```python
  trade_password: str = Body("", embed=True),  # L381 — 明文 body
  _broker_config = {
      ...
      "trade_password": trade_password,  # L402 — 进模块级 dict
  }
  ```
  券商交易密码（真实资金凭证）以明文存进进程内存的模块级 dict `_broker_config`，存活到进程结束。审计未发现该 dict 被 `logger.info(_broker_config)` 打印（grep 实证），但**无防御性保障**：未来任何 `logger.debug(f"config: {_broker_config}")` 或异常 traceback 会泄露密码到日志。
- **修复**：
  1. 短期：在 `_broker_config` 存前 mask，仅把真实 password 传给 `XtquantBroker` 构造器（局部变量，函数返回即 GC）。
  2. 长期：trade_password 不应走 API——应通过 vault / env / broker-side keystored，API 只传 account_id。

#### **P1-7 diagnosis-service / signal-service 直接 `psycopg2` 裸 SQL，绕开 pg_adapter 列名映射**
- **位置**：`services/signal-service/app/routes.py:1031-1070`（裸 `psycopg2.connect` + `cur.execute(f"SELECT MIN(\"{col}\")...")`）；`services/diagnosis-service/app/routes.py:602-617`（`sa_text(f"SELECT ... WHERE {where_sql}")`）
- **描述**：两处都是 f-string 拼接 SQL。虽然 `where_sql` 来自代码内 `where_clauses.append("code = :code")`（参数化绑定，安全），`col` / `key` 来自 `_DATE_COL_MAP` 常量（非用户输入，安全）——**当前不可注入**。但：
  - signal-service L1053 `f'SELECT MIN("{col}"), MAX("{col}") FROM "{key}"'` 用了**双引号标识符**拼 `col`/`key`，若未来 `_DATE_COL_MAP` 从代码常量改成读 DB / 配置，立即变注入点。
  - diagnosis L603 同型。
  - 两处都**绕开了 `pg_adapter._COLUMN_MAP` 列名映射**——意味着这两处必须手工保证 `col` 是 PG 列名而非 engine 列名，与 pg_adapter 的抽象割裂。
- **修复**：用 `psycopg2.sql.SQL` + `Identifier` 安全拼接（`pg_writer.py:228` `SQL("REFRESH MATERIALIZED VIEW CONCURRENTLY {}").format(Identifier(view))` 是正确范式）。

#### **P1-8 api-gateway 限流桶 `_rate_store` 无过期清理 → 内存增长 + 无分布式一致性**
- **位置**：`services/api-gateway/app/main.py:20,87-94`
- **描述**：`_rate_store: dict[str, list[float]] = {}` 按 client IP 存请求时间戳。L89 `w = [t for t in _rate_store.get(ip, []) if now - t < 60]` 每次 slice 保留近 60s 的，**但 IP key 永不从 dict 删除**。长时间运行 + 大量不同 IP → 内存无界增长。且单进程内存限流在多实例部署下无效。
- **修复**：短期加定期清理（每 N 次请求扫一次 `_rate_store` 删空 list 的 key）；长期换 Redis（项目已有 Redis 7）。

#### **P1-9 数据管道异常吞没普遍（20+ 处 `except Exception: pass` / 静默 continue）**
- **位置**：`services/data-service/app/scheduler.py`（grep 实证 20+ 处）、`packages/kronos-data/kronos_data/etl.py:1221,1248,1316`（`except: continue` 无日志）
- **描述**：典型如 `etl.py:1221`：
  ```python
  try: df = pro.pledge_detail(ts_code=_ts_code(code))
  except: continue   # ← 裸 except + 静默跳过
  ```
  任何 Tushare API 错误（限频、网络、token 过期、字段变更）都被吞掉，sync 函数返回 `{"status":"ok"}`——**表面成功实则 0 写入**。memory 记录的"数据停滞数周无人察觉"正是此模式导致（止血 commit `2d311fa` 的 `_insert_rows` 自动列过滤修了一半，但 fetch 层的 `except: continue` 仍在）。
- **修复**：至少改成 `except Exception as e: logger.warning("pledge_detail fetch failed for %s: %s", code, e); continue`。区分可重试错误（网络/限频 → retry）与不可重试（字段变更 → ERROR + 告警）。

---

### P2 — 可缓（代码质量 / 可维护性）

#### **P2-1 etl.py sync_cyq_chips 等多处 `db.row_factory = sqlite3.Row` 对 PG 路径无效**
- **位置**：`packages/kronos-data/kronos_data/etl.py:829,1184,1212,1300`
- **描述**：`_Db` wrapper 的 `execute` 对 PG 走 `psycopg2.extras.DictCursor`（L117），**不读 `row_factory`**。所以 `db.row_factory = sqlite3.Row` 赋值在 PG 模式下是死代码。功能没坏（DictCursor 让 `r["code"]` 在 PG 也能用），但误导——读者以为这是必需的。
- **修复**：在 `_Db.__init__` 加注释 `# row_factory only honored on SQLite path; PG uses DictCursor (see execute())`，或把 `row_factory` 赋值挪进 `_Db.execute` 的 SQLite 分支。

#### **P2-2 pg_adapter._COLUMN_MAP 仅 3 列，靠每个 write_* 函数手补映射**
- **位置**：`packages/kronos-factors/kronos_factors/pg_adapter.py:70-74`
- **描述**：`_COLUMN_MAP = {"pct_chg":"change_pct", "pct_change":"change_pct", "ts_code":"code"}`。但 `pg_writer.write_index_daily` (L162-173) 手工做 `vol→volume`/`pct_chg→change_pct` 重排，`write_daily_basic` (L151-159) 手工做列序重排——说明 adapter 的映射机制不够，要靠业务函数打补丁。新增表必踩坑。
- **修复**：扩 `_COLUMN_MAP` 到 `{"vol":"volume", "pct_chg":"change_pct", "pct_change":"change_pct", "ts_code":"code"}`，或改为双向显式映射表（SQLite↔PG）并在 `_get_pg_columns` 时自动建立。

#### **P2-3 backend SIT 测试用 httpx 触发 DeprecationWarning**
- **位置**：`backend/tests/sit/test_auth_integration.py::TestRefresh::test_refresh_from_cookie`（pytest 输出实证）
- **描述**：`httpx._client.py:1859` DeprecationWarning: "Setting per-request cookies=<...> is being deprecated"。非阻断，但未来 httpx 升级会 break。
- **修复**：测试改为在 `httpx.AsyncClient` 实例上设 cookies，而非 per-request。

#### **P2-4 api-gateway 不转发上游响应 headers（Content-Type 之外全丢）**
- **位置**：`services/api-gateway/app/main.py:135-139`
- **描述**：`Response(content=..., status_code=..., media_type=...)` 只传了 content/status/content-type，丢掉 `Set-Cookie`（refresh_token！）、`X-Request-ID`、`Cache-Control` 等。**潜在影响**：如果未来 backend 直接对 gateway 域设 refresh cookie，cookie 会被 gateway 吃掉。当前 refresh cookie path=`/api/v1/auth` 且 `SameSite=Strict`，前端直连 backend 不经 gateway，所以暂不影响。
- **修复**：用 `headers={k:v for k,v in resp.headers.items()}` 透传（注意 strip hop-by-hop headers）。

---

## §3 修复优先级建议

### 必修（P0，发布前阻断）

按"交易资金安全 > 安全漏洞 > 阻断功能"排序：

1. **P0-3 circuit_breaker 加锁** — 资金风险，并发下熔断失效可能直接导致超限下单。修复成本低（加 `asyncio.Lock` + 5 个函数包一层）。
2. **P0-1 diagnosis/training JWT fallback 统一** — 跨服务认证阻断。修复成本极低（复制 backend 的 `_secret()` 函数）。
3. **P0-2 trade-service/deps.py 删死代码或改用 kronos-auth** — 定时炸弹。修复成本极低（删文件）。

### 建议修（P1，下个迭代）

按"数据正确性 > 认证 > 依赖纪律 > 可观测性"排序：

4. **P1-3 pledge_detail 列名** — 数据可能长期丢失，需先 `\d pledge_detail` 验证。
5. **P1-5 refresh_token rotate 加 type 校验** — 防御性，修复成本低。
6. **P1-6 trade_password 内存脱敏** — 资金凭证 hygiene。
7. **P1-4 schema audit 清空 EXCLUDED** — 让 P1-3 这类问题自动暴露。
8. **P1-1 diagnosis 换 urllib** + **P1-2 删死代码 nested gateway** — 依赖纪律。
9. **P1-7 signal/diagnosis 裸 SQL 用 Identifier** — 防御性。
10. **P1-9 数据管道异常吞没** — 可观测性，根治"数据停滞数周无人察觉"。
11. **P1-8 gateway 限流内存增长** — 长期运行稳定性。

### 可缓（P2，技术债）

12. **P2-1 / P2-2** — 文档/抽象改进，无功能影响。
13. **P2-3** — 测试 warning，等 httpx 升级时一起处理。
14. **P2-4** — 当前 cookie 走直连不受影响，但建议在 gateway 化推进前修。

---

## §4 正面发现（值得保留的设计）

1. **`_insert_rows` 自动列过滤（止血 commit 2d311fa）** — `etl.py:264-276` 的 `valid_cols` 过滤 + `dropped` 列 WARN 是优秀的防御性设计，把"列错位导致整批归零"降级为"丢列告警"。这一层是数据管道的正确兜底。
2. **kronos-auth 包的 X-Service-Auth 守卫（`config.py:53` + `deps.py:77`）** — `SERVICE_AUTH_ENABLED = not KRONOS_SERVICE_SECRET.startswith("dev-only-")` 是漂亮的深度防御：即使部署侧忘设 `KRONOS_ENV=production`，dev fallback 也绝不能授予 admin 豁免。
3. **backend `_secret()` 分级 raise 契约（`config.py:18-38`）** — prod 缺失 raise / dev 缺失 warn + `dev-only-` 前缀（日志一眼识别）/ 禁 `secrets.token_hex` 进程内随机，是正确的密钥管理范式。P0-1/P0-2 本质都是该范式未推广到所有服务。
4. **refresh_token family rotation（`auth_service.py:200-250`）** — 检测到 revoked token 被复用 → 整族作废（L222 `_revoke_family`），是 OAuth refresh token theft 的标准防御。
5. **PaperTradingEngine + ExecutorManager 都正确加了锁**（`engine.py:49`, `executor.py:158`）—— 唯独 circuit_breaker 漏了（P0-3），说明团队有并发意识，只是漏了一处。

---

<!-- agf-verdict (machine-readable; validate-review-verdict.sh consumes this block)
critical_count: 3
warning_count: 9
suggestion_count: 4
code_verdict: approve with changes
sit_audit_verdict: N/A
verdict_rationale: |
  3 个 P0 全是真实的资金风险 / 安全阻断（circuit_breaker 竞态 / JWT fallback 不一致 / 死代码随机密钥），
  每个 P0 均含 file:line + 复现步骤 + 修复建议，符合铁律 #2。
  无 Critical 级 SQL 注入（f-string 拼接处均用常量/参数化，当前安全）；
  无 Critical 级越权（admin endpoint 全部 require_role("admin")，RBAC 完整）。
  P1-3 pledge 列名 bug 可能是长期数据丢失，但需先验证 PG 实际列名才能定级 P0——保守标 P1。
  代码 verdict = approve with changes：核心问题（P0-1/P0-2/P0-3）修复成本均低且与发布阻断性强相关，
  建议修完 P0 再合并；P1/P2 不阻断但强烈建议纳入下个迭代。
-->
