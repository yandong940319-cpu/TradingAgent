#!/bin/bash
ssh ubuntu@150.109.57.228 << 'SSH_CMD'
# 重启 Dashboard
pkill -f "dashboard.py" 2>/dev/null || true
sleep 1
cd ~/ai-quant-fund && source ~/.hermes/.env
nohup python3 dashboard.py > ~/ai-quant-fund/dashboard.log 2>&1 &
echo "Dashboard restarted, PID: $!"
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:9090/
SSH_CMD