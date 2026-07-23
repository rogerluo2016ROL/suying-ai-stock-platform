"""SQL / YAML / JSON adapter 单测（04 §3.3 / §4.3 / §4.4）。"""

from codemap.extract.json_adapter import JSONAdapter
from codemap.extract.sql_adapter import SQLAdapter
from codemap.extract.yaml_adapter import YAMLAdapter


# ---- SQL ----

SQL_SOURCE = b"""\
CREATE TABLE users (
    id INTEGER PRIMARY KEY,
    name TEXT
);

CREATE TABLE orders (
    id INTEGER PRIMARY KEY,
    user_id INTEGER REFERENCES users(id)
);
"""


def test_sql_extracts_table_nodes():
    a = SQLAdapter()
    root = a.parse(SQL_SOURCE)
    syms = a.extract_symbols(root, "migrations/1.sql")
    names = {s.name for s in syms}
    assert {"users", "orders"} <= names
    assert all(s.type == "schema" for s in syms)
    assert all(s.id.startswith("schema:migrations/1.sql:") for s in syms)


def test_sql_fk_creates_depends_on_edge():
    a = SQLAdapter()
    root = a.parse(SQL_SOURCE)
    edges = a.extract_edges(root, "migrations/1.sql")
    # orders.user_id REFERENCES users → schema:orders depends_on schema:users
    assert any(
        e.src.endswith(":orders") and e.dst.endswith(":users") and e.type == "depends_on"
        for e in edges
    )


# ---- YAML（docker-compose）----

COMPOSE = b"""\
services:
  web:
    image: nginx
    depends_on:
      - db
      - cache
  db:
    image: postgres
  cache:
    image: redis
"""


def test_yaml_extracts_service_nodes():
    a = YAMLAdapter()
    doc = a.parse(COMPOSE)
    syms = a.extract_symbols(doc, "docker-compose.yml")
    names = {s.name for s in syms}
    assert {"web", "db", "cache"} <= names
    assert all(s.type == "service" for s in syms)


def test_yaml_depends_on_edges():
    a = YAMLAdapter()
    doc = a.parse(COMPOSE)
    edges = a.extract_edges(doc, "docker-compose.yml")
    # web depends_on db + cache
    targets = {e.dst.split(":")[-1] for e in edges if e.src.endswith(":web")}
    assert {"db", "cache"} <= targets
    assert all(e.type == "depends_on" for e in edges)


def test_yaml_long_form_depends_on(tmp_path):
    """depends_on long form（dict with condition）也解析。"""
    a = YAMLAdapter()
    doc = a.parse(b"services:\n  web:\n    depends_on:\n      db:\n        condition: service_started\n")
    edges = a.extract_edges(doc, "c.yml")
    assert any(e.src.endswith(":web") and e.dst.endswith(":db") for e in edges)


def test_yaml_loose_loader_ignores_custom_tag():
    """自定义 tag（docker-compose !override / !reset）降级 None 不崩，services/depends_on 仍提取。

    防 PyYAML safe_load 遇 !override 崩 → build Pass 2 整事务回滚（RolexOps 实例）。
    """
    a = YAMLAdapter()
    doc = a.parse(b"services:\n  web:\n    ports: !override\n    depends_on: [db]\n  db: {}\n")
    assert "web" in doc["services"]
    assert doc["services"]["web"]["ports"] is None              # !override → None
    edges = a.extract_edges(doc, "c.yml")
    assert any(e.src.endswith(":web") and e.dst.endswith(":db") for e in edges)


# ---- JSON（package.json）----

PACKAGE_JSON = b"""\
{
  "name": "myapp",
  "dependencies": { "react": "^18.0.0", "lodash": "^4.0.0" }
}
"""


def test_json_extracts_config_node():
    a = JSONAdapter()
    doc = a.parse(PACKAGE_JSON)
    syms = a.extract_symbols(doc, "package.json")
    assert len(syms) == 1
    assert syms[0].type == "config"
    assert syms[0].name == "myapp"


def test_json_no_internal_edges():
    """package.json dependencies 全 external，不建项目内边。"""
    a = JSONAdapter()
    doc = a.parse(PACKAGE_JSON)
    assert a.extract_edges(doc, "package.json") == []


def test_json_parses_jsonc_comments():
    """tsconfig 等 JSONC（/* */ 块 + // 行注释）容错解析。

    防 json.loads 遇注释崩 → build Pass 2 回滚（RolexOps tsconfig.app.json）。
    """
    a = JSONAdapter()
    doc = a.parse(b'{\n"name":"x",\n/* block comment */\n"v":1\n// line comment\n}')
    assert doc["name"] == "x"
    assert doc["v"] == 1
