#!/usr/bin/env python3
"""测试 Shell 工具失败原因"""
import subprocess
import json
import threading
import time

class ACPClient:
    def __init__(self):
        self.process = None
        self.response_map = {}
        self.notifications = []
        self._lock = threading.Lock()
        self._reader_thread = None
        self._init()

    def _log(self, msg):
        print(f"[ACP] {msg}", flush=True)

    def _init(self):
        # 使用 stderr 捕获错误信息
        self.process = subprocess.Popen(
            ['kimi', 'acp'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,  # 捕获 stderr
            text=True,
            bufsize=1
        )
        
        # 启动 stderr 读取线程
        threading.Thread(target=self._read_stderr, daemon=True).start()
        
        self._reader_thread = threading.Thread(target=self._read, daemon=True)
        self._reader_thread.start()
        
        result, error = self.call('initialize', {'protocolVersion': 1})
        self._log(f"初始化: {error or 'OK'}")
        
        result, error = self.call('session/new', {
            'cwd': '/Users/suntom/work/test/larkbot',
            'mcpServers': []
        })
        if error:
            raise Exception(f"会话创建失败: {error}")
        self.session_id = result['sessionId']
        self._log(f"会话: {self.session_id}")

    def _read_stderr(self):
        """读取 stderr 查看错误信息"""
        for line in self.process.stderr:
            line = line.strip()
            if line:
                self._log(f"STDERR: {line}")

    def _read(self):
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                msg_id = data.get('id')
                method = data.get('method')

                if method == 'session/request_permission' and 'id' in data:
                    self._log(f"权限请求: {data['id']}")
                    resp = {
                        "jsonrpc": "2.0",
                        "id": data['id'],
                        "result": {"outcome": {"type": "allowed", "optionId": "approve"}}
                    }
                    self.process.stdin.write(json.dumps(resp) + '\n')
                    self.process.stdin.flush()
                    self._log("已批准")
                    continue

                if method and msg_id is None:
                    with self._lock:
                        self.notifications.append(data)
                    # 打印工具调用详情
                    if method == 'session/update':
                        update = data.get('params', {}).get('update', {})
                        update_type = update.get('sessionUpdate')
                        if update_type == 'tool_call':
                            self._log(f"工具调用开始: {update.get('title', 'N/A')}")
                            self._log(f"工具内容: {update.get('content', [])}")
                        elif update_type == 'tool_call_update':
                            status = update.get('status', 'N/A')
                            content = update.get('content', [])
                            self._log(f"工具状态更新: {status}")
                            if content:
                                self._log(f"工具结果: {str(content)[:300]}")

                if msg_id is not None and method is None:
                    with self._lock:
                        self.response_map[msg_id] = data
            except Exception as e:
                pass

    def call(self, method, params, timeout=30):
        import uuid
        msg_id = str(uuid.uuid4())
        req = {"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params}
        self.process.stdin.write(json.dumps(req) + '\n')
        self.process.stdin.flush()
        
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                if msg_id in self.response_map:
                    r = self.response_map.pop(msg_id)
                    return r.get('result'), r.get('error')
            time.sleep(0.05)
        return None, "超时"

    def chat(self, message, timeout=60):
        with self._lock:
            self.notifications.clear()
        
        result, error = self.call('session/prompt', {
            'sessionId': self.session_id,
            'prompt': [{'type': 'text', 'text': message}]
        }, timeout=10)
        
        self._log(f"prompt 结果: {result is not None}, 错误: {error}")
        
        start_time = time.time()
        last_chunk_time = start_time
        
        while time.time() - start_time < timeout:
            time.sleep(0.1)
            
            with self._lock:
                for n in list(self.notifications):
                    params = n.get('params', {})
                    update = params.get('update', {})
                    update_type = update.get('sessionUpdate')
                    
                    if update_type == 'tool_call_update':
                        status = update.get('status', '')
                        content = update.get('content', [])
                        self._log(f"[工具] 状态: {status}")
                        if content:
                            self._log(f"[工具] 内容: {str(content)[:500]}")
                    
                    if result and isinstance(result, dict):
                        stop_reason = result.get('stopReason')
                        if stop_reason and time.time() - last_chunk_time > 2:
                            self._log(f"完成: {stop_reason}")
                            return

    def close(self):
        if self.process:
            self.process.terminate()
            self.process.wait()


if __name__ == "__main__":
    client = None
    try:
        client = ACPClient()
        client.chat('ls', timeout=30)
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        if client:
            client.close()
