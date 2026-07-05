"""
设备类实体识别测试 - P34
"""
import pytest
from src.baa_engine.semantic_analyzer import SemanticAnalyzer


class TestEquipmentDetection:
    """设备类实体识别测试"""

    def setup_method(self):
        self.analyzer = SemanticAnalyzer()

    def test_fire_hydrant_layer(self):
        """测试消火栓图层识别"""
        assert self.analyzer._classify_by_layer("EQUIP_消火栓") == "fire_hydrant"

    def test_sprinkler_layer(self):
        """测试喷淋图层识别"""
        assert self.analyzer._classify_by_layer("VALVE_喷淋") == "sprinkler"

    def test_smoke_detector_layer(self):
        """测试烟感图层识别"""
        assert self.analyzer._classify_by_layer("VESDA") == "smoke_detector"
        assert self.analyzer._classify_by_layer("烟感") == "smoke_detector"
        assert self.analyzer._classify_by_layer("温感") == "smoke_detector"

    def test_fire_extinguisher_layer(self):
        """测试灭火器图层识别"""
        assert self.analyzer._classify_by_layer("灭火器") == "fire_extinguisher"

    def test_electrical_equipment_layer(self):
        """测试电气设备图层识别"""
        assert self.analyzer._classify_by_layer("电-") == "equipment"
        assert self.analyzer._classify_by_layer("配电") == "equipment"
        assert self.analyzer._classify_by_layer("配电箱") == "equipment"
        assert self.analyzer._classify_by_layer("应急照明") == "equipment"

    def test_alarm_device_layer(self):
        """测试报警设备图层识别"""
        assert self.analyzer._classify_by_layer("报警") == "alarm_device"
        assert self.analyzer._classify_by_layer("广播") == "alarm_device"
        assert self.analyzer._classify_by_layer("疏散指示") == "alarm_device"


class TestEquipmentDetectionByGeometry:
    """设备几何特征识别测试"""

    def setup_method(self):
        self.analyzer = SemanticAnalyzer()

    def test_circle_fire_hydrant(self):
        """测试圆形消火栓识别"""
        # 模拟圆形几何体
        pass

    def test_rectangular_electrical_box(self):
        """测试矩形配电箱识别"""
        # 模拟矩形几何体
        pass


class TestEquipmentDetectionByText:
    """设备文本识别测试"""

    def setup_method(self):
        self.analyzer = SemanticAnalyzer()

    def test_text_fire_hydrant(self):
        """测试文本消火栓识别"""
        # 模拟文本识别
        pass

    def test_text_sprinkler(self):
        """测试文本喷淋识别"""
        # 模拟文本识别
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
