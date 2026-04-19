#!/usr/bin/env python3
"""
版本号同步脚本

用法:
    python scripts/bump_version.py 3.5.0

这个脚本会同步版本号到以下文件:
    - clawdboz/VERSION
    - pyproject.toml
    - README.md
    - clawdboz/templates/.bots.md
"""

import re
import sys
from pathlib import Path


def update_version_file(version: str):
    """更新 VERSION 文件"""
    version_file = Path('clawdboz/VERSION')
    version_file.write_text(f"{version}\n")
    print(f"[OK] Updated {version_file}: {version}")


def update_pyproject_toml(version: str):
    """更新 pyproject.toml"""
    pyproject = Path('pyproject.toml')
    content = pyproject.read_text()
    
    # 替换 version = "x.x.x"
    new_content = re.sub(
        r'^version = "[^"]+"',
        f'version = "{version}"',
        content,
        flags=re.MULTILINE
    )
    
    pyproject.write_text(new_content)
    print(f"[OK] Updated {pyproject}: {version}")


def update_readme_md(version: str):
    """更新 README.md"""
    readme = Path('README.md')
    content = readme.read_text()
    
    # 替换 version badge
    new_content = re.sub(
        r'version-\d+\.\d+\.\d+-blue',
        f'version-{version}-blue',
        content
    )
    
    readme.write_text(new_content)
    print(f"[OK] Updated {readme}: {version}")


def update_bots_md_template(version: str):
    """更新 .bots.md 模板"""
    bots_md = Path('clawdboz/templates/.bots.md')
    content = bots_md.read_text()
    
    # 替换版本号 vX.X.X
    new_content = re.sub(
        r'v\d+\.\d+\.\d+',
        f'v{version}',
        content
    )
    
    bots_md.write_text(new_content)
    print(f"[OK] Updated {bots_md}: {version}")


def main():
    if len(sys.argv) != 2:
        print("Usage: python scripts/bump_version.py <version>")
        print("Example: python scripts/bump_version.py 3.5.0")
        sys.exit(1)
    
    version = sys.argv[1]
    
    # 验证版本号格式
    if not re.match(r'^\d+\.\d+\.\d+$', version):
        print(f"[ERROR] Invalid version format: {version}")
        print("Version should be in format: x.x.x (e.g., 3.5.0)")
        sys.exit(1)
    
    print(f"Bumping version to: {version}")
    print()
    
    update_version_file(version)
    update_pyproject_toml(version)
    update_readme_md(version)
    update_bots_md_template(version)
    
    print()
    print(f"[OK] All files updated to version {version}")
    print()
    print("Next steps:")
    print("  1. Review the changes: git diff")
    print("  2. Commit: git add -A && git commit -m 'chore: bump version to x.x.x'")
    print("  3. Tag: git tag vx.x.x")
    print("  4. Push: git push origin main --tags")
    print("  5. Build and publish: rm -rf dist/ && uv build && uv publish")


if __name__ == '__main__':
    main()
