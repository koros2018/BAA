"""P48: 施工图审查深度标准测试"""

from src.baa_engine.spec_data.construction_review import (
    CONSTRUCTION_REVIEW_ITEMS,
    get_construction_review_items,
)
from src.baa_engine.spec_data import get_construction_review_items as from_init


class TestConstructionReview:
    def test_item_count(self):
        assert len(CONSTRUCTION_REVIEW_ITEMS) == 30

    def test_level_distribution(self):
        levels = [i.level for i in CONSTRUCTION_REVIEW_ITEMS]
        assert levels.count("L1") == 10
        assert levels.count("L2") == 10
        assert levels.count("L3") == 10

    def test_auto_checkable(self):
        auto = [i for i in CONSTRUCTION_REVIEW_ITEMS if i.check_method == "auto"]
        assert len(auto) == 7  # CD-011/014/015/019/024/025/027

    def test_filter_by_level(self):
        l1 = get_construction_review_items(level="L1")
        assert len(l1) == 10
        assert all(i["level"] == "L1" for i in l1)

    def test_filter_by_major(self):
        arch = get_construction_review_items(major="arch")
        assert len(arch) > 10  # arch is the most covered major

    def test_filter_by_category(self):
        completeness = get_construction_review_items(category="completeness")
        assert len(completeness) == 10

    def test_filter_combined(self):
        l3_auto = get_construction_review_items(level="L3", check_method="auto")
        for i in l3_auto:
            assert i["level"] == "L3"
            assert i["check_method"] == "auto"

    def test_func_ids_attached(self):
        auto_items = [i for i in CONSTRUCTION_REVIEW_ITEMS if i.check_method == "auto"]
        for i in auto_items:
            assert i.func_id is not None

    def test_api_compat_import(self):
        """验证从 __init__ 也能导入"""
        items = from_init(level="L2")
        assert isinstance(items, list)
