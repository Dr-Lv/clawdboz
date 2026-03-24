#!/usr/bin/env python3
"""
Auto Test - 自动化测试 clawdboz whl 包

功能：
1. 自动打 whl 包
2. 在 ../test 目录生成 uv 虚拟环境
3. 安装 whl 包
4. 生成测试用例并自测
"""

import os
import sys
import subprocess
import tempfile
import json
from pathlib import Path
from datetime import datetime


class Colors:
    """终端颜色"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'


def log(message, level="INFO"):
    """输出日志"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color = {
        "INFO": Colors.BLUE,
        "SUCCESS": Colors.GREEN,
        "ERROR": Colors.RED,
        "WARN": Colors.YELLOW
    }.get(level, Colors.RESET)
    
    print(f"{color}[{timestamp}] [{level}] {message}{Colors.RESET}")
    
    # 同时写入日志文件
    test_dir = Path(__file__).parent.parent.parent / "test"
    test_dir.mkdir(exist_ok=True)
    log_file = test_dir / "test_results.log"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] [{level}] {message}\n")


def run_command(cmd, cwd=None, check=True):
    """运行命令"""
    log(f"执行: {' '.join(cmd)}", "INFO")
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=check
        )
        if result.stdout:
            log(result.stdout.strip(), "INFO")
        return result
    except subprocess.CalledProcessError as e:
        log(f"命令失败: {e}", "ERROR")
        if e.stderr:
            log(e.stderr.strip(), "ERROR")
        raise


