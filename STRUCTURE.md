ai-quant-fund/
├── main.py                    # 系统入口
├── core/
│   ├── protocols.py           # Agent 通信协议、状态机枚举
│   ├── agent.py               # Agent 基类
│   ├── state_machine.py       # 系统状态机
│   ├── tool_governance.py     # 工具治理协议
│   └── engine.py              # 编排引擎
├── memory/
│   └── memory_store.py        # 四层记忆系统
├── layers/
│   ├── data/                  # Layer 1 — 待实现
│   ├── intelligence/
│   │   ├── regime_detection.py    # 市场状态检测
│   │   ├── debate.py              # Bull/Bear/Risk 辩论
│   │   ├── adversarial_reflection.py  # 对抗+反思
│   │   ├── risk_management.py     # 风险管理
│   │   └── portfolio_manager.py   # 投资组合
│   ├── governance/
│   │   ├── cio.py                 # CIO 仲裁
│   │   ├── killswitch_reliability.py  # 熔断+可靠性
│   │   └── alpha_lifecycle.py     # Alpha 生命周期
│   └── execution/
│       └── execution_agents.py    # 执行层 Agent
├── config/
│   └── default.json           # 默认配置
├── tests/
│   └── test_pipeline.py       # 流水线测试
└── requirements.txt           # Python 依赖
