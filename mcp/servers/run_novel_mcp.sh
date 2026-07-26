#!/bin/bash
# nohup 方式运行 novel_mcp_server，确保脱离终端
cd /mnt/d/AI/AI_Ori/Project_Omega_OCO/mcp/servers
exec /mnt/d/AI/AI_Ori/Project_Omega/.venv/bin/python novel_mcp_server.py \
    >> /mnt/d/AI/AI_Ori/Project_Omega/cloud_brain/novel_mcp.log 2>&1
