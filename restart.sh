pkill -f dashboard.py
sleep 2
cd ~/ai-quant-fund
source ~/.hermes/.env
nohup python3 dashboard.py > ~/ai-quant-fund/dashboard.log 2>&1 &
echo "PID=$!"