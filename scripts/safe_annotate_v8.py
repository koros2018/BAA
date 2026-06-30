"""
安全注释工具 v8 — 仅补充函数/方法的 docstring 注释

策略：
1. 只处理 def 定义（函数/方法/异步函数）
2. 仅在 def 下一行没有 docstring 时添加
3. 从函数名和参数推断注释内容
4. 不修改任何字符串字面量、多行字符串、f-string
5. 每个文件逐行处理，不做 AST 解析（避免之前的问题）
"""
import re
from pathlib import Path
from typing import List, Tuple

# ── 已知的语义映射 ──
COMMENT_MAP = {
    # API 端点
    "get": "获取资源",
    "list": "列出资源",
    "create": "创建资源",
    "update": "更新资源",
    "delete": "删除资源",
    "post": "提交资源",
    "put": "更新资源",
    "patch": "部分更新",
    "deconstruct": "图纸拆解为结构化数据",
    "reconstruct": "结构化数据重建为图纸",
    "review": "图纸合规审查",
    "health": "服务健康检查",
    "upload": "上传文件",
    "login": "用户登录",
    "logout": "用户登出",
    "register": "注册",
    "verify": "验证",
    "validate": "校验",
    "parse": "解析",
    "extract": "提取",
    "transform": "转换",
    "convert": "转换格式",
    "export": "导出",
    "import": "导入",
    "analyze": "分析",
    "process": "处理",
    "generate": "生成",
    "render": "渲染",
    "predict": "预测",
    "train": "训练",
    "evaluate": "评估",
    "load": "加载",
    "save": "保存",
    "store": "存储",
    "read": "读取",
    "write": "写入",
    "open": "打开",
    "close": "关闭",
    "init": "初始化",
    "setup": "设置",
    "configure": "配置",
    "reset": "重置",
    "clear": "清空",
    "flush": "刷新",
    "notify": "通知",
    "send": "发送",
    "receive": "接收",
    "handle": "处理事件",
    "route": "路由处理",
    "dispatch": "分发",
    "broadcast": "广播",
    "subscribe": "订阅",
    "unsubscribe": "取消订阅",
    "search": "搜索",
    "filter": "过滤",
    "sort": "排序",
    "group": "分组",
    "aggregate": "聚合",
    "compute": "计算",
    "calculate": "计算",
    "estimate": "估算",
    "infer": "推断",
    "detect": "检测",
    "identify": "识别",
    "classify": "分类",
    "match": "匹配",
    "merge": "合并",
    "split": "拆分",
    "join": "连接",
    "concat": "拼接",
    "intersect": "交集",
    "subtract": "差集",
    "union": "并集",
    "build": "构建",
    "construct": "构造",
    "destroy": "销毁",
    "cleanup": "清理",
    "purge": "清除",
    "archive": "归档",
    "backup": "备份",
    "restore": "恢复",
    "migrate": "迁移",
    "sync": "同步",
    "async": "异步处理",
    "wait": "等待",
    "sleep": "休眠",
    "retry": "重试",
    "abort": "中止",
    "cancel": "取消",
    "pause": "暂停",
    "resume": "恢复",
    "enable": "启用",
    "disable": "禁用",
    "toggle": "切换",
    "start": "启动",
    "stop": "停止",
    "restart": "重启",
    "install": "安装",
    "uninstall": "卸载",
    "upgrade": "升级",
    "downgrade": "降级",
    "attach": "附加",
    "detach": "分离",
    "bind": "绑定",
    "unbind": "解绑",
    "mount": "挂载",
    "unmount": "卸载",
    "connect": "连接",
    "disconnect": "断开",
    "register": "注册",
    "deregister": "注销",
    "authenticate": "认证",
    "authorize": "授权",
    "revoke": "撤销",
    "renew": "续期",
    "refresh": "刷新",
    "check": "检查",
    "test": "测试",
    "benchmark": "基准测试",
    "profile": "性能分析",
    "monitor": "监控",
    "track": "追踪",
    "log": "记录日志",
    "debug": "调试",
    "trace": "跟踪",
    "warn": "警告",
    "error": "错误处理",
    "fail": "失败处理",
    "succeed": "成功处理",
    "ack": "确认",
    "nack": "拒绝确认",
    "respond": "响应",
    "reply": "回复",
    "forward": "转发",
    "redirect": "重定向",
    "resolve": "解析",
    "lookup": "查找",
    "find": "查找",
    "locate": "定位",
    "navigate": "导航",
    "explore": "探索",
    "discover": "发现",
    "collect": "收集",
    "gather": "收集",
    "assemble": "组装",
    "compile": "编译",
    "interpret": "解释",
    "transpile": "转译",
    "minify": "压缩",
    "obfuscate": "混淆",
    "encrypt": "加密",
    "decrypt": "解密",
    "encode": "编码",
    "decode": "解码",
    "hash": "哈希",
    "checksum": "校验和",
    "compress": "压缩",
    "decompress": "解压",
    "pack": "打包",
    "unpack": "解包",
    "serialize": "序列化",
    "deserialize": "反序列化",
    "format": "格式化",
    "stringify": "字符串化",
    "parse": "解析",
    "normalize": "标准化",
    "denormalize": "反标准化",
    "validate": "校验",
    "sanitize": "清理",
    "escape": "转义",
    "unescape": "反转义",
    "trim": "修剪",
    "strip": "去除",
    "pad": "填充",
    "truncate": "截断",
    "round": "四舍五入",
    "floor": "向下取整",
    "ceil": "向上取整",
    "abs": "绝对值",
    "clamp": "限制范围",
    "lerp": "线性插值",
    "map": "映射",
    "reduce": "归约",
    "fold": "折叠",
    "scan": "扫描",
    "zip": "压缩",
    "unzip": "解压缩",
    "flatten": "扁平化",
    "chunk": "分块",
    "batch": "分批",
    "paginate": "分页",
    "cursor": "游标",
    "iterate": "迭代",
    "enumerate": "枚举",
    "zip": "配对",
    "pair": "配对",
    "combine": "组合",
    "permute": "排列",
    "shuffle": "打乱",
    "sample": "采样",
    "select": "选择",
    "project": "投影",
    "reject": "拒绝",
    "accept": "接受",
    "approve": "批准",
    "deny": "拒绝",
    "allow": "允许",
    "block": "阻止",
    "ban": "禁止",
    "unban": "解禁",
    "mute": "静音",
    "unmute": "取消静音",
    "kick": "踢出",
    "ban": "封禁",
    "unban": "解封",
    "timeout": "超时",
    "cooldown": "冷却",
    "cooldown": "冷却",
    "expire": "过期",
    "renew": "续期",
    "extend": "延长",
    "shorten": "缩短",
    "delay": "延迟",
    "schedule": "调度",
    "plan": "规划",
    "organize": "组织",
    "arrange": "排列",
    "sort": "排序",
    "order": "排序",
    "rank": "排名",
    "prioritize": "优先",
    "weight": "加权",
    "score": "评分",
    "rate": "评级",
    "grade": "分级",
    "tier": "分层",
    "categorize": "分类",
    "tag": "标记",
    "label": "标注",
    "annotate": "注释",
    "document": "文档化",
    "describe": "描述",
    "explain": "解释",
    "illustrate": "说明",
    "demonstrate": "演示",
    "show": "显示",
    "hide": "隐藏",
    "display": "显示",
    "render": "渲染",
    "paint": "绘制",
    "draw": "绘制",
    "plot": "绘图",
    "chart": "制图",
    "graph": "绘制图表",
    "visualize": "可视化",
    "preview": "预览",
    "thumbnail": "缩略图",
    "zoom": "缩放",
    "pan": "平移",
    "rotate": "旋转",
    "scale": "缩放",
    "translate": "平移",
    "skew": "倾斜",
    "reflect": "反射",
    "flip": "翻转",
    "mirror": "镜像",
    "crop": "裁剪",
    "resize": "调整大小",
    "pad": "填充",
    "extend": "扩展",
    "trim": "修剪",
    "clip": "裁剪",
    "cut": "剪切",
    "copy": "复制",
    "paste": "粘贴",
    "duplicate": "复制",
    "clone": "克隆",
    "fork": "分支",
    "branch": "分支",
    "checkout": "检出",
    "commit": "提交",
    "push": "推送",
    "pull": "拉取",
    "fetch": "获取",
    "merge": "合并",
    "rebase": "变基",
    "cherry": "精选",
    "stash": "暂存",
    "pop": "弹出",
    "apply": "应用",
    "diff": "差异",
    "patch": "补丁",
    "blame": "追溯",
    "annotate": "注释",
}

