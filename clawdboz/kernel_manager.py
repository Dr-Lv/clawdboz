#!/usr/bin/env python3
"""
内核管理模块 - 优雅的多内核支持
支持 Kimi Code、Claude Code 等多种 ACP 兼容内核
"""
import json
import os
import subprocess
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from enum import Enum

from .config import CONFIG, get_absolute_path, PROJECT_ROOT


class KernelType(Enum):
    """支持的内核类型"""
    KIMI_CODE = "kimi-code"
    CLAUDE_CODE = "claude-code-acp"
    CLAUDE_CODE_LEGACY = "claude-code"


@dataclass
class KernelConfig:
    """内核配置数据类"""
    name: str
    type: KernelType
    command: str
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    description: str = ""
    
    @classmethod
    def from_dict(cls, data: dict) -> 'KernelConfig':
        """从字典创建配置"""
        return cls(
            name=data.get('name', 'Unknown'),
            type=KernelType(data.get('type', 'kimi-code')),
            command=data.get('command', 'kimi'),
            args=data.get('args', []),
            env=data.get('env', {}),
            description=data.get('description', '')
        )


@dataclass
class KernelInfo:
    """内核运行时信息"""
    name: str
    type: KernelType
    status: str  # 'idle', 'running', 'error'
    pid: Optional[int] = None
    session_id: Optional[str] = None
    start_time: Optional[float] = None
    error_message: Optional[str] = None


