# 定时任务 Skill

## 描述
创建和管理定时任务数据，生成标准的 `scheduler_tasks.json` 文件。

**注意：本 skill 只负责数据管理，不执行任务调度。** 任务执行由外部系统（如 Bot 心跳机制）读取 JSON 文件后处理。

## 功能

### 1. 创建定时任务
解析用户自然语言，生成任务数据：
- "设置一个定时任务，明天上午9点提醒我开会"
- "10分钟后帮我查一下今天的天气"
- "每隔5分钟获取纳斯达克指数"
- "今天下午3点总结这个群的所有消息"

### 2. 列出/查看任务
- "列出所有定时任务"
- "查看我的任务列表"
- "任务 #1 的详情"

### 3. 更新/删除任务
- "修改任务 #1 的执行时间"
- "取消定时任务 #1"
- "删除任务 #2"

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
      "time_interval": 60,
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
| `execute_time` | number | ✅ | 任务执行时间戳（Unix秒，必须为正数） |
| `time_interval` | number | 可选 | 重复周期（秒），**有值=重复任务**，**无值=一次性任务** |
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

### 状态说明

| 状态 | 说明 |
|------|------|
| `pending` | 等待执行 |
| `running` | 正在执行 |
| `completed` | 执行完成（一次性任务） |
| `failed` | 执行失败 |

## 支持的时间格式

### 相对时间
- "X分钟后" - 如 "10分钟后"
- "X小时后" - 如 "1小时后"
- "X天后" - 如 "2天后"

### 绝对时间
- "明天上午9点"
- "今天下午3点"
- "YYYY-MM-DD HH:MM" - 如 "2024-01-15 09:00"

### 重复间隔
- "每X分钟" / "X分钟一次"
- "每X小时" / "X小时一次"
- "每X天" / "X天一次"

## 工作原理

```
用户输入
    │
    ▼
┌─────────────────┐
│ 解析时间/间隔    │  ← parse_time(), parse_interval()
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 生成任务对象     │  ← TaskScheduler.create_task()
│ {               │
│   id, chat_id,  │
│   execute_time, │
│   description,  │
│   status        │
│ }               │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ 保存到 JSON 文件 │  ← scheduler_tasks.json
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────┐
│      外部系统（如 Bot 心跳）      │
│  1. 读取 scheduler_tasks.json   │
│  2. 检查 execute_time <= now()  │
│  3. 执行 description            │
│  4. 更新 status                 │
│  5. 重复任务更新 execute_time   │
└─────────────────────────────────┘
```

## API 接口

```python
from scheduler import TaskScheduler, get_scheduler

# 获取实例
scheduler = get_scheduler(data_dir='./WORKPLACE')

# 创建任务
task_id = scheduler.create_task(
    chat_id="oc_xxx",
    description="明天上午9点提醒开会",
    execute_time=1771526400,  # 时间戳
    time_interval=None        # None=一次性，数字=重复间隔
)

# 获取任务
task = scheduler.get_task("1")

# 列出任务
tasks = scheduler.list_tasks(chat_id="oc_xxx", status="pending")

# 更新任务
scheduler.update_task("1", execute_time=1771600000, status="pending")

# 删除任务
scheduler.delete_task("1")
```

## 注意事项

1. **本 skill 无调度功能** - 只生成 JSON，不执行任何定时逻辑
2. `execute_time` 必须为正数时间戳
3. 重复任务需外部系统更新 `execute_time` 实现循环
4. 文件使用原子写入，防止损坏
5. 线程安全：内部使用锁保护文件读写

## 外部执行示例

Bot 心跳机制读取并执行任务的伪代码：

```python
def heartbeat():
    data = load_json('scheduler_tasks.json')
    now = time.time()
    
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
