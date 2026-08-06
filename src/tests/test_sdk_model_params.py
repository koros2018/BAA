"""P93: SDK 模型参数导出方法签名与 URL 构建测试"""

import pytest


class TestSDKModelParams:
    @pytest.fixture
    def c(self):
        from src.sdk import BAAClient

        return BAAClient(api_key="k", base_url="http://test")

    def test_all_methods_exist(self, c):
        for m in (
            "model_params_functions",
            "model_params_layer_rules",
            "model_params_cd_items",
            "model_params_samples",
            "model_params_spatial_graph",
            "export_model_params",
        ):
            assert hasattr(c, m) and callable(getattr(c, m))

    def test_export_url_json(self, c):
        url = c._url("/api/v1/model-params/export", {"format": "json", "limit": 500})
        assert "format=json" in url
        assert "limit=500" in url

    @pytest.mark.parametrize("fmt", ["json", "jsonl-sft", "hf-dataset", "csv"])
    def test_export_format_param(self, c, fmt):
        url = c._url("/api/v1/model-params/export", {"format": fmt, "limit": 100})
        assert f"format={fmt}" in url

    def test_functions_url(self, c):
        url = c._url("/api/v1/model-params/functions", {"category": "dim", "limit": 50})
        assert "category=dim" in url

    def test_samples_url(self, c):
        url = c._url("/api/v1/model-params/samples", {"limit": 200})
        assert "limit=200" in url
