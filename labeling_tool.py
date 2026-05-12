#!/usr/bin/env python3
"""
手动标记工具 — 本地网页版
运行后在浏览器打开 http://localhost:8888
"""

import sys, os, json, asyncio
from pathlib import Path
from datetime import datetime, timedelta
sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

app = FastAPI()

LABELS_FILE = Path("scanner_data/labels.json")
LABELS_FILE.parent.mkdir(exist_ok=True)

def load_labels():
    if LABELS_FILE.exists():
        return json.loads(LABELS_FILE.read_text())
    return []

def save_labels(labels):
    LABELS_FILE.write_text(json.dumps(labels, indent=2, ensure_ascii=False))

@app.get("/api/klines")
async def get_klines(symbol: str = "BTCUSDT", interval: str = "1d", limit: int = 300):
    from layers.data.orchestrator import DataOrchestrator
    dc = DataOrchestrator(
        binance_key=os.getenv("BINANCE_API_KEY", ""),
        binance_secret=os.getenv("BINANCE_API_SECRET", ""),
    )
    raw = dc.binance.get_klines(symbol, interval, limit=limit)
    return JSONResponse(raw)

@app.get("/api/labels")
async def get_labels():
    return JSONResponse(load_labels())

@app.post("/api/labels")
async def add_label(data: dict):
    labels = load_labels()
    # 同一个时间戳+币种只保留最新标记
    labels = [l for l in labels if not (l["time"] == data["time"] and l["symbol"] == data["symbol"])]
    labels.append(data)
    save_labels(labels)
    return {"ok": True, "total": len(labels)}

@app.delete("/api/labels/{time}/{symbol}")
async def delete_label(time: int, symbol: str):
    labels = load_labels()
    labels = [l for l in labels if not (l["time"] == time and l["symbol"] == symbol)]
    save_labels(labels)
    return {"ok": True}

@app.get("/api/export")
async def export_labels():
    labels = load_labels()
    return JSONResponse({
        "total": len(labels),
        "long": len([l for l in labels if l["action"] == "LONG"]),
        "short": len([l for l in labels if l["action"] == "SHORT"]),
        "skip": len([l for l in labels if l["action"] == "SKIP"]),
        "labels": labels,
    })

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(HTML)

