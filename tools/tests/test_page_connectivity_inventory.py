import importlib.util
import sys
from pathlib import Path


_INVENTORY_PATH = Path(__file__).resolve().parents[1] / "page_connectivity_inventory.py"
_SPEC = importlib.util.spec_from_file_location("page_connectivity_inventory", _INVENTORY_PATH)
inventory = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules[_SPEC.name] = inventory
_SPEC.loader.exec_module(inventory)


def test_extract_routes_from_app_source():
    source = """
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Training = lazy(() => import('./pages/Training'))

const protectedRoutes: { path: string; element: React.ReactNode; roles: Role[] }[] = [
  { path: '/', element: <Dashboard />, roles: ['admin'] },
  { path: '/training', element: <Training />, roles: ['admin'] },
]
"""

    lazy_imports = inventory.extract_lazy_page_imports(source)
    routes = inventory.extract_protected_routes(source, lazy_imports)

    assert lazy_imports["Dashboard"] == "frontend/src/pages/Dashboard.tsx"
    assert routes == [
        inventory.RouteEntry(path="/", component="Dashboard", page_file="frontend/src/pages/Dashboard.tsx"),
        inventory.RouteEntry(path="/training", component="Training", page_file="frontend/src/pages/Training.tsx"),
    ]


def test_build_inventory_classifies_api_static_and_prototype_pages(tmp_path):
    project = tmp_path
    pages = project / "frontend/src/pages"
    pages.mkdir(parents=True)
    (project / "frontend/src").mkdir(parents=True, exist_ok=True)
    (project / "frontend/src/App.tsx").write_text(
        """
const Dashboard = lazy(() => import('./pages/Dashboard'))
const Training = lazy(() => import('./pages/Training'))
const AutoTrade = lazy(() => import('./pages/AutoTrade'))

const protectedRoutes: { path: string; element: React.ReactNode; roles: Role[] }[] = [
  { path: '/', element: <Dashboard />, roles: ['admin'] },
  { path: '/training', element: <Training />, roles: ['admin'] },
  { path: '/auto-trade', element: <AutoTrade />, roles: ['admin'] },
]
""",
        encoding="utf-8",
    )
    (pages / "Dashboard.tsx").write_text(
        """
import { signalApi } from '../api/client'
signalApi.getDashboardSummary()
""",
        encoding="utf-8",
    )
    (pages / "Training.tsx").write_text("export default function Training() { return <div /> }", encoding="utf-8")
    (pages / "AutoTrade.tsx").write_text(
        """
import api from '../api/client'
api.get('/strategy/list')
""",
        encoding="utf-8",
    )

    rows = inventory.build_inventory(project)
    by_path = {row.path: row for row in rows}

    assert by_path["/"].status == "needs-smoke"
    assert "signalApi.getDashboardSummary" in by_path["/"].api_calls
    assert by_path["/training"].status == "prototype-only"
    assert by_path["/training"].risk == "high"
    assert by_path["/auto-trade"].status == "needs-smoke"
    assert by_path["/auto-trade"].risk == "high"
    assert "api.get('/strategy/list')" in by_path["/auto-trade"].api_calls


def test_stale_contract_detection_ignores_api_client_base_url():
    assert inventory._stale_contract_notes(["api.get('/strategy/list')"]) == []
    assert inventory._stale_contract_notes(["fetch('/strategy/list')"]) == ["old strategy list endpoint"]


def test_build_inventory_follows_local_hook_imports(tmp_path):
    project = tmp_path
    pages = project / "frontend/src/pages"
    hooks = project / "frontend/src/hooks"
    pages.mkdir(parents=True)
    hooks.mkdir(parents=True)
    (project / "frontend/src/App.tsx").write_text(
        """
const Trade = lazy(() => import('./pages/Trade'))

const protectedRoutes: { path: string; element: React.ReactNode; roles: Role[] }[] = [
  { path: '/trade', element: <Trade />, roles: ['admin'] },
]
""",
        encoding="utf-8",
    )
    (pages / "Trade.tsx").write_text(
        """
import { useLiveTrade } from '../hooks/useLiveTrade'
export default function Trade() {
  useLiveTrade()
  return <div />
}
""",
        encoding="utf-8",
    )
    (hooks / "useLiveTrade.ts").write_text(
        """
import { liveTradeApi } from '../api/liveTrade'
liveTradeApi.getRiskConfig()
""",
        encoding="utf-8",
    )

    rows = inventory.build_inventory(project)

    assert rows[0].status == "needs-smoke"
    assert "liveTradeApi.getRiskConfig" in rows[0].api_calls


def test_build_inventory_excludes_global_context_imports(tmp_path):
    project = tmp_path
    pages = project / "frontend/src/pages"
    components = project / "frontend/src/components"
    contexts = project / "frontend/src/contexts"
    pages.mkdir(parents=True)
    components.mkdir(parents=True)
    contexts.mkdir(parents=True)
    (project / "frontend/src/App.tsx").write_text(
        """
const Trade = lazy(() => import('./pages/Trade'))

const protectedRoutes: { path: string; element: React.ReactNode; roles: Role[] }[] = [
  { path: '/trade', element: <Trade />, roles: ['admin'] },
]
""",
        encoding="utf-8",
    )
    (pages / "Trade.tsx").write_text(
        """
import { ShellThing } from '../components/ShellThing'
export default function Trade() {
  return <ShellThing />
}
""",
        encoding="utf-8",
    )
    (components / "ShellThing.tsx").write_text(
        """
import { useAuth } from '../contexts/AuthContext'
export function ShellThing() { useAuth(); return <div /> }
""",
        encoding="utf-8",
    )
    (contexts / "AuthContext.tsx").write_text(
        """
fetch('/api/v1/auth/me')
""",
        encoding="utf-8",
    )

    rows = inventory.build_inventory(project)

    assert rows[0].api_calls == []


def test_render_markdown_groups_routes_and_summary(tmp_path):
    rows = [
        inventory.InventoryRow(
            path="/",
            component="Dashboard",
            page_file="frontend/src/pages/Dashboard.tsx",
            status="needs-smoke",
            risk="medium",
            api_calls=["signalApi.getDashboardSummary"],
            notes=["dashboard real-data path needs smoke"],
        ),
        inventory.InventoryRow(
            path="/training",
            component="Training",
            page_file="frontend/src/pages/Training.tsx",
            status="prototype-only",
            risk="high",
            api_calls=[],
            notes=["system/model page has no API calls"],
        ),
    ]

    markdown = inventory.render_markdown(rows)

    assert "# 全站页面联通盘点" in markdown
    assert "| `/training` | `Training` | `high` | `prototype-only` |" in markdown
    assert "- high: 1" in markdown
    assert "- needs-smoke: 1" in markdown
