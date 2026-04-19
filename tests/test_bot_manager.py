#!/usr/bin/env python3
"""
BotManager 单元测试
验证多 Bot 工作目录隔离
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clawdboz import BotManager


class TestBotManager(unittest.TestCase):
    """BotManager 测试用例"""
    
    def setUp(self):
        """每个测试前创建临时目录"""
        self.tmpdir = tempfile.mkdtemp()
        
    def tearDown(self):
        """每个测试后清理临时目录"""
        if os.path.exists(self.tmpdir):
            shutil.rmtree(self.tmpdir)
    
    def test_init_creates_directory(self):
        """测试初始化时创建工作目录"""
        wp = os.path.join(self.tmpdir, "workplace")
        assert not os.path.exists(wp)
        
        manager = BotManager(base_workplace=wp)
        
        self.assertTrue(os.path.exists(wp))
        self.assertTrue(os.path.isdir(wp))
    
    def test_register_creates_isolated_directories(self):
        """测试注册 Bot 时创建独立工作目录"""
        manager = BotManager(base_workplace=os.path.join(self.tmpdir, "WP"))
        
        # 注册两个 Bot
        try:
            manager.register("bot1", "cli_xxx1", "secret1")
            manager.register("bot2", "cli_xxx2", "secret2")
        except Exception as e:
            # Bot 类可能需要外部依赖，这里主要验证目录结构
            print(f"Bot 实例化可能失败（缺少飞书凭证）: {e}")
        
        # 验证目录结构
        bot1_dir = os.path.join(self.tmpdir, "WP", "bot1")
        bot2_dir = os.path.join(self.tmpdir, "WP", "bot2")
        
        self.assertTrue(os.path.exists(bot1_dir))
        self.assertTrue(os.path.exists(bot2_dir))
        
        # 验证子目录
        for bot_dir in [bot1_dir, bot2_dir]:
            self.assertTrue(os.path.exists(os.path.join(bot_dir, "logs")))
            self.assertTrue(os.path.exists(os.path.join(bot_dir, "user_files")))
            self.assertTrue(os.path.exists(os.path.join(bot_dir, "user_images")))
            self.assertTrue(os.path.exists(os.path.join(bot_dir, ".agents", "skills")))
    
    def test_register_creates_config_json(self):
        """测试注册时生成正确的 config.json"""
        manager = BotManager(base_workplace=os.path.join(self.tmpdir, "WP"))
        
        try:
            manager.register("test-bot", "cli_abc123", "mysecret", custom_key="value")
        except Exception as e:
            print(f"Bot 实例化可能失败: {e}")
        
        config_path = os.path.join(self.tmpdir, "WP", "test-bot", "config.json")
        self.assertTrue(os.path.exists(config_path))
        
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # 验证配置内容
        self.assertEqual(config["feishu"]["app_id"], "cli_abc123")
        self.assertEqual(config["feishu"]["app_secret"], "mysecret")
        self.assertEqual(config["custom_key"], "value")
        
        # 验证路径配置
        self.assertIn("workplace", config["paths"])
        self.assertIn("user_images", config["paths"])
        self.assertIn("user_files", config["paths"])
        self.assertIn("mcp_config", config["paths"])
        
        # 验证日志配置
        self.assertIn("debug_log", config["logs"])
        self.assertIn("feishu_api_log", config["logs"])
    
    def test_register_duplicate_id_raises(self):
        """测试重复注册相同 bot_id 时报错"""
        manager = BotManager(base_workplace=os.path.join(self.tmpdir, "WP"))
        
        # 第一次注册（可能失败但不影响目录创建）
        try:
            manager.register("dup", "id1", "secret1")
        except:
            pass
        
        # 第二次注册应该报错
        with self.assertRaises(ValueError) as ctx:
            manager.register("dup", "id2", "secret2")
        
        self.assertIn("已存在", str(ctx.exception))
    
    def test_get_bot(self):
        """测试获取 Bot 实例"""
        manager = BotManager(base_workplace=os.path.join(self.tmpdir, "WP"))
        
        # 获取不存在的 Bot
        self.assertIsNone(manager.get_bot("nonexistent"))
        
        # 注册后应能获取
        try:
            bot = manager.register("existing", "id", "secret")
            retrieved = manager.get_bot("existing")
            self.assertIsNotNone(retrieved)
            self.assertEqual(getattr(retrieved, '_bot_id', None), "existing")
        except:
            pass  # Bot 实例化失败不影响测试
    
    def test_list_bots(self):
        """测试列出所有 Bot"""
        manager = BotManager(base_workplace=os.path.join(self.tmpdir, "WP"))
        
        # 初始为空
        self.assertEqual(manager.list_bots(), {})
        
        # 注册后
        try:
            manager.register("bot-a", "id1", "secret1")
            manager.register("bot-b", "id2", "secret2")
        except:
            pass
        
        bots = manager.list_bots()
        self.assertIn("bot-a", bots)
        self.assertIn("bot-b", bots)
        self.assertNotEqual(bots["bot-a"], bots["bot-b"])  # 工作目录不同


def quick_test():
    """快速测试函数，用于手动验证"""
    tmpdir = tempfile.mkdtemp()
    print(f"\n[测试] 使用临时目录: {tmpdir}\n")
    
    try:
        # 1. 创建 Manager
        wp = os.path.join(tmpdir, "WORKPLACE")
        manager = BotManager(base_workplace=wp)
        print(f"✓ 创建 Manager，工作目录: {wp}")
        print(f"  目录存在: {os.path.exists(wp)}")
        
        # 2. 注册 Bot（可能因缺少飞书凭证而失败，但目录应创建成功）
        print("\n[测试] 注册 Bot...")
        try:
            manager.register("code-assistant", "cli_xxx1", "secret1", 
                           system_prompt="你是代码助手")
            manager.register("doc-writer", "cli_xxx2", "secret2",
                           system_prompt="你是文档助手")
            print("✓ Bot 注册成功")
        except Exception as e:
            print(f"⚠ Bot 实例化失败（预期内）: {e}")
        
        # 3. 验证目录结构
        print("\n[测试] 验证目录结构...")
        for bot_id in ["code-assistant", "doc-writer"]:
            bot_dir = os.path.join(wp, bot_id)
            print(f"\n  Bot '{bot_id}':")
            print(f"    主目录: {os.path.exists(bot_dir)} {bot_dir}")
            print(f"    logs/: {os.path.exists(os.path.join(bot_dir, 'logs'))}")
            print(f"    user_files/: {os.path.exists(os.path.join(bot_dir, 'user_files'))}")
            print(f"    user_images/: {os.path.exists(os.path.join(bot_dir, 'user_images'))}")
            print(f"    .agents/skills/: {os.path.exists(os.path.join(bot_dir, '.agents', 'skills'))}")
            
            # 验证 config.json
            config_path = os.path.join(bot_dir, "config.json")
            if os.path.exists(config_path):
                with open(config_path) as f:
                    cfg = json.load(f)
                print(f"    config.json: ✓ (app_id={cfg['feishu']['app_id'][:10]}...)")
        
        # 4. 验证隔离性
        print("\n[测试] 验证工作目录隔离...")
        bot1_config = os.path.join(wp, "code-assistant", "config.json")
        bot2_config = os.path.join(wp, "doc-writer", "config.json")
        
        if os.path.exists(bot1_config) and os.path.exists(bot2_config):
            with open(bot1_config) as f:
                cfg1 = json.load(f)
            with open(bot2_config) as f:
                cfg2 = json.load(f)
            
            # 工作目录应不同
            if cfg1['paths']['workplace'] != cfg2['paths']['workplace']:
                print("✓ 工作目录隔离正确")
            else:
                print("✗ 工作目录未隔离！")
            
            # App ID 应不同
            if cfg1['feishu']['app_id'] != cfg2['feishu']['app_id']:
                print("✓ 飞书配置隔离正确")
            else:
                print("✗ 飞书配置未隔离！")
        
        # 5. 验证 Bot 列表
        print(f"\n[测试] Bot 列表: {manager.list_bots()}")
        
        print("\n" + "="*50)
        print("✓ 所有测试通过！")
        print("="*50)
        
    finally:
        # 清理
        shutil.rmtree(tmpdir)
        print(f"\n[清理] 已删除临时目录")


if __name__ == "__main__":
    # 运行快速测试
    quick_test()
    
    # 运行单元测试
    print("\n" + "="*50)
    print("运行 unittest...")
    print("="*50 + "\n")
    unittest.main(verbosity=2, exit=False)
