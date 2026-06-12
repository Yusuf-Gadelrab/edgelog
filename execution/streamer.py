import os
import asyncio
from dotenv import load_dotenv

try:
    from alpaca_trade_api.stream import Stream
except ImportError:
    Stream = None

async def process_bar(bar):
    # This is where Hermes evaluates incoming market data against learned edges
    # e.g., if vbt_signal(bar) == 1: ChatOps.send_approval(...)
    print(f"[Hermes Streamer] New Bar: {bar.symbol} Close: {bar.close}")

def start_stream():
    load_dotenv()
    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET")
    base_url = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

    if not api_key or not Stream:
        print("Missing Alpaca API Key or alpaca-trade-api package. Halting execution streamer.")
        return

    stream = Stream(api_key, api_secret, base_url=base_url, data_feed='iex')
    
    # Subscribe to SPY minute bars as a default baseline
    stream.subscribe_bars(process_bar, 'SPY')
    
    print("🚀 Hermes Streamer Online. Awaiting market ticks...")
    stream.run()

if __name__ == "__main__":
    start_stream()
