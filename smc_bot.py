import ccxt
import requests
import pandas as pd
import time
import threading
from flask import Flask

TELEGRAM_BOT_TOKEN = "9147785620:AAGDSk6n_dppdsFt0xsGKlnoD8rCHfp3rdo"
TELEGRAM_CHAT_ID = "1709473407"

app = Flask(__name__)

@app.route('/')
def home():
    return "SMC Bot Aktif!"

def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        return response.json()
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}")

def check_smc_signals():
    exchange = ccxt.binance()
    symbol = 'BTC/USDT'
    timeframe = '1h'
    
    print(f"{symbol} taranıyor...")
    
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        last_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]
        price_change = ((last_close - prev_close) / prev_close) * 100
        
        signal_msg = (
            f"🚨 *SMC / Piyasa Alarmı!* 🚨\n\n"
            f"📊 *Parite:* `{symbol}`\n"
            f"⏱ *Zaman Dilimi:* `{timeframe}`\n"
            f"💡 *Durum:* Bot başarıyla çalıştı!\n"
            f"💲 *Güncel Fiyat:* `{last_close}`\n"
            f"📈 *Değişim:* `%{price_change:.2f}`"
        )
        send_telegram_message(signal_msg)
        print("Sinyal Telegram'a gönderildi.")
            
    except Exception as e:
        print(f"Veri çekme hatası: {e}")

def bot_loop():
    time.sleep(3)
    check_smc_signals()
    while True:
        time.sleep(300) # Her 5 dakikada bir
        check_smc_signals()

# Arka plan iş parçacığını doğrudan başlatıyoruz
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
    
