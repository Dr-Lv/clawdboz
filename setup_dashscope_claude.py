#!/usr/bin/env python3
"""
阿里云 DashScope Claude Code 快速设置脚本
一键配置通义千问模型作为 Claude Code 后端
"""
import os
import sys
import json
from pathlib import Path


def print_banner():
    """打印横幅"""
    print("\n" + "=" * 70)
    print("🚀 阿里云 DashScope Claude Code 设置工具")
    print("=" * 70)
    print("\n本工具将帮助你配置 Claude Code 使用阿里云通义千问模型")
    print("支持的模型: qwen3.5-plus, qwen-max, qwen-turbo, qwen-plus 等\n")


def check_api_key():
    """检查 API Key"""
    api_key = os.environ.get('DASHSCOPE_API_KEY')
    
    if api_key:
        print(f"✅ 找到环境变量 DASHSCOPE_API_KEY")
        masked = api_key[:8] + "..." + api_key[-4:] if len(api_key) > 12 else "***"
        print(f"   Key: {masked}")
        return api_key
    
    print("⚠️  未找到 DASHSCOPE_API_KEY 环境变量")
    print("\n请从阿里云控制台获取 API Key:")
    print("   https://dashscope.console.aliyun.com/apiKey")
    print("\n然后选择以下方式之一:")
    print("   1. 设置环境变量: export DASHSCOPE_API_KEY='your-key'")
    print("   2. 在运行时输入")
    
    choice = input("\n是否现在输入 API Key? (y/n): ").strip().lower()
    if choice == 'y':
        api_key = input("请输入 DashScope API Key: ").strip()
        if api_key:
            # 询问是否保存到环境变量
            save = input("是否保存到 ~/.bashrc? (y/n): ").strip().lower()
            if save == 'y':
                bashrc = Path.home() / '.bashrc'
                with open(bashrc, 'a') as f:
                    f.write(f"\n# DashScope API Key for Claude Code\n")
                    f.write(f"export DASHSCOPE_API_KEY='{api_key}'\n")
                print(f"✅ 已添加到 {bashrc}")
                print("   请运行: source ~/.bashrc")
            return api_key
    
    return None


def select_model():
    """选择模型"""
    models = {
        '1': ('qwen3.5-plus', '通义千问3.5 Plus - 平衡性能和成本'),
        '2': ('qwen-max', '通义千问Max - 最强性能'),
        '3': ('qwen-turbo', '通义千问Turbo - 最快响应'),
        '4': ('qwen-plus', '通义千问Plus - 高性价比'),
    }
    
    print("\n📋 请选择要使用的模型:")
    for key, (model, desc) in models.items():
        print(f"   {key}. {model}")
        print(f"      {desc}")
    
    choice = input("\n请输入选项 (1-4) [默认: 1]: ").strip() or '1'
    
    if choice in models:
        return models[choice][0]
    
    # 自定义模型
    custom = input("请输入自定义模型名称: ").strip()
    return custom if custom else 'qwen3.5-plus'


def generate_config(api_key: str, model: str):
    """生成配置文件"""
    kernel_name = model.replace('.', '').replace('-', '')
    
    config = {
        "kernels": {
            "default": "kimi",
            "available": {
                "kimi": {
                    "name": "Kimi Code",
                    "type": "kimi-code",
                    "command": "kimi",
                    "args": ["--mcp", "stdio"],
                    "env": {"KIMI_API_KEY": "${KIMI_API_KEY}"},
                    "description": "Moonshot Kimi Code CLI"
                },
                kernel_name: {
                    "name": f"Claude Code ({model})",
                    "type": "claude-code-acp",
                    "command": "npx",
                    "args": ["@zed-industries/claude-code-acp"],
                    "env": {
                        "ANTHROPIC_AUTH_TOKEN": api_key,
                        "ANTHROPIC_BASE_URL": "https://dashscope.aliyuncs.com/apps/anthropic",
                        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
                        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
                        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                        "ANTHROPIC_MODEL": model,
                        "ANTHROPIC_REASONING_MODEL": model
                    },
                    "description": f"基于阿里云 DashScope 的 Claude Code，使用 {model} 模型"
                }
            }
        },
        "paths": {
            "workplace": "WORKPLACE",
            "logs": "logs"
        },
        "scheduler": {
            "heart_beat": 60
        }
    }
    
    return config, kernel_name


def save_config(config: dict, kernel_name: str):
    """保存配置文件"""
    # 检查现有配置
    config_path = Path('config.json')
    if config_path.exists():
        backup = Path('config.json.backup')
        backup.write_text(config_path.read_text(), encoding='utf-8')
        print(f"✅ 已备份现有配置到 {backup}")
    
    # 保存新配置
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding='utf-8'
    )
    
    print(f"✅ 配置已保存到 {config_path}")
    return config_path


def print_usage(kernel_name: str, model: str):
    """打印使用说明"""
    print("\n" + "=" * 70)
    print("🎉 设置完成！")
    print("=" * 70)
    print(f"\n已配置内核: {kernel_name}")
    print(f"使用模型: {model}")
    
    print("\n📖 使用方法:")
    print("   1. 启动 Bot:")
    print("      python -m clawdboz")
    print("")
    print("   2. 在飞书中切换内核:")
    print(f"      /kernel {kernel_name}")
    print("      或")
    print(f"      /k {kernel_name}")
    print("")
    print("   3. 查看所有内核:")
    print("      /kernel list")
    print("")
    print("   4. 查看当前状态:")
    print("      /kernel")
    
    print("\n💡 提示:")
    print("   - 你可以同时配置多个模型，重复运行此脚本")
    print("   - 在 config.json 中手动编辑可添加更多自定义配置")
    print("   - API Key 已写入配置文件，请妥善保管")
    
    print("\n" + "=" * 70)


def main():
    """主函数"""
    print_banner()
    
    # 检查 API Key
    api_key = check_api_key()
    if not api_key:
        print("\n❌ 未提供 API Key，退出设置")
        return 1
    
    # 选择模型
    model = select_model()
    print(f"\n✅ 选择模型: {model}")
    
    # 生成配置
    print("\n📝 生成配置文件...")
    config, kernel_name = generate_config(api_key, model)
    
    # 保存配置
    save_config(config, kernel_name)
    
    # 打印使用说明
    print_usage(kernel_name, model)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
