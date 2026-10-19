"""T3 标记图元采样豁免（治理②③：组件层 vs 实体层过滤差异）。

根因（d3 实测）：primitives 23,651 > max_entities=10,000 时 random.sample
把组件层已识别的 381 个 T3 标记图元丢弃 227 个（含 T-B3 FN 门 handle=13A55），
造成「组件层已识别、实体层消失」漏报。修复：标记图元全量保留，
采样仅从未标记图元池进行。
"""

from src.baa_engine.drawing_parser import RawPrimitive
from src.baa_engine.semantic_analyzer import SemanticAnalyzer


def _noise_prim(i):
    # 短碎线: 几何兜底为 other, 不干扰目标实体计数
    return RawPrimitive(
        dxf_type="LINE", layer="DOTE", handle=f"N{i:05d}",
        bbox={"x": float(i * 100), "y": 0.0, "width": 10.0, "height": 0.0},
        properties={},
    )


def _t3_door(handle, x, y):
    return RawPrimitive(
        dxf_type="INSERT", layer="WINDOW", handle=handle,
        bbox={"x": x, "y": y, "width": 0.0, "height": 0.0},
        properties={"_t3_native": "door", "block_name": "$DorLib2D$00000001"},
    )


def _t3_wall_line(handle, i):
    return RawPrimitive(
        dxf_type="LINE", layer="WALL", handle=handle,
        bbox={"x": float(i * 5000), "y": 900000.0, "width": 3000.0, "height": 0.0},
        properties={"_t3_wall_gid": i,
                    "_t3_wall_seg": {"orientation": "h", "pos": 900000.0,
                                     "start": float(i * 5000),
                                     "end": float(i * 5000) + 3000.0,
                                     "thickness": 200.0}},
    )


class TestT3SamplingExemption:
    def test_marked_door_survives_sampling(self):
        """超 max_entities 采样时,T3 标记门图元全量保留(修复前随机丢失)。"""
        doors = [_t3_door(f"D{k}", 1000.0 + k * 2000.0, 5000.0) for k in range(5)]
        noise = [_noise_prim(i) for i in range(300)]
        ents = SemanticAnalyzer().analyze(
            noise + doors, [], block_refs=None, max_entities=50
        ).get("entities", [])
        out = [e for e in ents if e["type"] == "door"]
        assert len(out) == 5

    def test_marked_wall_survives_sampling(self):
        """T3 墙标记图元(_t3_wall_gid)同样豁免采样。"""
        walls = [_t3_wall_line(f"W{k}", k) for k in range(4)]
        noise = [_noise_prim(i) for i in range(300)]
        ents = SemanticAnalyzer().analyze(
            noise + walls, [], block_refs=None, max_entities=50
        ).get("entities", [])
        out = [e for e in ents if e["type"] == "wall"]
        assert len(out) == 4

    def test_unmarked_sample_size_bounded(self):
        """未标记图元池仍按预算采样,总量不超 max_entities。"""
        noise = [_noise_prim(i) for i in range(300)]
        doors = [_t3_door(f"D{k}", 1000.0 + k * 2000.0, 5000.0) for k in range(10)]
        sa = SemanticAnalyzer()
        sa.analyze(noise + doors, [], block_refs=None, max_entities=100)
        # 分类总量 = 标记(10) + 采样未标记(90) = 100(分类循环每图元+1)
        assert sa._classify_total <= 100

    def test_below_cap_no_sampling_unchanged(self):
        """低于 max_entities 不触发采样,行为与修复前一致。"""
        noise = [_noise_prim(i) for i in range(30)]
        doors = [_t3_door("D0", 1000.0, 5000.0)]
        ents = SemanticAnalyzer().analyze(
            noise + doors, [], block_refs=None, max_entities=10000
        ).get("entities", [])
        assert sum(1 for e in ents if e["type"] == "door") == 1