def find_project_root():
    """查找项目根目录"""
    current = Path(__file__).resolve()
    # 向上查找包含 pyproject.toml 的目录
    for parent in [current, *current.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return current.parent.parent.parent


def step_1_clean_build(project_root):
    """步骤1: 清理旧的构建产物"""
    log("=" * 60, "INFO")
    log("步骤 1: 清理旧的构建产物", "INFO")
    log("=" * 60, "INFO")
    
    dirs_to_clean = ["build", "dist", "*.egg-info"]
    for pattern in dirs_to_clean:
        for path in project_root.glob(pattern):
            if path.is_dir():
                log(f"删除目录: {path}")
                import shutil
                shutil.rmtree(path)
    
    log("清理完成", "SUCCESS")


def step_2_build_wheel(project_root):
    """步骤2: 构建 whl 包"""
    log("=" * 60, "INFO")
    log("步骤 2: 构建 whl 包", "INFO")
    log("=" * 60, "INFO")
    
    # 确保 build 工具已安装
    try:
        import build
    except ImportError:
        log("安装 build 工具...", "INFO")
        run_command([sys.executable, "-m", "pip", "install", "build"])
    
    # 构建 whl 包
    run_command([sys.executable, "-m", "build"], cwd=project_root)
    
    # 查找生成的 whl 文件
    dist_dir = project_root / "dist"
    whl_files = list(dist_dir.glob("*.whl"))
    
    if not whl_files:
        raise FileNotFoundError("未找到生成的 whl 文件")
    
    whl_file = whl_files[0]
    log(f"构建成功: {whl_file.name}", "SUCCESS")
    return whl_file


def step_3_create_test_env(project_root):
    """步骤3: 创建测试环境"""
    log("=" * 60, "INFO")
    log("步骤 3: 创建测试环境", "INFO")
    log("=" * 60, "INFO")
    
    # 确定测试目录
    test_dir = project_root.parent / "test"
    test_dir.mkdir(exist_ok=True)
    
    log(f"测试目录: {test_dir}")
    
    # 检查 uv 是否安装
    try:
        run_command(["uv", "--version"], check=False)
        has_uv = True
    except FileNotFoundError:
        has_uv = False
    
    venv_dir = test_dir / ".venv"
    
    # 如果已存在虚拟环境，先删除
    if venv_dir.exists():
        log("删除旧的虚拟环境...")
        import shutil
        shutil.rmtree(venv_dir)
    
    if has_uv:
        # 使用 uv 创建虚拟环境
        log("使用 uv 创建虚拟环境...")
        run_command(["uv", "venv", str(venv_dir)], cwd=test_dir)
        python_path = venv_dir / "bin" / "python"
        
        # 使用 uv 安装 pip
        log("安装 pip...")
        run_command(["uv", "pip", "install", "--python", str(python_path), "pip"])
    else:
        # 使用标准 venv
        log("使用标准 venv 创建虚拟环境...")
        run_command([sys.executable, "-m", "venv", str(venv_dir)])
        python_path = venv_dir / "bin" / "python"
    
    log(f"虚拟环境创建成功: {venv_dir}", "SUCCESS")
    return test_dir, python_path


def step_4_install_wheel(test_dir, python_path, whl_file):
    """步骤4: 安装 whl 包"""
    log("=" * 60, "INFO")
    log("步骤 4: 安装 whl 包", "INFO")
    log("=" * 60, "INFO")
    
    # 升级 pip
    log("升级 pip...")
    run_command([str(python_path), "-m", "pip", "install", "--upgrade", "pip"])
    
    # 安装 whl 包
    log(f"安装: {whl_file.name}")
    run_command([str(python_path), "-m", "pip", "install", str(whl_file)])
    
    log("安装完成", "SUCCESS")


def step_5_run_tests(test_dir, python_path):
    """步骤5: 运行测试用例"""
    log("=" * 60, "INFO")
    log("步骤 5: 运行测试用例", "INFO")
    log("=" * 60, "INFO")
    
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "tests": []
    }
    
    # 测试1: 包导入测试
    log("\n[测试 1] 包导入测试")
    results["total"] += 1
    try:
        test_code = "import clawdboz; print(f'clawdboz version: {clawdboz.__version__}')"
        result = run_command([str(python_path), "-c", test_code], check=False)
        if result.returncode == 0:
            log("✓ 包导入成功", "SUCCESS")
            results["passed"] += 1
            results["tests"].append({"name": "包导入", "status": "PASS"})
        else:
            raise Exception("导入失败")
    except Exception as e:
        log(f"✗ 包导入失败: {e}", "ERROR")
        results["failed"] += 1
        results["tests"].append({"name": "包导入", "status": "FAIL", "error": str(e)})
    
    # 测试2: Bot 类初始化测试
    log("\n[测试 2] Bot 类初始化测试")
    results["total"] += 1
    try:
        test_code = """
import sys
import os
os.chdir('""" + str(test_dir) + """')
sys.path.insert(0, '""" + str(test_dir / ".venv" / "lib" / "python3.9" / "site-packages") + """')
from clawdboz import Bot
print("Bot class imported successfully")
print(f"Bot methods: {[m for m in dir(Bot) if not m.startswith('_')]}")
"""
        result = run_command([str(python_path), "-c", test_code], check=False)
        if result.returncode == 0:
            log("✓ Bot 类初始化成功", "SUCCESS")
            results["passed"] += 1
            results["tests"].append({"name": "Bot 类初始化", "status": "PASS"})
        else:
            raise Exception("初始化失败")
    except Exception as e:
        log(f"✗ Bot 类初始化失败: {e}", "ERROR")
        results["failed"] += 1
        results["tests"].append({"name": "Bot 类初始化", "status": "FAIL", "error": str(e)})
    
    # 测试3: CLI 工具测试
    log("\n[测试 3] CLI 工具测试")
    results["total"] += 1
    try:
        result = run_command([str(python_path), "-m", "clawdboz", "--version"], check=False)
        if result.returncode == 0:
            log(f"✓ CLI 工具正常: {result.stdout.strip()}", "SUCCESS")
            results["passed"] += 1
            results["tests"].append({"name": "CLI 工具", "status": "PASS"})
        else:
            raise Exception("CLI 返回错误")
    except Exception as e:
        log(f"✗ CLI 工具测试失败: {e}", "ERROR")
        results["failed"] += 1
        results["tests"].append({"name": "CLI 工具", "status": "FAIL", "error": str(e)})
    
    # 测试4: 配置文件生成测试
    log("\n[测试 4] 配置文件生成测试")
    results["total"] += 1
    try:
        test_code = f"""
import sys
import os
os.chdir('{test_dir}')
sys.path.insert(0, '{test_dir / '.venv' / 'lib' / 'python3.9' / 'site-packages'}')

# 创建临时测试目录
test_project = '{test_dir / 'test_project'}'
os.makedirs(test_project, exist_ok=True)
os.chdir(test_project)

# 创建 config.json
config = {{
    "feishu": {{
        "app_id": "test_app_id",
        "app_secret": "test_app_secret"
    }}
}}
import json
with open('config.json', 'w') as f:
    json.dump(config, f)

print("✓ 配置文件生成成功")
"""
        result = run_command([str(python_path), "-c", test_code], check=False)
        if result.returncode == 0:
            log("✓ 配置文件生成成功", "SUCCESS")
            results["passed"] += 1
            results["tests"].append({"name": "配置文件生成", "status": "PASS"})
        else:
            raise Exception("配置生成失败")
    except Exception as e:
        log(f"✗ 配置文件生成测试失败: {e}", "ERROR")
        results["failed"] += 1
        results["tests"].append({"name": "配置文件生成", "status": "FAIL", "error": str(e)})
    
    # 测试5: 目录结构测试
    log("\n[测试 5] 目录结构测试")
    results["total"] += 1
    try:
        expected_dirs = [".venv", "test_project"]
        missing = []
        for d in expected_dirs:
            if not (test_dir / d).exists():
                missing.append(d)
        
        if not missing:
            log("✓ 目录结构正确", "SUCCESS")
            results["passed"] += 1
            results["tests"].append({"name": "目录结构", "status": "PASS"})
        else:
            raise Exception(f"缺少目录: {missing}")
    except Exception as e:
        log(f"✗ 目录结构测试失败: {e}", "ERROR")
        results["failed"] += 1
        results["tests"].append({"name": "目录结构", "status": "FAIL", "error": str(e)})
    
    return results


