import ccxt
import requests
import pandas as pd
import yfinance as yf
import time
import threading
import os
from flask import Flask

TELEGRAM_BOT_TOKEN = "9147785620:AAGDSk6n_dppdsFt0xsGKlnoD8rCHfp3rdo"
TELEGRAM_CHAT_ID = "1709473407"

app = Flask(__name__)

@app.route('/')
def home():
    return "Çoklu Piyasa SMC Bot 7/24 Aktif ve Çalışıyor!"

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

def detect_fvg(df):
    """
    Fair Value Gap (FVG) ve Basit Yapı Analizi
    """
    if len(df) < 3:
        return "Yetersiz Veri", False
        
    if df['low'].iloc[-1] > df['high'].iloc[-3]:
        return "🟢 Boğa FVG (Alım Bölgesi)", True
    elif df['high'].iloc[-1] < df['low'].iloc[-3]:
        return "🔴 Ayı FVG (Satış Bölgesi)", True
    else:
        return "⚖️ Denge Bölgesi (Consolidation)", False

def scan_crypto_markets():
    exchange = ccxt.binance()
    # Kripto Pariteleri (Bitcoin ve Altcoinler)
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    for symbol in symbols:
        try:
            print(f"Kripto taranıyor: {symbol}")
            ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=50)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            last_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            change = ((last_close - prev_close) / prev_close) * 100
            
            zone, _ = detect_fvg(df)
            
            msg = (
                f"🪙 *Kripto SMC Raporu*\n\n"
                f"📊 *Parite:* `{symbol}`\n"
                f"💲 *Fiyat:* `{last_close}`\n"
                f"📈 *Değişim:* `%{change:.2f}`\n"
                f"🧠 *Analiz:* `{zone}`"
            )
            send_telegram_message(TELEGRAM_CHAT_ID, msg)
            time.sleep(2) # Telegram spam koruması için kısa bekleme
        except Exception as e:
            print(f"Kripto hata ({symbol}): {e}")

def scan_traditional_markets():
    # BIST ve Forex sembolleri (Yahoo Finance formatı)
    # BIST için .IS eklenir (Örn: THYAO.IS, GARAN.IS)
    # Forex/Emtia için (EURUSD=X, XAUUSD=X veya GC=F)
    assets = {
        "BIST: THYAO": "THYAO.IS",
        "BIST: EREGL": "EREGL.IS",
        "Forex: EUR/USD": "EURUSD=X",
        "Emtia: Altın (XAUUSD)": "GC=F"
    }
    
    for name, ticker in assets.items():
        try:
            print(f"Geleneksel piyasa taranıyor: {name}")
            data = yf.download(ticker, period="5d", interval="1h", progress=False)
            
            if data.empty or len(data) < 3:
                continue
                
            # yfinance çoklu kolon yapısını tekliye indirgeme
            df = pd.DataFrame({
                'open': data['Open'].values.flatten(),
                'high': data['High'].values.flatten(),
                'low': data['Low'].values.flatten(),
                'close': data['Close'].values.flatten()
            })
            
            last_close = float(df['close'].iloc[-1])
            prev_close = float(df['close'].iloc[-2])
            change = ((last_close - prev_close) / prev_close) * 100
            
            zone, _ = detect_fvg(df)
            
            msg = (
                f"📈 *Piyasa / Döviz SMC Raporu*\n\n"
                f"📊 *Varlık:* `{name}`\n"
                f"💲 *Fiyat:* `{last_close:.2f}`\n"
                f"📈 *Değişim:* `%{change:.2f}`\n"
                f"🧠 *Analiz:* `{zone}`"
            )
            send_telegram_message(TELEGRAM_CHAT_ID, msg)
            time.sleep(2)
        except Exception as e:
            print(f"Piyasa hata ({name}): {e}")

def bot_loop():
    time.sleep(10)
    while True:
        print("--- Genel Piyasa Taraması Başlatılıyor ---")
        scan_crypto_markets()
        scan_traditional_markets()
        print("--- Tarama Tamamlandı, bekleniyor ---")
        time.sleep(600) # Tüm piyasalar bittikten sonra 10 dakika bekle

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
                        send_telegram_message(chat_id, "🤖 Çoklu Piyasa (Kripto, BIST, Forex) SMC Botu aktif! Tüm taramalar bu sohbet üzerinden iletilecektir.")
        except Exception as e:
            print(f"Dinleme hatası: {e}")
        time.sleep(2)

# Arka plan görevleri
threading.Thread(target=telegram_listener, daemon=True).start()
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
                  
