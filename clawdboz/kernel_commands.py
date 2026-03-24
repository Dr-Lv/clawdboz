#!/usr/bin/env python3
"""
内核切换命令模块 - 为 Bot 添加优雅的内核管理命令
"""
import json
from typing import List, Dict, Optional, Callable
from .kernel_manager import KernelManager, get_default_kernel_manager


class KernelCommandHandler:
    """内核命令处理器"""
    
    # 命令前缀
    COMMAND_PREFIXES = ['/kernel', '/k', '/switch']
    
    def __init__(self, kernel_manager: KernelManager):
        self.kernel_manager = kernel_manager
        self._register_commands()
    
    def _register_commands(self):
        """注册命令处理器"""
        self.commands = {
            'list': self._cmd_list,
            'ls': self._cmd_list,
            'switch': self._cmd_switch,
            'use': self._cmd_switch,
            'status': self._cmd_status,
            'info': self._cmd_status,
            'help': self._cmd_help,
        }
    
    def handle(self, args: List[str]) -> Dict:
        """处理内核命令
        
        Args:
            args: 命令参数列表
            
        Returns:
            响应字典，包含 content 字段
        """
        if not args:
            return self._cmd_status([])
        
        cmd = args[0].lower()
        cmd_args = args[1:]
        
        handler = self.commands.get(cmd)
        if handler:
            return handler(cmd_args)
        
        # 尝试作为内核名称直接切换
        return self._cmd_switch([cmd])
    
    def _cmd_list(self, args: List[str]) -> Dict:
        """列出可用内核"""
        kernels = self.kernel_manager.list_available()
        current = self.kernel_manager.current_kernel_name
        
        lines = ["**🤖 可用内核列表**", ""]
        
        for info in kernels:
            name = info['name']
            display = info['display_name']
            desc = info.get('description', '')
            
            marker = "▸" if name == current else "•"
            lines.append(f"{marker} **{name}** - {display}")
            if desc:
                lines.append(f"  {desc}")
        
        lines.extend([
            "",
            "**使用方法**: `/kernel <内核名称>` 或 `/k <内核名称>`"
        ])
        
        return {"content": "\n".join(lines)}
    
    def _cmd_switch(self, args: List[str]) -> Dict:
        """切换内核"""
        if not args:
            return {
                "content": "❌ 请指定内核名称\n\n用法: `/kernel switch <名称>` 或 `/kernel <名称>`"
            }
        
        kernel_name = args[0].lower()
        
        # 检查内核是否存在
        available = self.kernel_manager.list_available()
        kernel_names = [k['name'] for k in available]
        
        if kernel_name not in kernel_names:
            return {
                "content": f"❌ 未知内核: `{kernel_name}`\n\n可用内核: {', '.join(kernel_names)}"
            }
        
        # 执行切换
        success = self.kernel_manager.switch_kernel(kernel_name)
        
        if success:
            kernel_info = self.kernel_manager.registry.get_kernel_info(kernel_name)
            return {
                "content": (
                    f"✅ **已切换到 {kernel_info['display_name']}**\n\n"
                    f"类型: `{kernel_info['type']}`\n"
                    f"命令: `{kernel_info['command']}`"
                )
            }
        else:
            return {
                "content": f"❌ 切换失败，请检查内核配置或日志"
            }
    
    def _cmd_status(self, args: List[str]) -> Dict:
        """查看当前状态"""
        current = self.kernel_manager.current_kernel_name
        status = self.kernel_manager.get_status()
        
        lines = ["**🎯 内核状态**", ""]
        
        if current:
            kernel = self.kernel_manager.current_kernel
            info = kernel.get_info()
            lines.extend([
                f"**当前内核**: {info.name}",
                f"**类型**: {info.type.value}",
                f"**状态**: {'🟢 运行中' if info.status == 'running' else '⚪ 空闲'}",
                f"**进程 ID**: {info.pid or 'N/A'}",
                f"**会话 ID**: {info.session_id or '未创建'}",
            ])
        else:
            lines.append("**当前内核**: 未选择")
        
        lines.extend([
            "",
            f"**默认内核**: {status['default']}",
            "",
            "**可用内核**: " + ", ".join([k['name'] for k in status['available']])
        ])
        
        return {"content": "\n".join(lines)}
    
    def _cmd_help(self, args: List[str]) -> Dict:
        """显示帮助"""
        help_text = """**🤖 内核管理命令帮助**

**基本命令**:
• `/kernel` 或 `/k` - 查看当前状态
• `/kernel list` 或 `/k ls` - 列出所有内核
• `/kernel <名称>` - 切换到指定内核

**常用快捷方式**:
• `/k kimi` - 切换到 Kimi Code
• `/k claude` - 切换到 Claude Code
• `/k status` - 查看详细状态

**内核说明**:
• **kimi** - Kimi Code CLI，优秀的代码助手
• **claude** - Claude Code，强大的 AI 编程助手

内核切换后，新的对话将使用选定的内核。
"""
        return {"content": help_text}
    
    def is_command(self, text: str) -> bool:
        """检查文本是否是内核命令"""
        text = text.strip().lower()
        return any(text.startswith(prefix) for prefix in self.COMMAND_PREFIXES)
    
    def parse_command(self, text: str) -> List[str]:
        """解析命令文本"""
        # 移除命令前缀
        for prefix in self.COMMAND_PREFIXES:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()
                break
        
        # 分割参数
        return text.split() if text else []


def create_kernel_commands(kernel_manager: KernelManager) -> Dict[str, Callable]:
    """创建内核命令字典（用于 Bot 注册）
    
    Returns:
        命令名到处理函数的映射
    """
    handler = KernelCommandHandler(kernel_manager)
    
    def kernel_command(args, user_id, chat_id, message_id):
        """内核命令入口"""
        result = handler.handle(args)
        return result
    
    # 注册多个命令别名
    return {
        '/kernel': kernel_command,
        '/k': kernel_command,
        '/switch': kernel_command,
    }


__all__ = ['KernelCommandHandler', 'create_kernel_commands']
