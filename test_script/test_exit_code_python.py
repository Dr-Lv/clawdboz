#!/usr/bin/env python3
"""测试 Python 中捕获子进程退出码"""
import subprocess
import sys

print("=== Python 子进程退出码捕获测试 ===\n")

# 测试1: 成功的命令
print("测试1: 成功的命令 (echo hello)")
result = subprocess.run(["echo", "hello"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print(f"  退出码: {result.returncode} (期望: 0)")
print(f"  stdout: {result.stdout.decode().strip()}")
print(f"  ✓ 成功" if result.returncode == 0 else "  ✗ 失败")
print()

# 测试2: 失败的命令
print("测试2: 失败的命令 (ls /nonexistent)")
result = subprocess.run(["ls", "/nonexistent"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
print(f"  退出码: {result.returncode} (期望: 非0)")
print(f"  stderr: {result.stderr.decode().strip()}")
print(f"  ✓ 成功捕获错误" if result.returncode != 0 else "  ✗ 应该失败")
print()

# 测试3: 使用 check=True 抛出异常
print("测试3: 使用 check=True 抛出异常")
try:
    result = subprocess.run(["false"], check=True)
except subprocess.CalledProcessError as e:
    print(f"  捕获到 CalledProcessError")
    print(f"  退出码: {e.returncode}")
    print(f"  命令: {e.cmd}")
    print("  ✓ 成功捕获异常")
print()

# 测试4: 捕获自定义退出码
print("测试4: 捕获自定义退出码 (exit 42)")
result = subprocess.run(["bash", "-c", "exit 42"])
print(f"  退出码: {result.returncode} (期望: 42)")
print(f"  ✓ 成功" if result.returncode == 42 else "  ✗ 失败")
print()

# 测试5: 管道命令退出码
print("测试5: 管道命令退出码")
result = subprocess.run(
    "ls /nonexistent 2>/dev/null | grep xxx",
    shell=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
print(f"  退出码: {result.returncode}")
print("  注意: shell=True 时返回管道最后一个命令的退出码")
print()

# 测试6: 使用 Popen 获取退出码
print("测试6: 使用 Popen 获取退出码")
process = subprocess.Popen(
    ["sleep", "0.1"],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)
stdout, stderr = process.communicate()
print(f"  进程退出码: {process.returncode}")
print("  ✓ 成功" if process.returncode == 0 else "  ✗ 失败")
print()

# 测试7: 测试 call() 函数 (旧方式)
print("测试7: 使用 call() 函数 (旧方式)")
with open('/dev/null', 'w') as devnull:
    exit_code = subprocess.call(["echo", "test"], stdout=devnull)
print(f"  call() 返回的退出码: {exit_code}")
print()

# 测试8: 检查特定退出码并处理
print("测试8: 根据退出码进行不同处理")
result = subprocess.run(["grep", "nonexistent", "/etc/passwd"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
if result.returncode == 0:
    print("  找到匹配")
elif result.returncode == 1:
    print("  退出码 1: 未找到匹配 (这是正常情况)")
else:
    print(f"  退出码 {result.returncode}: 发生错误")
    print(f"  stderr: {result.stderr.decode()}")
print()

print("=== Python 退出码捕获测试完成 ===")
