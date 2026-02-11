#!/usr/bin/env python3
"""直接测试 ACP，不通过飞书"""
import subprocess
import json
import threading
import time
import sys

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
        self.process = subprocess.Popen(
            ['kimi', 'acp'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )
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

    def _read(self):
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                msg_id = data.get('id')
                method = data.get('method')

                # 自动批准权限请求
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

    def chat(self, message, on_chunk=None, timeout=60):
        with self._lock:
            self.notifications.clear()
        
        result, error = self.call('session/prompt', {
            'sessionId': self.session_id,
            'prompt': [{'type': 'text', 'text': message}]
        }, timeout=10)
        
        if error and error != "超时":
            return f"错误: {error}"

        self._log(f"prompt 结果: {result is not None}, 错误: {error}")
        
        start_time = time.time()
        last_chunk_time = start_time
        collected = []
        processed = set()
        
        while time.time() - start_time < timeout:
            time.sleep(0.05)
            callback_data = None
            
            with self._lock:
                for n in self.notifications:
                    notif_key = str(n)
                    if notif_key in processed:
                        continue
                    processed.add(notif_key)
                    
                    params = n.get('params', {})
                    update = params.get('update', {})
                    update_type = update.get('sessionUpdate')
                    
                    if update_type == 'agent_message_chunk':
                        text = update.get('content', {}).get('text', '')
                        if text:
                            collected.append(text)
                            last_chunk_time = time.time()
                            self._log(f"收到消息 chunk: {len(text)} 字符")
                    elif update_type == 'agent_thought_chunk':
                        text = update.get('content', {}).get('text', '')
                        if text:
                            collected.append(text)
                            last_chunk_time = time.time()
                            self._log(f"收到思考 chunk: {len(text)} 字符")
                    elif update_type == 'tool_call':
                        self._log(f"工具调用: {update.get('title', 'N/A')}")
                    elif update_type == 'tool_call_update':
                        self._log(f"工具状态: {update.get('status', 'N/A')}")
                
                if on_chunk and collected:
                    callback_data = ''.join(collected)
                
                if result and isinstance(result, dict):
                    stop_reason = result.get('stopReason')
                    if stop_reason and time.time() - last_chunk_time > 2:
                        self._log(f"完成: {stop_reason}")
                        break
            
            if callback_data and on_chunk:
                on_chunk(callback_data)
            
            if time.time() - last_chunk_time > 5 and collected:
                self._log("5秒无新内容，退出")
                break
        
        return ''.join(collected)

    def close(self):
        if self.process:
            self.process.terminate()
            self.process.wait()


def main():
    client = None
    try:
        print("="*60)
        print("测试 ACP")
        print("="*60)
        
        client = ACPClient()
        
        msg = sys.argv[1] if len(sys.argv) > 1 else "ls"
        print(f"\n发送: {msg}\n")
        
        def on_chunk(text):
            print(f"\r[流式] 长度: {len(text):4d}", end='', flush=True)
        
        result = client.chat(msg, on_chunk=on_chunk, timeout=30)
        
        print(f"\n\n结果 ({len(result)} 字符):")
        print(result[:500])
        
    except KeyboardInterrupt:
        print("\n中断")
    except Exception as e:
        import traceback
        traceback.print_exc()
    finally:
        if client:
            client.close()
            print("\n已关闭")

if __name__ == "__main__":
    main()
