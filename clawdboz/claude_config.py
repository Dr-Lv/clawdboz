#!/usr/bin/env python3
"""
Claude Code 自定义配置管理器
支持使用第三方模型（如阿里云通义千问）替代官方 Claude
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class ClaudeCodeConfig:
    """Claude Code 配置数据类"""
    
    # 核心配置
    always_thinking_enabled: bool = False
    include_co_authored_by: bool = False
    
    # 环境变量配置
    env: Dict[str, str] = None
    
    def __post_init__(self):
        if self.env is None:
            self.env = {}
    
    @classmethod
    def for_dashscope_qwen(
        cls,
        api_key: str,
        model: str = "qwen3.5-plus",
        base_url: str = "https://dashscope.aliyuncs.com/apps/anthropic"
    ) -> 'ClaudeCodeConfig':
        """创建阿里云 DashScope 通义千问配置
        
        Args:
            api_key: DashScope API Key
            model: 模型名称，默认 qwen3.5-plus
            base_url: 阿里云 Anthropic 兼容接口地址
        """
        return cls(
            always_thinking_enabled=False,
            include_co_authored_by=False,
            env={
                "ANTHROPIC_AUTH_TOKEN": api_key,
                "ANTHROPIC_BASE_URL": base_url,
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
                "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                "ANTHROPIC_MODEL": model,
                "ANTHROPIC_REASONING_MODEL": model,
            }
        )
    
    @classmethod
    def for_openrouter(
        cls,
        api_key: str,
        model: str = "anthropic/claude-3.5-sonnet"
    ) -> 'ClaudeCodeConfig':
        """创建 OpenRouter 配置
        
        Args:
            api_key: OpenRouter API Key
            model: 模型名称
        """
        return cls(
            always_thinking_enabled=False,
            include_co_authored_by=False,
            env={
                "ANTHROPIC_AUTH_TOKEN": api_key,
                "ANTHROPIC_BASE_URL": "https://openrouter.ai/api/v1",
                "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
                "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
                "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
                "ANTHROPIC_MODEL": model,
                "ANTHROPIC_REASONING_MODEL": model,
            }
        )
    
    @classmethod
    def from_file(cls, path: str) -> 'ClaudeCodeConfig':
        """从文件加载配置"""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        return cls(
            always_thinking_enabled=data.get('alwaysThinkingEnabled', False),
            include_co_authored_by=data.get('includeCoAuthoredBy', False),
            env=data.get('env', {})
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（符合 Claude Code 配置格式）"""
        return {
            "alwaysThinkingEnabled": self.always_thinking_enabled,
            "includeCoAuthoredBy": self.include_co_authored_by,
            "env": self.env
        }
    
    def save(self, path: str):
        """保存配置到文件"""
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)


