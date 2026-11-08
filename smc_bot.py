import ccxt
import requests
import pandas as pd
import time

# Telegram Bot Ayarları
TELEGRAM_BOT_TOKEN = "9147785620:AAGDSk6n_dppdsFt0xsGKlnoD8rCHfp3rdo"
TELEGRAM_CHAT_ID = "1709473407"

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
        
        if abs(price_change) > 0.0:  # Test için eşiği düşük tuttuk
            signal_msg = (
                f"🚨 *SMC / Piyasa Alarmı!* 🚨\n\n"
                f"📊 *Parite:* `{symbol}`\n"
                f"⏱ *Zaman Dilimi:* `{timeframe}`\n"
                f"💡 *Durum:* Test sinyali / Fiyat hareketi tetiklendi!\n"
                f"💲 *Güncel Fiyat:* `{last_close}`\n"
                f"📈 *Değişim:* `%{price_change:.2f}`"
            )
            send_telegram_message(signal_msg)
            print("Sinyal Telegram'a gönderildi.")
        else:
            print("Koşul sağlanmadı.")
            
    except Exception as e:
        print(f"Veri çekme hatası: {e}")

if __name__ == "__main__":
    print("SMC Tarama Botu Çalıştı...")
    check_smc_signals()
  
