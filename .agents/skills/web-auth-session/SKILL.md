---
name: web-auth-session
description: Handle website authentication by detecting login requirements, capturing QR codes for user scanning, and managing persistent login sessions. Use when users need to (1) access websites requiring login, (2) automate QR code-based authentication workflow, (3) save and restore complete login states including cookies/localStorage/sessionStorage, or (4) maintain persistent sessions across multiple visits.
---

# Web Auth Session Manager

Manage website authentication workflows with QR code scanning and persistent session storage.

## Overview

This skill provides a complete solution for handling website authentication:

1. **Detect** if a website requires login
2. **Capture** QR code for user scanning
3. **Wait** for user to scan and confirm
4. **Save** complete login state (cookies, localStorage, sessionStorage)
5. **Restore** session on subsequent visits

## Quick Start

### Basic Workflow

```python
# 1. Check if login is required
python scripts/detect_login.py https://example.com

# 2. If QR login needed, capture and send to user
python scripts/capture_qr.py https://example.com --output qr.png

# 3. After user scans QR, save session (use v2 for enhanced capture)
python scripts/save_session_v2.py https://example.com --name example --verbose

# 4. Later, restore session and continue (use v2 for enhanced restore)
python scripts/restore_session_v2.py https://example.com --name example --verify
```

### Enhanced v2 Scripts

Use v2 scripts for better login state capture:

- **save_session_v2.py** - Captures: cookies, localStorage, sessionStorage, JS variables, network tokens, auth headers
- **restore_session_v2.py** - Restores all captured data, injects auth headers, restores JS state

## Workflow Details

### Step 1: Detect Login Requirement

Use `detect_login.py` to check if a website requires authentication:

```bash
python scripts/detect_login.py <url> [--timeout 10]
```

**Returns:**
- `NEED_LOGIN` - Login required (redirected to login page or login elements found)
- `LOGGED_IN` - Already authenticated
- `PUBLIC` - Public access, no login needed

### Step 2: Capture QR Code

When login is required, capture the QR code and send to user:

```bash
python scripts/capture_qr.py <url> [--output qr.png] [--wait 60]
```

**Features:**
- Auto-detects QR code on the page
- Waits for QR to fully load
- Takes high-quality screenshot
- Saves to specified output path

**After capture:** Send the image to user via Feishu/file sharing.

### Step 3: Save Session

After user confirms scanning, save the complete login state:

```bash
python scripts/save_session.py <url> --name <site_name> [--wait 10]
```

**Saved data includes:**
- Cookies (all domains)
- localStorage
- sessionStorage
- IndexedDB (basic support)

**Output file:** `assets/<site_name>_status.json`

### Step 4: Restore Session

On subsequent visits, restore the saved session:

```bash
python scripts/restore_session.py <url> --name <site_name> [--verify]
```

**Options:**
- `--verify` - Check if session is still valid after restoration

## Complete Example

```python
import subprocess
import os

url = "https://watcha.com"
site_name = "watcha"

# Step 1: Detect login status
result = subprocess.run(
    ["python", "scripts/detect_login.py", url],
    capture_output=True, text=True
)

if "NEED_LOGIN" in result.stdout:
    # Step 2: Capture QR
    subprocess.run([
        "python", "scripts/capture_qr.py", 
        url, "--output", f"WORKPLACE/{site_name}_qr.png"
    ])
    
    # Send QR to user (manual step)
    print(f"请扫描 WORKPLACE/{site_name}_qr.png 中的二维码")
    input("扫码完成后按回车继续...")
    
    # Step 3: Save session
    subprocess.run([
        "python", "scripts/save_session.py",
        url, "--name", site_name, "--wait", "5"
    ])
    
    print(f"登录状态已保存到 assets/{site_name}_status.json")
else:
    print("已登录或无需登录")

# Later visits - restore session
subprocess.run([
    "python", "scripts/restore_session.py",
    url, "--name", site_name, "--verify"
])
```

## Session File Format

### v1 (Basic)

```json
{
  "metadata": { "url": "...", "saved_at": "...", "domain": "..." },
  "cookies": [...],
  "localStorage": {...},
  "sessionStorage": {...},
  "indexedDB": {}
}
```

### v2 (Enhanced) - Recommended for complex sites

v2 captures additional auth data including network tokens and JS variables:

```json
{
  "metadata": { "url": "...", "saved_at": "...", "domain": "...", "login_detected": true },
  "network": {
    "authorization_headers": [{"url": "...", "auth": "Bearer token..."}],
    "api_tokens": [{"header": "x-token", "value": "..."}]
  },
  "cookies": [...],
  "localStorage": {...},
  "sessionStorage": {...},
  "jsVariables": { "userToken": "...", "currentUser": "{...}" },
  "authData": { "local_token": "..." },
  "documentCookies": "..."
}
```

## Scripts Reference

### Core Scripts

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `detect_login.py` | Check if login is required | `url`, `--timeout` |
| `capture_qr.py` | Screenshot QR code | `url`, `--output`, `--wait` |
| `save_session.py` | Basic login state save | `url`, `--name`, `--wait` |
| `restore_session.py` | Basic session restore | `url`, `--name`, `--verify` |

### Enhanced v2 Scripts (Recommended for OAuth/WeChat Login)

| Script | Purpose | Key Parameters |
|--------|---------|----------------|
| `save_session_v2.py` | Enhanced capture with network tokens, JS variables | `url`, `--name`, `--verbose` |
| `restore_session_v2.py` | Enhanced restore with header injection | `url`, `--name`, `--verify` |

## Best Practices

1. **Always verify session** after restoration with `--verify` flag
2. **Keep session files secure** - they contain sensitive auth data
3. **Handle session expiration** - saved sessions may expire, be prepared to re-auth
4. **Use descriptive names** - site names should be clear and consistent
5. **Check before saving** - ensure user is actually logged in before saving

## Troubleshooting

### QR Code Not Found

```bash
# Increase wait time for QR to load
python scripts/capture_qr.py https://example.com --wait 120
```

### Session Not Working

```bash
# Verify session is valid
python scripts/restore_session.py https://example.com --name example --verify

# Re-authenticate if needed
python scripts/save_session.py https://example.com --name example --force
```

### Detection Issues

Some sites use complex login detection. Manually inspect:

```bash
# Check what the script sees
python scripts/detect_login.py https://example.com --verbose
```

## Requirements

- Python 3.8+
- playwright: `pip install playwright`
- browsers: `playwright install chromium`
