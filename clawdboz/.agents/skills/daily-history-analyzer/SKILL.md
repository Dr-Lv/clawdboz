---
name: daily-history-analyzer
description: 每日 HISTORY 对话分析器。读取前一天的对话记录，提取重要信息并保存到记忆中，同时生成文本报告保存到 assets 文件夹。
triggers:
  - "每日对话分析"
  - "HISTORY 分析"
  - "对话记录分析"
  - "daily history analyze"
---

# Daily History Analyzer

每日 HISTORY 对话分析 Skill。

## 功能

- 读取前一天的 HISTORY 对话记录
- 提取重要主题和互动摘要
- 将分析结果保存到 local-memory
- 生成文本报告保存到 skill 的 `assets/` 目录

## 使用方式

### Python 调用

```python
import sys
sys.path.insert(0, '.agents/skills/daily-history-analyzer')
from daily_history_analyzer import run

report, memory_id, report_path = run()
```

### 命令行

```bash
python .agents/skills/daily-history-analyzer/daily_history_analyzer.py
```

## 输出

- **记忆**: `daily_history_analysis` 分类
- **报告文件**: `assets/daily_history_report_YYYY-MM-DD.txt`
