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
    return "Pro SMC & Likidite Botu 7/24 Aktif!"

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

def advanced_smc_analysis(df):
    """
    1-3 Özellikleri Entegre Edilmiş Gelişmiş SMC Analizi:
    - Likidite Taraması (Liquidity Sweep)
    - Hacim Filtresi (Volume SMA)
    - FVG (Fair Value Gap) Tespiti
    """
    if len(df) < 25:
        return "Yetersiz Veri", False

    # Hacim Filtresi (Son mum hacmi, son 20 mumun ortalama hacminin üstünde mi?)
    if 'volume' in df.columns:
        avg_volume = df['volume'].iloc[-21:-1].mean()
        current_volume = df['volume'].iloc[-1]
        is_high_volume = current_volume > (avg_volume * 1.2)
    else:
        is_high_volume = True # Hacim verisi olmayan piyasalar için esnetilir

    # Likidite Taraması (Sweep): Fiyat önceki yüksek/düşük seviyeyi kırıp geri döndü mü?
    prev_high = df['high'].iloc[-5:-1].max()
    prev_low = df['low'].iloc[-5:-1].min()
    current_close = df['close'].iloc[-1]
    
    sweep_status = "Normal Seyir"
    if current_close < prev_low:
        sweep_status = "💧 Satıcı Likiditesi Alındı (Alt Dip Patlatıldı)"
    elif current_close > prev_high:
        sweep_status = "⚡ Alıcı Likiditesi Alındı (Üst Tepe Patlatıldı)"

    # FVG Tespiti
    fvg_signal = "Denge Bölgesi"
    is_valid_fvg = False
    
    if df['low'].iloc[-1] > df['high'].iloc[-3]:
        fvg_signal = "🟢 Boğa FVG (Alım Bölgesi)"
        is_valid_fvg = True
    elif df['high'].iloc[-1] < df['low'].iloc[-3]:
        fvg_signal = "🔴 Ayı FVG (Satış Bölgesi)"
        is_valid_fvg = True

    # Sonuç değerlendirmesi
    if is_valid_fvg and is_high_volume:
        analysis_result = f"{fvg_signal} + 📊 Yüksek Hacimli Kurumsal Hareket"
    elif sweep_status != "Normal Seyir":
        analysis_result = f"{sweep_status} | {fvg_signal}"
    else:
        analysis_result = f"⚖️ {fvg_signal} (Hacim Normal)"

    return analysis_result, is_valid_fvg

def scan_crypto_markets():
    exchange = ccxt.binance()
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    
    for symbol in symbols:
        try:
            print(f"Kripto taranıyor: {symbol}")
            # 1 saatlik ve 4 saatlik yapı simülasyonu için 1h veri çekilir
            ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=50)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            last_close = df['close'].iloc[-1]
            prev_close = df['close'].iloc[-2]
            change = ((last_close - prev_close) / prev_close) * 100
            
            analysis, _ = advanced_smc_analysis(df)
            
            msg = (
                f"🚀 *Pro Kripto SMC Raporu*\n\n"
                f"📊 *Parite:* `{symbol}`\n"
                f"💲 *Fiyat:* `{last_close}`\n"
                f"📈 *Değişim:* `%{change:.2f}`\n"
                f"🧠 *Gelişmiş Analiz:* `{analysis}`"
            )
            send_telegram_message(TELEGRAM_CHAT_ID, msg)
            time.sleep(2)
        except Exception as e:
            print(f"Kripto hata ({symbol}): {e}")

def scan_traditional_markets():
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
            
            if data.empty or len(data) < 25:
                continue
                
            df = pd.DataFrame({
                'open': data['Open'].values.flatten(),
                'high': data['High'].values.flatten(),
                'low': data['Low'].values.flatten(),
                'close': data['Close'].values.flatten(),
                'volume': data['Volume'].values.flatten() if 'Volume' in data else 0
            })
            
            last_close = float(df['close'].iloc[-1])
            prev_close = float(df['close'].iloc[-2])
            change = ((last_close - prev_close) / prev_close) * 100
            
            analysis, _ = advanced_smc_analysis(df)
            
            msg = (
                f"📈 *Pro Piyasa SMC Raporu*\n\n"
                f"📊 *Varlık:* `{name}`\n"
                f"💲 *Fiyat:* `{last_close:.2f}`\n"
                f"📈 *Değişim:* `%{change:.2f}`\n"
                f"🧠 *Gelişmiş Analiz:* `{analysis}`"
            )
            send_telegram_message(TELEGRAM_CHAT_ID, msg)
            time.sleep(2)
        except Exception as e:
            print(f"Piyasa hata ({name}): {e}")

def bot_loop():
    time.sleep(10)
    while True:
        print("--- Gelişmiş Çoklu Piyasa Taraması Başlatıldı ---")
        scan_crypto_markets()
        scan_traditional_markets()
        print("--- Tarama Tamamlandı ---")
        time.sleep(600) # 10 dakikada bir tarama

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
                        send_telegram_message(chat_id, "🤖 Pro SMC & Likidite Tarama Botu aktif! Gelişmiş analizler iletiliyor.")
        except Exception as e:
            print(f"Dinleme hatası: {e}")
        time.sleep(2)

threading.Thread(target=telegram_listener, daemon=True).start()
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
            