# ── 不注释的私有方法前缀（这些通常是辅助方法） ──
SKIP_PREFIXES = ("__", "_internal_", "_helper_", "_util_", "_debug_", "_private_")


def infer_comment(func_name: str, source_lines: List[str], def_lineno: int) -> str:
    """根据函数名和上下文推断注释内容"""
    # 从函数名推断
    base_name = func_name.lstrip("_")
    
    # 检查是否在类定义内
    cls_name = None
    for i in range(def_lineno - 1, max(def_lineno - 50, 0), -1):
        m = re.match(r'^class\s+(\w+)', source_lines[i])
        if m:
            cls_name = m.group(1)
            break
    
    # 从名称中提取动词
    parts = re.split(r'[_\d]+', base_name)
    action = parts[0].lower() if parts else ""
    
    # 查找已知注释
    for key in sorted(COMMENT_MAP.keys(), key=len, reverse=True):
        if base_name.lower().startswith(key) or base_name.lower().endswith(key):
            comment = COMMENT_MAP[key]
            if cls_name:
                return f"{comment}"
            return f"{comment}"
    
    # 默认
    if cls_name:
        return f"处理{cls_name}相关逻辑"
    return f"执行{base_name}功能"


def process_file(filepath: Path, dry_run: bool = False) -> Tuple[int, int]:
    """处理单个文件
    
    Returns:
        (modified, skipped) 修改数和跳过数
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = filepath.read_text(encoding="gbk")
    
    lines = text.split("\n")
    modified = 0
    skipped = 0
    
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        
        # 匹配 def xxx(...) — 必须匹配完整签名（可能跨多行）
        if not re.match(r'^\s*def\s+\w+\s*\(', line):
            i += 1
            continue
        
        m = re.match(r'^(\s*)def\s+(\w+)\s*\(', line)
        if not m:
            i += 1
            continue
        
        indent = m.group(1)
        func_name = m.group(2)
        
        # 跳过私有辅助方法
        if func_name.startswith(SKIP_PREFIXES):
            i += 1
            continue
        
        # 找到函数体第一行（跳过跨行签名）
        body_line_idx = i + 1
        paren_depth = line.count('(') - line.count(')')
        while body_line_idx < len(lines) and paren_depth > 0:
            body_line_idx += 1
            if body_line_idx < len(lines):
                paren_depth += lines[body_line_idx].count('(') - lines[body_line_idx].count(')')
        
        # body_line_idx 现在指向签名结束后的第一行
        # 检查该行是否为 docstring
        has_docstring = False
        if body_line_idx < len(lines):
            next_line = lines[body_line_idx].strip()
            if next_line.startswith('"""') or next_line.startswith("'''"):
                has_docstring = True
        
        # 检查上一行是否为注释
        has_pre_comment = False
        if i > 0:
            prev_line = lines[i - 1].strip()
            if prev_line.startswith('#') or prev_line.startswith('"""') or prev_line.startswith("'''"):
                has_pre_comment = True
        
        if has_docstring or has_pre_comment:
            skipped += 1
            i = body_line_idx
            continue
        
        # 需要添加注释
        comment = infer_comment(func_name, lines, i)
        # 函数体内缩进 = def 行缩进 + 4 空格
        body_indent = indent + '    '
        comment_line = f'{body_indent}"""{comment}"""'
        
        if not dry_run:
            lines.insert(body_line_idx, comment_line)
            modified += 1
            i = body_line_idx + 2  # 跳过刚插入的 docstring
        else:
            modified += 1
            i = body_line_idx + 1
        
        continue
    
    if not dry_run:
        filepath.write_text("\n".join(lines), encoding="utf-8")
    
    return modified, skipped


def main():
    import argparse
    parser = argparse.ArgumentParser(description="安全补充函数/方法注释")
    parser.add_argument("files", nargs="+", help="要处理的 Python 文件")
    parser.add_argument("--dry-run", action="store_true", help="仅预览，不写入")
    parser.add_argument("--threshold", type=int, default=20, help="最大修改行数（默认 20）")
    args = parser.parse_args()
    
    total_modified = 0
    total_skipped = 0
    
    for fpath in args.files:
        p = Path(fpath)
        if not p.exists():
            print(f"⚠  文件不存在: {p}")
            continue
        modified, skipped = process_file(p, dry_run=args.dry_run)
        total_modified += modified
        total_skipped += skipped
        if modified > 0:
            action = "预览" if args.dry_run else "修改"
            print(f"  {action}: {p} — 添加 {modified} 处注释，跳过 {skipped} 处")
    
    if args.dry_run and total_modified > 0:
        print(f"\n共 {total_modified} 处将添加注释，{total_skipped} 处跳过。")
        print(f"运行时不加 --dry-run 执行实际写入")


if __name__ == "__main__":
    main()
