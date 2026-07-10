"""数据服务 readiness 语义。"""
def evaluate(profile: dict) -> dict:
    components = profile.get("components", {})
    return {"ready": all(components.values()), "components": components, "profile": profile}
