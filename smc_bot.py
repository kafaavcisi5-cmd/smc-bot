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
    return "Pro R&R ve Zaman Dilimli SMC Bot Aktif!"

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

def calculate_risk_reward(df, fvg_type, current_price):
    """
    Otomatik Stop-Loss, Take-Profit ve Risk/Ödül (R:R 1:2 / 1:3) Hesaplama
    """
    recent_low = df['low'].iloc[-5:-1].min()
    recent_high = df['high'].iloc[-5:-1].max()
    
    if "Boğa" in fvg_type:
        entry = current_price
        stop_loss = recent_low - (recent_low * 0.002) # Güvenlik payı ile dip seviye
        risk = entry - stop_loss
        if risk <= 0: risk = entry * 0.01
        tp1 = entry + (risk * 2) # 1:2 R:R
        tp2 = entry + (risk * 3) # 1:3 R:R
        return entry, stop_loss, tp1, tp2
        
    elif "Ayı" in fvg_type:
        entry = current_price
        stop_loss = recent_high + (recent_high * 0.002) # Güvenlik payı ile tepe seviye
        risk = stop_loss - entry
        if risk <= 0: risk = entry * 0.01
        tp1 = entry - (risk * 2) # 1:2 R:R
        tp2 = entry - (risk * 3) # 1:3 R:R
        return entry, stop_loss, tp1, tp2
        
    return current_price, 0, 0, 0

def advanced_smc_analysis(df, timeframe):
    if len(df) < 25:
        return "Yetersiz Veri", False, 0, 0, 0, 0

    # Hacim Filtresi
    if 'volume' in df.columns:
        avg_volume = df['volume'].iloc[-21:-1].mean()
        current_volume = df['volume'].iloc[-1]
        is_high_volume = current_volume > (avg_volume * 1.1)
    else:
        is_high_volume = True

    # FVG Tespiti
    fvg_signal = "Denge Bölgesi"
    is_valid_fvg = False
    
    if df['low'].iloc[-1] > df['high'].iloc[-3]:
        fvg_signal = "🟢 Boğa FVG (Alım Bölgesi)"
        is_valid_fvg = True
    elif df['high'].iloc[-1] < df['low'].iloc[-3]:
        fvg_signal = "🔴 Ayı FVG (Satış Bölgesi)"
        is_valid_fvg = True

    current_price = float(df['close'].iloc[-1])
    entry, sl, tp1, tp2 = calculate_risk_reward(df, fvg_signal, current_price)

    analysis_result = f"{fvg_signal}"
    if is_high_volume and is_valid_fvg:
        analysis_result += " + 📊 Yüksek Hacim"

    return analysis_result, is_valid_fvg, entry, sl, tp1, tp2

def scan_crypto_markets():
    exchange = ccxt.binance()
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    timeframes = ['1h', '4h'] # Çoklu zaman dilimi taraması
    
    for symbol in symbols:
        for tf in timeframes:
            try:
                print(f"Kripto taranıyor: {symbol} [{tf}]")
                ohlcv = exchange.fetch_ohlcv(symbol, tf, limit=50)
                df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                
                last_close = df['close'].iloc[-1]
                prev_close = df['close'].iloc[-2]
                change = ((last_close - prev_close) / prev_close) * 100
                
                analysis, is_fvg, entry, sl, tp1, tp2 = advanced_smc_analysis(df, tf)
                
                # Sadece FVG veya önemli yapı yakalandığında detaylı R:R raporu gönder
                msg = (
                    f"🚀 *Pro Kripto Sinyal ({tf})*\n\n"
                    f"📊 *Parite:* `{symbol}`\n"
                    f"💲 *Fiyat:* `{last_close}`\n"
                    f"📈 *Değişim:* `%{change:.2f}`\n"
                    f"🧠 *Analiz:* `{analysis}`\n"
                )
                
                if is_fvg:
                    msg += (
                        f"\n🎯 *İşlem Seviyeleri (R:R):*\n"
                        f"• Giriş: `{entry:.4f}`\n"
                        f"• Stop-Loss (SL): `{sl:.4f}`\n"
                        f"• Hedef 1 (TP1 - 1:2): `{tp1:.4f}`\n"
                        f"• Hedef 2 (TP2 - 1:3): `{tp2:.4f}`"
                    )
                
                send_telegram_message(TELEGRAM_CHAT_ID, msg)
                time.sleep(2)
            except Exception as e:
                print(f"Kripto hata ({symbol} - {tf}): {e}")

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
            
            analysis, is_fvg, entry, sl, tp1, tp2 = advanced_smc_analysis(df, "1h")
            
            msg = (
                f"📈 *Pro Piyasa Sinyal*\n\n"
                f"📊 *Varlık:* `{name}`\n"
                f"💲 *Fiyat:* `{last_close:.2f}`\n"
                f"📈 *Değişim:* `%{change:.2f}`\n"
                f"🧠 *Analiz:* `{analysis}`\n"
            )
            
            if is_fvg:
                msg += (
                    f"\n🎯 *İşlem Seviyeleri (R:R):*\n"
                    f"• Giriş: `{entry:.2f}`\n"
                    f"• Stop-Loss (SL): `{sl:.2f}`\n"
                    f"• Hedef 1 (TP1): `{tp1:.2f}`\n"
                    f"• Hedef 2 (TP2): `{tp2:.2f}`"
                )
            
            send_telegram_message(TELEGRAM_CHAT_ID, msg)
            time.sleep(2)
        except Exception as e:
            print(f"Piyasa hata ({name}): {e}")

def bot_loop():
    time.sleep(10)
    while True:
        print("--- Çoklu Zaman Dilimli ve R:R Taraması Başlatıldı ---")
        scan_crypto_markets()
        scan_traditional_markets()
        print("--- Tarama Tamamlandı ---")
        time.sleep(600)

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
                        send_telegram_message(chat_id, "🤖 Pro R&R ve Zaman Dilimli SMC Bot aktif!")
        except Exception as e:
            print(f"Dinleme hatası: {e}")
        time.sleep(2)

threading.Thread(target=telegram_listener, daemon=True).start()
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
            
