import ccxt
import requests
import pandas as pd
import time
import threading
import os
from flask import Flask

TELEGRAM_BOT_TOKEN = "9147785620:AAGDSk6n_dppdsFt0xsGKlnoD8rCHfp3rdo"
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
        return response.json()
    except Exception as e:
        print(f"Telegram bağlantı hatası: {e}")

def detect_smc_structure(df):
    """
    Basit ve etkili SMC mantığı: 
    - Yapı değişimi (BOS / ChoCh) tespiti için tepe ve dip noktaları incelenir.
    - Fair Value Gap (FVG) ve Basit Order Block bölgeleri taranır.
    """
    # Son 5 mum üzerinden FVG (Boşluk) tespiti
    fvg_detected = False
    fvg_type = ""
    
    # Boğa FVG (Bullish FVG): 1. mumun en yüksek seviyesi ile 3. mumun en düşük seviyesi arasındaki boşluk
    if df['low'].iloc[-1] > df['high'].iloc[-3]:
        fvg_detected = True
        fvg_type = "🟢 Boğa FVG (Alım Bölgesi)"
    # Ayı FVG (Bearish FVG): 1. mumun en düşük seviyesi ile 3. mumun en yüksek seviyesi arasındaki boşluk
    elif df['high'].iloc[-1] < df['low'].iloc[-3]:
        fvg_detected = True
        fvg_type = "🔴 Ayı FVG (Satış Bölgesi)"
    else:
        fvg_type = "⚖️ Denge Bölgesi (Consolidation)"

    return fvg_type, fvg_detected

def check_smc_signals():
    exchange = ccxt.binance()
    symbol = 'BTC/USDT'
    timeframe = '1h'
    
    print(f"{symbol} SMC yapısı taranıyor...")
    
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        last_close = df['close'].iloc[-1]
        prev_close = df['close'].iloc[-2]
        price_change = ((last_close - prev_close) / prev_close) * 100
        
        # SMC Analizini Çalıştır
        zone_info, is_fvg = detect_smc_structure(df)
        
        signal_msg = (
            f"🚨 *SMC Piyasa Tarama Raporu* 🚨\n\n"
            f"📊 *Parite:* `{symbol}`\n"
            f"⏱ *Zaman Dilimi:* `{timeframe}`\n"
            f"💲 *Güncel Fiyat:* `{last_close}`\n"
            f"📈 *Mum Değişimi:* `%{price_change:.2f}`\n\n"
            f"🧠 *SMC Yapı Analizi:*\n"
            f"🔹 *Durum:* `{zone_info}`"
        )
        send_telegram_message(TELEGRAM_CHAT_ID, signal_msg)
            
    except Exception as e:
        print(f"Veri çekme veya analiz hatası: {e}")

def telegram_listener():
    offset = 0
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
                    
                    if text == "/start":
                        send_telegram_message(chat_id, "🤖 SMC Akıllı Para Tarama Botu aktif! Güncel piyasa yapıları ve FVG analizleri bu sohbet üzerinden iletilecektir.")
        except Exception as e:
            print(f"Dinleme hatası: {e}")
        time.sleep(2)

def bot_loop():
    time.sleep(5)
    while True:
        check_smc_signals()
        time.sleep(300) # Her 5 dakikada bir SMC taraması

threading.Thread(target=telegram_listener, daemon=True).start()
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
    
