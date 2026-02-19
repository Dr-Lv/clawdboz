---
name: scheduler
description: 定时任务管理 - 通过修改 scheduler_tasks.json 文件创建和管理定时任务
---

# 定时任务 Skill

定时任务功能通过修改 `WORKPLACE/scheduler_tasks.json` 文件实现。
Bot 的心跳线程会自动检测并执行到期的任务。

## 任务文件格式

文件位置：`WORKPLACE/scheduler_tasks.json`

```json
{
  "task_id_counter": 1,
  "tasks": {
    "1": {
      "id": 1,
      "chat_id": "oc_xxxxx",
      "description": "任务描述",
      "execute_time": 1234567890.0,
      "created_at": 1234567890.0,
      "status": "pending"
    }
  }
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int | 任务唯一标识 |
| `chat_id` | string | 发送结果的聊天 ID |
| `description` | string | 任务描述，Bot 会执行这个内容 |
| `execute_time` | float | 执行时间戳（秒），可为 null |
| `created_at` | float | 创建时间戳 |
| `status` | string | 状态：pending/executing/completed/failed |

## 使用方式

### 1. 创建定时任务

直接编辑或创建 `WORKPLACE/scheduler_tasks.json`：

```python
import json
import time
from clawdboz.config import get_absolute_path

tasks_file = get_absolute_path('WORKPLACE/scheduler_tasks.json')

# 读取现有任务
try:
    with open(tasks_file, 'r') as f:
        data = json.load(f)
except:
    data = {'task_id_counter': 0, 'tasks': {}}

# 生成新任务 ID
data['task_id_counter'] += 1
task_id = data['task_id_counter']

# 添加新任务
data['tasks'][str(task_id)] = {
    'id': task_id,
    'chat_id': 'oc_xxxxx',  # 用户聊天 ID
    'description': '提醒我吃午饭',
    'execute_time': time.time() + 3600,  # 1小时后
    'created_at': time.time(),
    'status': 'pending'
}

# 保存
with open(tasks_file, 'w') as f:
    json.dump(data, f, indent=2)
```

### 2. 常用时间格式

创建任务时可以使用以下时间格式：

| 格式 | 示例 | 说明 |
|------|------|------|
| 相对分钟 | "10分钟后" | 当前时间 +10 分钟 |
| 相对小时 | "1小时后" | 当前时间 +1 小时 |
| 相对天数 | "明天上午9点" | 明天 9:00 |
| 绝对时间 | "2024-01-15 09:00" | 指定日期时间 |
| 仅时间 | "14:30" | 今天或明天 14:30 |

### 3. 使用辅助工具函数

```python
from skills.scheduler.scheduler import create_task, parse_time, list_tasks

# 解析时间
execute_time = parse_time("明天上午9点")  # 返回时间戳

# 创建任务
task_id = create_task(
    chat_id='oc_xxxxx',
    description='明天早上9点提醒我开会',
    execute_time=execute_time
)

# 查看所有任务
tasks = list_tasks()
```

### 4. 任务执行规则

- **空 execute_time**：任务会立即执行
- **pending 状态**：等待执行
- **时间窗口内**：心跳线程会在 `execute_time` 落在检查窗口内时执行
- **执行完成后**：Bot 自动更新状态为 `completed` 或 `failed`

### 5. 取消/修改任务

直接编辑 JSON 文件：

```python
from skills.scheduler.scheduler import load_tasks, save_tasks

# 加载
data = load_tasks()

# 修改任务状态为 pending（重新执行）
data['tasks']['1']['status'] = 'pending'

# 或删除任务
del data['tasks']['1']

# 保存
save_tasks(data)
```

## 注意事项

1. 任务文件必须位于 `WORKPLACE/scheduler_tasks.json`
2. 任务 ID 必须唯一，使用 `task_id_counter` 自增
3. 执行失败的任务会在每天早上9点汇总提醒
4. 已完成或失败的任务不会自动删除，可手动清理
