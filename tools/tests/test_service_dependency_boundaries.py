from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def _dependencies(service: str) -> set[str]:
    payload = tomllib.loads(
        (ROOT / "services" / service / "pyproject.toml").read_text(encoding="utf-8")
    )
    return {dependency.split(">", 1)[0].split(" ", 1)[0] for dependency in payload["project"]["dependencies"]}


def test_api_only_services_do_not_install_model_runtime():
    for service in ("trade-service", "strategy-service", "alert-service"):
        dependencies = _dependencies(service)
        assert "kronos-core" not in dependencies, service


def test_prediction_image_installs_cpu_torch_before_kronos_core():
    dockerfile = (ROOT / "services" / "prediction-service" / "Dockerfile").read_text(encoding="utf-8")
    cpu_install = "pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch"
    assert cpu_install in dockerfile
    assert dockerfile.index(cpu_install) < dockerfile.index("/app/packages/kronos-core")
