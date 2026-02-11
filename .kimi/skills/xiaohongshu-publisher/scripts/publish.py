#!/usr/bin/env python3
"""
小红书图文自动发布脚本
使用 Playwright 模拟浏览器操作，包含防机器人检测机制
"""

import json
import random
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# 登录状态文件路径
SCRIPT_DIR = Path(__file__).parent.absolute()
STORAGE_PATH = SCRIPT_DIR.parent / "storage_state.json"


# ==================== 人类行为模拟函数 ====================

# 常见的真实用户代理列表
REAL_USER_AGENTS = [
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
]


def get_random_user_agent():
    """获取随机用户代理"""
    return random.choice(REAL_USER_AGENTS)


def random_delay(min_ms=500, max_ms=2000):
    """随机延迟，模拟人类操作间隔"""
    delay = random.uniform(min_ms, max_ms) / 1000
    time.sleep(delay)


def human_like_type(page, selector, text, min_delay=50, max_delay=200):
    """模拟人类打字速度"""
    element = page.locator(selector).first
    element.click()

    # 逐字输入，每个字符之间有随机延迟
    for char in text:
        element.type(char, delay=random.randint(min_delay, max_ms))
        # 偶尔停顿，模拟思考
        if random.random() < 0.1:  # 10%概率停顿
            time.sleep(random.uniform(0.3, 0.8))


def smooth_mouse_move(page, target_x, target_y):
    """平滑鼠标移动，模拟人类鼠标轨迹"""
    # 获取当前鼠标位置（假设在页面中心）
    current_x = 640  # 页面宽度的一半
    current_y = 400  # 页面高度的一半

    # 生成几个中间点，创建贝塞尔曲线效果
    steps = random.randint(5, 10)
    for i in range(steps + 1):
        t = i / steps
        # 添加一些随机偏移
        offset_x = random.randint(-20, 20)
        offset_y = random.randint(-20, 20)

        x = int(current_x + (target_x - current_x) * t) + offset_x
        y = int(current_y + (target_y - current_y) * t) + offset_y

        page.mouse.move(x, y)
        time.sleep(random.uniform(0.01, 0.03))


def human_like_click(page, selector, index=0):
    """模拟人类点击，带位置偏移和鼠标移动"""
    element = page.locator(selector).nth(index)

    # 获取元素位置和大小
    box = element.bounding_box()
    if not box:
        raise Exception("无法获取元素位置")

    # 计算点击位置（在元素中心附近随机偏移）
    center_x = box['x'] + box['width'] / 2
    center_y = box['y'] + box['height'] / 2

    # 添加随机偏移（-10到+10像素）
    offset_x = random.randint(-10, 10)
    offset_y = random.randint(-10, 10)

    click_x = center_x + offset_x
    click_y = center_y + offset_y

    # 先移动鼠标到目标位置
    smooth_mouse_move(page, click_x, click_y)

    # 随机延迟后点击
    random_delay(100, 500)
    page.mouse.click(click_x, click_y)


def human_like_scroll(page, distance=300):
    """模拟人类滚动行为"""
    # 分几次滚动，不是一次性滚动到位
    steps = random.randint(3, 6)
    step_distance = distance / steps

    for _ in range(steps):
        page.evaluate(f"window.scrollBy(0, {step_distance})")
        time.sleep(random.uniform(0.1, 0.3))


def random_reading_time(word_count):
    """根据字数返回合理的阅读时间"""
    # 人类阅读速度约 200-300 字/分钟
    reading_speed = random.uniform(200, 300)
    minutes = word_count / reading_speed
    # 转换为秒，并添加一些随机变化
    seconds = int(minutes * 60 * random.uniform(0.8, 1.2))
    return max(3, min(seconds, 30))  # 限制在3-30秒之间


def simulate_human_idling(page):
    """模拟人类浏览时的空闲行为"""
    actions = [
        lambda: page.evaluate("window.scrollBy(0, 100)"),
        lambda: page.evaluate("window.scrollBy(0, -50)"),
        lambda: page.wait_for_timeout(random.randint(500, 1500)),
        lambda: page.mouse.move(random.randint(100, 800), random.randint(100, 600)),
    ]

    # 随机执行1-2个动作
    num_actions = random.randint(1, 2)
    for _ in range(num_actions):
        action = random.choice(actions)
        action()
        time.sleep(random.uniform(0.3, 0.8))


# ==================== 原有功能函数 ====================


