# ADR-016 平台运行时契约

## 决策

Gateway 是唯一外部入口；`/api/v1/data` 归 `data-service:8010`。signal-service 的旧 dashboard/data 路径仅作兼容并返回弃用头。training 由 training-service 独占，screener 不注册 mock。

## 影响

客户端只提交租户、账户和交易模式选择；用户身份由已验证 JWT 重建。内部服务使用 compose 网络，不对宿主机发布端口。
