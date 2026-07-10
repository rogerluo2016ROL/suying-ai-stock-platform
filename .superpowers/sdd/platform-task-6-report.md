# Task 6 报告：微服务隔离测试与 CI 矩阵

## RED

`bash tools/codex-lowio.sh py tools/tests/test_run_service_tests.py -q` 首次运行因缺少 `run_service_tests` 模块失败（预期）。

## GREEN

- 新增 `tools/run_service_tests.py`：每个服务使用独立子进程、独立 cwd 和服务优先 `PYTHONPATH`。
- 新增 runner 单测，覆盖 cwd/进程、未知服务拒绝、12 个 core target。
- CI 增加 12 服务矩阵，前端增加 build，Docker build 依赖服务测试。
- lowio 增加 `service-test` 入口，pyproject 纳入 `tools/tests`。

## 命令结果

- `bash tools/codex-lowio.sh py tools/tests/test_run_service_tests.py -q`：3 passed。
- `python3 tools/run_service_tests.py --core -q`：runner 可逐服务启动；本机依赖未安装且已有服务测试存在路径假设，backend/data-service 等测试收集失败，随后手动中断。
- `git diff --check`：通过。

## SHA

见提交后的 `git rev-parse HEAD`。

## 遗留问题

CI 仍需各服务依赖安装步骤（当前仓库没有统一服务依赖安装清单）；本地全矩阵不能作为绿灯结果。
