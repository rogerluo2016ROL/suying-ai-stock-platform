# 全模型飞书自动推送实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让统一流水线中的全部已注册选股、选债模型默认推送飞书，并记录可复核的送达证据。

**Architecture:** `configs/model_pipeline.json` 保存默认开关，命令行双向参数可以覆盖它。`tools/run_research_pipeline.py` 在本地结果落盘后发送消息，提取 `message_id`，通过 `lark-cli` 反查目标群，并把发送状态写回本次运行文件。

**Tech Stack:** Python 3、argparse、pytest、lark-cli、JSON

## Global Constraints

- 不改变模型逻辑、数据刷新规则、入选结果或报告内容。
- 不把应用密钥、访问令牌写入代码、日志、结果文件或测试夹具。
- “全部模型”限定为 `configs/model_pipeline.json` 中注册且由 `tools/run_research_pipeline.py` 执行的模型。
- 飞书发送失败或送达反查失败时，流水线必须以失败结束，已生成的本地模型结果仍需保留。
- 不提交工作区中与本功能无关的改动。

---

### Task 1: 默认推送开关和命令行覆盖

**Files:**
- Modify: `configs/model_pipeline.json`
- Modify: `tools/run_research_pipeline.py:693-707`
- Modify: `tools/tests/test_run_research_manifest.py`

**Interfaces:**
- Consumes: `load_config(path) -> dict[str, Any]`
- Produces: `resolve_send_feishu(args: argparse.Namespace, config: dict[str, Any]) -> bool`

- [ ] **Step 1: 写失败测试**

在 `tools/tests/test_run_research_manifest.py` 增加：

```python
def test_send_feishu_defaults_to_config():
    assert pipeline.resolve_send_feishu(_args(send_feishu=None), {"send_feishu_by_default": True}) is True
    assert pipeline.resolve_send_feishu(_args(send_feishu=None), {"send_feishu_by_default": False}) is False


def test_send_feishu_cli_overrides_config():
    assert pipeline.resolve_send_feishu(_args(send_feishu=True), {"send_feishu_by_default": False}) is True
    assert pipeline.resolve_send_feishu(_args(send_feishu=False), {"send_feishu_by_default": True}) is False


def test_parser_accepts_both_feishu_switches():
    parser = pipeline.build_parser()
    assert parser.parse_args(["--model", "short"]).send_feishu is None
    assert parser.parse_args(["--model", "short", "--send-feishu"]).send_feishu is True
    assert parser.parse_args(["--model", "short", "--no-send-feishu"]).send_feishu is False
```

- [ ] **Step 2: 运行测试并确认因缺少函数或双向参数而失败**

Run: `pytest -q tools/tests/test_run_research_manifest.py -k 'send_feishu or parser_accepts'`

Expected: FAIL，错误包含 `resolve_send_feishu` 不存在，或 `--no-send-feishu` 无法解析。

- [ ] **Step 3: 写最小实现**

在 `tools/run_research_pipeline.py` 增加：

```python
def resolve_send_feishu(args: argparse.Namespace, config: dict[str, Any]) -> bool:
    if args.send_feishu is not None:
        return bool(args.send_feishu)
    return bool(config.get("send_feishu_by_default", False))
```

把参数改为：

```python
parser.add_argument(
    "--send-feishu",
    action=argparse.BooleanOptionalAction,
    default=None,
    help="发送飞书群消息（默认读取配置，可用 --no-send-feishu 临时关闭）",
)
```

把发送条件改为 `if resolve_send_feishu(args, config):`，并在 `configs/model_pipeline.json` 顶层加入：

```json
"send_feishu_by_default": true
```

- [ ] **Step 4: 运行测试并确认通过**

Run: `pytest -q tools/tests/test_run_research_manifest.py -k 'send_feishu or parser_accepts'`

Expected: `3 passed`。

---

### Task 2: 消息 ID 提取和送达反查

**Files:**
- Modify: `tools/run_research_pipeline.py`
- Modify: `tools/tests/test_run_research_manifest.py`

**Interfaces:**
- Produces: `extract_message_id(response: Any) -> str`
- Produces: `confirm_message_delivery(chat_id: str, message_id: str) -> bool`
- Produces: `write_delivery_state(run_dir: Path, result: dict[str, Any], state: dict[str, Any]) -> None`

- [ ] **Step 1: 写失败测试**

```python
def test_extract_message_id_from_nested_response():
    assert pipeline.extract_message_id({"code": 0, "data": {"message_id": "om_test"}}) == "om_test"
    assert pipeline.extract_message_id({"data": {"message": {"message_id": "om_nested"}}}) == "om_nested"
    assert pipeline.extract_message_id({"code": 0}) == ""


def test_confirm_message_delivery_uses_bot_chat_query(monkeypatch):
    seen = {}

    class FakeProc:
        returncode = 0
        stdout = '{"items":[{"message_id":"om_test"}]}'
        stderr = ""

    def fake_run(cmd, **kwargs):
        seen["cmd"] = cmd
        return FakeProc()

    monkeypatch.setattr(pipeline.subprocess, "run", fake_run)
    assert pipeline.confirm_message_delivery("oc_test", "om_test", attempts=1) is True
    assert seen["cmd"][:5] == ["lark-cli", "im", "+chat-messages-list", "--as", "bot"]


def test_write_delivery_state_updates_both_run_files(tmp_path):
    result = {"pipeline": {"model_key": "short"}}
    pipeline._write_json(tmp_path / "pipeline.json", {"status": "ok"})
    state = {"push_status": "confirmed", "chat_id": "oc_test", "message_id": "om_test"}
    pipeline.write_delivery_state(tmp_path, result, state)
    assert json.loads((tmp_path / "result.json").read_text())["pipeline"]["feishu_delivery"] == state
    assert json.loads((tmp_path / "pipeline.json").read_text())["feishu_delivery"] == state
```

