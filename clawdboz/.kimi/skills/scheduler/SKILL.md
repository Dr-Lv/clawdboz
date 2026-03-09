# 定时任务 Skill

## 描述
创建和管理定时任务数据，生成标准的 `scheduler_tasks.json` 文件。

**职责边界：**

| 责任方 | 职责 |
|-------|------|
| **本 Skill** | 数据存储、CRUD 操作、JSON 格式管理 |
| **调用方 (Agent)** | 自然语言解析、时区转换、UTC 时间戳生成 |

**核心原则：**
- 本 skill **不负责**时间字符串解析和自然语言理解
- 调用方必须提供标准的 **UTC Unix 时间戳**（正数）
- 任务执行由外部系统（如 Bot 心跳机制）读取 JSON 文件后处理

---

## 输入规范

### execute_time 格式
- **类型**: Unix 时间戳（float 或 int）
- **时区**: 必须是 **UTC** 时间
- **范围**: 正数（> 0）
- **示例**: `1772672400.0` 表示 2025-03-05 01:00:00 UTC

### 调用方处理流程

```
用户输入: "明天晚上9点"
    ↓
Agent 解析:
  - 识别为北京时间 21:00 (UTC+8)
  - 转换为 UTC: 2025-03-05 13:00
  - 转为时间戳: 1772715600.0
    ↓
Skill 存储: {execute_time: 1772715600.0, ...}
```

### 示例代码（Agent 侧）

```python
from datetime import datetime, timezone, timedelta

# 1. 解析用户时间（北京时间）
beijing_tz = timezone(timedelta(hours=8))
dt = datetime(2025, 3, 5, 21, 0, tzinfo=beijing_tz)

# 2. 转为 UTC 时间戳
utc_timestamp = dt.timestamp()  # 1772715600.0

# 3. 调用 skill
task_id = scheduler.create_task(
    chat_id="oc_xxx",
    description="明天晚上9点收集数据",
    execute_time=utc_timestamp,
    time_interval=86400  # 每天重复
)
```

---

## 功能

### 1. 创建定时任务
- 接收 UTC 时间戳和任务描述
- 生成标准 JSON 格式任务数据

### 2. 列出/查看任务
- "列出所有定时任务"
- "查看我的任务列表"
- "任务 #1 的详情"

### 3. 更新/删除任务
- "修改任务 #1 的执行时间"
- "取消定时任务 #1"
- "删除任务 #2"

---

## JSON 数据格式规范

```json
{
  "task_id_counter": 3,
  "tasks": {
    "1": {
      "id": "1",
      "chat_id": "oc_xxx",
      "execute_time": 1771526400,
      "description": "任务描述",
      "status": "pending"
    },
    "2": {
      "id": "2",
      "chat_id": "oc_xxx",
      "execute_time": 1771508400,
      "time_interval": 86400,
      "description": "重复任务描述",
      "status": "pending"
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `id` | string | ✅ | 任务唯一标识（字符串） |
| `chat_id` | string | ✅ | 飞书聊天会话ID |
| `execute_time` | number | ✅ | UTC Unix 时间戳（必须为正数） |
| `time_interval` | number | 可选 | 重复周期（秒），有值=重复任务 |
| `description` | string | ✅ | 任务描述，执行时发送给 Kimi ACP |
| `status` | string | ✅ | 状态：`pending`/`running`/`completed`/`failed` |

### 任务类型

**一次性任务**（无 `time_interval`）：
- 在 `execute_time` 执行一次
- 执行完成后状态变为 `completed`

**重复任务**（有 `time_interval`）：
- 首次在 `execute_time` 执行
- 之后每隔 `time_interval` 秒执行
- 外部系统负责更新 `execute_time` 为下次执行时间

---

## API 接口

```python
from scheduler import TaskScheduler, get_scheduler

# 获取实例
scheduler = get_scheduler(data_dir='./WORKPLACE')

# 创建任务（execute_time 必须是 UTC 时间戳）
task_id = scheduler.create_task(
    chat_id="oc_xxx",
    description="明天上午9点提醒开会",
    execute_time=1772672400.0,  # UTC 时间戳
    time_interval=None          # None=一次性，数字=重复间隔
)

# 获取任务
task = scheduler.get_task("1")

# 列出任务
tasks = scheduler.list_tasks(chat_id="oc_xxx", status="pending")

# 更新任务
scheduler.update_task("1", execute_time=1772715600.0, status="pending")

# 删除任务
scheduler.delete_task("1")

# 心跳 tick（检查待执行的任务）
now = datetime.now(timezone.utc).timestamp()
pending_tasks = scheduler.tick(current_time=now)
```

---

## 注意事项

1. **本 skill 无调度功能** - 只生成 JSON，不执行任何定时逻辑
2. **本 skill 不解析时间字符串** - 必须由调用方提供 UTC 时间戳
3. `execute_time` 必须是正数 UTC 时间戳
4. 重复任务需外部系统更新 `execute_time` 实现循环
5. 文件使用原子写入，防止损坏
6. 线程安全：内部使用锁保护文件读写

---

## 外部执行示例

Bot 心跳机制读取并执行任务的伪代码：

```python
def heartbeat():
    from datetime import datetime, timezone
    
    data = load_json('scheduler_tasks.json')
    now = datetime.now(timezone.utc).timestamp()  # 使用 UTC 时间
    
    for task in data['tasks'].values():
        if task['status'] != 'pending':
            continue
            
        if task['execute_time'] <= now:
            # 执行任务
            execute_task(task)
            
            # 更新状态
            if task.get('time_interval'):
                # 重复任务：更新下次执行时间
                task['execute_time'] = now + task['time_interval']
                task['status'] = 'pending'
            else:
                # 一次性任务：标记完成
                task['status'] = 'completed'
    
    save_json(data)
```