class Kernel(ABC):
    """内核抽象基类"""
    
    def __init__(self, config: KernelConfig, bot_ref=None):
        self.config = config
        self.bot_ref = bot_ref
        self.process: Optional[subprocess.Popen] = None
        self.session_id: Optional[str] = None
        self._lock = threading.Lock()
        self._response_map: Dict[str, Any] = {}
        self._notifications: List[dict] = []
        self._log_file = None
        self._init_logging()
    
    def _init_logging(self):
        """初始化日志"""
        log_dir = os.path.join(PROJECT_ROOT, 'logs', 'kernels')
        os.makedirs(log_dir, exist_ok=True)
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        log_file = os.path.join(log_dir, f'{self.config.type.value}_{timestamp}.log')
        self._log_file = open(log_file, 'w', encoding='utf-8')
        self._log(f"Kernel initialized: {self.config.name} ({self.config.type.value})")
    
    def _log(self, message: str):
        """记录日志"""
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_line = f"[{timestamp}] {message}\n"
        if self._log_file:
            self._log_file.write(log_line)
            self._log_file.flush()
    
    @property
    def is_running(self) -> bool:
        """检查内核是否运行中"""
        return self.process is not None and self.process.poll() is None
    
    def start(self) -> bool:
        """启动内核"""
        if self.is_running:
            self._log("Kernel already running")
            return True
        
        try:
            # 准备环境变量
            env = os.environ.copy()
            env.update(self.config.env)
            
            # 替换环境变量占位符
            for key, value in env.items():
                if value.startswith('${') and value.endswith('}'):
                    env_var = value[2:-1]
                    env[key] = os.environ.get(env_var, '')
            
            workplace = get_absolute_path(
                CONFIG.get('paths', {}).get('workplace', 'WORKPLACE')
            )
            
            self._log(f"Starting: {self.config.command} {' '.join(self.config.args)}")
            self._log(f"Working directory: {workplace}")
            
            self.process = subprocess.Popen(
                [self.config.command] + self.config.args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                env=env,
                cwd=workplace
            )
            
            # 启动读取线程
            threading.Thread(target=self._read_stdout, daemon=True).start()
            threading.Thread(target=self._read_stderr, daemon=True).start()
            
            self._log(f"Kernel started with PID: {self.process.pid}")
            
            # 等待内核就绪
            time.sleep(0.5)
            return self.is_running
            
        except Exception as e:
            self._log(f"Failed to start kernel: {e}")
            return False
    
    def stop(self):
        """停止内核"""
        if not self.is_running:
            return
        
        self._log("Stopping kernel...")
        try:
            self.process.terminate()
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._log("Force killing kernel")
            self.process.kill()
        except Exception as e:
            self._log(f"Error stopping kernel: {e}")
        finally:
            self.process = None
            if self._log_file:
                self._log_file.close()
                self._log_file = None
    
    def _read_stdout(self):
        """读取标准输出"""
        while self.is_running:
            try:
                line = self.process.stdout.readline()
                if line:
                    self._handle_message(line.strip())
            except Exception as e:
                self._log(f"Error reading stdout: {e}")
                break
    
    def _read_stderr(self):
        """读取标准错误"""
        while self.is_running:
            try:
                line = self.process.stderr.readline()
                if line:
                    self._log(f"[STDERR] {line.strip()}")
            except Exception as e:
                self._log(f"Error reading stderr: {e}")
                break
    
    def _handle_message(self, line: str):
        """处理 ACP 消息"""
        try:
            message = json.loads(line)
            msg_type = message.get('type')
            
            if msg_type == 'response':
                req_id = message.get('id')
                if req_id in self._response_map:
                    self._response_map[req_id] = message
            elif msg_type == 'notification':
                self._notifications.append(message)
                self._handle_notification(message)
        except json.JSONDecodeError:
            self._log(f"Non-JSON output: {line[:200]}")
    
    def _handle_notification(self, message: dict):
        """处理通知消息"""
        method = message.get('method', '')
        params = message.get('params', {})
        
        # 处理工具调用请求
        if method == 'tools/call':
            self._handle_tool_call(params)
    
    def _handle_tool_call(self, params: dict):
        """处理工具调用（转发给 bot）"""
        if self.bot_ref and hasattr(self.bot_ref, 'handle_tool_call'):
            try:
                result = self.bot_ref.handle_tool_call(params)
                # 发送响应
                self._send_response(params.get('id'), result)
            except Exception as e:
                self._send_error(params.get('id'), str(e))
    
    def _send_response(self, req_id: str, result: Any):
        """发送响应"""
        self._send_message({
            'type': 'response',
            'id': req_id,
            'result': result
        })
    
    def _send_error(self, req_id: str, error: str):
        """发送错误响应"""
        self._send_message({
            'type': 'response',
            'id': req_id,
            'error': error
        })
    
    def _send_message(self, message: dict):
        """发送 ACP 消息"""
        if self.process and self.process.stdin:
            try:
                line = json.dumps(message) + '\n'
                self.process.stdin.write(line)
                self.process.stdin.flush()
                self._log(f"Sent: {line[:200]}")
            except Exception as e:
                self._log(f"Error sending message: {e}")
    
    def call_method(self, method: str, params: dict, timeout: int = 60) -> tuple:
        """调用 ACP 方法
        
        Returns:
            (result, error) 元组
        """
        if not self.is_running:
            return None, "Kernel not running"
        
        req_id = str(uuid.uuid4())
        request = {
            'type': 'request',
            'id': req_id,
            'method': method,
            'params': params
        }
        
        with self._lock:
            self._response_map[req_id] = None
        
        try:
            self._send_message(request)
            
            # 等待响应
            start_time = time.time()
            while time.time() - start_time < timeout:
                with self._lock:
                    response = self._response_map.get(req_id)
                    if response is not None:
                        result = response.get('result')
                        error = response.get('error')
                        return result, error
                time.sleep(0.05)
            
            return None, "Request timeout"
            
        finally:
            with self._lock:
                self._response_map.pop(req_id, None)
    
    def create_session(self, params: dict = None) -> Optional[str]:
        """创建 ACP 会话"""
        params = params or {}
        
        # 添加 MCP 配置
        mcp_config = self._get_mcp_config()
        if mcp_config:
            params['mcpServers'] = mcp_config
        
        result, error = self.call_method('session/new', params)
        if error:
            self._log(f"Failed to create session: {error}")
            return None
        
        self.session_id = result.get('sessionId')
        self._log(f"Session created: {self.session_id}")
        return self.session_id
    
    def _get_mcp_config(self) -> dict:
        """获取 MCP 配置"""
        # 从配置文件读取 MCP 配置
        mcp_path = os.path.join(PROJECT_ROOT, 'mcp.json')
        if os.path.exists(mcp_path):
            try:
                with open(mcp_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                self._log(f"Error loading MCP config: {e}")
        return {}
    
    def get_info(self) -> KernelInfo:
        """获取内核信息"""
        return KernelInfo(
            name=self.config.name,
            type=self.config.type,
            status='running' if self.is_running else 'idle',
            pid=self.process.pid if self.is_running else None,
            session_id=self.session_id,
            start_time=None
        )


class KernelRegistry:
    """内核注册表 - 管理所有可用内核"""
    
    # 内置内核定义
    BUILTIN_KERNELS = {
        'kimi': KernelConfig(
            name='Kimi Code',
            type=KernelType.KIMI_CODE,
            command='kimi',
            args=['--mcp', 'stdio'],
            description='Moonshot Kimi Code CLI - 优秀的代码助手'
        ),
        'claude': KernelConfig(
            name='Claude Code',
            type=KernelType.CLAUDE_CODE,
            command='npx',
            args=['@zed-industries/claude-code-acp'],
            env={'ACP_PERMISSION_MODE': 'acceptEdits'},
            description='Anthropic Claude Code - 强大的 AI 编程助手'
        ),
        'claude-legacy': KernelConfig(
            name='Claude Code (Legacy)',
            type=KernelType.CLAUDE_CODE_LEGACY,
            command='claude',
            args=['--mcp', 'stdio'],
            description='Claude Code CLI 原生模式'
        )
    }
    
    def __init__(self):
        self._kernels: Dict[str, Kernel] = {}
        self._configs: Dict[str, KernelConfig] = {}
        self._load_configs()
    
    def _load_configs(self):
        """从配置加载内核定义"""
        kernel_configs = CONFIG.get('kernels', {}).get('available', {})
        
        for name, data in kernel_configs.items():
            try:
                self._configs[name] = KernelConfig.from_dict(data)
            except Exception as e:
                print(f"Warning: Failed to load kernel config '{name}': {e}")
        
        # 如果没有配置，使用内置定义
        if not self._configs:
            self._configs = self.BUILTIN_KERNELS.copy()
    
    def get_config(self, name: str) -> Optional[KernelConfig]:
        """获取内核配置"""
        return self._configs.get(name)
    
    def list_kernels(self) -> List[str]:
        """列出所有可用内核名称"""
        return list(self._configs.keys())
    
    def get_kernel_info(self, name: str) -> Optional[dict]:
        """获取内核信息（用于展示）"""
        config = self._configs.get(name)
        if not config:
            return None
        return {
            'name': name,
            'display_name': config.name,
            'type': config.type.value,
            'description': config.description,
            'command': f"{config.command} {' '.join(config.args)}"
        }
    
    def create_kernel(self, name: str, bot_ref=None) -> Optional[Kernel]:
        """创建内核实例"""
        config = self._configs.get(name)
        if not config:
            return None
        
        return Kernel(config, bot_ref)


class KernelManager:
    """内核管理器 - 高级内核管理"""
    
    def __init__(self, bot_ref=None):
        self.bot_ref = bot_ref
        self.registry = KernelRegistry()
        self._active_kernels: Dict[str, Kernel] = {}
        self._current_kernel: Optional[str] = None
        self._default_kernel = CONFIG.get('kernels', {}).get('default', 'kimi')
    
    @property
    def current_kernel_name(self) -> Optional[str]:
        """当前内核名称"""
        return self._current_kernel
    
    @property
    def current_kernel(self) -> Optional[Kernel]:
        """获取当前激活的内核"""
        if not self._current_kernel:
            # 自动切换到默认内核
            self.switch_kernel(self._default_kernel)
        return self._active_kernels.get(self._current_kernel)
    
    def list_available(self) -> List[dict]:
        """列出所有可用内核信息"""
        return [
            self.registry.get_kernel_info(name)
            for name in self.registry.list_kernels()
        ]
    
    def switch_kernel(self, name: str) -> bool:
        """切换到指定内核
        
        Args:
            name: 内核名称
            
        Returns:
            是否切换成功
        """
        if name not in self.registry.list_kernels():
            print(f"Error: Unknown kernel '{name}'")
            return False
        
        # 如果已经是当前内核，无需切换
        if self._current_kernel == name:
            return True
        
        # 停止当前内核
        if self._current_kernel and self._current_kernel in self._active_kernels:
            old_kernel = self._active_kernels[self._current_kernel]
            old_kernel.stop()
            print(f"Stopped kernel: {self._current_kernel}")
        
        # 启动或获取新内核
        if name not in self._active_kernels:
            kernel = self.registry.create_kernel(name, self.bot_ref)
            if not kernel:
                return False
            
            if not kernel.start():
                return False
            
            self._active_kernels[name] = kernel
            print(f"Started kernel: {name}")
        
        self._current_kernel = name
        print(f"Switched to kernel: {name}")
        return True
    
    def get_kernel(self, name: str) -> Optional[Kernel]:
        """获取指定内核实例（不切换）"""
        if name not in self._active_kernels:
            kernel = self.registry.create_kernel(name, self.bot_ref)
            if kernel and kernel.start():
                self._active_kernels[name] = kernel
        return self._active_kernels.get(name)
    
    def stop_all(self):
        """停止所有内核"""
        for name, kernel in self._active_kernels.items():
            print(f"Stopping kernel: {name}")
            kernel.stop()
        self._active_kernels.clear()
        self._current_kernel = None
    
    def get_status(self) -> dict:
        """获取管理器状态"""
        return {
            'current': self._current_kernel,
            'default': self._default_kernel,
            'available': self.list_available(),
            'active': [
                {
                    'name': name,
                    'info': kernel.get_info().__dict__
                }
                for name, kernel in self._active_kernels.items()
            ]
        }


# 便捷函数
def get_default_kernel_manager(bot_ref=None) -> KernelManager:
    """获取默认内核管理器实例"""
    return KernelManager(bot_ref)


__all__ = [
    'Kernel',
    'KernelConfig',
    'KernelInfo',
    'KernelManager',
    'KernelRegistry',
    'KernelType',
    'get_default_kernel_manager'
]