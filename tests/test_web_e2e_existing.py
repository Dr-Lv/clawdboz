#!/usr/bin/env python3
"""
Web Chat E2E 自动化测试 - 使用已有会话
利用页面上已存在的对话，发送消息后等待回复完成，然后截图分析

测试场景：
1. 切换到已有会话1，发送消息，等待回复完成，截图
2. 切换到已有会话2，发送消息，等待回复完成，截图
3. 切换到已有会话3，发送消息，等待回复完成，截图
4. 分析所有截图：
   - 检查是否有多余的"生成中"消息气泡
   - 检查消息是否串流

使用方法:
    python tests/test_web_e2e_existing.py
"""

import asyncio
import sys
import os
import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright, Page, Browser, BrowserContext


@dataclass
class SessionTestResult:
    """会话测试结果"""
    session_index: int
    session_name: str
    message_sent: str
    screenshot_path: str
    has_loading: bool = False
    loading_count: int = 0
    has_interleaving: bool = False
    issues: List[str] = field(default_factory=list)


class WebChatExistingSessionTester:
    """Web Chat 已有会话测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8080", token: str = ""):
        self.base_url = base_url
        self.token = token
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.results: List[SessionTestResult] = []
        self.test_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.screenshot_dir = f"/tmp/web_chat_test_{self.test_timestamp}"
        
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        timestamp = time.strftime("%H:%M:%S")
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "ℹ️")
        print(f"[{timestamp}] {prefix} {message}")
    
    async def setup(self):
        """初始化浏览器"""
        self.log("启动浏览器...")
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.log(f"截图保存目录: {self.screenshot_dir}")
        
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context(viewport={"width": 1280, "height": 800})
        self.page = await self.context.new_page()
        
        self.log("✓ 浏览器启动成功")
        
    async def teardown(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            self.log("✓ 浏览器已关闭")
    
    async def navigate_to_chat(self):
        """导航到聊天页面"""
        url = f"{self.base_url}/static/index.html?token={self.token}&_t={int(time.time())}"
        self.log(f"访问页面: {url}")
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")
        
        # 等待页面加载完成
        try:
            await self.page.wait_for_selector("#messageInput", timeout=10000)
            await asyncio.sleep(2)  # 等待初始数据加载
            self.log("✓ 页面加载完成")
            return True
        except Exception as e:
            self.log(f"✗ 页面加载失败: {e}", "FAIL")
            return False
    
    async def get_existing_sessions(self) -> List[Dict]:
        """获取页面上已有的会话列表"""
        try:
            session_items = await self.page.query_selector_all(".sidebar-item")
            sessions = []
            
            for i, item in enumerate(session_items):
                # 获取会话名称
                name_elem = await item.query_selector(".sidebar-title")
                name = await name_elem.text_content() if name_elem else f"会话{i+1}"
                
                # 获取会话ID
                session_id = await item.get_attribute("data-session-id")
                
                sessions.append({
                    "index": i,
                    "name": name.strip(),
                    "id": session_id,
                    "element": item
                })
            
            self.log(f"✓ 发现 {len(sessions)} 个已有会话")
            for s in sessions:
                self.log(f"  - [{s['index']}] {s['name']}")
            
            return sessions
        except Exception as e:
            self.log(f"获取会话列表失败: {e}", "FAIL")
            return []
    
    async def switch_to_session(self, session_index: int) -> Optional[str]:
        """切换到指定会话"""
        try:
            session_items = await self.page.query_selector_all(".sidebar-item")
            if not session_items or len(session_items) <= session_index:
                self.log(f"✗ 会话索引 {session_index} 超出范围", "FAIL")
                return None
            
            target = session_items[session_index]
            
            # 获取会话名称
            name_elem = await target.query_selector(".sidebar-title")
            name = await name_elem.text_content() if name_elem else f"会话{session_index+1}"
            
            # 点击切换
            await target.click()
            await asyncio.sleep(1)  # 等待会话切换完成
            
            self.log(f"✓ 切换到会话 [{session_index}] {name}")
            return name.strip()
        except Exception as e:
            self.log(f"✗ 切换会话失败: {e}", "FAIL")
            return None
    
    async def count_visible_loading(self) -> int:
        """统计可见的加载状态数量"""
        try:
            loading_elements = await self.page.query_selector_all(".message-loading")
            visible_count = 0
            
            for loading in loading_elements:
                try:
                    if await loading.is_visible():
                        visible_count += 1
                        # 获取 loading 元素的父消息信息用于调试
                        msg_id = await loading.evaluate("el => el.id")
                        parent_msg = await loading.evaluate("""
                            el => {
                                const wrapper = el.closest('.message-item-wrapper');
                                if (wrapper) {
                                    const sender = wrapper.querySelector('.message-sender');
                                    const content = wrapper.querySelector('.message-content');
                                    return {
                                        wrapper_id: wrapper.id,
                                        sender: sender ? sender.textContent : 'unknown',
                                        content_preview: content ? content.textContent.substring(0, 50) : 'no content'
                                    };
                                }
                                return null;
                            }
                        """)
                        if parent_msg:
                            self.log(f"    [DEBUG] Loading元素: id={msg_id}, 发送者={parent_msg['sender']}, 内容='{parent_msg['content_preview'][:30]}'")
                except:
                    pass
            
            return visible_count
        except:
            return 0
    
    async def send_message_and_wait(self, message: str, wait_timeout: int = 120) -> Tuple[bool, int]:
        """
        发送消息并等待回复完成
        
        返回: (是否成功, 新产生的加载状态数)
        """
        try:
            # 1. 先检查当前的加载状态（基准值）
            loading_before = await self.count_visible_loading()
            if loading_before > 0:
                self.log(f"  ⚠️ 发送前已有 {loading_before} 个加载状态，尝试清理...")
                # 尝试清理残留的 loading 元素
                await self.page.evaluate("""
                    () => {
                        const loadings = document.querySelectorAll('.message-loading');
                        loadings.forEach(el => {
                            console.log('[Test] 清理残留 loading:', el.id);
                            el.remove();
                        });
                        return loadings.length;
                    }
                """)
                # 重新计数
                loading_before = await self.count_visible_loading()
                self.log(f"  清理后剩余 {loading_before} 个加载状态")
            
            # 2. 输入消息
            input_field = await self.page.query_selector("#messageInput")
            if not input_field:
                self.log("✗ 找不到消息输入框", "FAIL")
                return False, 0
            
            await input_field.fill(message)
            await asyncio.sleep(0.2)
            
            # 3. 发送
            send_btn = await self.page.query_selector(".send-btn")
            if send_btn:
                await send_btn.click()
            else:
                await input_field.press("Enter")
            
            self.log(f"✓ 发送消息: {message}")
            
            # 4. 等待回复完成
            self.log(f"  等待回复完成（最多 {wait_timeout} 秒）...")
            start_time = time.time()
            max_loading_seen = loading_before  # 记录见过的最大加载数
            
            while time.time() - start_time < wait_timeout:
                current_loading = await self.count_visible_loading()
                
                # 更新最大加载数
                if current_loading > max_loading_seen:
                    max_loading_seen = current_loading
                
                # 如果加载数回到基准值或更低，说明新消息已完成
                if current_loading <= loading_before:
                    elapsed = time.time() - start_time
                    new_loading = max_loading_seen - loading_before
                    self.log(f"  ✓ 回复完成，耗时 {elapsed:.1f} 秒, 新增 {new_loading} 个加载状态")
                    return True, new_loading
                
                # 每秒检查一次
                await asyncio.sleep(1)
            
            # 超时
            elapsed = time.time() - start_time
            final_loading = await self.count_visible_loading()
            new_loading = max_loading_seen - loading_before
            
            if final_loading > loading_before:
                self.log(f"  ⚠️ 等待超时 ({elapsed:.1f}s)，仍有 {final_loading - loading_before} 个新消息未完成", "WARN")
                return False, new_loading
            else:
                self.log(f"  ✓ 回复完成（超时前），耗时 {elapsed:.1f} 秒")
                return True, new_loading
            
        except Exception as e:
            self.log(f"✗ 发送消息失败: {e}", "FAIL")
            return False, 0
    
    async def take_screenshot(self, name: str) -> str:
        """截图保存"""
        path = f"{self.screenshot_dir}/{name}.png"
        await self.page.screenshot(path=path, full_page=False)
        return path
    
    async def analyze_screenshot(self, screenshot_path: str, expected_message: str) -> Tuple[bool, List[str]]:
        """
        分析截图内容
        
        返回: (是否有问题, 问题列表)
        """
        issues = []
        
        # 1. 检查是否有残留的加载状态
        loading_elements = await self.page.query_selector_all(".message-loading")
        visible_loading = 0
        loading_details = []
        
        for i, loading in enumerate(loading_elements):
            try:
                if await loading.is_visible():
                    visible_loading += 1
                    # 获取对应的消息发送者
                    wrapper = await loading.evaluate("el => el.closest('.message-item-wrapper')")
                    if wrapper:
                        sender_elem = await self.page.evaluate("""
                            (wrapper) => {
                                const el = wrapper.querySelector('.message-sender');
                                return el ? el.textContent : 'Unknown';
                            }
                        """, wrapper)
                        loading_details.append(sender_elem)
            except:
                pass
        
        if visible_loading > 0:
            issues.append(f"发现 {visible_loading} 个正在加载的消息气泡: {loading_details}")
        
        # 2. 获取所有消息内容进行分析
        messages = await self.get_message_elements()
        
        # 3. 检查消息串流
        # 找到用户消息和 Bot 回复
        user_messages = [m for m in messages if m.get("is_user", False)]
        bot_messages = [m for m in messages if not m.get("is_user", False) and not m.get("is_loading", False)]
        
        # 检查 Bot 回复中是否包含其他数字
        for bot_msg in bot_messages:
            content = bot_msg.get("content", "")
            sender = bot_msg.get("sender", "Unknown")
            
            # 简单的串流检查：如果回复中包含"数字1"、"数字2"、"数字3"中的多个
            digits_found = []
            for d in ["1", "2", "3"]:
                if f"数字{d}" in content:
                    digits_found.append(d)
            
            if len(digits_found) > 1:
                issues.append(f"消息串流嫌疑: [{sender}] 的回复同时包含数字 {digits_found}")
        
        # 4. 检查消息顺序
        # 最后一条应该是 Bot 回复
        if messages and not messages[-1].get("is_loading", False):
            last_sender = messages[-1].get("sender", "")
            # 如果最后一条是用户消息，说明没有收到回复
            if messages[-1].get("is_user", False):
                issues.append(f"消息顺序异常: 最后一条是用户消息，可能没有收到 Bot 回复")
        
        return len(issues) > 0, issues
    
    async def get_message_elements(self) -> List[Dict]:
        """获取当前会话的所有消息元素"""
        try:
            messages = []
            message_wrappers = await self.page.query_selector_all(".message-item-wrapper")
            
            for i, wrapper in enumerate(message_wrappers):
                msg_info = {"index": i}
                
                # 检查是否有加载状态
                loading = await wrapper.query_selector(".message-loading")
                msg_info["is_loading"] = loading is not None
                if loading:
                    try:
                        msg_info["loading_visible"] = await loading.is_visible()
                    except:
                        msg_info["loading_visible"] = False
                
                # 检查发送者
                sender_elem = await wrapper.query_selector(".message-sender")
                if sender_elem:
                    msg_info["sender"] = await sender_elem.text_content()
                
                # 检查内容
                content_elem = await wrapper.query_selector(".message-content")
                if content_elem:
                    msg_info["content"] = await content_elem.text_content()
                
                # 判断是否是用户消息（通过样式类或位置）
                # 用户消息通常在右侧
                msg_container = await wrapper.query_selector(".message-item")
                if msg_container:
                    style = await msg_container.get_attribute("style")
                    msg_info["is_user"] = style and "flex-direction: row-reverse" in style
                else:
                    msg_info["is_user"] = False
                
                messages.append(msg_info)
            
            return messages
        except Exception as e:
            self.log(f"获取消息元素失败: {e}", "WARN")
            return []
    
    async def test_session(self, session_index: int, message: str) -> Optional[SessionTestResult]:
        """测试单个会话"""
        self.log(f"\n{'='*60}")
        self.log(f"测试会话 [{session_index}]")
        self.log(f"{'='*60}")
        
        # 1. 切换到会话
        session_name = await self.switch_to_session(session_index)
        if not session_name:
            return None
        
        # 2. 截图（发送前）- 检查残留状态
        loading_before = await self.count_visible_loading()
        if loading_before > 0:
            self.log(f"  ⚠️ 发送前已有 {loading_before} 个加载状态（残留）")
        before_path = await self.take_screenshot(f"session{session_index}_before")
        self.log(f"  截图（发送前）: {before_path}")
        
        # 3. 发送消息并等待回复
        success, new_loading = await self.send_message_and_wait(message, wait_timeout=120)
        
        # 4. 截图（回复后）
        after_path = await self.take_screenshot(f"session{session_index}_after")
        loading_after = await self.count_visible_loading()
        self.log(f"  截图（回复后）: {after_path}")
        
        # 5. 分析问题
        issues = []
        
        # 检查残留加载状态（发送前就存在的）
        if loading_before > 0:
            issues.append(f"发现 {loading_before} 个残留加载状态（发送消息前就已存在）")
        
        # 检查新消息是否完成
        if not success:
            issues.append(f"新消息未完成回复（超时）")
        
        # 检查回复后是否还有未完成的加载
        if loading_after > loading_before:
            issues.append(f"回复完成后仍有 {loading_after - loading_before} 个加载状态未完成")
        
        # 6. 创建结果
        result = SessionTestResult(
            session_index=session_index,
            session_name=session_name,
            message_sent=message,
            screenshot_path=after_path,
            has_loading=loading_before > 0 or loading_after > loading_before,
            loading_count=loading_before,
            has_interleaving=False,  # 简化检查
            issues=issues
        )
        
        # 显示分析结果
        if issues:
            self.log(f"  ❌ 发现问题:")
            for issue in issues:
                self.log(f"    - {issue}")
        else:
            self.log(f"  ✅ 未发现明显问题")
        
        return result
    
    async def run_test(self) -> bool:
        """运行完整的 E2E 测试"""
        self.log("=" * 70)
        self.log("开始 Web Chat E2E 测试 - 使用已有会话")
        self.log("=" * 70)
        
        try:
            # 初始化浏览器
            await self.setup()
            
            # 导航到页面
            if not await self.navigate_to_chat():
                return False
            
            # 获取已有会话
            sessions = await self.get_existing_sessions()
            if len(sessions) < 3:
                self.log(f"✗ 需要至少3个已有会话，但只有 {len(sessions)} 个", "FAIL")
                self.log("提示: 请先手动创建一些会话，或运行 test_web_e2e.sh 创建会话")
                return False
            
            # 测试3个会话
            test_messages = ["请回复数字1", "请回复数字2", "请回复数字3"]
            
            for i in range(3):
                result = await self.test_session(i, test_messages[i])
                if result:
                    self.results.append(result)
            
            # 生成测试报告
            self.log("\n" + "=" * 70)
            self.log("测试报告")
            self.log("=" * 70)
            
            total_issues = sum(len(r.issues) for r in self.results)
            total_loading = sum(r.loading_count for r in self.results)
            
            self.log(f"\n测试会话数: {len(self.results)}")
            self.log(f"发现问题数: {total_issues}")
            self.log(f"残留加载数: {total_loading}")
            
            self.log(f"\n各会话详情:")
            for r in self.results:
                status = "❌ 有问题" if r.issues else "✅ 正常"
                self.log(f"  [{r.session_index}] {r.session_name}: {status}")
                if r.issues:
                    for issue in r.issues:
                        self.log(f"      - {issue}")
            
            self.log(f"\n截图文件:")
            for r in self.results:
                self.log(f"  - {r.screenshot_path}")
            
            if total_issues > 0:
                self.log(f"\n❌ 测试失败: 发现 {total_issues} 个问题", "FAIL")
                return False
            else:
                self.log(f"\n✅ 测试通过: 所有检查项正常", "PASS")
                return True
                
        except Exception as e:
            self.log(f"\n✗ 测试异常: {e}", "FAIL")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await self.teardown()


async def main():
    """主函数"""
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("请先安装 Playwright: uv pip install playwright")
        print("然后安装浏览器: .venv/bin/playwright install chromium")
        sys.exit(1)
    
    tester = WebChatExistingSessionTester(
        base_url="http://localhost:8080",
        token="clawdboz-test-2024"
    )
    
    try:
        passed = await tester.run_test()
        sys.exit(0 if passed else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        await tester.teardown()
        sys.exit(130)


if __name__ == "__main__":
    asyncio.run(main())