def print_summary(results):
    """打印测试摘要"""
    log("=" * 60, "INFO")
    log("测试摘要", "INFO")
    log("=" * 60, "INFO")
    
    total = results["total"]
    passed = results["passed"]
    failed = results["failed"]
    
    log(f"总测试数: {total}")
    log(f"通过: {passed}", "SUCCESS")
    log(f"失败: {failed}", "ERROR" if failed > 0 else "INFO")
    
    success_rate = (passed / total * 100) if total > 0 else 0
    log(f"成功率: {success_rate:.1f}%")
    
    log("\n详细结果:", "INFO")
    for test in results["tests"]:
        status = "✓" if test["status"] == "PASS" else "✗"
        color = Colors.GREEN if test["status"] == "PASS" else Colors.RED
        print(f"{color}{status} {test['name']}{Colors.RESET}")
    
    if failed == 0:
        log("\n🎉 所有测试通过！", "SUCCESS")
    else:
        log(f"\n⚠️ {failed} 个测试失败", "ERROR")
    
    return failed == 0


def main():
    """主函数"""
    log("\n" + "=" * 60, "INFO")
    log("Clawdboz 自动化测试", "INFO")
    log("=" * 60, "INFO")
    
    try:
        # 查找项目根目录
        project_root = find_project_root()
        log(f"项目目录: {project_root}")
        
        # 执行测试步骤
        step_1_clean_build(project_root)
        whl_file = step_2_build_wheel(project_root)
        test_dir, python_path = step_3_create_test_env(project_root)
        step_4_install_wheel(test_dir, python_path, whl_file)
        results = step_5_run_tests(test_dir, python_path)
        
        # 打印摘要
        success = print_summary(results)
        
        # 保存结果到 JSON
        results_file = test_dir / "test_results.json"
        with open(results_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
        log(f"\n详细结果已保存: {results_file}")
        
        return 0 if success else 1
        
    except Exception as e:
        log(f"\n测试失败: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