def load_content(content_path: str) -> dict:
    """加载帖子内容配置"""
    with open(content_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def validate_content(content: dict) -> None:
    """验证内容格式"""
    required_fields = ['title', 'content', 'images']
    for field in required_fields:
        if field not in content:
            raise ValueError(f"缺少必要字段: {field}")
    
    if not isinstance(content['images'], list) or len(content['images']) == 0:
        raise ValueError("至少需要一张图片")
    
    if len(content['images']) > 18:
        raise ValueError("小红书最多支持 18 张图片")


def check_images(images: list, base_path: Path) -> list:
    """检查图片是否存在并返回完整路径"""
    full_paths = []
    for img in images:
        img_path = base_path / img
        if not img_path.exists():
            raise FileNotFoundError(f"图片不存在: {img_path}")
        full_paths.append(str(img_path.absolute()))
    return full_paths


def wait_for_login(page, timeout=60):
    """等待用户完成登录"""
    print("等待登录完成...")
    for i in range(timeout):
        time.sleep(1)
        current_url = page.url
        has_login_text = False
        try:
            has_login_text = page.locator('text=手机号登录').is_visible(timeout=500)
        except:
            pass
        
        if "login" not in current_url and not has_login_text:
            print("✅ 登录成功！")
            return True
        if i % 10 == 0 and i > 0:
            print(f"已等待 {i} 秒，请完成登录...")
    return False


def close_popup_dialogs(page):
    """关闭浏览器弹出的提醒/弹窗"""
    try:
        popup_selectors = [
            'button:has-text("我知道了")',
            'button:has-text("关闭")',
            'button:has-text("确定")',
            'button:has-text("取消")',
            'button:has-text("不再提醒")',
            '.close-btn',
            '.dialog-close',
            '[class*="close"]',
            '[class*="Close"]',
        ]
        
        for selector in popup_selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=500):
                    print(f"关闭弹窗: {selector}")
                    btn.click()
                    page.wait_for_timeout(500)
            except:
                pass
        
        try:
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)
        except:
            pass
            
        try:
            page.mouse.click(100, 100)
            page.wait_for_timeout(300)
        except:
            pass
            
    except:
        pass


