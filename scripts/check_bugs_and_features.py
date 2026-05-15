#!/usr/bin/env python3
"""
Bugs & Features 状态检查器

每次调用时，读取项目根目录的 Bugs_and_Feartures.md（注意文件名拼写），
在代码库中搜索相关实现，输出每个 bug/feature 的完成状态报告。

用法:
    cd /root/code/clawdboz
    python scripts/check_bugs_and_features.py

退出码:
    0 - 所有 bugs 已修复、所有 features 已完成
    1 - 仍有未修复的 bug 或未完成的 feature
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple, Callable

# 项目根目录（脚本位于 scripts/ 下，向上退一级）
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
INDEX_HTML = PROJECT_ROOT / "clawdboz" / "web" / "static" / "index.html"
BUGS_MD = PROJECT_ROOT / "Bugs_and_Feartures.md"

# 颜色输出
C_RED = "\033[91m"
C_GREEN = "\033[92m"
C_YELLOW = "\033[93m"
C_CYAN = "\033[96m"
C_RESET = "\033[0m"
C_BOLD = "\033[1m"


def read_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def parse_bugs_and_features(content: str) -> Tuple[List[str], List[str]]:
    """解析 md 文件，提取 bugs 和 features 列表"""
    bugs = []
    features = []
    current = None
    for line in content.splitlines():
        line = line.strip()
        if line.lower().startswith("###bugs"):
            current = "bugs"
            continue
        if line.lower().startswith("###features"):
            current = "features"
            continue
        if line.lower().startswith("###requirements"):
            current = None
            continue
        if current == "bugs" and re.match(r"^\d+\.", line):
            bugs.append(re.sub(r"^\d+\.\s*", "", line))
        if current == "features" and re.match(r"^\d+\.", line):
            features.append(re.sub(r"^\d+\.\s*", "", line))
    return bugs, features


def grep_in_file(path: Path, pattern: str) -> List[str]:
    """在文件中搜索正则，返回匹配行列表"""
    text = read_file(path)
    return [m for m in re.findall(pattern, text, re.IGNORECASE)]


def grep_lines(path: Path, pattern: str) -> List[str]:
    """在文件中搜索正则，返回匹配行内容列表"""
    text = read_file(path)
    return [line for line in text.splitlines() if re.search(pattern, line, re.IGNORECASE)]


def extract_js_function(text: str, func_name: str) -> str:
    """从 JS 代码中提取指定函数体（支持嵌套大括号）"""
    pattern = rf"function\s+{re.escape(func_name)}\s*\([^)]*\)\s*\{{"
    match = re.search(pattern, text)
    if not match:
        return ""
    start = match.end() - 1  # 指向第一个 '{'
    brace_depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            brace_depth += 1
        elif ch == "}":
            brace_depth -= 1
            if brace_depth == 0:
                return text[start:i+1]
        elif ch == '"':
            # 跳过字符串
            i += 1
            while i < len(text) and text[i] != '"':
                if text[i] == "\\":
                    i += 1
                i += 1
        elif ch == "'":
            i += 1
            while i < len(text) and text[i] != "'":
                if text[i] == "\\":
                    i += 1
                i += 1
        elif text[i:i+2] == "//":
            # 跳过单行注释
            while i < len(text) and text[i] != "\n":
                i += 1
            continue
        i += 1
    return ""


# ========================================================================
# 检查函数注册表：每个 bug/feature 对应一个检查函数
# 返回 (status: str, detail: str)
# status: "fixed" | "open" | "partial" | "unknown"
# ========================================================================

def check_bug_1_message_count() -> Tuple[str, str]:
    """Bug 1: 新消息数量提示，数字要显示新增消息条数，而不是消息更新次数"""
    text = read_file(INDEX_HTML)
    # 查找未读计数逻辑
    matches = re.findall(r"sessionUnreadCounts\.set\([^,]+,\s*count\s*\+\s*1\)", text)
    if not matches:
        return "unknown", "未找到未读计数逻辑"

    body = extract_js_function(text, "handleMsg")
    if not body:
        return "unknown", "未找到 handleMsg 函数"

    # 未读计数逻辑是否区分了消息类型
    has_unread_logic = "sessionUnreadCounts.set" in body and "count + 1" in body
    has_type_filter = "data.type" in body

    if has_unread_logic and not has_type_filter:
        return "open", (
            "handleMsg() 中未读计数逻辑没有按 data.type 过滤。"
            "每次收到流式 chunk 都会增加未读数，导致未读数等于 chunk 数量而非消息数量。"
            "建议：只在 data.type === 'start' 或 'done' 时增加未读计数。"
        )

    if has_unread_logic and has_type_filter:
        # 检查 set 语句是否在 type 判断之后（同一分支内）
        lines = body.splitlines()
        in_type_guard = False
        set_after_guard = False
        for line in lines:
            stripped = line.strip()
            if "data.type" in stripped and ("===" in stripped or "==" in stripped):
                in_type_guard = True
            if "sessionUnreadCounts.set" in stripped and in_type_guard:
                set_after_guard = True
                break
            # 如果遇到了闭合大括号或新的 if，退出 type_guard
            if in_type_guard and stripped == "}" and "sessionUnreadCounts.set" not in stripped:
                in_type_guard = False
        if set_after_guard:
            return "fixed", "已增加类型判断，未读计数只在特定消息类型时增加"
        return "open", (
            "handleMsg() 中有 data.type 判断（可能仅用于日志），"
            "但未读计数逻辑（sessionUnreadCounts.set）不在类型过滤分支内。"
            "流式 chunk 仍会导致未读数错误增加。"
        )

    return "unknown", "未读计数逻辑异常"


def check_bug_2_long_message_timeout() -> Tuple[str, str]:
    """Bug 2: 长消息回复到一半，动态圆圈会超时不见"""
    text = read_file(INDEX_HTML)
    # 检查 loading 元素的移除逻辑
    timeouts = re.findall(r"setTimeout\s*\(\s*.*?loading", text, re.DOTALL | re.IGNORECASE)
    # 检查是否有专门针对长消息保活的机制
    has_heartbeat = "heartbeat" in text.lower() and "loading" in text.lower()
    has_keepalive = bool(re.search(r"loading.*?(keepalive|ping|heartbeat)", text, re.IGNORECASE))

    # 检查 finishMsg / done 时是否正确移除 loading
    finish_lines = grep_lines(INDEX_HTML, r"function finishMsg|type.*['\"]done['\"]")
    loading_removed_in_finish = bool(
        re.search(r"loading.*remove|remove.*loading", text, re.IGNORECASE)
    )

    if not loading_removed_in_finish:
        return "open", "finishMsg/done 处理中可能没有正确移除 loading 元素"

    # 检查是否有超时清理loading的setTimeout
    timeout_cleanups = re.findall(r"setTimeout\s*\(\s*function\s*\(\)\s*\{[^}]*loading[^}]*\}", text, re.DOTALL | re.IGNORECASE)
    if len(timeout_cleanups) > 2:
        return "partial", (
            f"发现 {len(timeout_cleanups)} 处 setTimeout 清理 loading 的逻辑，"
            "长消息可能在超时前被误清理。建议改为只在收到 'done' 或 WebSocket 断开时才移除 loading。"
        )

    return "partial", (
        "loading 圆圈移除逻辑分散在多处（finishMsg、selectSession、init 等），"
        "长消息场景下可能因某个 setTimeout 提前触发而被误删。"
        "建议统一：仅在收到 'done' 消息或 WebSocket 明确断开时移除 loading。"
    )


def check_bug_3_duplicate_message_on_switch() -> Tuple[str, str]:
    """Bug 3: 消息回复完，切换回当前会话时，多显示了一条消息"""
    text = read_file(INDEX_HTML)

    func_body = extract_js_function(text, "loadChatHistory")
    if func_body:
        # 检查是否有清空消息容器的逻辑
        if "innerHTML = ''" in func_body or 'innerHTML = ""' in func_body:
            # 进一步检查 restoreBotMessage 是否使用 msg_id 去重
            if "getElementById" in func_body or "existing" in func_body:
                return "fixed", "loadChatHistory() 已清空消息容器，且 restoreBotMessage 有重复检查"
            return "partial", (
                "loadChatHistory() 已清空消息容器，但 restoreBotMessage 可能没有 msg_id 去重。"
                "如果切换会话时内存中仍有 pending 的流式消息，可能重复显示。"
            )
        return "open", "loadChatHistory() 中没有先清空消息容器，切换会话时消息会重复累积"

    return "unknown", "未找到 loadChatHistory 函数"


def check_bug_4_user_avatar() -> Tuple[str, str]:
    """Bug 4: 用户自定义头像没有生效，一刷新就恢复默认了"""
    text = read_file(INDEX_HTML)

    # 检查 loadUserProfile 是否读取 avatar_image
    body = extract_js_function(text, "loadUserProfile")
    if body:
        if "avatar_image" not in body:
            return "open", (
                "loadUserProfile() 中没有读取 avatar_image 字段，"
                "导致用户保存的自定义图片头像在刷新后丢失。"
                "需要添加：userProfile.avatar_image = data.avatar_image || '';"
            )
        else:
            return "fixed", "loadUserProfile() 已读取 avatar_image"

    return "unknown", "未找到 loadUserProfile 函数"


def check_bug_5_bot_avatar() -> Tuple[str, str]:
    """Bug 5: Bot换了自定义头像后，在聊天会话框中，头像不显示了"""
    text = read_file(INDEX_HTML)

    body = extract_js_function(text, "createBotMsg")
    if body:
        uses_data_avatar = "data.avatar" in body or "data\.avatar" in body
        uses_getbotconfig = "getBotAvatarConfig" in body

        if uses_data_avatar:
            # 检查是否优先使用 data.avatar_image
            if "data.avatar_image" in body:
                return "fixed", "createBotMsg() 已从 data 中读取 avatar_image/avatar_color"
            if "data.avatar_color" in body:
                return "partial", "createBotMsg() 使用了 data.avatar_color 但没有 data.avatar_image"
            return "partial", "createBotMsg() 有 data.avatar 相关字段但逻辑不完整"

        if uses_getbotconfig and not uses_data_avatar:
            return "open", (
                "createBotMsg() 只使用 getBotAvatarConfig(bot_id) 查找头像，"
                "没有使用消息中携带的 data.avatar_image/data.avatar_color。"
                "Bot 自定义图片头像不会在聊天消息气泡中显示。"
            )

    return "unknown", "未找到 createBotMsg 函数"


def check_bug_6_remote_bot() -> Tuple[str, str]:
    """Bug 6: 远程bot通信还是失败"""
    manager_file = PROJECT_ROOT / "clawdboz" / "remote" / "manager.py"
    core_file = PROJECT_ROOT / "clawdboz" / "web" / "chat" / "core.py"

    manager_text = read_file(manager_file)
    core_text = read_file(core_file)

    checks = []
    if "avatar_url" in manager_text and "avatar_image" in manager_text:
        checks.append("manager.py 已处理 avatar_url -> avatar_image 映射")
    if "get_remote_bot_info" in core_text:
        checks.append("core.py 已调用 get_remote_bot_info")
    if "avatar_image" in core_text:
        checks.append("core.py 已发送 avatar_image 到前端")

    # 检查 WebSocket 连接稳定性
    ws_stable = "_remote_startup_called" in read_file(PROJECT_ROOT / "clawdboz" / "web" / "server.py")

    if len(checks) >= 3 and ws_stable:
        return "fixed", (
            "远程 Bot 通信链路已修复：Registry 字段映射正确、"
            "core.py 发送头像信息、WebSocket 有重复启动防护。"
            f" 通过检查项: {', '.join(checks)}"
        )

    return "partial", (
        "部分修复已完成，但建议人工端到端验证一次远程调用。"
        f" 通过检查项: {', '.join(checks) if checks else '无'}"
    )


def check_feature_1_friend_list_on_card() -> Tuple[str, str]:
    """Feature 1: 发布后的bot，要在卡片上显示bot的好友列表"""
    text = read_file(INDEX_HTML)

    # 检查 bot 详情卡片（showBotDetail 或类似）
    if "showBotDetail" in text:
        # 检查卡片内容中是否有好友列表相关
        body = extract_js_function(text, "showBotDetail")
        if body:
            if "friend" in body.lower() or "好友" in body:
                return "fixed", "showBotDetail() 卡片中已包含好友信息"

    # 检查 remote-bots.html
    remote_html = PROJECT_ROOT / "clawdboz" / "web" / "static" / "remote-bots.html"
    remote_text = read_file(remote_html)
    if "friend" in remote_text.lower() and ("bot-list" in remote_text or "card" in remote_text):
        return "partial", "remote-bots.html 中有好友相关显示，但需确认是否在发布后的 bot 卡片上"

    return "open", "未在发布后的 bot 卡片上找到好友列表显示逻辑"


def check_feature_2_remove_friend_on_card() -> Tuple[str, str]:
    """Feature 2: 发布后的bot，要支持在卡片上解除好友关系"""
    text = read_file(INDEX_HTML)

    remove_funcs = ["removeFriendAndReload", "removeFriendFromSidebarBot", "removeFriendFromContacts"]
    found = [f for f in remove_funcs if f in text]

    # 检查 bot 卡片上是否有解除好友按钮
    if "showBotDetail" in text:
        body = extract_js_function(text, "showBotDetail")
        if body:
            if "removeFriend" in body or "解除好友" in body:
                return "fixed", f"showBotDetail() 卡片中已包含解除好友按钮/功能 (后端函数: {', '.join(found)})"

    if found:
        return "partial", (
            f"解除好友的后端函数已存在 ({', '.join(found)})，"
            "但发布后的 bot 卡片上可能缺少对应的 UI 按钮"
        )

    return "open", "未找到发布后的 bot 卡片上解除好友关系的 UI 或逻辑"


# ========================================================================
# 注册表
# ========================================================================

BUG_CHECKS: List[Tuple[str, Callable[[], Tuple[str, str]]]] = [
    ("Bug 1: 新消息数量提示应显示新增消息条数而非更新次数", check_bug_1_message_count),
    ("Bug 2: 长消息回复到一半动态圆圈超时消失", check_bug_2_long_message_timeout),
    ("Bug 3: 切换回当前会话时多显示一条消息", check_bug_3_duplicate_message_on_switch),
    ("Bug 4: 用户自定义头像刷新后恢复默认", check_bug_4_user_avatar),
    ("Bug 5: Bot 换自定义头像后聊天框不显示", check_bug_5_bot_avatar),
    ("Bug 6: 远程 bot 通信失败", check_bug_6_remote_bot),
]

FEATURE_CHECKS: List[Tuple[str, Callable[[], Tuple[str, str]]]] = [
    ("Feature 1: 发布后的 bot 卡片显示好友列表", check_feature_1_friend_list_on_card),
    ("Feature 2: 发布后的 bot 卡片支持解除好友关系", check_feature_2_remove_friend_on_card),
]


def status_emoji(status: str) -> str:
    return {"fixed": "✅", "open": "❌", "partial": "🟡", "unknown": "❓"}.get(status, "❓")


def status_color(status: str) -> str:
    return {"fixed": C_GREEN, "open": C_RED, "partial": C_YELLOW, "unknown": C_CYAN}.get(status, C_RESET)


def main():
    if not BUGS_MD.exists():
        print(f"{C_RED}错误: 找不到 {BUGS_MD}{C_RESET}")
        sys.exit(1)

    bugs_md, features_md = parse_bugs_and_features(read_file(BUGS_MD))
    print(f"{C_BOLD}读取到 {len(bugs_md)} 个 bugs, {len(features_md)} 个 features{C_RESET}\n")

    has_open = False

    print(f"{C_BOLD}{'='*60}{C_RESET}")
    print(f"{C_BOLD}🐛 Bugs 状态检查{C_RESET}")
    print(f"{C_BOLD}{'='*60}{C_RESET}")
    for title, checker in BUG_CHECKS:
        status, detail = checker()
        if status in ("open", "partial"):
            has_open = True
        color = status_color(status)
        print(f"\n{status_emoji(status)} {color}{C_BOLD}{status.upper()}{C_RESET} {title}")
        print(f"   {detail}")

    print(f"\n{C_BOLD}{'='*60}{C_RESET}")
    print(f"{C_BOLD}✨ Features 状态检查{C_RESET}")
    print(f"{C_BOLD}{'='*60}{C_RESET}")
    for title, checker in FEATURE_CHECKS:
        status, detail = checker()
        if status in ("open", "partial"):
            has_open = True
        color = status_color(status)
        print(f"\n{status_emoji(status)} {color}{C_BOLD}{status.upper()}{C_RESET} {title}")
        print(f"   {detail}")

    print(f"\n{C_BOLD}{'='*60}{C_RESET}")
    if has_open:
        print(f"{C_RED}{C_BOLD}结论: 仍有未完全修复的 Bug 或未完成的 Feature{C_RESET}")
        sys.exit(1)
    else:
        print(f"{C_GREEN}{C_BOLD}结论: 所有 Bugs 已修复，所有 Features 已完成 ✅{C_RESET}")
        sys.exit(0)


if __name__ == "__main__":
    main()
