# CI/CD Pipeline for BAA

## 目标
- 每次 PR 和 `main` push 自动运行测试
- 代码质量门禁（lint + 类型检查）
- 测试覆盖率报告

## 流水线组成

### 1. lint.yml — 代码风格检查
- `black` 格式检查
- `pylint` 静态分析
- `flake8` 复杂度/可读性

### 2. test.yml — 测试
- `pytest` 运行所有非 slow 测试
- 覆盖率报告
- 缓存 venv 加速

### 3. test-slow.yml — 慢速测试
- 仅在 `main` 分支 push 时运行
- 包含 `slow` 标记的测试

## 使用方式

```bash
# 本地预检
source venv/bin/activate
black --check src/
pylint src/
pytest -m "not slow" --cov=src src/tests/

# 格式化
black src/

# 本地运行测试
pytest -m "not slow"
```

## 添加新测试

1. 文件命名: `test_<模块名>.py`
2. 放在 `src/tests/` 目录
3. 慢测试用 `@pytest.mark.slow` 标记
4. API 测试用 `@pytest.mark.api` 标记
