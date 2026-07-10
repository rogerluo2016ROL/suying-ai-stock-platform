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

审查发现初版 CI 只启动服务测试，没有安装服务依赖，可能在干净 runner 上产生误报失败。已补充 shared packages、各服务 `pyproject.toml` 可编辑安装，以及 training-service 的 requirements 安装；Docker job 仍由 service-tests 成功后执行。

本地全矩阵不能作为绿灯结果：当前环境仍缺少部分依赖，且已有 data-service 测试存在仓库根路径假设。
