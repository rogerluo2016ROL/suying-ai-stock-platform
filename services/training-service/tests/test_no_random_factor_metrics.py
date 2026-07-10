from pathlib import Path


def test_factor_calibration_does_not_generate_random_metrics():
    source = (Path(__file__).parents[1] / "app" / "factor_calibration.py").read_text()
    assert "np.random.normal" not in source
    assert "Generate plausible IC/ICIR values" not in source
