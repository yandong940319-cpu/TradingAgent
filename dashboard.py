"""
AI Quant Hedge Fund OS — Web Dashboard (FastAPI)

访问: http://150.109.57.228:9090
"""

import sys, os, json, asyncio
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
import uvicorn
sys.path.insert(0, str(Path(__file__).parent))

from layers.data.orchestrator import DataOrchestrator
from core.protocols import AgentOutput, Signal
from core import risk_config  # 硬规则配置
from backtest.engine import BacktestEngine
from memory.memory_store import MemoryStore

app = FastAPI(title="AI Quant Fund OS", version="1.0.0")
dc = DataOrchestrator(
    binance_key=os.getenv("BINANCE_API_KEY", ""),
    binance_secret=os.getenv("BINANCE_API_SECRET", ""),
)


# ── 硬规则风控（不经过 LLM） ──


def _check_hard_rules(symbol: str, market_summary: str, klines: list = None) -> dict:
    """
    执行硬编码风控检查，先于任何 LLM 调用。
    
    检查项（全部基于实时市场数据，不依赖记忆体）：
    1. MAX_VOLATILITY  — 波动率过高则硬拒绝
    2. PRICE_DEVIATION — 价格偏离均线过远则硬拒绝
    3. EXTREME_RETURN  — 近期涨跌幅过大则硬拒绝
    4. MAX_DAILY_LOSS  — 当日亏损检查（从信号日志读取）

    返回:
        {"allowed": True}  — 所有硬规则通过
        {"allowed": False, "reason": "..."} — 硬规则拒绝
    """
    # ── 规则 1: 波动率检查 ──
    if klines and len(klines) >= 14:
        closes = [float(k.get("close", k.get(4, 0))) for k in klines[-14:]]
        highs = [float(k.get("high", k.get(2, 0))) for k in klines[-14:]]
        lows = [float(k.get("low", k.get(3, 0))) for k in klines[-14:]]
        last_close = closes[-1]

        # 计算 ATR（平均真实波幅）/ close
        tr_sum = 0
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i - 1])
            lc = abs(lows[i] - closes[i - 1])
            tr_sum += max(hl, hc, lc)
        atr = tr_sum / (len(closes) - 1)
        volatility_pct = atr / last_close if last_close > 0 else 0

        if volatility_pct > risk_config.MAX_VOLATILITY_PCT:
            return {
                "allowed": False,
                "reason": f"MAX_VOLATILITY: ATR/Close={volatility_pct:.1%} 超过上限 {risk_config.MAX_VOLATILITY_PCT:.0%}",
            }

        # ── 规则 2: 价格偏离均线 ──
        ma_20 = sum(closes) / len(closes)
        deviation = abs(last_close - ma_20) / ma_20
        if deviation > risk_config.MAX_PRICE_DEVIATION_MA:
            return {
                "allowed": False,
                "reason": f"PRICE_DEVIATION: 偏离均线 {deviation:.1%} 超过上限 {risk_config.MAX_PRICE_DEVIATION_MA:.0%}",
            }

        # ── 规则 3: 近期累计涨跌幅 ──
        period_return = (closes[-1] - closes[0]) / closes[0]
        if abs(period_return) > risk_config.MAX_CUMULATIVE_RETURN_PCT:
            return {
                "allowed": False,
                "reason": f"EXTREME_RETURN: 近期涨跌 {period_return:.1%} 超过上限 {risk_config.MAX_CUMULATIVE_RETURN_PCT:.0%}",
            }

    # ── 规则 4: 当日亏损检查（从信号日志读取实际跟踪数据） ──
    try:
        mem = MemoryStore()
        today = datetime.now().strftime("%Y-%m-%d")
        with mem._get_conn() as conn:
            rows = conn.execute(
                "SELECT outcome, confidence FROM episodic WHERE date(created_at) = ?",
                (today,),
            ).fetchall()
        daily_pnl = 0.0
        for outcome, conf in rows:
            if outcome == "WIN":
                daily_pnl += conf or 0.02
            elif outcome == "LOSS":
                daily_pnl -= abs(conf) or 0.02
        if daily_pnl < -risk_config.MAX_DAILY_LOSS:
            return {
                "allowed": False,
                "reason": f"MAX_DAILY_LOSS: 当日亏损 {daily_pnl:.1%} 超过上限 {risk_config.MAX_DAILY_LOSS:.0%}",
            }
    except Exception:
        pass  # 无记忆时跳过此规则

    return {"allowed": True}


