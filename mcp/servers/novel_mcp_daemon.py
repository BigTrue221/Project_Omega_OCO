#!/usr/bin/env python3
"""novel_mcp_server 的 daemon wrapper - 确保进程常驻"""
import os
import sys
import signal
import subprocess
import time

LOG_FILE = "/mnt/d/AI/AI_Ori/Project_Omega/cloud_brain/novel_mcp.log"
PYTHON = "/mnt/d/AI/AI_Ori/Project_Omega/.venv/bin/python"
SERVER_SCRIPT = "/mnt/d/AI/AI_Ori/Project_Omega_OCO/mcp/servers/novel_mcp_server.py"

def write_log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [daemon] {msg}\n")

def main():
    write_log("Daemon wrapper starting")

    # 忽略 SIGHUP（nohup 不会杀掉我们）
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    while True:
        write_log("Spawning novel_mcp_server...")
        proc = subprocess.Popen(
            [PYTHON, SERVER_SCRIPT],
            stdout=open(LOG_FILE, "a"),
            stderr=subprocess.STDOUT,
            stdin=subprocess.PIPE,
            env=env,
            start_new_session=True,
        )
        write_log(f"novel_mcp_server started, PID={proc.pid}")

        # 等待子进程退出
        retcode = proc.wait()
        write_log(f"novel_mcp_server exited with code={retcode}")

        # 如果正常退出（不是被信号杀死），等待 3 秒后重启
        if retcode in (0, -15):  # 0=正常退出, -15=SIGTERM
            write_log("Will not restart after graceful exit")
            break

        write_log("Restarting in 3 seconds...")
        time.sleep(3)

if __name__ == "__main__":
    main()