def publish_to_xiaohongshu(content: dict, headless: bool = True) -> bool:
    """发布到小红书"""
    with sync_playwright() as p:
        # 随机选择用户代理
        user_agent = get_random_user_agent()

        # 启动浏览器配置 - 反检测设置
        launch_args = {
            'headless': headless,
            'args': [
                # 禁用 WebDriver 检测
                '--disable-blink-features=AutomationControlled',
                # 禁用某些检测特征
                '--disable-dev-shm-usage',
                '--no-sandbox',
                '--disable-setuid-sandbox',
            ]
        }
        browser = p.chromium.launch(**launch_args)

        # 加载登录状态
        storage_state = str(STORAGE_PATH) if STORAGE_PATH.exists() else None
        context = browser.new_context(
            storage_state=storage_state,
            viewport={'width': 1280, 'height': 800},
            user_agent=user_agent  # 使用随机用户代理
        )

        # 注入反检测脚本
        context.add_init_script('''() => {
            // 覆盖 navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => false
            });

            // 覆盖 chrome 对象
            window.chrome = {
                runtime: {}
            };

            // 覆盖 permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );

            // 覆盖 plugins 长度
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5]
            });

            // 覆盖 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en']
            });
        }''')

        page = context.new_page()
        
        try:
            # 直接访问发布页面（不指定target，默认为图文）
            target_url = "https://creator.xiaohongshu.com/publish/publish?from=menu"
            print(f"正在打开发布页面: {target_url}")
            page.goto(target_url, wait_until="domcontentloaded", timeout=60000)

            # 模拟人类浏览：页面加载后的随机停留
            random_delay(2000, 4000)

            # 检查是否在登录页
            current_url = page.url
            print(f"当前页面: {current_url}")

            if "login" in current_url:
                print("⚠️ 未登录，请先手动登录")
                if not wait_for_login(page):
                    print("❌ 登录超时")
                    return False
                # 保存登录状态
                context.storage_state(path=str(STORAGE_PATH))
                print(f"✅ 登录状态已保存到: {STORAGE_PATH}")
                # 重新进入发布页面
                page.goto(target_url, wait_until="domcontentloaded", timeout=60000)
                random_delay(2000, 4000)

            print("进入发布页面...")

            # 模拟人类浏览：随机滚动和鼠标移动
            simulate_human_idling(page)
            
            # 关闭可能的弹窗
            close_popup_dialogs(page)
            
            # 确保在图文发布页面 - 检查URL并点击选项卡
            current_url = page.url
            print(f"检查当前URL: {current_url}")

            # 如果URL包含video，说明在视频tab，需要切换
            if "target=video" in current_url:
                print("⚠️ 当前在视频发布页，切换到图文...")
                try:
                    # 尝试通过JavaScript查找并点击图文tab - 更精确的选择
                    result = page.evaluate('''() => {
                        // 查找所有可能的tab元素
                        const selectors = [
                            '.publish-tab',
                            '.tabs-item',
                            '[role="tab"]',
                            '.tab-item',
                            '.nav-tab',
                            'button[class*="tab"]',
                            'div[class*="tab"]',
                            'span[class*="tab"]'
                        ];

                        for (const sel of selectors) {
                            const tabs = document.querySelectorAll(sel);
                            for (const tab of tabs) {
                                const text = (tab.textContent || '').trim();
                                // 精确匹配"上传图文"而不是包含图文的所有元素
                                if (text === '上传图文' || text === '图文') {
                                    return {success: true, text: text, element: tab.tagName};
                                }
                            }
                        }
                        return {success: false};
                    }''')

                    if result.get('success'):
                        print(f"✅ 找到图文tab元素: {result.get('element')} - {result.get('text')}")
                        # 直接导航到图文URL
                        page.goto("https://creator.xiaohongshu.com/publish/publish?from=menu&target=image", wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)
                    else:
                        print("⚠️ 未找到图文tab，直接访问URL...")
                        page.goto("https://creator.xiaohongshu.com/publish/publish?from=menu&target=image", wait_until="domcontentloaded")
                        page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"切换失败: {e}")
                    # 最后尝试直接访问URL
                    page.goto("https://creator.xiaohongshu.com/publish/publish?from=menu&target=image", wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)

            # 再次确认URL
            current_url = page.url
            print(f"切换后URL: {current_url}")

            # 如果仍然在video页面，直接访问image URL
            if "target=video" in current_url:
                print("强制切换到图文发布页...")
                page.goto("https://creator.xiaohongshu.com/publish/publish?from=menu&target=image", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
            
            # 上传图片 - 使用JavaScript找到正确的图片输入框
            print(f"正在上传 {len(content['images'])} 张图片...")
            try:
                # 使用JavaScript找到接受图片的file input
                upload_info = page.evaluate('''(imageCount) => {
                    const inputs = Array.from(document.querySelectorAll('input[type="file"]'));
                    for (const input of inputs) {
                        const accept = input.getAttribute('accept') || '';
                        // 查找明确接受图片的输入框
                        if (accept.includes('image') || accept.includes('png') || accept.includes('jpg') || accept.includes('jpeg')) {
                            return {found: true, accept: accept, hasMultiple: input.hasAttribute('multiple')};
                        }
                    }
                    // 如果没找到明确的图片输入，找不排除视频的通用输入
                    for (const input of inputs) {
                        const accept = input.getAttribute('accept') || '';
                        if (!accept.toLowerCase().includes('video')) {
                            return {found: true, accept: accept, hasMultiple: input.hasAttribute('multiple')};
                        }
                    }
                    return {found: false, total: inputs.length};
                }''', len(content['images']))

                if not upload_info.get('found'):
                    raise Exception(f"未找到合适的文件上传输入框，总共有 {upload_info.get('total', 0)} 个file input")

                print(f"找到文件输入框: accept={upload_info.get('accept')}, multiple={upload_info.get('hasMultiple')}")

                # 现在使用Playwright找到并使用这个输入框
                file_inputs = page.locator('input[type="file"]').all()
                uploaded = False
                for file_input in file_inputs:
                    try:
                        accept_attr = file_input.get_attribute('accept') or ''
                        # 使用JavaScript找到的那个输入框
                        if accept_attr == upload_info.get('accept') or (upload_info.get('hasMultiple') == file_input.evaluate('el => el.hasAttribute("multiple")')):
                            # 如果支持多文件，一次性上传
                            if upload_info.get('hasMultiple'):
                                file_input.set_input_files(content['images'])
                            else:
                                # 单文件输入，逐个上传
                                for img_path in content['images']:
                                    file_input.set_input_files(img_path)
                                    page.wait_for_timeout(500)
                            uploaded = True
                            print("图片上传完成")
                            break
                    except Exception as e:
                        continue

                if not uploaded:
                    raise Exception("文件上传失败")
            except Exception as e:
                print(f"⚠️ 上传失败: {e}")
                page.screenshot(path="debug_screenshot.png")
                return False
            
            # 等待图片上传完成
            print("等待图片上传...")
            # 模拟人类：随机等待时间
            upload_wait = random.randint(6000, 10000)
            time.sleep(upload_wait / 1000)

            # 填写标题
            print("填写标题...")
            try:
                # 尝试多种选择器
                title_input = page.locator('input[placeholder*="标题"], input[class*="title"], input[class*="Title"], .title-input, textarea[placeholder*="标题"]').first
                if title_input.is_visible(timeout=5000):
                    # 模拟人类：点击前有随机延迟
                    random_delay(500, 1500)

                    # 模拟人类打字
                    title_input.click()
                    time.sleep(random.uniform(0.3, 0.6))

                    # 逐字输入标题
                    for char in content['title']:
                        title_input.type(char, delay=random.randint(50, 150))
                        # 10%概率停顿，模拟思考
                        if random.random() < 0.1:
                            time.sleep(random.uniform(0.2, 0.5))

                    print(f"✅ 标题已填写: {content['title'][:20]}...")

                    # 填写后随机停顿
                    random_delay(800, 2000)
                else:
                    print("⚠️ 未找到标题输入框")
            except Exception as e:
                print(f"填写标题失败: {e}")

            # 填写正文
            print("填写正文...")
            try:
                # 尝试多种选择器查找正文输入区
                content_input = page.locator('.content-editor [contenteditable="true"], .editor [contenteditable="true"], .desc-editor [contenteditable="true"], textarea[class*="content"], textarea[class*="desc"], [contenteditable="true"]').first
                if content_input.is_visible(timeout=5000):
                    # 模拟人类：点击前的延迟
                    random_delay(500, 1500)

                    content_input.click()
                    time.sleep(random.uniform(0.3, 0.6))

                    full_content = content['content']
                    if 'topics' in content:
                        for topic in content['topics']:
                            full_content += f" #{topic}"
                    # 截取前1000字
                    full_content = full_content[:1000]

                    # 模拟人类打字：先快速输入一部分，然后慢一些
                    chars = list(full_content)
                    for i, char in enumerate(chars):
                        # 前半部分较快，后半部分较慢
                        if i < len(chars) / 2:
                            delay = random.randint(30, 80)
                        else:
                            delay = random.randint(50, 150)

                        content_input.type(char, delay=delay)

                        # 偶尔停顿（模拟思考和检查）
                        if random.random() < 0.08:  # 8%概率
                            time.sleep(random.uniform(0.3, 0.8))

                        # 每50个字符左右停顿一下（模拟分段）
                        if i > 0 and i % random.randint(40, 60) == 0:
                            time.sleep(random.uniform(0.5, 1.0))

                    print(f"✅ 正文已填写: {len(full_content)} 字")

                    # 填写完成后，模拟人类查看
                    reading_time = random_reading_time(len(full_content))
                    print(f"模拟阅读内容 {reading_time} 秒...")
                    time.sleep(reading_time)
                else:
                    print("⚠️ 未找到正文输入框")
            except Exception as e:
                print(f"填写正文失败: {e}")

            # 模拟人类：填写完成后的一些随机行为
            simulate_human_idling(page)

            # 再次确认我们在正确的tab上（有时候页面会自动切换）
            current_url = page.url
            print(f"填写内容后URL: {current_url}")
            if "target=video" in current_url:
                print("⚠️ 页面切换到了视频tab，强制切回图文...")
                page.goto("https://creator.xiaohongshu.com/publish/publish?from=menu&target=image", wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                # 需要重新填写内容，因为页面刷新了
                print("重新填写标题和正文...")
                try:
                    title_input = page.locator('input[placeholder*="标题"], input[class*="title"], input[class*="Title"], .title-input, textarea[placeholder*="标题"]').first
                    title_input.fill(content['title'])
                    print("✅ 标题已重新填写")
                except:
                    pass
                try:
                    content_input = page.locator('.content-editor [contenteditable="true"], .editor [contenteditable="true"], .desc-editor [contenteditable="true"], textarea[class*="content"], textarea[class*="desc"], [contenteditable="true"]').first
                    full_content = content['content']
                    if 'topics' in content:
                        for topic in content['topics']:
                            full_content += f" #{topic}"
                    full_content = full_content[:1000]
                    content_input.fill(full_content)
                    print("✅ 正文已重新填写")
                except:
                    pass
                page.wait_for_timeout(2000)

            # 点击发布
            print("正在发布...")
            try:
                # 先检查当前URL，确保还在正确的tab
                current_url = page.url
                print(f"发布前URL: {current_url}")

                # 如果被切到video了，先切回来
                if "target=video" in current_url:
                    print("⚠️ 被切换到视频tab，强制切回...")
                    page.goto("https://creator.xiaohongshu.com/publish/publish?from=menu&target=image", wait_until="domcontentloaded")
                    page.wait_for_timeout(2000)
                    # 重新填写内容
                    try:
                        title_input = page.locator('input[placeholder*="标题"], input[class*="title"], input[class*="Title"], .title-input, textarea[placeholder*="标题"]').first
                        title_input.fill(content['title'])
                    except:
                        pass
                    try:
                        content_input = page.locator('.content-editor [contenteditable="true"], .editor [contenteditable="true"], .desc-editor [contenteditable="true"], textarea[class*="content"], textarea[class*="desc"], [contenteditable="true"]').first
                        full_content = content['content']
                        if 'topics' in content:
                            for topic in content['topics']:
                                full_content += f" #{topic}"
                        full_content = full_content[:1000]
                        content_input.fill(full_content)
                    except:
                        pass
                    page.wait_for_timeout(1000)

                # 模拟人类：滚动到页面底部（分几次滚动，不是一次性）
                print("滚动到发布按钮...")
                human_like_scroll(page, distance=random.randint(400, 600))

                # 模拟人类：滚动后的停顿
                random_delay(1000, 2000)

                # 等待发布按钮出现（可能需要等待页面加载完成）
                print("等待发布按钮出现...")
                random_delay(1500, 3000)

                # 尝试通过JavaScript查找并点击发布按钮
                result = page.evaluate('''() => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    for (const btn of buttons) {
                        const text = (btn.textContent || '').trim();
                        // 查找"发布"按钮
                        if (text === '发布' || text === '发布笔记' || text === '立即发布') {
                            return {success: true, text: text, found: true};
                        }
                    }
                    // 如果没找到精确匹配，尝试模糊匹配
                    for (const btn of buttons) {
                        const text = (btn.textContent || '').trim();
                        if (text.includes('发布') && !text.includes('草稿') && !text.includes('预览') && text.length < 10) {
                            return {success: true, text: text, found: true};
                        }
                    }
                    return {success: false, allTexts: buttons.map(b => (b.textContent || '').trim()).filter(t => t)};
                }''')

                if result.get('success'):
                    print(f"✅ 找到发布按钮: {result.get('text')}")

                    # 模拟人类：点击前的犹豫和随机移动
                    random_delay(1000, 2500)

                    # 模拟人类：鼠标在按钮周围移动
                    try:
                        publish_btn = page.locator('button:has-text("发布")').first
                        box = publish_btn.bounding_box()
                        if box:
                            # 在按钮附近移动鼠标
                            for _ in range(random.randint(1, 3)):
                                offset_x = random.randint(-30, 30)
                                offset_y = random.randint(-30, 30)
                                page.mouse.move(
                                    box['x'] + box['width'] / 2 + offset_x,
                                    box['y'] + box['height'] / 2 + offset_y
                                )
                                time.sleep(random.uniform(0.1, 0.3))
                    except:
                        pass

                    # 使用JavaScript直接点击，避免被弹窗/tooltip阻挡
                    click_result = page.evaluate('''() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        for (const btn of buttons) {
                            const text = (btn.textContent || '').trim();
                            if (text === '发布' || text === '发布笔记' || text === '立即发布') {
                                btn.click();
                                return {success: true, text: text};
                            }
                        }
                        // 尝试模糊匹配
                        for (const btn of buttons) {
                            const text = (btn.textContent || '').trim();
                            if (text.includes('发布') && !text.includes('草稿') && !text.includes('预览') && text.length < 10) {
                                btn.click();
                                return {success: true, text: text};
                            }
                        }
                        return {success: false};
                    }''')

                    if click_result.get('success'):
                        print(f"已通过JS点击发布按钮: {click_result.get('text')}")
                    else:
                        print("⚠️ JS点击失败，尝试Playwright...")
                        submit_btn = page.locator('button:has-text("发布")').first
                        submit_btn.scroll_into_view_if_needed()
                        random_delay(500, 1000)
                        submit_btn.click(force=True)
                        print("已强制点击发布按钮")
                else:
                    print(f"⚠️ 未找到发布按钮，页面上所有按钮文字: {result.get('allTexts', [])[:10]}")
                    page.screenshot(path="debug_no_button.png")

            except Exception as e:
                print(f"点击发布按钮失败: {e}")
                page.screenshot(path="debug_publish.png")
                return False

            # 等待发布完成
            print("等待发布完成...")
            # 模拟人类：等待发布完成的随机时间，分段等待
            for i in range(3):
                wait_time = random.uniform(2, 4)
                print(f"等待中... {i+1}/3")
                time.sleep(wait_time)

                # 每次等待后检查
                current_url = page.url
                print(f"当前页面URL: {current_url}")

                # 检查是否有成功弹窗
                success_popup = page.evaluate('''() => {
                    // 查找成功弹窗的标识
                    const bodyText = document.body.textContent || document.body.innerText || '';
                    const popupTexts = ['发布成功', '笔记已发布', '成功发布'];
                    for (const text of popupTexts) {
                        if (bodyText.includes(text)) {
                            return {found: true, text: text};
                        }
                    }

                    // 查找成功相关的按钮
                    const buttons = Array.from(document.querySelectorAll('button'));
                    for (const btn of buttons) {
                        const btnText = (btn.textContent || '').trim();
                        if (btnText.includes('查看笔记') || btnText.includes('返回首页')) {
                            return {found: true, text: btnText};
                        }
                    }

                    return {found: false};
                }''')

                is_success = False

                # 检查弹窗确认
                if success_popup.get('found'):
                    is_success = True
                    print(f"✅ 检测到发布成功弹窗: {success_popup.get('text')}")
                    break
                # 检查URL中的成功标识
                elif 'published=true' in current_url:
                    is_success = True
                    print("✅ URL包含published=true，发布成功！")
                    break
                elif 'publish' not in current_url:
                    is_success = True
                    print("✅ 页面已离开发布页，发布成功！")
                    break

            # 如果还没成功，最后检查页面内容
            if not is_success:
                page_content = page.content()
                success_indicators = ['发布成功', '笔记详情', 'publish/success', '/explore', '查看笔记']
                if any(indicator in page_content for indicator in success_indicators):
                    is_success = True
                    print("✅ 检测到成功提示，发布成功！")
                else:
                    page.screenshot(path="verify_publish.png")
                    print("⚠️ 无法确认发布状态，请检查 verify_publish.png")
                    print(f"页面内容前500字符: {page_content[:500]}")
                    return False

            # 模拟人类：关闭弹窗或点击按钮
            if is_success:
                random_delay(1000, 2000)
                try:
                    # 尝试点击"返回首页"或关闭按钮
                    close_result = page.evaluate('''() => {
                        const buttons = Array.from(document.querySelectorAll('button'));
                        for (const btn of buttons) {
                            const text = (btn.textContent || '').trim();
                            if (text.includes('返回首页') || text.includes('关闭') || text === '知道了') {
                                btn.click();
                                return {clicked: true, text: text};
                            }
                        }
                        return {clicked: false};
                    }''')
                    if close_result.get('clicked'):
                        print(f"已点击 {close_result.get('text')}")
                except:
                    pass
            
            # 保存登录状态
            context.storage_state(path=str(STORAGE_PATH))
            
            return True
            
        except Exception as e:
            print(f"❌ 发布失败: {e}")
            page.screenshot(path="error_screenshot.png")
            print("错误截图已保存到 error_screenshot.png")
            return False
            
        finally:
            print("\n⏹️ 发布完成，关闭浏览器...")
            browser.close()


def main():
    if len(sys.argv) < 2:
        print("用法: python publish.py <content.json 路径> [--no-headless]")
        print("示例: python publish.py assets/post_template/content.json")
        print("       python publish.py assets/post_template/content.json --no-headless  # 显示浏览器")
        sys.exit(1)
    
    content_path = sys.argv[1]
    headless = "--no-headless" not in sys.argv
    
    print(f"登录状态文件: {STORAGE_PATH}")
    print(f"登录状态: {'已保存' if STORAGE_PATH.exists() else '未找到'}")
    
    try:
        content = load_content(content_path)
        validate_content(content)
        
        base_path = Path(content_path).parent
        content['images'] = check_images(content['images'], base_path / "images")
        
        print(f"标题: {content['title']}")
        print(f"图片数: {len(content['images'])}")
        
        success = publish_to_xiaohongshu(content, headless=headless)
        sys.exit(0 if success else 1)
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
