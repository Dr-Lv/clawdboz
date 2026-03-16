# Web Chat 自动化测试指南

基于 **test-driven-development** 和 **verification-before-completion** superpower skills 构建的测试框架。

## 快速开始

```bash
# 一键运行所有测试
./test_web.sh
```

## 测试类型

### 1. 功能测试 (`tests/test_web_auto.py`)

测试 Web Chat 的核心功能：

| 测试项 | 描述 | 预期结果 |
|--------|------|----------|
| HTTP 健康检查 | 静态文件服务 | HTTP 200 |
| Bot 列表 API | `/api/bots` 接口 | 返回所有 Bot |
| Token 鉴权 | 正确/错误/空 Token | 按预期通过或拒绝 |
| WebSocket 连接 | 建立 WebSocket | 连接成功 |
| 单聊功能 | 与单个 Bot 对话 | 收到 start/chunk/done |
| 群聊功能 | 多个 Bot 同时回复 | 所有 Bot 正常回复 |

运行测试：
```bash
.venv/bin/python tests/test_web_auto.py
```

### 2. 会话切换并发测试 (`tests/test_session_switch.py`)

测试多会话并发场景，验证消息不串流、无残留加载状态：

**测试步骤：**
1. 创建3个独立的 WebSocket 连接（模拟3个浏览器标签页）
2. 同时在3个会话中发送消息（"数字1", "数字2", "数字3"）
3. 等待所有消息生成完成
4. 检查：
   - 是否有多余回复消息气泡一直显示生成中
   - 消息回复是否串流

**预期结果：**
| 检查项 | 预期 | 说明 |
|--------|------|------|
| 回复完整性 | ✅ 所有会话都收到完整回复 | start → chunks → done |
| 无残留加载 | ✅ 没有卡住的消息气泡 | 所有 done 都正常收到 |
| 无消息串流 | ✅ 消息内容不混合 | 每个会话只收到自己的回复 |

运行测试：
```bash
./test_session_switch.sh
# 或
.venv/bin/python tests/test_session_switch.py
```

### 2. 性能测试 (`tests/test_web_performance.py`)

测试系统性能指标：

| 测试项 | 描述 | 指标 |
|--------|------|------|
| API 延迟 | HTTP 请求响应时间 | 最小/最大/平均/中位数 |
| 并发连接 | 同时建立的 WebSocket | 成功连接数 |
| 消息吞吐量 | 每秒处理消息数 | msg/s |

运行测试：
```bash
.venv/bin/python tests/test_web_performance.py
```

### 3. E2E 自动化测试 - 已有会话 (`tests/test_web_e2e_existing.py`)

使用 Playwright 模拟真实浏览器操作，利用已有会话测试：

**测试场景：**
1. 切换到已有会话1，发送消息，**等待回复完成**，截图
2. 切换到已有会话2，发送消息，**等待回复完成**，截图
3. 切换到已有会话3，发送消息，**等待回复完成**，截图
4. 分析所有截图：
   - 是否有残留的"生成中"消息气泡
   - 消息是否串流

**运行测试：**
```bash
./test_web_e2e_existing.sh
# 或
.venv/bin/python tests/test_web_e2e_existing.py
```

**说明：**
- 使用 headless 浏览器（无界面）
- 每次测试生成独立目录保存截图 `/tmp/web_chat_test_YYYYMMDD_HHMMSS/`
- 截图命名：`session{n}_before.png`（发送前）和 `session{n}_after.png`（回复后）
- **特点**：利用已有对话，等待回复完成后再分析，更接近真实使用场景

### 4. E2E 自动化测试 - 新建会话 (`tests/test_web_e2e_playwright.py`)

使用 Playwright 模拟真实浏览器操作，创建新会话测试：

**测试场景：**
1. 创建会话1（选择 Bot1），发送消息"数字1"
2. 不等回复完成，切换到会话2（选择 Bot2），发送消息"数字2"
3. 不等回复完成，切换到会话3（选择 Bot3），发送消息"数字3"
4. 等待所有消息完成
5. 检查是否有多余的"生成中"消息气泡和消息串流

**运行测试：**
```bash
./test_web_e2e.sh
# 或
.venv/bin/python tests/test_web_e2e_playwright.py
```

### 4. 单元测试 (`tests/test_web_server.py`)

基于 FastAPI TestClient 的单元测试：

```bash
.venv/bin/python -m pytest tests/test_web_server.py -v
```

## 测试架构

```
tests/
├── test_web_auto.py          # 自动化功能测试
├── test_session_switch.py    # 会话切换并发测试
├── test_web_performance.py   # 性能测试
├── test_web_server.py        # 单元测试
└── e2e_test.py              # 端到端测试
```

## 测试报告

测试完成后会输出详细报告：

```
============================================================
测试报告
============================================================
总测试数: 6
通过: 6 ✓
失败: 0 ✗
耗时: 16.64 秒

  ✓ HTTP 健康检查: PASS
  ✓ Bot 列表 API: PASS
  ✓ Token 鉴权: PASS
  ✓ WebSocket 连接: PASS
  ✓ 单聊功能: PASS
  ✓ 群聊功能: PASS
============================================================
```

## 持续集成

可以将测试集成到 CI/CD 流程：

```yaml
# .github/workflows/test.yml
name: Web Chat Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      - name: Install dependencies
        run: |
          uv pip install -e ".[dev]"
          uv pip install aiohttp websockets
      - name: Start Web Server
        run: |
          .venv/bin/python web_server.py &
          sleep 5
      - name: Run tests
        run: .venv/bin/python tests/test_web_auto.py
```

## 故障排查

### 测试失败常见问题

1. **Web 服务器未启动**
   ```
   ✗ Web 服务器未运行
   请先启动 Web 服务器: ./start_all.sh
   ```

2. **依赖缺失**
   ```
   ModuleNotFoundError: No module named 'aiohttp'
   ```
   解决：`uv pip install aiohttp websockets`

3. **Token 错误**
   ```
   ✗ [正确 Token] 连接失败
   ```
   检查 `test_web_auto.py` 中的 `TEST_CONFIG["token"]`

## 扩展测试

添加新的测试用例：

```python
async def test_new_feature(self) -> bool:
    """测试新功能"""
    self.log("测试新功能...")
    try:
        # 测试代码
        result = await self.some_async_operation()
        if result:
            self.log("✓ 新功能正常")
            return True
        else:
            self.log("✗ 新功能异常", "ERROR")
            return False
    except Exception as e:
        self.log(f"✗ 测试失败: {e}", "ERROR")
        return False
```

然后在 `run_all_tests()` 中添加：

```python
tests = [
    # ... 现有测试
    ("新功能测试", self.test_new_feature),
]
```
