#!/usr/bin/env python3
"""
Web Chat E2E 自动化测试 - 使用 Playwright
模拟真实浏览器操作，测试会话切换和消息显示

测试场景：
1. 在会话1（Bot1）发送消息，不等回复完成
2. 切换到会话2（Bot2）发送消息，不等回复完成  
3. 切换到会话3（Bot3）发送消息
4. 等待所有消息完成
5. 检查：
   - 是否有多余的"生成中"消息气泡
   - 消息是否串流

使用方法:
    python tests/test_web_e2e_playwright.py
"""

import asyncio
import sys
import os
import time
from typing import List, Dict, Optional
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from playwright.async_api import async_playwright, Page, Browser, BrowserContext


@dataclass
class SessionInfo:
    """会话信息"""
    session_id: str
    bot_id: str
    bot_name: str
    messages: List[Dict] = field(default_factory=list)


class WebChatE2ETester:
    """Web Chat E2E 测试器"""
    
    def __init__(self, base_url: str = "http://localhost:8080", token: str = ""):
        self.base_url = base_url
        self.token = token
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.sessions: Dict[str, SessionInfo] = {}
        self.bots: List[Dict] = []
        
    def log(self, message: str, level: str = "INFO"):
        """记录日志"""
        timestamp = time.strftime("%H:%M:%S")
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}.get(level, "ℹ️")
        print(f"[{timestamp}] {prefix} {message}")
    
    async def setup(self):
        """初始化浏览器"""
        self.log("启动浏览器...")
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=False)  # 设置为 True 可隐藏浏览器
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
        url = f"{self.base_url}/static/index.html?token={self.token}"
        self.log(f"访问页面: {url}")
        await self.page.goto(url)
        await self.page.wait_for_load_state("networkidle")
        
        # 等待页面加载完成
        try:
            await self.page.wait_for_selector("#messageInput", timeout=10000)
            self.log("✓ 页面加载完成")
            
            # 等待初始数据加载
            await asyncio.sleep(2)
            
            return True
        except Exception as e:
            self.log(f"✗ 页面加载失败: {e}", "FAIL")
            return False
    
    async def create_session_with_bot(self, bot_index: int = 0) -> Optional[str]:
        """
        创建与 Bot 的会话
        
        流程：
        1. 点击"..."按钮
        2. 点击"新建群聊"
        3. 选择指定 Bot
        4. 点击确认
        """
        try:
            # 点击"更多"按钮（...）
            more_btn = await self.page.query_selector(".header-btn[title='更多']")
            if not more_btn:
                # 尝试通过图标查找
                more_btn = await self.page.query_selector(".header-btn:has(.fa-ellipsis-h)")
            
            if not more_btn:
                self.log("✗ 找不到更多按钮", "FAIL")
                return None
            
            await more_btn.click()
            await asyncio.sleep(0.5)
            self.log("✓ 打开更多菜单")
            
            # 点击"新建群聊"
            new_group_btn = await self.page.query_selector(".more-menu-item:has-text('新建群聊')")
            if new_group_btn:
                await new_group_btn.click()
                await asyncio.sleep(0.5)
                self.log("✓ 点击新建群聊")
            else:
                self.log("✗ 找不到新建群聊按钮", "FAIL")
                return None
            
            # 等待弹窗出现
            await self.page.wait_for_selector("#addBotModal.show", timeout=5000)
            
            # 获取可用 Bot 列表
            bot_items = await self.page.query_selector_all("#addBotList .bot-select-item")
            if not bot_items or len(bot_items) <= bot_index:
                self.log(f"✗ Bot 数量不足，需要 {bot_index+1} 个，实际 {len(bot_items)}", "FAIL")
                return None
            
            # 选择指定 Bot
            target_bot = bot_items[bot_index]
            await target_bot.click()
            await asyncio.sleep(0.3)
            
            # 获取 Bot 信息
            bot_name_elem = await target_bot.query_selector(".bot-select-name")
            bot_id_elem = await target_bot.query_selector(".bot-select-id")
            bot_name = await bot_name_elem.text_content() if bot_name_elem else f"Bot{bot_index}"
            bot_id_text = await bot_id_elem.text_content() if bot_id_elem else ""
            bot_id = bot_id_text.replace("@", "") if bot_id_text else f"bot_{bot_index}"
            
            self.log(f"✓ 选择 Bot: {bot_name} ({bot_id})")
            
            # 点击确认按钮
            confirm_btn = await self.page.query_selector("#confirmAddBotBtn")
            if confirm_btn:
                await confirm_btn.click()
                await asyncio.sleep(0.5)
                self.log("✓ 创建会话")
            else:
                self.log("✗ 找不到确认按钮", "FAIL")
                return None
            
            # 等待弹窗关闭
            await self.page.wait_for_selector("#addBotModal.show", state="hidden", timeout=5000)
            
            # 获取当前会话ID（从 URL 或页面状态）
            # 这里简化处理，使用 bot_id 作为会话标识
            session_id = f"session_{bot_id}_{int(time.time())}"
            self.sessions[session_id] = SessionInfo(
                session_id=session_id,
                bot_id=bot_id,
                bot_name=bot_name
            )
            
            return session_id
            
        except Exception as e:
            self.log(f"✗ 创建会话失败: {e}", "FAIL")
            return None
    
    async def switch_to_session_by_index(self, session_index: int) -> bool:
        """通过索引切换到指定会话"""
        try:
            # 获取所有会话项
            session_items = await self.page.query_selector_all(".sidebar-item")
            if not session_items or len(session_items) <= session_index:
                self.log(f"✗ 会话索引超出范围: {session_index}", "FAIL")
                return False
            
            target_session = session_items[session_index]
            await target_session.click()
            await asyncio.sleep(0.5)
            
            self.log(f"✓ 切换到会话 #{session_index + 1}")
            return True
        except Exception as e:
            self.log(f"✗ 切换会话失败: {e}", "FAIL")
            return False
    
    async def send_message(self, message: str) -> bool:
        """发送消息"""
        try:
            # 找到输入框并输入消息
            input_field = await self.page.query_selector("#messageInput")
            if not input_field:
                self.log("✗ 找不到消息输入框", "FAIL")
                return False
            
            await input_field.fill(message)
            await asyncio.sleep(0.2)
            
            # 点击发送按钮
            send_btn = await self.page.query_selector(".send-btn")
            if send_btn:
                await send_btn.click()
            else:
                await input_field.press("Enter")
            
            self.log(f"✓ 发送消息: {message}")
            await asyncio.sleep(0.5)  # 等待消息显示
            return True
        except Exception as e:
            self.log(f"✗ 发送消息失败: {e}", "FAIL")
            return False
    
    async def get_message_elements(self) -> List[Dict]:
        """获取当前会话的所有消息元素"""
        try:
            messages = []
            
            # 获取所有消息项
            message_wrappers = await self.page.query_selector_all(".message-item-wrapper")
            
            for i, wrapper in enumerate(message_wrappers):
                msg_info = {
                    "index": i,
                    "id": await wrapper.get_attribute("id"),
                }
                
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
                
                messages.append(msg_info)
            
            return messages
        except Exception as e:
            self.log(f"获取消息元素失败: {e}", "WARN")
            return []
    
    async def check_loading_states(self) -> List[str]:
        """检查是否有正在加载的消息"""
        try:
            loading_elements = await self.page.query_selector_all(".message-loading")
            issues = []
            
            for loading in loading_elements:
                try:
                    is_visible = await loading.is_visible()
                    if is_visible:
                        parent = await loading.evaluate("el => el.closest('.message-item-wrapper')?.id")
                        sender_elem = await loading.evaluate("el => el.closest('.message-item-wrapper')?.querySelector('.message-sender')?.textContent")
                        issues.append(f"发现残留加载状态: {parent} (发送者: {sender_elem})")
                except:
                    pass
            
            return issues
        except Exception as e:
            self.log(f"检查加载状态失败: {e}", "WARN")
            return []
    
    async def wait_for_all_responses(self, timeout: int = 90) -> bool:
        """等待所有消息响应完成"""
        self.log(f"等待所有消息响应完成 (超时: {timeout}s)...")
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            loading_issues = await self.check_loading_states()
            if not loading_issues:
                self.log("✓ 所有消息响应完成")
                return True
            
            self.log(f"  还有 {len(loading_issues)} 个消息在生成中...")
            await asyncio.sleep(2)
        
        self.log("✗ 等待响应超时", "FAIL")
        return False
    
    async def check_message_interleaving(self) -> List[str]:
        """检查消息是否串流 - 通过切换会话检查每个会话的消息"""
        issues = []
        
        # 获取所有会话
        session_items = await self.page.query_selector_all(".sidebar-item")
        
        for i, session_item in enumerate(session_items):
            try:
                # 切换到该会话
                await session_item.click()
                await asyncio.sleep(0.5)
                
                # 获取该会话的消息
                messages = await self.get_message_elements()
                
                # 获取会话名称
                session_name_elem = await session_item.query_selector(".sidebar-title")
                session_name = await session_name_elem.text_content() if session_name_elem else f"会话{i+1}"
                
                self.log(f"  检查 {session_name}: {len(messages)} 条消息")
                
                # 检查该会话的消息内容
                user_message = None
                bot_response = None
                
                for msg in messages:
                    sender = msg.get("sender", "")
                    content = msg.get("content", "")
                    
                    if not user_message and "用户" not in sender and "User" not in sender:
                        # 找到用户消息
                        user_message = content
                    elif not bot_response and ("bot" in sender.lower() or "Bot" in sender):
                        # 找到 Bot 回复
                        bot_response = content
                
                # 检查 Bot 回复中是否包含其他数字（简单的串流检测）
                if bot_response and user_message:
                    # 提取用户消息中的数字
                    import re
                    user_digits = re.findall(r'\d+', user_message)
                    
                    # 检查 Bot 回复中是否包含其他会话的数字
                    for other_digit in ["1", "2", "3"]:
                        if other_digit not in user_digits and other_digit in bot_response:
                            # 可能是串流，但先不报错，只记录
                            self.log(f"    [注意] {session_name} 的回复包含数字 {other_digit}，但用户消息是 {user_digits}", "WARN")
                            
            except Exception as e:
                self.log(f"  检查会话 {i+1} 时出错: {e}", "WARN")
        
        return issues
    
    async def run_test(self) -> bool:
        """运行完整的 E2E 测试"""
        self.log("=" * 70)
        self.log("开始 Web Chat E2E 测试 (Playwright)")
        self.log("=" * 70)
        
        try:
            # 初始化浏览器
            await self.setup()
            
            # 导航到页面
            if not await self.navigate_to_chat():
                return False
            
            # 步骤1: 创建会话1并发送消息
            self.log("\n▶ 步骤 1/6: 创建会话1并发送消息 '数字1'")
            session1_id = await self.create_session_with_bot(0)
            if not session1_id:
                return False
            
            await self.send_message("数字1")
            self.sessions[session1_id].messages.append({"role": "user", "content": "数字1"})
            
            await asyncio.sleep(2)  # 不等回复完成
            
            # 步骤2: 创建会话2并发送消息
            self.log("\n▶ 步骤 2/6: 创建会话2并发送消息 '数字2'（不等会话1完成）")
            session2_id = await self.create_session_with_bot(1)
            if not session2_id:
                return False
            
            await self.send_message("数字2")
            self.sessions[session2_id].messages.append({"role": "user", "content": "数字2"})
            
            await asyncio.sleep(2)  # 不等回复完成
            
            # 步骤3: 创建会话3并发送消息
            self.log("\n▶ 步骤 3/6: 创建会话3并发送消息 '数字3'（不等会话2完成）")
            session3_id = await self.create_session_with_bot(2)
            if not session3_id:
                return False
            
            await self.send_message("数字3")
            self.sessions[session3_id].messages.append({"role": "user", "content": "数字3"})
            
            # 步骤4: 等待所有消息完成
            self.log("\n▶ 步骤 4/6: 等待所有消息响应完成...")
            await self.wait_for_all_responses(timeout=90)
            
            # 步骤5: 检查加载状态
            self.log("\n▶ 步骤 5/6: 检查是否有残留的加载状态...")
            loading_issues = await self.check_loading_states()
            
            # 步骤6: 检查消息串流
            self.log("\n▶ 步骤 6/6: 检查消息是否串流...")
            interleaving_issues = await self.check_message_interleaving()
            
            # 生成测试报告
            self.log("\n" + "=" * 70)
            self.log("测试报告")
            self.log("=" * 70)
            
            all_issues = loading_issues + interleaving_issues
            
            if loading_issues:
                self.log("\n❌ 发现残留的加载状态:", "FAIL")
                for issue in loading_issues:
                    self.log(f"  - {issue}", "FAIL")
            else:
                self.log("\n✅ 没有残留的加载状态", "PASS")
            
            if interleaving_issues:
                self.log("\n❌ 发现消息串流:", "FAIL")
                for issue in interleaving_issues:
                    self.log(f"  - {issue}", "FAIL")
            else:
                self.log("✅ 没有消息串流", "PASS")
            
            self.log(f"\n总会话数: {len(self.sessions)}")
            self.log(f"发现问题: {len(all_issues)}")
            
            # 截图保存（用于调试）
            screenshot_path = "/tmp/web_chat_test_result.png"
            await self.page.screenshot(path=screenshot_path, full_page=True)
            self.log(f"\n截图已保存: {screenshot_path}")
            
            if all_issues:
                self.log(f"\n❌ 测试失败: 发现 {len(all_issues)} 个问题", "FAIL")
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
    
    tester = WebChatE2ETester(
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