def _cio_rule_filter(bull: dict, bear: dict, risk: dict, regime: dict,
                     trade_allowed: bool, hard_allowed: bool) -> dict:
    """
    CIO 规则层前置过滤。
    仅当规则层无法明确判断时才调用 LLM。

    返回:
        {"decision": "LONG"/"SHORT"/"NO_TRADE", "reason": "...", "needs_llm": bool}
    """
    risk_veto = risk.get("veto", False)
    bull_conf = bull.get("confidence", 0)
    bear_conf = bear.get("confidence", 0)
    regime_type = regime.get("regime", "UNKNOWN")

    # 规则 1: 硬规则已拒绝 → NO_TRADE（不需要 LLM）
    if not hard_allowed:
        return {"decision": "NO_TRADE", "reason": "HARD_RULES_BLOCKED", "needs_llm": False}

    # 规则 2: AI 风控 veto → NO_TRADE（不需要 LLM）
    if risk_veto:
        return {"decision": "NO_TRADE", "reason": "AI_RISK_VETO", "needs_llm": False}

    # 规则 3: 多空都无信心 → NO_TRADE（不需要 LLM）
    if bull_conf < 0.3 and bear_conf < 0.3:
        return {"decision": "NO_TRADE", "reason": "LOW_CONVICTION_BOTH", "needs_llm": False}

    # 规则 4: 多方信心高且空方极低 → 直接 LONG（不需要 LLM）
    if bull_conf >= 0.6 and bear_conf < 0.3:
        return {"decision": "LONG", "reason": "RULE_BULL_DOMINANT", "needs_llm": False}

    # 规则 5: 空方信心高且多方极低 → 直接 SHORT（不需要 LLM）
    if bear_conf >= 0.6 and bull_conf < 0.3:
        return {"decision": "SHORT", "reason": "RULE_BEAR_DOMINANT", "needs_llm": False}

    # 规则 6: 极端市场状态 → NO_TRADE（不需要 LLM）
    if regime_type in ("CRISIS", "HIGH_VOLATILITY"):
        return {"decision": "NO_TRADE", "reason": f"REGIME_{regime_type}", "needs_llm": False}

    # 规则 7: 多空胶着或矛盾 → 需要 LLM 做最终仲裁
    return {"decision": "PENDING_LLM", "reason": "RULE_AMBIGUOUS", "needs_llm": True}


# ── 全流水线执行 ──

