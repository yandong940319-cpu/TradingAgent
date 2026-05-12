"""
AI Quant Fund OS — 飞书私聊通知
"""

import json, os, requests
from pathlib import Path


FEISHU_APP_ID = ""
FEISHU_APP_SECRET = ""
DM_CHAT_ID = "oc_af66d39f9fb56e0e57fe235d3831e5b1"


def _load_creds():
    global FEISHU_APP_ID, FEISHU_APP_SECRET
    if FEISHU_APP_ID and FEISHU_APP_SECRET:
        return
    env_path = Path.home() / ".hermes" / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line.startswith("FEISHU_APP_ID="):
                FEISHU_APP_ID = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("FEISHU_APP_SECRET="):
                FEISHU_APP_SECRET = line.split("=", 1)[1].strip().strip("\"'")


def _get_token() -> str:
    _load_creds()
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        return ""
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
            timeout=10,
        )
        return r.json().get("tenant_access_token", "")
    except Exception:
        return ""


def send_dm(text: str):
    """发送私聊消息"""
    token = _get_token()
    if not token:
        return
    try:
        payload = {
            "receive_id": DM_CHAT_ID,
            "msg_type": "text",
            "content": json.dumps({"text": text}, ensure_ascii=False),
        }
        requests.post(
            "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=10,
        )
    except Exception:
        pass