class ClaudeCodeConfigurator:
    """Claude Code 配置管理器"""
    
    # Claude Code 配置目录
    CONFIG_DIR = Path.home() / '.claude-code'
    CONFIG_FILE = CONFIG_DIR / 'settings.json'
    
    # 内核特定的配置目录
    KERNEL_CONFIG_DIR = Path.home() / '.clawdboz' / 'claude-kernels'
    
    def __init__(self):
        self.KERNEL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    def create_dashscope_kernel(
        self,
        kernel_name: str,
        api_key: str,
        model: str = "qwen3.5-plus",
        **kwargs
    ) -> Path:
        """创建阿里云 DashScope 内核配置
        
        Args:
            kernel_name: 内核名称，如 "qwen35", "qwen-max"
            api_key: DashScope API Key
            model: 模型名称
            **kwargs: 其他配置参数
            
        Returns:
            配置文件路径
        """
        config = ClaudeCodeConfig.for_dashscope_qwen(api_key, model)
        
        # 添加额外环境变量
        for key, value in kwargs.items():
            if key.startswith('ANTHROPIC_') or key.startswith('DASHSCOPE_'):
                config.env[key] = value
        
        # 保存配置
        config_path = self.KERNEL_CONFIG_DIR / f'{kernel_name}.json'
        config.save(str(config_path))
        
        print(f"✅ 创建内核配置: {kernel_name}")
        print(f"   模型: {model}")
        print(f"   配置: {config_path}")
        
        return config_path
    
    def create_openrouter_kernel(
        self,
        kernel_name: str,
        api_key: str,
        model: str = "anthropic/claude-3.5-sonnet"
    ) -> Path:
        """创建 OpenRouter 内核配置"""
        config = ClaudeCodeConfig.for_openrouter(api_key, model)
        
        config_path = self.KERNEL_CONFIG_DIR / f'{kernel_name}.json'
        config.save(str(config_path))
        
        print(f"✅ 创建内核配置: {kernel_name}")
        print(f"   模型: {model}")
        print(f"   配置: {config_path}")
        
        return config_path
    
    def get_kernel_config(self, kernel_name: str) -> Optional[ClaudeCodeConfig]:
        """获取内核配置"""
        config_path = self.KERNEL_CONFIG_DIR / f'{kernel_name}.json'
        if config_path.exists():
            return ClaudeCodeConfig.from_file(str(config_path))
        return None
    
    def list_kernels(self) -> list:
        """列出所有自定义内核"""
        kernels = []
        for config_file in self.KERNEL_CONFIG_DIR.glob('*.json'):
            kernel_name = config_file.stem
            config = self.get_kernel_config(kernel_name)
            if config:
                kernels.append({
                    'name': kernel_name,
                    'model': config.env.get('ANTHROPIC_MODEL', 'unknown'),
                    'base_url': config.env.get('ANTHROPIC_BASE_URL', ''),
                    'path': str(config_file)
                })
        return kernels
    
    def apply_kernel_config(self, kernel_name: str) -> Dict[str, str]:
        """应用内核配置到环境变量
        
        返回需要设置的环境变量字典
        """
        config = self.get_kernel_config(kernel_name)
        if not config:
            raise ValueError(f"Kernel config not found: {kernel_name}")
        
        return config.env.copy()
    
    def generate_kernel_entry(
        self,
        kernel_name: str,
        display_name: str = None,
        description: str = None
    ) -> dict:
        """生成内核配置条目（用于 config.json）
        
        Returns:
            内核配置字典
        """
        config = self.get_kernel_config(kernel_name)
        if not config:
            raise ValueError(f"Kernel config not found: {kernel_name}")
        
        # 构建启动命令
        # 使用环境变量文件方式传递配置
        env_file = self.KERNEL_CONFIG_DIR / f'{kernel_name}.env'
        self._generate_env_file(kernel_name, env_file)
        
        return {
            "name": display_name or f"Claude Code ({kernel_name})",
            "type": "claude-code-acp",
            "command": "npx",
            "args": ["@zed-industries/claude-code-acp"],
            "env": config.env,
            "description": description or f"使用 {config.env.get('ANTHROPIC_MODEL', 'unknown')} 模型的 Claude Code"
        }
    
    def _generate_env_file(self, kernel_name: str, env_file: Path):
        """生成环境变量文件"""
        config = self.get_kernel_config(kernel_name)
        if not config:
            return
        
        lines = [f"{key}={value}" for key, value in config.env.items()]
        env_file.write_text('\n'.join(lines), encoding='utf-8')


def setup_dashscope_claude(
    api_key: str = None,
    model: str = "qwen3.5-plus",
    kernel_name: str = "qwen35"
) -> dict:
    """快速设置阿里云 DashScope Claude
    
    这是一个便捷函数，一键创建配置并返回内核配置条目
    
    Args:
        api_key: DashScope API Key，默认从环境变量读取
        model: 模型名称
        kernel_name: 内核名称
        
    Returns:
        可直接用于 config.json 的内核配置字典
    """
    api_key = api_key or os.environ.get('DASHSCOPE_API_KEY')
    if not api_key:
        raise ValueError("请提供 api_key 或设置 DASHSCOPE_API_KEY 环境变量")
    
    configurator = ClaudeCodeConfigurator()
    configurator.create_dashscope_kernel(kernel_name, api_key, model)
    
    return configurator.generate_kernel_entry(
        kernel_name,
        display_name=f"Claude Code ({model})",
        description=f"基于阿里云 DashScope 的 Claude Code，使用 {model} 模型"
    )


__all__ = [
    'ClaudeCodeConfig',
    'ClaudeCodeConfigurator',
    'setup_dashscope_claude'
]