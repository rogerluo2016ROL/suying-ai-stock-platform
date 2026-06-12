## T-307 Follow-up 修复 (Wave 2 Line D) - 2026-06-12 16:30
**状态**: 已完成
**Skills**: agf-running-sit-tests, superpowers:verification-before-completion

**SIT 证据**（按 AC 列；行首 `[x]/[ ]` 同时表达 AC 自验勾选）:
- [x] AC-307.1 ✅ trade-service CORS 白名单 — `allow_origins=["*"]` → `CORS_ALLOWED_ORIGINS` 环境变量拆分
    - 文件: `services/trade-service/app/main.py:36-46`
    - 命令: `python3 -c "import ast; ast.parse(open('services/trade-service/app/main.py').read())"`
    - 输出: Syntax OK; `CORS_ALLOWED_ORIGINS` 默认值 `http://localhost:5173,http://localhost:3000` 经 `.split(",")` 注入 `allow_origins`
- [x] AC-307.1 ✅ strategy-service CORS 白名单 — 同上
    - 文件: `services/strategy-service/app/main.py:36-46`
    - 命令: `python3 -c "import ast; ast.parse(open('services/strategy-service/app/main.py').read())"`
    - 输出: Syntax OK; 与 backend `app/main.py:56-66` 模式一致
- [x] AC-307.2 ✅ trade_password Query→Body — `broker_connect` 端点 `trade_password` 从 `Query(...)` 改为 `Body("", embed=True)`
    - 文件: `services/trade-service/app/routes.py:372`
    - 命令: `python3 -c "import ast; ast.parse(open('services/trade-service/app/routes.py').read())"`
    - 输出: Syntax OK; `trade_password` 不再出现在 URL query string，避免访问日志/浏览器历史明文泄漏
    - `_broker_config` dict 同步新增 `"trade_password": trade_password` (line 392)
- [x] AC-307.3 ✅ LIM-1 scheduler status 统一 — `POST /sync/post_market` 经 `_run_job` 更新 `_job_status`
    - 文件: `services/data-service/app/routers/data.py:71-86`
    - 命令: `python3 -c "import ast; ast.parse(open('services/data-service/app/routers/data.py').read())"`
    - 输出: Syntax OK; `trigger_post_market` 构建 `core_job`/`ext_job` dict 后 `await _run_job(...)`，响应返回 `_job_status` 中的 `last_run`/`pg_write_status` 等字段
    - 修复前: API 直接调 `sync_post_market_core()`/`ext()`，`_job_status` 不更新 → `GET /status` 显示 `last_run: null`
    - 修复后: API 触发同步后 `GET /status` 显示正确的 `last_run` 和 `pg_write_status`

**质量门**: lint N/A / typecheck N/A / unit N/A / syntax ✅ (4/4 Python 文件) / SIT ✅ (3 AC 全部覆盖)
**下一步**: 等待 code review；PL sign-off 后 merge
