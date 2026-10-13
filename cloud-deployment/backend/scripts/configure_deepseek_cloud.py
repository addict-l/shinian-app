#!/usr/bin/env python3
"""Securely stage or activate the DeepSeek Flash API settings on Aliyun."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import urllib.error
import urllib.request


BASE_URL = "https://api.deepseek.com"
MODEL = "deepseek-flash"
REMOTE_DIR = "/opt/ai-memories/backend"

REMOTE_SCRIPT = r'''
import datetime, json, os, pathlib, shutil, subprocess, sys, tempfile, time, urllib.request
import base64

data = json.load(sys.stdin)
mode = data.get("mode")
root = pathlib.Path("/opt/ai-memories/backend")
pending = root / ".env.deepseek.pending"
production = root / ".env.production"

def atomic_env(path, values):
    old = path.read_text() if path.exists() else ""
    wanted = set(values)
    lines = [line for line in old.splitlines() if not line.split("=", 1)[0] in wanted]
    lines.extend(f"{name}={value}" for name, value in values.items())
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write("\n".join(lines) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    except BaseException:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
        raise

if mode == "stage":
    key = data["api_key"]
    existing = {}
    if production.is_file():
        for line in production.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                name, value = line.split("=", 1)
                existing[name] = value
    values = {
        # Base64 keeps arbitrary opaque key characters safe in Compose env files.
        # It is encoding, not encryption; the file remains mode 0600.
        "LLM_API_KEY_B64": base64.b64encode(key.encode("utf-8")).decode("ascii"),
        "LLM_BASE_URL": "https://api.deepseek.com",
        "LLM_MODEL": "deepseek-flash",
        # The user approved the parallel path and its higher request cost.
        "LLM_TURN_MODEL": "deepseek-flash",
        "LLM_TURN_SECONDARY_MODEL": "deepseek-flash",
        "LLM_DRAFT_MODEL": "deepseek-flash",
        "LLM_TURN_PARALLEL": "true",
        "LLM_TURN_STRATEGY": "parallel_tasks",
    }
    if pending.exists():
        backup = pending.with_name(pending.name + ".previous")
        shutil.copy2(pending, backup)
        os.chmod(backup, 0o600)
    atomic_env(pending, values)
    print("DeepSeek 配置已安全暂存；线上 API 尚未切换。")
    sys.exit(0)

if mode == "optimize":
    if not production.is_file():
        raise SystemExit("missing production configuration")
    current = {}
    for line in production.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            name, value = line.split("=", 1)
            current[name] = value
    if current.get("LLM_MODEL") != "deepseek-flash" or not (current.get("LLM_API_KEY_B64") or current.get("LLM_API_KEY")):
        raise SystemExit("DeepSeek must be active before enabling the parallel strategy")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_dir = pathlib.Path("/opt/shinian-backups") / ("deepseek-parallel-" + stamp)
    backup_dir.mkdir(parents=True, mode=0o700)
    os.chmod(backup_dir, 0o700)
    shutil.copy2(production, backup_dir / "env.production")
    os.chmod(backup_dir / "env.production", 0o600)
    container = subprocess.run([
        "docker", "compose", "--project-name", "backend", "--env-file", str(production),
        "-f", str(root / "docker-compose.demo.yml"), "ps", "-q", "api",
    ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True).stdout.strip()
    if not container:
        raise SystemExit("API container is not running")
    image = subprocess.run(["docker", "inspect", "-f", "{{.Image}}", container],
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True).stdout.strip()
    (backup_dir / "api-image").write_text(image + "\\n")
    os.chmod(backup_dir / "api-image", 0o600)
    atomic_env(production, {
        "LLM_TURN_MODEL": "deepseek-flash",
        "LLM_TURN_SECONDARY_MODEL": "deepseek-flash",
        "LLM_DRAFT_MODEL": "deepseek-flash",
        "LLM_TURN_PARALLEL": "true",
        "LLM_TURN_STRATEGY": "parallel_tasks",
    })
    compose = ["docker", "compose", "--project-name", "backend", "--env-file", str(production),
               "-f", str(root / "docker-compose.demo.yml")]
    updated = subprocess.run(compose + ["up", "-d", "--no-build", "--force-recreate", "api"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    def restore_parallel_config():
        shutil.copy2(backup_dir / "env.production", production)
        os.chmod(production, 0o600)
        subprocess.run(["docker", "tag", image, "backend-api:latest"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        subprocess.run(compose + ["up", "-d", "--no-build", "--force-recreate", "api"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if updated.returncode:
        restore_parallel_config()
        raise SystemExit(updated.returncode)
    healthy = False
    for _ in range(30):
        try:
            with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
                payload = json.loads(response.read())
                healthy = response.status == 200 and payload.get("status") == "ok" and payload.get("database") == "ok" and payload.get("llm_configured") is True
            if healthy: break
        except Exception:
            time.sleep(1)
    if not healthy:
        restore_parallel_config()
        raise SystemExit("parallel strategy health check failed; previous configuration restored")
    print("DeepSeek 并行访谈与草稿模型配置已启用；健康检查通过。配置回退备份：" + str(backup_dir))
    sys.exit(0)

if mode != "activate":
    raise SystemExit("invalid operation")
if not pending.is_file() or not production.is_file():
    raise SystemExit("missing pending or production configuration")

# Refuse to activate a credential against an image that still sends the
# provider-specific strict JSON Schema request unsupported by Chat Completions.
check = subprocess.run([
    "docker", "compose", "--project-name", "backend", "--env-file", str(production),
    "-f", str(root / "docker-compose.demo.yml"), "exec", "-T", "api", "python", "-c",
    "from app.ai.llm_client import LLMClient; assert LLMClient.deepseek_compatible is True",
], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if check.returncode:
    raise SystemExit("running API image lacks DeepSeek JSON-mode compatibility; deploy compatible backend before activation")

stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
backup_dir = pathlib.Path("/opt/shinian-backups") / ("deepseek-config-" + stamp)
backup_dir.mkdir(parents=True, mode=0o700)
os.chmod(backup_dir, 0o700)
shutil.copy2(production, backup_dir / "env.production")
os.chmod(backup_dir / "env.production", 0o600)
container = subprocess.run([
    "docker", "compose", "--project-name", "backend", "--env-file", str(production),
    "-f", str(root / "docker-compose.demo.yml"), "ps", "-q", "api",
], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True).stdout.strip()
if not container:
    raise SystemExit("API container is not running")
image = subprocess.run(["docker", "inspect", "-f", "{{.Image}}", container],
                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=True).stdout.strip()
(backup_dir / "api-image").write_text(image + "\n")
os.chmod(backup_dir / "api-image", 0o600)

# Promote only the pending provider/model keys; preserve database, media,
# auth-independent and parallel-strategy settings from the production file.
keys = ("LLM_API_KEY_B64", "LLM_BASE_URL", "LLM_MODEL", "LLM_TURN_MODEL",
        "LLM_TURN_SECONDARY_MODEL", "LLM_DRAFT_MODEL", "LLM_TURN_PARALLEL", "LLM_TURN_STRATEGY")
pending_values = {}
for line in pending.read_text().splitlines():
    if "=" in line:
        name, value = line.split("=", 1)
        if name in keys: pending_values[name] = value
if set(pending_values) != set(keys):
    raise SystemExit("pending provider configuration is incomplete")
atomic_env(production, pending_values)

def restore_previous_config():
    shutil.copy2(backup_dir / "env.production", production)
    os.chmod(production, 0o600)
    subprocess.run(["docker", "tag", image, "backend-api:latest"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

compose = ["docker", "compose", "--project-name", "backend", "--env-file", str(production),
           "-f", str(root / "docker-compose.demo.yml")]
updated = subprocess.run(compose + ["up", "-d", "--no-build", "--force-recreate", "api"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if updated.returncode:
    restore_previous_config()
    subprocess.run(compose + ["up", "-d", "--no-build", "--force-recreate", "api"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("API restart failed; previous configuration restored. Backup: " + str(backup_dir))
    raise SystemExit(updated.returncode)

healthy = False
for _ in range(30):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
            payload = json.loads(response.read())
            healthy = response.status == 200 and payload.get("status") == "ok" and payload.get("database") == "ok" and payload.get("llm_configured") is True
        if healthy: break
    except Exception:
        time.sleep(1)
if not healthy:
    restore_previous_config()
    subprocess.run(compose + ["up", "-d", "--no-build", "--force-recreate", "api"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print("API health check failed; previous configuration restored. Backup: " + str(backup_dir))
    raise SystemExit(1)
pending.unlink(missing_ok=True)
print("DeepSeek Flash 已配置并重启 API；健康检查通过。配置回退备份：" + str(backup_dir))
'''


def validate_key(key: str) -> None:
    if not key or any(character.isspace() for character in key):
        raise ValueError("API key must be non-empty and contain no whitespace")

    request = urllib.request.Request(
        BASE_URL + "/models",
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise ValueError(f"DeepSeek API key verification failed (HTTP {error.code})") from None
    except Exception as error:
        raise ValueError(f"DeepSeek API key verification failed ({type(error).__name__})") from None
    models = {entry.get("id") for entry in payload.get("data", [])}
    if MODEL not in models:
        raise ValueError("key is valid, but the account model list does not include deepseek-flash")

    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "Return one valid JSON object with the key ok set to true."},
            {"role": "user", "content": "Return the requested JSON."},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "max_tokens": 32,
    }).encode()
    request = urllib.request.Request(
        BASE_URL + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.loads(response.read())
        output = result["choices"][0]["message"]["content"]
        if not isinstance(json.loads(output), dict):
            raise ValueError("response was not a JSON object")
    except urllib.error.HTTPError as error:
        raise ValueError(f"DeepSeek model compatibility check failed (HTTP {error.code})") from None
    except Exception as error:
        raise ValueError(f"DeepSeek model compatibility check failed ({type(error).__name__})") from None


def remote(args: argparse.Namespace, payload: dict) -> None:
    encoded = __import__("base64").b64encode(REMOTE_SCRIPT.encode()).decode()
    remote_python = "exec(__import__('base64').b64decode(" + repr(encoded) + "))"
    command = "sudo -n python3 -c " + shlex.quote(remote_python)
    target = f"{args.user}@{args.host}"
    ssh = ["ssh", "-i", str(args.identity_file), "-o", "IdentitiesOnly=yes",
           "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", target, command]
    result = subprocess.run(ssh, input=json.dumps(payload).encode(), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=False)
    if result.returncode:
        message = result.stderr.decode(errors="replace").strip()
        if message:
            print("SSH/服务器操作失败：" + message, file=sys.stderr)
        raise SystemExit(result.returncode)
    print(result.stdout.decode(errors="replace").strip())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "activate", "optimize"), nargs="?", default="stage")
    parser.add_argument("--host", default="47.82.83.74")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--identity-file", type=Path,
                        default=Path.home() / ".ssh" / "id_ed25519_shinian")
    args = parser.parse_args()
    if not args.identity_file.is_file():
        print("找不到 SSH 身份文件；可通过 --identity-file 指定。", file=sys.stderr)
        return 2

    if args.action == "stage":
        key = getpass.getpass("DeepSeek API Key（输入不会显示）: ")
        confirm = getpass.getpass("再次输入确认: ")
        if key != confirm:
            print("两次输入不一致。", file=sys.stderr)
            return 2
        try:
            validate_key(key)
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        remote(args, {"mode": "stage", "api_key": key})
        print("配置已存入云端受限暂存文件。兼容后端部署完成后，运行同一脚本并加 activate 才会切换线上 API。")
        return 0

    remote(args, {"mode": args.action})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
