#!/bin/bash
ssh ubuntu@150.109.57.228 << 'SSH_CMD'
# 重启 gateway
kill 1038252 2>/dev/null || true
sleep 2
cd ~/hermes && source venv/bin/activate
nohup hermes gateway run --replace > ~/hermes/gateway.log 2>&1 &
echo "Gateway restarted, PID: $!"
sleep 3
curl -s http://localhost:9090/api/analyze?symbol=BTCUSDT 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'Dashboard OK - BTC: \${d.get(\"metadata\",{}).get(\"close\",\"?\")}')" 2>/dev/null || echo "Dashboard: $(curl -s -o /dev/null -w '%{http_code}' http://localhost:9090/)"
SSH_CMD