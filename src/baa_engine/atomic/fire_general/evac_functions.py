"""
BAA 原子函数 - EVAC 类别
4 条原子函数
"""

from ...atomic_functions import (
    AtomicFunction,
    FuncCategory,
)

MODULE_FUNCS = [
AtomicFunction(
        "EVAC-001",
        "疏散路径连通性判定",
        FuncCategory.EVAC,
        "GB50016-5.5.17",
        "每个房间应有通往安全出口的疏散路径",
        "==",
        1.0,
        "有/无",
        target_entities=["room", "space", "floor"],
    ),
AtomicFunction(
        "EVAC-002",
        "疏散路径长度判定",
        FuncCategory.EVAC,
        "GB50016-5.5.17",
        "房间到最近安全出口的疏散距离不应大于30m",
        "<=",
        30.0,
        "m",
        target_entities=["room", "space", "floor"],
        depends_on=["EVAC-001"],
    ),
AtomicFunction(
        "EVAC-003",
        "疏散路径合规性判定",
        FuncCategory.EVAC,
        "GB50016-5.5.17",
        "房间到安全出口的疏散路径应满足规范要求",
        "==",
        1.0,
        "合规/违规",
        target_entities=["room", "space", "floor"],
        depends_on=["EVAC-001"],
    ),
AtomicFunction(
        "EVAC-004",
        "疏散路径瓶颈判定",
        FuncCategory.EVAC,
        "GB50016-5.5.18",
        "疏散路径上的走廊净宽不应小于1.2m，门净宽不应小于0.8m",
        "==",
        1.0,
        "通畅/瓶颈",
        target_entities=["room", "space", "floor"],
        depends_on=["EVAC-001"],
    ),
]