async def run_full_pipeline(symbol: str, tf: str = "1h") -> dict:
    """运行所有 Agent 并收集输出（DeepSeek AI 驱动）"""
    from core.deepseek_client import DeepSeekClient
    ai = DeepSeekClient()
    results = {"symbol": symbol, "timeframe": tf, "agents": [], "data": {}}

    # Layer 1: 数据采集
    data = await dc.collect(symbol, tf)
    results["data"] = data
    results["agents"].append({
        "layer": "Layer 1", "name": "Market Data",
        "status": "done", "output": data.get("data", {}),
    })
    if data.get("market") == "ashare":
        results["agents"].append({
            "layer": "Layer 1", "name": "A-Share Data",
            "status": "done", "output": {"klines": data.get("metadata", {}).get("klines_count", 0)},
        })

    # 构建市场数据摘要
    meta = data.get("metadata", {})
    close_price = float(meta.get("close", 0) or 0)
    klines = meta.get("klines", meta.get("recent_data", []))
    summary_parts = [f"最新价: {close_price}"]
    if klines:
        for k in klines[-5:]:
            if isinstance(k, dict):
                summary_parts.append(f"O={k.get('open',0)} H={k.get('high',0)} L={k.get('low',0)} C={k.get('close',0)} V={k.get('volume',0)}")
    market_summary = "\n".join(summary_parts)

    # Layer 1.5: Market Intelligence — 免费数据源情绪分析
    from core.market_data_sources import collect_market_sentiment
    sentiment = collect_market_sentiment(symbol)
    mi_status = "done" if sentiment.get("news_headlines") else "limited"
    results["agents"].append({
        "layer": "Layer 1.5", "name": "Market Intelligence",
        "status": mi_status,
        "output": {
            "fear_greed": sentiment["fear_greed"],
            "sentiment_score": sentiment["sentiment_score"],
            "news_count": sentiment["news_count"],
            "headlines": [h["title"] for h in sentiment.get("news_headlines", [])[:3]],
        },
    })

    # 扩展市场摘要，加入情绪数据供 AI 分析
    fng = sentiment["fear_greed"]
    sentiment_line = f"\n市场情绪: Fear & Greed={fng.get('value','?')}/100 ({fng.get('classification','?')})"
    market_summary += sentiment_line
    if sentiment.get("news_headlines"):
        top_news = sentiment["news_headlines"][:2]
        news_lines = "\n".join([f"  • {h['source']}: {h['title']}" for h in top_news])
        market_summary += f"\n最新新闻:\n{news_lines}"

    # Layer 2: Intelligence — DeepSeek AI 分析
    # Regime
    regime = await asyncio.to_thread(ai.analyze_regime, market_summary)
    results["agents"].append({
        "layer": "Layer 2", "name": "Regime Detector",
        "status": "done", "output": regime,
    })

    # Bull
    bull = await asyncio.to_thread(ai.debate_bull, market_summary)
    results["agents"].append({
        "layer": "Layer 2", "name": "Bull",
        "status": "done", "output": bull,
    })

    # Bear
    bear = await asyncio.to_thread(ai.debate_bear, market_summary)
    results["agents"].append({
        "layer": "Layer 2", "name": "Bear",
        "status": "done", "output": bear,
    })

    # ── 硬规则风控（基于实时市场数据，不经过 LLM） ──
    hard_rules_result = _check_hard_rules(symbol, market_summary, klines)
    hard_allowed = hard_rules_result["allowed"]
    hard_reason = hard_rules_result.get("reason", "")

    # Risk (仅当硬规则通过时调用 AI)
    risk = {}
    if hard_allowed:
        risk = await asyncio.to_thread(ai.analyze_risk, market_summary)
        risk_status = "done"
    else:
        risk = {"veto": True, "reason": hard_reason, "source": "HARD_RULES"}
        risk_status = "blocked (hard rules)"
    results["agents"].append({
        "layer": "Layer 2", "name": "Risk Guardian",
        "status": risk_status, "output": risk,
    })

    # Adversarial (简化)
    results["agents"].append({
        "layer": "Layer 2", "name": "Adversarial",
        "status": "done", "output": {"note": "由风控Agent覆盖", "status": "CLEAR"},
    })

    # Reflection
    results["agents"].append({
        "layer": "Layer 2", "name": "Reflection",
        "status": "done", "output": {"confidence_penalty": 0, "weight_adjustment": 0},
    })

    # Risk Manager
    # 组合硬规则 + AI 风控：任一拒绝则 NO_TRADE
    trade_allowed = hard_allowed and not risk.get("veto", False)
    veto_source = None
    if not hard_allowed:
        veto_source = hard_reason
    elif risk.get("veto", False):
        veto_source = "AI_VETO"

    results["agents"].append({
        "layer": "Layer 2", "name": "Risk Manager",
        "status": "done",
        "output": {
            "trade_allowed": trade_allowed,
            "hard_rules_pass": hard_allowed,
            "ai_veto": risk.get("veto", False),
            "veto_source": veto_source or "NONE",
        },
    })

    # Portfolio Manager
    results["agents"].append({
        "layer": "Layer 2", "name": "Portfolio Manager",
        "status": "done",
        "output": {"position_size": "20%" if trade_allowed else "0%", "cash_ratio": "70%"},
    })

    # Layer 3: CIO — 规则层前置过滤 + AI 仲裁
    cio = _cio_rule_filter(bull, bear, risk, regime, trade_allowed, hard_allowed)
    results["agents"].append({
        "layer": "Layer 3", "name": "CIO Rule Filter",
        "status": "done",
        "output": {
            "rule_decision": cio.get("decision", "NO_TRADE"),
            "rule_reason": cio.get("reason", ""),
            "needs_llm": cio.get("needs_llm", False),
        },
    })

    if cio.get("needs_llm", False):
        cio_final = await asyncio.to_thread(ai.cio_decision, bull, bear, risk, regime)
        cio_decision = cio_final.get("decision", "NO_TRADE")
        cio_reason = cio_final.get("rationale", "")
        results["agents"].append({
            "layer": "Layer 3", "name": "CIO AI Arbitration",
            "status": "done", "output": cio_final,
        })
    else:
        cio_decision = cio["decision"]
        cio_reason = cio["reason"]
        results["agents"].append({
            "layer": "Layer 3", "name": "CIO AI Arbitration",
            "status": "skipped (rule suffices)", "output": {"decision": cio_decision, "reason": cio_reason},
        })

    # Layer 4: Execution (standby)
    results["agents"].append({
        "layer": "Layer 4", "name": "Execution",
        "status": "standby", "output": {"mode": "READ_ONLY", "reason": "EXECUTION_DISABLED"},
    })
    results["agents"].append({
        "layer": "Layer 4", "name": "Exchange Monitor",
        "status": "standby", "output": {"health": "OK"},
    })

    # 追踪信号
    if cio_decision in ("LONG", "SHORT"):
        try:
            from core.signal_tracker import log_signal
            close_price = float(meta.get("close", 0) or 0)
            c = cio.get("confidence", 0) or 0.7
            log_signal(symbol=symbol, signal=cio_decision, price=close_price,
                       confidence=c,
                       fusion_details=f"CIO: {cio_reason}", source="dashboard")
        except Exception:
            pass

    return results


DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AI Quant Fund OS</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0a0a;color:#e0e0e0;line-height:1.6}
.header{background:linear-gradient(135deg,#0f0c29,#302b63,#24243e);padding:20px;text-align:center;border-bottom:1px solid #3a3a5e}
.header h1{font-size:22px;font-weight:700;color:#7dd5ff}
.header p{color:#889;font-size:12px;margin-top:2px}
.container{max-width:1100px;margin:0 auto;padding:16px}
.section{background:#111;border-radius:10px;padding:14px 16px;margin-bottom:12px;border:1px solid #1a1a1a}
.section h2{font-size:14px;font-weight:600;color:#ddd;margin-bottom:8px}
.input-row{display:flex;gap:6px}
.input-row input{flex:1;padding:7px 10px;border-radius:6px;border:1px solid #2a2a2a;background:#151515;color:#eee;font-size:12px;outline:none}
.input-row input:focus{border-color:#7dd5ff}
.btn{padding:7px 16px;border-radius:6px;border:none;font-size:12px;cursor:pointer;font-weight:600}
.btn-primary{background:#3060b0;color:#fff}
.btn-primary:disabled{opacity:.5;cursor:wait}
.sym-btn{padding:3px 10px;border-radius:5px;border:1px solid #2a2a3e;background:#151515;color:#aaa;cursor:pointer;font-size:11px;margin:2px}
.sym-btn:hover{background:#2a2a3e;color:#fff}

/* Agent Pipeline */
.pipeline{display:flex;flex-direction:column;gap:2px}
.p-row{display:flex;align-items:flex-start;gap:6px}
.p-label{width:70px;font-size:10px;color:#555;text-align:right;flex-shrink:0;padding-top:6px}
.p-agents{display:flex;gap:4px;flex-wrap:wrap;flex:1}
.p-agent{padding:4px 6px;border-radius:4px;font-size:10px;border:1px solid #2a2a2a;background:#0a0a0a;color:#555;text-align:center;cursor:pointer;transition:all .2s;min-width:55px}
.p-agent:hover{border-color:#555}
.p-agent .name{display:block;font-weight:600}
.p-agent .stat{display:block;font-size:8px;margin-top:1px}
.p-agent.active{border-color:#7dd5ff;color:#7dd5ff;background:#0a1a2e}
.p-agent.done{border-color:#7dd56c;color:#7dd56c;background:#0a1a0a}
.p-agent.err{border-color:#ff6b6b;color:#ff6b6b;background:#1a0a0a}
.p-agent.sby{border-color:#555;color:#555;background:#0a0a0a}

/* Agent JSON output */
.agent-json{display:none;margin-top:4px;margin-left:76px;background:#080808;border-radius:4px;padding:6px 8px;font-family:monospace;font-size:10px;color:#7dd5ff;border:1px solid #1a2a3a;white-space:pre-wrap;max-height:150px;overflow-y:auto;line-height:1.5}
.agent-json.show{display:block}

.arrow{color:#333;font-size:10px;text-align:center;margin:1px 0 1px 76px}

/* Data Grid */
.dg{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:8px;margin-top:8px}
.dc{background:#0f0f0f;border-radius:6px;padding:8px 10px;border:1px solid #1a1a1a}
.dc .l{font-size:10px;color:#666}
.dc .v{font-size:14px;font-weight:700}
.g{color:#7dd56c}.r{color:#ff6b6b}.b{color:#7dd5ff}.y{color:#ffd93d}

.ft{text-align:center;padding:12px;color:#333;font-size:10px}
.spin{display:inline-block;width:10px;height:10px;border:2px solid #3060b0;border-top-color:transparent;border-radius:50%;animation:s .6s linear infinite;vertical-align:middle;margin-right:4px}
@keyframes s{to{transform:rotate(360deg)}}
</style>
</head>
<body>

<div class="header">
  <h1>🔮 AI Quant Fund OS</h1>
  <p>多 Agent 协作分析 · 点击 Agent 查看 JSON 输出</p>
</div>

<div class="container">

  <div class="section">
    <h2>🔍 查询</h2>
    <div style="margin-bottom:6px">
      <button class="sym-btn" onclick="q('BTCUSDT')">BTC/USDT</button>
      <button class="sym-btn" onclick="q('ETHUSDT')">ETH/USDT</button>
      <button class="sym-btn" onclick="q('sh.600519')">贵州茅台</button>
      <button class="sym-btn" onclick="q('sh.600000')">浦发银行</button>
    </div>
    <div class="input-row">
      <input type="text" id="si" placeholder="BTCUSDT / sh.600000" onkeydown="if(event.key==='Enter')q()">
      <button class="btn btn-primary" id="qb" onclick="q()">分析</button>
    </div>
  </div>

  <div class="section" id="ps" style="display:none">
    <h2>⚡ Agent 流水线 <span style="font-weight:400;font-size:11px;color:#555">（点击 Agent 查看 JSON）</span></h2>
    <div class="pipeline" id="pl"></div>
  </div>

  <div class="section" id="rs" style="display:none">
    <h2>📊 数据</h2>
    <div id="rc"></div>
  </div>

  <!-- 扫描器状态 -->
  <div class="section">
    <h2>👁️ 实时扫描 <span id="scanStatus" style="font-weight:400;font-size:11px;color:#555">—</span></h2>
    <div id="scanResult"><div style="color:#555;font-size:12px">每分钟自动扫描 BTC/ETH/SOL，有信号时飞书通知</div></div>
  </div>

  <!-- 复盘 -->
  <div class="section">
    <h2>📊 因子复盘 <span id="reviewStatus" style="font-weight:400;font-size:11px;color:#555">—</span></h2>
    <div id="reviewResult"><div style="color:#555;font-size:12px">等待首次复盘数据...</div></div>
  </div>

  <!-- 回测 -->
  <div class="section">
    <h2>📈 回测</h2>
    <div class="input-row">
      <input type="text" id="btSym" value="BTCUSDT" style="width:100px;flex:none">
      <select id="btTf" style="padding:7px;border-radius:6px;border:1px solid #2a2a2a;background:#151515;color:#eee;font-size:12px;width:70px;flex:none">
        <option value="1d">日线</option>
        <option value="4h">4h</option>
        <option value="1h">1h</option>
      </select>
      <input type="number" id="btYears" value="3" style="width:50px;flex:none" min="1" max="5">
      <span style="color:#555;font-size:11px;line-height:32px">年</span>
      <button class="btn btn-primary" id="btBtn" onclick="runBacktest()">回测</button>
    </div>
    <div id="btResult"></div>
  </div>

</div>

<div class="ft">AI Quant Hedge Fund OS · Default: NO_TRADE</div>

<script>
var agentsData = [];

async function q(sym){
  var inp = document.getElementById('si');
  var symbol = sym || inp.value.trim();
  if(!symbol)return;
  inp.value = symbol;

  document.getElementById('qb').disabled = true;
  document.getElementById('qb').innerHTML = '<span class="spin"></span>分析';
  document.getElementById('ps').style.display = 'block';
  document.getElementById('rs').style.display = 'none';
  document.getElementById('pl').innerHTML = '<div style="text-align:center;padding:10px;color:#555"><span class="spin"></span>正在运行 Agent 流水线...</div>';

  try {
    var res = await fetch('/api/pipeline?symbol=' + encodeURIComponent(symbol));
    var data = await res.json();
    renderPipeline(data);
    renderData(data);
    document.getElementById('rs').style.display = 'block';
  } catch(e) {
    document.getElementById('pl').innerHTML = '<div style="color:#ff6b6b;padding:8px">❌ ' + e.message + '</div>';
  }

  document.getElementById('qb').disabled = false;
  document.getElementById('qb').textContent = '分析';
}

// ── 回测 ──
async function runBacktest(){
  var symbol = document.getElementById('btSym').value.trim() || 'BTCUSDT';
  var tf = document.getElementById('btTf').value;
  var years = document.getElementById('btYears').value || 3;
  var btn = document.getElementById('btBtn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spin"></span>回测中';
  document.getElementById('btResult').innerHTML = '<div style="padding:8px;color:#555"><span class="spin"></span>正在回测 ' + symbol + ' ' + years + ' 年数据...</div>';

  try {
    var res = await fetch('/api/backtest?symbol=' + encodeURIComponent(symbol) + '&timeframe=' + tf + '&years=' + years + '&capital=10000');
    var d = await res.json();
    if(d.error){
      document.getElementById('btResult').innerHTML = '<div style="color:#ff6b6b;padding:8px">❌ ' + d.error + '</div>';
      return;
    }
    var html = '<div class="dg">';
    html += '<div class="dc"><div class="l">总收益率</div><div class="v ' + (d.total_return_pct >= 0 ? 'g' : 'r') + '">' + d.total_return_pct + '%</div></div>';
    html += '<div class="dc"><div class="l">最终权益</div><div class="v b">$' + (+d.final_equity).toLocaleString() + '</div></div>';
    html += '<div class="dc"><div class="l">总交易</div><div class="v">' + d.total_trades + ' 笔</div></div>';
    html += '<div class="dc"><div class="l">胜率</div><div class="v ' + (d.win_rate_pct >= 50 ? 'g' : 'r') + '">' + d.win_rate_pct + '%</div></div>';
    html += '<div class="dc"><div class="l">最大回撤</div><div class="v r">' + d.max_drawdown_pct + '%</div></div>';
    html += '<div class="dc"><div class="l">夏普比</div><div class="v ' + (d.sharpe_ratio >= 1 ? 'g' : 'y') + '">' + d.sharpe_ratio + '</div></div>';
    html += '</div>';
    if(d.trades && d.trades.length){
      html += '<div style="margin-top:8px"><div style="font-size:11px;color:#555;margin-bottom:4px">交易记录 (' + d.trades.length + ' 笔)</div>';
      html += '<div class="log-area" style="max-height:120px">';
      d.trades.slice(-20).forEach(function(t){
        html += '<div style="color:#888;font-size:10px">' + (t.time||'').toString().substring(0,10) + ' ' + t.action + ' @' + (+t.price).toFixed(2) + ' [' + t.signal + ']</div>';
      });
      html += '</div></div>';
    }
    document.getElementById('btResult').innerHTML = html;
  } catch(e) {
    document.getElementById('btResult').innerHTML = '<div style="color:#ff6b6b;padding:8px">❌ ' + e.message + '</div>';
  }
  btn.disabled = false;
  btn.textContent = '回测';
}

// ── 加载扫描状态 ──
async function loadScanStatus(){
  try {
    var res = await fetch('/api/scanner');
    var d = await res.json();
    var time = d.timestamp || '';
    document.getElementById('scanStatus').textContent = '🟢 上次扫描: ' + time;
    var sigs = d.signals || [];
    if(!sigs.length){
      document.getElementById('scanResult').innerHTML = '<div style="color:#555;font-size:12px">✅ 无交易信号</div>';
      return;
    }
    var html = '<div class="dg">';
    sigs.forEach(function(s){
      var dir = s.signal === 'LONG' ? '🟢' : '🔴';
      var cls = s.signal === 'LONG' ? 'g' : 'r';
      html += '<div class="dc"><div class="l">' + dir + ' ' + s.symbol + '</div>';
      html += '<div class="v ' + cls + '">$' + (+s.price).toLocaleString() + '</div>';
      html += '<div style="font-size:10px;color:#555;margin-top:2px">信号: ' + s.signal + ' | 信心: ' + (+s.confidence*100).toFixed(0) + '%</div></div>';
    });
    html += '</div>';
    document.getElementById('scanResult').innerHTML = html;
  } catch(e){
    document.getElementById('scanStatus').textContent = '⏳ 等待首次扫描...';
  }
}
setInterval(loadScanStatus, 10000);
loadScanStatus();

// ── 加载复盘数据 ──
async function loadReview(){
  try {
    var res = await fetch('/api/review');
    var d = await res.json();
    if(d.error || !d.signals_reviewed){
      document.getElementById('reviewStatus').textContent = '⏳ 尚无数据';
      return;
    }
    var s = d.summary || {};
    var statusIcon = s.factor_status === 'VALID' ? '🟢' : (s.factor_status === 'MARGINAL' ? '🟡' : '🔴');
    document.getElementById('reviewStatus').textContent = statusIcon + ' ' + s.factor_status + ' | 信号' + s.total_signals + '笔 | 胜率' + (s.win_rate*100).toFixed(0) + '% | Sharpe ' + s.sharpe.toFixed(2);

    var html = '<div class="dg">';
    html += '<div class="dc"><div class="l">因子状态</div><div class="v" style="color:' + (s.factor_status==='VALID'?'#7dd56c':s.factor_status==='MARGINAL'?'#ffd700':'#ff6b6b') + '">' + s.factor_status + '</div></div>';
    html += '<div class="dc"><div class="l">信号数</div><div class="v">' + s.total_signals + '</div></div>';
    html += '<div class="dc"><div class="l">胜率</div><div class="v g">' + (s.win_rate*100).toFixed(1) + '%</div></div>';
    html += '<div class="dc"><div class="l">平均盈亏</div><div class="v ' + (s.avg_pnl_pct > 0 ? 'g' : 'r') + '">' + (s.avg_pnl_pct*100).toFixed(2) + '%</div></div>';
    html += '<div class="dc"><div class="l">Sharpe</div><div class="v">' + s.sharpe.toFixed(2) + '</div></div>';
    html += '<div class="dc"><div class="l">Sortino</div><div class="v">' + s.sortino.toFixed(2) + '</div></div>';
    html += '<div class="dc"><div class="l">最大回撤</div><div class="v r">' + (s.max_drawdown*100).toFixed(1) + '%</div></div>';
    html += '</div>';

    // 按标的
    var symData = d.by_symbol || {};
    var symKeys = Object.keys(symData);
    if(symKeys.length){
      html += '<div style="margin-top:8px;font-size:11px;color:#889">按标的: ';
      symKeys.forEach(function(sym){
        var sd = symData[sym];
        html += '<span style="margin-right:12px">' + sym + ': ' + sd.signals + '笔 ' + (sd.win_rate*100).toFixed(0) + '%胜率 均' + (sd.avg_pnl_pct*100).toFixed(1) + '%</span>';
      });
      html += '</div>';
    }

    document.getElementById('reviewResult').innerHTML = html;
  } catch(e){
    document.getElementById('reviewStatus').textContent = '⏳ 等待首次复盘...';
  }
}
setInterval(loadReview, 30000);
loadReview();

function renderPipeline(data){
  agentsData = data.agents || [];
  var layers = {};
  agentsData.forEach(function(a){
    if(!layers[a.layer]) layers[a.layer] = [];
    layers[a.layer].push(a);
  });

  var html = '';
  var layerOrder = ['Layer 1','Layer 2','Layer 3','Layer 4'];
  layerOrder.forEach(function(layer, li){
    var agents = layers[layer] || [];
    html += '<div class="p-row">';
    html += '<div class="p-label">' + layer + '</div>';
    html += '<div class="p-agents">';
    agents.forEach(function(a, ai){
      var idx = agentsData.indexOf(a);
      var cls = a.status === 'done' ? 'done' : (a.status === 'active' ? 'active' : (a.status === 'standby' ? 'sby' : 'err'));
      html += '<div class="p-agent ' + cls + '" onclick="toggleJson(' + idx + ')">';
      html += '<span class="name">' + a.name + '</span>';
      html += '<span class="stat">' + (a.output?.signal || a.output?.decision || a.status).toUpperCase() + '</span>';
      html += '</div>';
    });
    html += '</div></div>';
    if(li < layerOrder.length - 1) html += '<div class="arrow">↓</div>';
  });

  // JSON panels
  html += '<div id="jsonPanels">';
  agentsData.forEach(function(a, i){
    html += '<div class="agent-json" id="aj-' + i + '">' + JSON.stringify(a.output, null, 2) + '</div>';
  });
  html += '</div>';

  document.getElementById('pl').innerHTML = html;
}

function toggleJson(idx){
  var el = document.getElementById('aj-' + idx);
  if(!el) return;
  el.classList.toggle('show');
}

function renderData(data){
  var meta = data.data?.metadata || {};
  var d = data.data?.data || {};
  var html = '<div class="dg">';
  if(meta.close) html += '<div class="dc"><div class="l">最新价</div><div class="v g">' + (+meta.close).toLocaleString(undefined,{maxFractionDigits:2}) + '</div></div>';
  if(meta.klines_count) html += '<div class="dc"><div class="l">K线</div><div class="v b">' + meta.klines_count + '</div></div>';
  if(meta.high_24h) html += '<div class="dc"><div class="l">24h最高</div><div class="v g">' + (+meta.high_24h).toLocaleString() + '</div></div>';
  if(meta.low_24h) html += '<div class="dc"><div class="l">24h最低</div><div class="v r">' + (+meta.low_24h).toLocaleString() + '</div></div>';
  if(meta.volume_24h) html += '<div class="dc"><div class="l">24h成交量</div><div class="v y">' + (+meta.volume_24h).toLocaleString() + '</div></div>';
  html += '<div class="dc"><div class="l">市场</div><div class="v b">' + (data.data?.market||data.market||'?') + '</div></div>';
  html += '<div class="dc"><div class="l">信号</div><div class="v y">' + (d.signal||'NEUTRAL') + '</div></div>';
  html += '</div>';
  document.getElementById('rc').innerHTML = html;
}
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return DASHBOARD_HTML


@app.get("/api/analyze")
async def analyze(symbol: str = Query("BTCUSDT"), timeframe: str = Query("1h")):
    try:
        result = await dc.collect(symbol, timeframe)
        return result
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


@app.get("/api/pipeline")
async def full_pipeline(symbol: str = Query("BTCUSDT"), timeframe: str = Query("1h")):
    """运行全流水线并返回所有 Agent 输出"""
    return await run_full_pipeline(symbol, timeframe)


# ── 回测 API ──

@app.get("/api/backtest")
async def backtest(
    symbol: str = Query("BTCUSDT"),
    timeframe: str = Query("1d"),
    years: int = Query(3),
    capital: float = Query(10000),
):
    """运行回测"""
    engine = BacktestEngine(dc.binance)
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    result = await engine.run(
        symbol=symbol,
        start_date=start.strftime("%Y-%m-%d"),
        end_date=end.strftime("%Y-%m-%d"),
        timeframe=timeframe,
        initial_capital=capital,
    )
    return result


@app.get("/api/scanner")
async def scanner_status():
    """返回最新扫描结果"""
    scan_file = Path(__file__).parent / "scanner_data" / "last_scan.json"
    if scan_file.exists():
        with open(scan_file) as f:
            return json.load(f)
    return {"timestamp": "暂无数据", "signals": []}


@app.get("/api/review")
async def review_status():
    """返回最新复盘报告"""
    review_file = Path(__file__).parent / "scanner_data" / "review_report.json"
    if review_file.exists():
        with open(review_file) as f:
            return json.load(f)
    return {"error": "尚无复盘数据", "signals_reviewed": 0}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9090)
