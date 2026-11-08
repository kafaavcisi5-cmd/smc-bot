import ccxt
import requests
import pandas as pd
import time
import threading
from flask import Flask

TELEGRAM_BOT_TOKEN = "9147785620:AAGDSk6n_dppdsFt0xsGKlnoD8rCHfp3rdo"
# Doğru Chat ID'yi otomatik yakalamak için boş bırakabiliriz ama sizinki: 1709473407
TELEGRAM_CHAT_ID = "1709473407"

app = Flask(__name__)

@app.route('/')
def home():
    return "SMC Bot 7/24 Aktif ve Çalışıyor!"

def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload)
        print(f"Telegram Yanıtı: {response.text}")
        return response.json()
    except Exception as e:
        print(f"Telegram bağlantı hatası: {e}")

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
            f"💡 *Durum:* Bot aktif ve tarama yapıyor!\n"
            f"💲 *Güncel Fiyat:* `{last_close}`\n"
            f"📈 *Değişim:* `%{price_change:.2f}`"
        )
        send_telegram_message(TELEGRAM_CHAT_ID, signal_msg)
            
    except Exception as e:
        print(f"Veri çekme hatası: {e}")

# Telegram'dan gelen mesajları dinleyen ve /start yazıldığında size "Bot aktif!" diyen döngü
def telegram_listener():
    offset = 0
    print("Telegram dinleyicisi başlatıldı...")
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url)
            data = response.json()
            
            if data.get("ok"):
                for result in data.get("result", []):
                    offset = result["update_id"] + 1
                    message = result.get("message", {})
                    chat_id = message.get("chat", {}).get("id")
                    text = message.get("text", "")
                    
                    print(f"Gelen Mesaj: {text} | Chat ID: {chat_id}")
                    
                    if text == "/start":
                        send_telegram_message(chat_id, "🤖 SMC Tarama Botu başarıyla bağlandı! Sinyaller bu sohbet üzerinden gelecektir.")
        except Exception as e:
            print(f"Dinleme hatası: {e}")
        time.sleep(2)

def bot_loop():
    time.sleep(5)
    while True:
        check_smc_signals()
        time.sleep(300) # Her 5 dakikada bir piyasa taraması

# İki görevi de arka planda aynı anda başlatıyoruz (Dinleme + Piyasa Taraması)
threading.Thread(target=telegram_listener, daemon=True).start()
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
        
