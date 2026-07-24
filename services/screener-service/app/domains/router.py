"""Composition root for the three Screener HTTP domains."""

from fastapi import APIRouter, Depends
from kronos_auth import get_current_user_jwt, require_role

from app.domains.candidates.router import router as candidates_router
from app.domains.screening.router import router as screening_router
from app.domains.supply_chain.router import router as supply_chain_router

# 只读 GET 统一要求登录 JWT（服务间调用走 X-Service-Auth 豁免，由 kronos_auth 内部处理）。
router = APIRouter(dependencies=[Depends(get_current_user_jwt)])

# 写/触发类端点角色守卫（按 method+path 集中分类，免逐端点改签名）：
# _USER_WRITE_PATHS 为前端普通用户可达页面会调的写接口（选股执行/政策解读/自选/候选池/
# 产业链 extract 与映射、capex 评审），放行 user；其余写接口默认仅 admin/internal_analyst。
# 新增写端点未列入白名单时自动落入 analyst-only（fail-closed）。
# 注意：include_router 会新建 route 对象，不能就地改 domain router 的 route.dependencies——
# 域 router 与 app.routers.screener 兼容门面共享 route 对象，就地支改会把认证依赖泄漏给门面。
_USER_WRITE_PATHS = {
    "/api/v1/screener/run",
    "/api/v1/screener/policy/interpret",
    "/api/v1/screener/candidate-pool",
    "/api/v1/screener/watchlist",
    "/api/v1/screener/supply-chain/extract",
    "/api/v1/screener/supply-chain/capex-evidence/{capex_evidence_id}/review",
    "/api/v1/screener/supply-chain/mapping-review/{code}/{node_id}",
}

_ANALYST_DEP = Depends(require_role("admin", "internal_analyst"))
_USER_DEP = Depends(require_role("admin", "internal_analyst", "user"))
_WRITE_METHODS = {"POST", "PUT", "DELETE", "PATCH"}


def _include_with_write_guards(domain_router: APIRouter) -> None:
    """按读/写拆分后分别 include，写接口经 include_router(dependencies=...) 挂角色守卫。"""
    readonly = APIRouter()
    user_write = APIRouter()
    analyst_write = APIRouter()
    for route in domain_router.routes:
        # FastAPI 0.139 起 route.methods 由 set 变 tuple, 统一 set 化兼容两个版本
        methods = set(getattr(route, "methods", None) or ())
        if not methods & _WRITE_METHODS:
            readonly.routes.append(route)
        elif route.path in _USER_WRITE_PATHS:
            user_write.routes.append(route)
        else:
            analyst_write.routes.append(route)
    router.include_router(readonly)
    router.include_router(user_write, dependencies=[_USER_DEP])
    router.include_router(analyst_write, dependencies=[_ANALYST_DEP])


for _domain_router in (screening_router, candidates_router, supply_chain_router):
    _include_with_write_guards(_domain_router)
