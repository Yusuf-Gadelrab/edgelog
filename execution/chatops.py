import os
import httpx
from dotenv import load_dotenv

def send_approval_request(symbol: str, side: str, win_rate: float, ev: float):
    """
    ChatOps Human-in-the-Loop Webhook.
    Notifies Discord/Telegram so the user can approve or deny the AI's execution command.
    """
    load_dotenv()
    webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("No Discord webhook configured. Logging locally instead:")
        print(f"🚨 HERMES SIGNAL: {side.upper()} {symbol} | Win Rate: {win_rate}% | EV: {ev}R")
        return
        
    msg = {
        "content": f"🚨 **HERMES SIGNAL** 🚨\\n**{side.upper()}** `{symbol}`\\nWin Rate: {win_rate}%\\nExpected Value: {ev}R\\n\\nReply 'YES' to execute or 'NO' to skip."
    }
    
    try:
        httpx.post(webhook_url, json=msg)
    except Exception as e:
        print(f"Failed to send webhook: {e}")