- [ ] **Step 2: 运行测试并确认缺少三个函数**

Run: `pytest -q tools/tests/test_run_research_manifest.py -k 'message_id or delivery'`

Expected: FAIL，错误指向 `extract_message_id`、`confirm_message_delivery` 或 `write_delivery_state` 不存在。

- [ ] **Step 3: 写最小实现**

实现递归查找 `message_id`；用以下命令反查群消息：

```python
cmd = [
    "lark-cli", "im", "+chat-messages-list", "--as", "bot",
    "--chat-id", chat_id, "--page-size", "20", "--no-reactions", "--json",
]
```

`confirm_message_delivery` 最多查询三次，每次先用机器人身份，机器人缺少读取权限时再用本机已登录的用户身份做只读核验；每轮间隔 0.5 秒。命令非零退出、JSON 解析失败或三次未找到消息时返回 `False`。`write_delivery_state` 只写 `push_status`、`chat_id`、`message_id` 和不含凭据的 `error` 字段。

- [ ] **Step 4: 运行测试并确认通过**

Run: `pytest -q tools/tests/test_run_research_manifest.py -k 'message_id or delivery'`

Expected: `3 passed`。

---

### Task 3: 串联发送、失败状态和真实验收

**Files:**
- Modify: `tools/run_research_pipeline.py:659-687`
- Modify: `tools/tests/test_run_research_manifest.py`
- Create: `outputs/feishu_delivery_evidence/2026-07-14-auto-push-test.json`（运行产物，不提交）

**Interfaces:**
- Consumes: `send_text_to_chat(chat_id: str, text: str) -> dict[str, Any]`
- Consumes: Task 2 的三个函数
- Produces: `deliver_feishu_message(...) -> dict[str, Any]`，成功返回 `push_status: confirmed`

- [ ] **Step 1: 写失败测试**

```python
def test_deliver_feishu_message_records_confirmed_state(monkeypatch, tmp_path):
    result = {"pipeline": {"model_key": "short"}}
    pipeline._write_json(tmp_path / "pipeline.json", {"status": "ok"})
    monkeypatch.setattr(pipeline, "confirm_message_delivery", lambda chat_id, message_id: True)
    state = pipeline.deliver_feishu_message(
        run_dir=tmp_path,
        result=result,
        chat_id="oc_test",
        message="功能测试",
        sender=lambda chat_id, text: {"data": {"message_id": "om_test"}},
    )
    assert state["push_status"] == "confirmed"
    assert state["message_id"] == "om_test"


def test_deliver_feishu_message_records_unconfirmed_and_raises(monkeypatch, tmp_path):
    result = {"pipeline": {"model_key": "short"}}
    pipeline._write_json(tmp_path / "pipeline.json", {"status": "ok"})
    monkeypatch.setattr(pipeline, "confirm_message_delivery", lambda chat_id, message_id: False)
    with pytest.raises(RuntimeError, match="未确认送达"):
        pipeline.deliver_feishu_message(
            run_dir=tmp_path,
            result=result,
            chat_id="oc_test",
            message="功能测试",
            sender=lambda chat_id, text: {"data": {"message_id": "om_test"}},
        )
    state = json.loads((tmp_path / "pipeline.json").read_text())["feishu_delivery"]
    assert state["push_status"] == "unconfirmed"
```

测试文件顶部增加 `import pytest`。

- [ ] **Step 2: 运行测试并确认缺少交付函数**

Run: `pytest -q tools/tests/test_run_research_manifest.py -k 'deliver_feishu_message'`

Expected: FAIL，错误包含 `deliver_feishu_message` 不存在。

- [ ] **Step 3: 写最小实现并接入流水线**

`deliver_feishu_message` 负责发送、提取消息 ID、反查和写状态。发送异常写 `push_status: failed` 后重新抛出；缺少消息 ID 或反查失败写 `push_status: unconfirmed` 后抛出 `RuntimeError`。

流水线用该函数替换直接调用 `send_text_to_chat(chat_id, message)`。海报发送保持原逻辑，不计入摘要消息的送达状态。

- [ ] **Step 4: 运行定向和相关回归测试**

Run: `pytest -q tools/tests/test_run_research_manifest.py services/screener-service/tests/test_lark_bot.py`

Expected: 所有测试通过，0 failures。

- [ ] **Step 5: 运行配置和语法检查**

Run: `python -m json.tool configs/model_pipeline.json >/dev/null && python -m py_compile tools/run_research_pipeline.py && git diff --check`

Expected: exit code 0，无输出错误。

- [ ] **Step 6: 发送真实功能测试消息并反查**

使用项目默认群发送文本：

```text
飞书自动推送功能测试
日期：2026-07-14
说明：这是功能验收消息，不是选股或选债建议。
```

调用 `deliver_feishu_message`，把返回的非敏感字段写入 `outputs/feishu_delivery_evidence/2026-07-14-auto-push-test.json`。随后独立运行 `lark-cli im +chat-messages-list --as bot --chat-id <默认群> --page-size 20 --no-reactions --json`，核对同一个 `message_id`。

Expected: `push_status` 为 `confirmed`，群消息列表存在同一个 `message_id`。

- [ ] **Step 7: 复核改动范围并提交**

Run: `git diff -- configs/model_pipeline.json tools/run_research_pipeline.py tools/tests/test_run_research_manifest.py`

只暂存上述三个文件，提交信息：

```bash
git commit -m "feat: enable confirmed Feishu delivery by default"
```
