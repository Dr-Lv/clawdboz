---
name: xiaohongshu-publisher
description: 小红书图文自动发布工具。当用户需要将图文内容发布到小红书平台时使用。支持从指定文件夹获取素材，自动创建发布目录，自动处理登录状态保持，支持多图片上传、标题、正文和话题标签。
---

# 小红书图文自动发布

使用 Playwright 浏览器自动化技术，将准备好的图文内容发布到小红书。

## 使用方法

当用户需要发布小红书图文时，执行以下步骤：

### 1. 获取素材文件夹路径

请用户提供包含素材的文件夹路径。该文件夹应包含：
- **图片文件**：jpg/png 格式（最多 18 张）
- **文本文件（可选）**：content.txt，包含标题和正文

### 2. 创建发布目录

在 `assets/` 目录下创建 `post_<时间戳>` 子文件夹，结构如下：

```
assets/post_<时间戳>/
├── content.json    # 帖子配置（自动生成）
└── images/         # 图片素材（从用户文件夹复制）
```

### 3. 生成 content.json

参考 `assets/post_template/content.json` 的格式，创建配置文件：

```json
{
  "title": "帖子标题（20字以内最佳）",
  "content": "帖子正文内容，支持换行\\n\\n多段落写作",
  "images": ["1.jpg", "2.jpg", "3.jpg"],
  "topics": ["话题1", "话题2"]
}
```

**字段说明：**
- `title`: 帖子标题，必须控制在18个字以内
- `content`: 正文内容，支持换行符 `\n`
- `images`: 图片文件名列表（放在 `images/` 目录下），最多 18 张
- `topics`: 话题标签列表（可选，会自动加上 # 号）

### 4. 执行发布

运行发布脚本（默认使用无头模式，不显示浏览器窗口）：

```bash
cd xiaohongshu-publisher
python scripts/publish.py assets/post_<时间戳>/content.json
```

如需调试查看浏览器操作，可添加 `--no-headless` 参数：

```bash
python scripts/publish.py assets/post_<时间戳>/content.json
```

首次运行需要手动登录小红书，登录状态会自动保存供后续使用。

## 完整示例

假设用户提供的素材文件夹为 `/path/to/user_materials/`：

```bash
# 1. 创建发布目录（示例时间戳：20260203_152530）
mkdir -p assets/post_20260203_152530/images

# 2. 复制图片素材
cp /path/to/user_materials/*.jpg assets/post_20260203_152530/images/
cp /path/to/user_materials/*.png assets/post_20260203_152530/images/

# 3. 创建 content.json（根据用户提供的标题、内容、话题生成）
# 文件路径: assets/post_20260203_152530/content.json

# 4. 执行发布
python scripts/publish.py assets/post_20260203_152530/content.json
```

## 工作流

### 标准发布流程

1. **接收用户请求**
   - 获取用户素材文件夹路径
   - 获取帖子标题、内容、话题标签

2. **准备发布目录**
   - 生成时间戳（格式：YYYYMMDD_HHMMSS）
   - 创建 `assets/post_<时间戳>/` 目录
   - 复制图片到 `images/` 子目录

3. **生成配置文件**
   - 创建 `content.json`
   - 验证 JSON 格式正确

4. **执行发布脚本**
   - 运行 `python scripts/publish.py assets/post_<时间戳>/content.json`
   - 脚本会自动检查登录状态

5. **处理登录（首次）**
   - 如果未检测到当前skill文件夹下存在storage_state.json，则使用 `--no-headless` 参数显示浏览器窗口
   - 浏览器会自动打开小红书
   - 用户手动完成登录（扫码/手机号）
   - 脚本检测登录成功后继续
   - 后续发布可使用默认无头模式

6. **自动发布**
   - 上传图片
   - 填写标题和正文
   - 添加话题标签
   - 点击发布

## 命令行参数

```bash
python scripts/publish.py <content.json>
```

- `<content.json>`: 内容配置文件路径（必需）
- `--no-headless`: 显示浏览器窗口（调试用）

## 文件结构

```
xiaohongshu-publisher/
├── scripts/
│   └── publish.py          # 发布脚本
├── assets/
│   ├── post_template/      # 内容模板（参考用）
│   │   ├── content.json
│   │   └── images/
│   └── post_<时间戳>/      # 自动创建的发布目录
│       ├── content.json
│       └── images/
└── storage_state.json      # 登录状态（自动生成）
```

## 注意事项

1. **登录状态**：首次登录后，状态保存在 `storage_state.json`，下次无需重新登录
2. **图片限制**：小红书最多支持 18 张图片，单张不超过 20MB
3. **频率控制**：建议合理控制发布频率，避免触发平台风控
4. **素材来源**：确保用户提供的素材文件夹存在且包含有效图片
5. **特殊字符**: 注意content.json字段中的中文引号，要替换成「」

## 故障排查

| 问题 | 解决方案 |
|------|----------|
| 提示未登录 | 删除 `storage_state.json` 重新登录 |
| 图片上传失败 | 检查图片是否存在、格式是否支持（jpg/png）|
| 发布按钮找不到 | 小红书页面可能更新，检查脚本选择器 |
| 发布超时 | 增加 `page.wait_for_timeout()` 时间 |

## 高级用法

### 批量发布

创建多个内容目录，循环执行：

```bash
for dir in assets/post_*/; do
    python scripts/publish.py "$dir/content.json"
    sleep 60  # 间隔 60 秒
done
```

### 查看历史发布

```bash
ls -la assets/post_*
```

### 多账号支持（扩展）

复制 skill 目录，使用不同的 `storage_state.json` 文件路径。