HTML = """
<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<title>交易标记工具</title>
<script src="https://cdn.jsdelivr.net/npm/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js"></script>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body { background: #0d1117; color: #e6edf3; font-family: -apple-system, monospace; }

.toolbar {
    display: flex; align-items: center; gap: 12px;
    padding: 12px 16px; background: #161b22;
    border-bottom: 1px solid #30363d; flex-wrap: wrap;
}
.toolbar select, .toolbar input {
    background: #21262d; color: #e6edf3;
    border: 1px solid #30363d; border-radius: 6px;
    padding: 6px 10px; font-size: 13px;
}
.btn {
    padding: 6px 16px; border-radius: 6px; border: none;
    font-size: 13px; cursor: pointer; font-weight: 600;
    transition: opacity 0.15s;
}
.btn:hover { opacity: 0.8; }
.btn-long  { background: #238636; color: #fff; }
.btn-short { background: #da3633; color: #fff; }
.btn-skip  { background: #6e7681; color: #fff; }
.btn-del   { background: #21262d; color: #e6edf3; border: 1px solid #30363d; }

#chart { width: 100%; height: calc(100vh - 100px); }

.panel {
    position: fixed; right: 16px; top: 70px;
    background: #161b22; border: 1px solid #30363d;
    border-radius: 8px; padding: 14px; width: 220px;
    font-size: 12px; z-index: 100;
}
.panel h3 { margin-bottom: 10px; font-size: 13px; color: #8b949e; }
.stat { display: flex; justify-content: space-between; margin: 4px 0; }
.stat-long  { color: #3fb950; }
.stat-short { color: #f85149; }
.stat-skip  { color: #8b949e; }

.label-list {
    position: fixed; right: 16px; bottom: 16px;
    background: #161b22; border: 1px solid #30363d;
    border-radius: 8px; padding: 14px; width: 220px;
    max-height: 300px; overflow-y: auto;
    font-size: 11px; z-index: 100;
}
.label-item {
    display: flex; justify-content: space-between;
    align-items: center; padding: 4px 0;
    border-bottom: 1px solid #21262d;
}
.label-item:last-child { border-bottom: none; }
.tag {
    padding: 1px 6px; border-radius: 4px; font-size: 10px; font-weight: 700;
}
.tag-LONG  { background: #238636; }
.tag-SHORT { background: #da3633; }
.tag-SKIP  { background: #6e7681; }
.del-btn { cursor: pointer; color: #6e7681; font-size: 14px; }
.del-btn:hover { color: #f85149; }

.hint { font-size: 11px; color: #8b949e; }
.selected-info {
    padding: 4px 10px; background: #21262d;
    border-radius: 6px; font-size: 12px; color: #8b949e;
    min-width: 200px;
}
</style>
</head>
<body>

<div class="toolbar">
    <select id="symbol">
        <option>BTCUSDT</option>
        <option>ETHUSDT</option>
        <option>SOLUSDT</option>
    </select>
    <select id="interval">
        <option value="1d">日线</option>
        <option value="4h">4小时</option>
        <option value="1h">1小时</option>
        <option value="15m" selected>15分钟</option>
    </select>
    <button class="btn btn-long"  onclick="labelSelected('LONG')">🟢 做多</button>
    <button class="btn btn-short" onclick="labelSelected('SHORT')">🔴 做空</button>
    <button class="btn btn-skip"  onclick="labelSelected('SKIP')">⚪ 观望</button>
    <div class="selected-info" id="selectedInfo">点击K线选择时间点</div>
    <button class="btn btn-del" onclick="exportLabels()">📥 导出统计</button>
    <span class="hint">已标记: <b id="totalCount">0</b> 个</span>
</div>

<div id="chart"></div>

<div class="panel">
    <h3>📊 标记统计</h3>
    <div class="stat"><span>🟢 做多</span><span class="stat-long" id="longCount">0</span></div>
    <div class="stat"><span>🔴 做空</span><span class="stat-short" id="shortCount">0</span></div>
    <div class="stat"><span>⚪ 观望</span><span class="stat-skip" id="skipCount">0</span></div>
</div>

<div class="label-list" id="labelList">
    <div style="color:#8b949e;font-size:11px;">暂无标记</div>
</div>

<script>
let chart, candleSeries, markers = [];
let selectedBar = null;
let allLabels = [];
let currentSymbol = 'BTCUSDT';
let currentInterval = '15m';

// 初始化图表
function initChart() {
    chart = LightweightCharts.createChart(document.getElementById('chart'), {
        layout: { background: { color: '#0d1117' }, textColor: '#e6edf3' },
        grid: { vertLines: { color: '#21262d' }, horzLines: { color: '#21262d' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { borderColor: '#30363d', timeVisible: true },
        rightPriceScale: { borderColor: '#30363d' },
    });

    candleSeries = chart.addCandlestickSeries({
        upColor: '#3fb950', downColor: '#f85149',
        borderUpColor: '#3fb950', borderDownColor: '#f85149',
        wickUpColor: '#3fb950', wickDownColor: '#f85149',
    });

    // 点击选择K线
    chart.subscribeClick(param => {
        if (!param.time) return;
        selectedBar = param;
        const price = param.seriesData?.get(candleSeries);
        const timeStr = new Date(param.time * 1000).toLocaleString('zh-CN');
        document.getElementById('selectedInfo').textContent =
            price ? `${timeStr}  收盘: ${price.close?.toFixed(2)}` : timeStr;
    });

    loadData();
}

async function loadData() {
    const symbol = document.getElementById('symbol').value;
    const interval = document.getElementById('interval').value;
    currentSymbol = symbol;
    currentInterval = interval;

    const limit = interval === '15m' ? 500 : interval === '1h' ? 400 : 300;
    const resp = await fetch(`/api/klines?symbol=${symbol}&interval=${interval}&limit=${limit}`);
    const raw = await resp.json();

    const candles = raw.map(k => ({
        time: Math.floor(k.time / 1000),
        open: parseFloat(k.open),
        high: parseFloat(k.high),
        low: parseFloat(k.low),
        close: parseFloat(k.close),
    }));

    candleSeries.setData(candles);
    chart.timeScale().fitContent();

    await loadLabels();
}

async function loadLabels() {
    const resp = await fetch('/api/labels');
    allLabels = await resp.json();
    renderMarkers();
    renderLabelList();
    updateStats();
}

function renderMarkers() {
    const colorMap = { LONG: '#3fb950', SHORT: '#f85149', SKIP: '#8b949e' };
    const shapeMap = { LONG: 'arrowUp', SHORT: 'arrowDown', SKIP: 'circle' };
    const posMap   = { LONG: 'belowBar', SHORT: 'aboveBar', SKIP: 'aboveBar' };

    const filtered = allLabels.filter(
        l => l.symbol === currentSymbol && l.interval === currentInterval
    );

    markers = filtered.map(l => ({
        time: Math.floor(l.time / 1000),
        position: posMap[l.action],
        color: colorMap[l.action],
        shape: shapeMap[l.action],
        text: l.action,
    }));

    candleSeries.setMarkers(markers.sort((a, b) => a.time - b.time));
}

function renderLabelList() {
    const filtered = allLabels
        .filter(l => l.symbol === currentSymbol)
        .slice(-20).reverse();

    const el = document.getElementById('labelList');
    if (!filtered.length) {
        el.innerHTML = '<div style="color:#8b949e;font-size:11px;">暂无标记</div>';
        return;
    }

    el.innerHTML = filtered.map(l => {
        const t = new Date(l.time).toLocaleDateString('zh-CN');
        return `
        <div class="label-item">
            <span>${t} <span class="tag tag-${l.action}">${l.action}</span></span>
            <span class="del-btn" onclick="deleteLabel(${l.time}, '${l.symbol}')">✕</span>
        </div>`;
    }).join('');
}

function updateStats() {
    const filtered = allLabels.filter(l => l.symbol === currentSymbol);
    const long  = filtered.filter(l => l.action === 'LONG').length;
    const short = filtered.filter(l => l.action === 'SHORT').length;
    const skip  = filtered.filter(l => l.action === 'SKIP').length;
    document.getElementById('longCount').textContent  = long;
    document.getElementById('shortCount').textContent = short;
    document.getElementById('skipCount').textContent  = skip;
    document.getElementById('totalCount').textContent = filtered.length;
}

async function labelSelected(action) {
    if (!selectedBar || !selectedBar.time) {
        alert('请先点击一根K线');
        return;
    }
    const price = selectedBar.seriesData?.get(candleSeries);
    const data = {
        time: selectedBar.time * 1000,
        symbol: currentSymbol,
        interval: currentInterval,
        action: action,
        close: price?.close || 0,
        labeled_at: new Date().toISOString(),
    };
    await fetch('/api/labels', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data),
    });
    await loadLabels();
    selectedBar = null;
    document.getElementById('selectedInfo').textContent = '点击K线选择时间点';
}

async function deleteLabel(time, symbol) {
    await fetch(`/api/labels/${time}/${symbol}`, { method: 'DELETE' });
    await loadLabels();
}

async function exportLabels() {
    const resp = await fetch('/api/export');
    const data = await resp.json();
    alert(`标记统计\\n总计: ${data.total}\\n做多: ${data.long}\\n做空: ${data.short}\\n观望: ${data.skip}\\n\\n数据已保存到 scanner_data/labels.json`);
}

// 切换币种/周期
document.getElementById('symbol').addEventListener('change', loadData);
document.getElementById('interval').addEventListener('change', loadData);

// 键盘快捷键
document.addEventListener('keydown', e => {
    if (e.key === 'l' || e.key === 'L') labelSelected('LONG');
    if (e.key === 's' || e.key === 'S') labelSelected('SHORT');
    if (e.key === 'k' || e.key === 'K') labelSelected('SKIP');
});

window.addEventListener('resize', () => {
    chart.resize(window.innerWidth, window.innerHeight - 100);
});

initChart();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print("标记工具启动中...")
    print("请在浏览器打开: http://localhost:8888")
    print("快捷键: L=做多  S=做空  K=观望")
    uvicorn.run(app, host="0.0.0.0", port=8888)
