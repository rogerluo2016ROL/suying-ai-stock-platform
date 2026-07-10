from tools.page_api_smoke import probe

def test_page_smoke_module_exposes_probe():
    assert callable(probe)
