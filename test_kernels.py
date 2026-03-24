#!/usr/bin/env python3
"""
内核管理器测试脚本
验证多内核支持功能
"""
import sys
import os

# 添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clawdboz import KernelManager, KernelType, get_default_kernel_manager


def test_kernel_manager():
    """测试内核管理器"""
    print("=" * 60)
    print("🧪 测试内核管理器")
    print("=" * 60)
    
    # 创建管理器
    manager = get_default_kernel_manager()
    
    # 测试 1: 列出内核
    print("\n📋 测试 1: 列出可用内核")
    kernels = manager.list_available()
    print(f"找到 {len(kernels)} 个内核:")
    for k in kernels:
        print(f"  - {k['name']}: {k['display_name']}")
    
    # 测试 2: 查看状态
    print("\n📊 测试 2: 查看状态")
    status = manager.get_status()
    print(f"默认内核: {status['default']}")
    print(f"当前内核: {status['current'] or '未选择'}")
    
    # 测试 3: 切换内核（仅测试配置，不实际启动）
    print("\n🔄 测试 3: 内核切换逻辑")
    available_names = [k['name'] for k in kernels]
    
    for name in available_names[:2]:  # 测试前两个
        print(f"\n  尝试切换到: {name}")
        config = manager.registry.get_config(name)
        if config:
            print(f"    ✓ 配置存在")
            print(f"    - 类型: {config.type.value}")
            print(f"    - 命令: {config.command}")
            print(f"    - 参数: {config.args}")
        else:
            print(f"    ✗ 配置不存在")
    
    print("\n" + "=" * 60)
    print("✅ 测试完成")
    print("=" * 60)
    
    return True


def test_imports():
    """测试模块导入"""
    print("\n📦 测试模块导入")
    
    try:
        from clawdboz import Kernel, KernelConfig, KernelInfo
        from clawdboz import KernelManager, KernelRegistry, KernelType
        from clawdboz import KernelCommandHandler, create_kernel_commands
        print("  ✓ 所有模块导入成功")
        return True
    except ImportError as e:
        print(f"  ✗ 导入失败: {e}")
        return False


def main():
    """主函数"""
    print("\n" + "🦞" * 30)
    print("Clawdboz 多内核支持测试")
    print("🦞" * 30 + "\n")
    
    # 测试导入
    if not test_imports():
        print("\n❌ 导入测试失败，请检查安装")
        return 1
    
    # 测试内核管理器
    try:
        test_kernel_manager()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("\n" + "=" * 60)
    print("🎉 所有测试通过！")
    print("=" * 60)
    print("\n现在你可以:")
    print("  1. 运行: python -m clawdboz")
    print("  2. 在飞书中使用: /kernel list")
    print("  3. 切换内核: /kernel claude 或 /kernel kimi")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
