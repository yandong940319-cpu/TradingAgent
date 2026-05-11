"""
AI Quant Hedge Fund OS — 四层记忆系统

支持 AI Evolution 的核心基础设施。
"""

import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional


class MemoryStore:
    """四层记忆系统基类"""

    def __init__(self, db_path: str = "~/.ai-quant-fund/memory.db"):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.executescript("""
                -- 1. Episodic Memory: 近期市场行为
                CREATE TABLE IF NOT EXISTS episodic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT, timeframe TEXT,
                    event_type TEXT, description TEXT,
                    outcome TEXT, confidence REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- 2. Strategic Memory: 长期 alpha 规律
                CREATE TABLE IF NOT EXISTS strategic (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alpha_id TEXT UNIQUE,
                    strategy_name TEXT, pattern TEXT,
                    sharpe_peak REAL, sharpe_current REAL,
                    status TEXT DEFAULT 'ACTIVE',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- 3. Failure Memory: 失败组合与错误策略
                CREATE TABLE IF NOT EXISTS failures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_id TEXT, symbol TEXT,
                    strategy TEXT, reason TEXT,
                    loss_amount REAL,
                    failure_type TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- 4. Regime Memory: 不同市场状态下的历史行为
                CREATE TABLE IF NOT EXISTS regimes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    regime_type TEXT,
                    symbol TEXT, timeframe TEXT,
                    optimal_strategy TEXT,
                    sharpe_achieved REAL,
                    volatility_avg REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                -- Indexes
                CREATE INDEX IF NOT EXISTS idx_episodic_time ON episodic(created_at);
                CREATE INDEX IF NOT EXISTS idx_failures_type ON failures(failure_type);
                CREATE INDEX IF NOT EXISTS idx_regimes_type ON regimes(regime_type);
            """)

    def _get_conn(self):
        """返回一个新的数据库连接（用作上下文管理器）"""
        return sqlite3.connect(str(self.db_path))

    # ── Episodic Memory ──

    def save_episode(self, symbol: str, timeframe: str, event_type: str,
                     description: str, outcome: str, confidence: float):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO episodic (symbol,timeframe,event_type,description,outcome,confidence) VALUES (?,?,?,?,?,?)",
                (symbol, timeframe, event_type, description, outcome, confidence)
            )

    def get_recent_episodes(self, limit: int = 20) -> list[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT * FROM episodic ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Strategic Memory ──

    def save_strategy(self, alpha_id: str, name: str, pattern: str, sharpe: float):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                """INSERT INTO strategic (alpha_id,strategy_name,pattern,sharpe_peak,sharpe_current)
                   VALUES (?,?,?,?,?) ON CONFLICT(alpha_id) DO UPDATE SET
                   sharpe_current=excluded.sharpe_current""",
                (alpha_id, name, pattern, sharpe, sharpe)
            )

    def get_active_strategies(self) -> list[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT * FROM strategic WHERE status='ACTIVE' ORDER BY sharpe_current DESC"
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Failure Memory ──

    def save_failure(self, trade_id: str, symbol: str, strategy: str,
                     reason: str, loss: float, failure_type: str):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO failures (trade_id,symbol,strategy,reason,loss_amount,failure_type) VALUES (?,?,?,?,?,?)",
                (trade_id, symbol, strategy, reason, loss, failure_type)
            )

    def get_recent_failures(self, limit: int = 20) -> list[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT * FROM failures ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(r) for r in rows]

    # ── Regime Memory ──

    def save_regime(self, regime_type: str, symbol: str, timeframe: str,
                    optimal_strategy: str, sharpe: float, vol: float):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO regimes (regime_type,symbol,timeframe,optimal_strategy,sharpe_achieved,volatility_avg) VALUES (?,?,?,?,?,?)",
                (regime_type, symbol, timeframe, optimal_strategy, sharpe, vol)
            )

    def get_regime_strategy(self, regime_type: str) -> Optional[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT * FROM regimes WHERE regime_type=? ORDER BY sharpe_achieved DESC LIMIT 1",
                (regime_type,)
            ).fetchone()
            return dict(row) if row else None
