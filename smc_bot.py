import ccxt
import requests
import pandas as pd
import yfinance as yf
import time
import threading
import os
import json
from datetime import datetime
from flask import Flask

TELEGRAM_BOT_TOKEN = "9147785620:AAGDSk6n_dppdsFt0xsGKlnoD8rCHfp3rdo"
TELEGRAM_CHAT_ID = "1709473407"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "signals_log.json")

app = Flask(__name__)

@app.route('/')
def home():
    return "Kesin Çözüm SMC Bot Aktif!"

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

def load_signals():
    if not os.path.exists(LOG_FILE):
        return []
    try:
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_signals(signals):
    try:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(signals, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"Log kayıt hatası: {e}")

def log_new_signal(symbol, fvg_type, entry, sl, tp1, tp2):
    signals = load_signals()
    for s in signals:
        if s["symbol"] == symbol and s["status"] == "Açık":
            return
            
    new_sig = {
        "id": len(signals) + 1,
        "symbol": symbol,
        "type": fvg_type,
        "entry": entry,
        "sl": sl,
        "tp1": tp1,
        "tp2": tp2,
        "status": "Açık",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    signals.append(new_sig)
    save_signals(signals)

def update_open_signals(current_prices):
    signals = load_signals()
    updated = False
    
    for sig in signals:
        if sig["status"] == "Açık":
            sym = sig["symbol"]
            if sym in current_prices:
                price = current_prices[sym]
                is_bullish = "Boğa" in sig["type"]
                
                if is_bullish:
                    if price >= sig["tp1"]:
                        sig["status"] = "Kazandı (TP1)"
                        updated = True
                        send_telegram_message(TELEGRAM_CHAT_ID, f"🎯 *Hedef Başarıyla Ulaşıldı!*\nParite: `{sym}`\nDurum: Kazandı (TP1: {sig['tp1']:.4f})")
                    elif price <= sig["sl"]:
                        sig["status"] = "Kaybetti (SL)"
                        updated = True
                        send_telegram_message(TELEGRAM_CHAT_ID, f"🛑 *Stop-Loss Patladı!*\nParite: `{sym}`\nDurum: Kaybetti (SL: {sig['sl']:.4f})")
                else:
                    if price <= sig["tp1"]:
                        sig["status"] = "Kazandı (TP1)"
                        updated = True
                        send_telegram_message(TELEGRAM_CHAT_ID, f"🎯 *Hedef Başarıyla Ulaşıldı!*\nParite: `{sym}`\nDurum: Kazandı (TP1: {sig['tp1']:.4f})")
                    elif price >= sig["sl"]:
                        sig["status"] = "Kaybetti (SL)"
                        updated = True
                        send_telegram_message(TELEGRAM_CHAT_ID, f"🛑 *Stop-Loss Patladı!*\nParite: `{sym}`\nDurum: Kaybetti (SL: {sig['sl']:.4f})")
                        
    if updated:
        save_signals(signals)

def get_performance_stats():
    signals = load_signals()
    total = len(signals)
    if total == 0:
        return "📊 *Bot Performans İstatistiği*\n\nHenüz kaydedilmiş bir sinyal bulunmuyor."
        
    won = sum(1 for s in signals if "Kazandı" in s["status"])
    lost = sum(1 for s in signals if "Kaybetti" in s["status"])
    active = sum(1 for s in signals if s["status"] == "Açık")
    
    closed = won + lost
    win_rate = (won / closed * 100) if closed > 0 else 0
    
    return (
        f"📊 *Bot Performans ve Başarı İstatistiği*\n\n"
        f"• Toplam Sinyal: `{total}`\n"
        f"• Sonuçlanan İşlem: `{closed}`\n"
        f"• Açık Sinyaller: `{active}`\n"
        f"• Kazanan (TP): `{won}` 🟢\n"
        f"• Kaybeden (SL): `{lost}` 🔴\n"
        f"🏆 *Başarı Oranı (Win Rate):* `%{win_rate:.1f}`"
    )

def run_backtest_simulation():
    """Genişletilmiş pencere ve optimize edilmiş oranlarla kesin çözüm simülasyonu"""
    try:
        data = yf.download("BTC-USD", period="1mo", interval="1h", progress=False)
        if data.empty or len(data) < 50:
            return "Backtest için yeterli veri alınamadı."

        df = pd.DataFrame({
            'open': data['Open'].values.flatten(),
            'high': data['High'].values.flatten(),
            'low': data['Low'].values.flatten(),
            'close': data['Close'].values.flatten(),
            'volume': data['Volume'].values.flatten() if 'Volume' in data else 0
        })
        
        df['sma50'] = df['close'].rolling(50).mean()
        df['body'] = abs(df['close'] - df['open'])
        df['avg_body'] = df['body'].rolling(20).mean()
        
        total_signals = 0
        won_trades = 0
        lost_trades = 0

        # 48 mumluk (2 günlük) gelecek penceresi bırakıyoruz
        for i in range(50, len(df) - 48):
            window_df = df.iloc[i-25:i].copy()
            current_close = float(df['close'].iloc[i-1])
            sma_val = float(df['sma50'].iloc[i-1])
            
            current_body = float(df['body'].iloc[i-1])
            avg_body = float(df['avg_body'].iloc[i-1])
            is_displacement = current_body > (avg_body * 1.3)

            is_bullish_fvg = (window_df['low'].iloc[-1] > window_df['high'].iloc[-3]) and (current_close > sma_val) and is_displacement
            is_bearish_fvg = (window_df['high'].iloc[-1] < window_df['low'].iloc[-3]) and (current_close < sma_val) and is_displacement
            
            if is_bullish_fvg or is_bearish_fvg:
                total_signals += 1
                entry = current_close
                recent_low = window_df['low'].iloc[-5:-1].min()
                recent_high = window_df['high'].iloc[-5:-1].max()
                
                future_candles = df.iloc[i:i+48]
                trade_result = "Açık"
                
                if is_bullish_fvg:
                    sl = recent_low - (recent_low * 0.01)
                    risk = entry - sl
                    if risk <= 0: risk = entry * 0.01
                    tp1 = entry + (risk * 1.5) # Gerçekçi 1:1.5 hedef
                    
                    for _, row in future_candles.iterrows():
                        hit_tp = row['high'] >= tp1
                        hit_sl = row['low'] <= sl
                        if hit_tp and not hit_sl:
                            trade_result = "Kazandı"
                            break
                        elif hit_sl and not hit_tp:
                            trade_result = "Kaybetti"
                            break
                        elif hit_tp and hit_sl:
                            trade_result = "Kaybetti"
                            break

                elif is_bearish_fvg:
                    sl = recent_high + (recent_high * 0.01)
                    risk = sl - entry
                    if risk <= 0: risk = entry * 0.01
                    tp1 = entry - (risk * 1.5)
                    
                    for _, row in future_candles.iterrows():
                        hit_tp = row['low'] <= tp1
                        hit_sl = row['high'] >= sl
                        if hit_tp and not hit_sl:
                            trade_result = "Kazandı"
                            break
                        elif hit_sl and not hit_tp:
                            trade_result = "Kaybetti"
                            break
                        elif hit_tp and hit_sl:
                            trade_result = "Kaybetti"
                            break

                if trade_result == "Kazandı":
                    won_trades += 1
                elif trade_result == "Kaybetti":
                    lost_trades += 1

        closed_trades = won_trades + lost_trades
        win_rate = (won_trades / closed_trades * 100) if closed_trades > 0 else 0
        
        return (
            f"🚀 *Gerçekçi Backtest Raporu (BTC)*\n\n"
            f"• Taranan Mum: `{len(df)} adet`\n"
            f"• Toplam Sinyal: `{total_signals}`\n"
            f"• Sonuçlanan: `{closed_trades}`\n"
            f"• Kazanan (TP): `{won_trades}` 🟢\n"
            f"• Kaybeden (SL): `{lost_trades}` 🔴\n"
            f"🏆 *Gerçekçi Başarı Oranı:* `%{win_rate:.1f}`"
        )
    except Exception as e:
        return f"Backtest hatası: {e}"

def calculate_risk_reward(df, fvg_type, current_price):
    recent_low = df['low'].iloc[-5:-1].min()
    recent_high = df['high'].iloc[-5:-1].max()
    
    if "Boğa" in fvg_type:
        entry = current_price
        stop_loss = recent_low - (recent_low * 0.01)
        risk = entry - stop_loss
        if risk <= 0: risk = entry * 0.01
        tp1 = entry + (risk * 1.5)
        tp2 = entry + (risk * 2.5)
        return entry, stop_loss, tp1, tp2
    elif "Ayı" in fvg_type:
        entry = current_price
        stop_loss = recent_high + (recent_high * 0.01)
        risk = stop_loss - entry
        if risk <= 0: risk = entry * 0.01
        tp1 = entry - (risk * 1.5)
        tp2 = entry - (risk * 2.5)
        return entry, stop_loss, tp1, tp2
    return current_price, 0, 0, 0

def advanced_smc_analysis(df, timeframe):
    if len(df) < 50:
        return "Yetersiz Veri", False, 0, 0, 0, 0

    df['sma50'] = df['close'].rolling(50).mean()
    df['body'] = abs(df['close'] - df['open'])
    df['avg_body'] = df['body'].rolling(20).mean()
    
    current_close = float(df['close'].iloc[-1])
    sma_val = float(df['sma50'].iloc[-1])
    current_body = float(df['body'].iloc[-1])
    avg_body = float(df['avg_body'].iloc[-1])
    is_displacement = current_body > (avg_body * 1.3)

    fvg_signal = "Denge Bölgesi"
    is_valid_fvg = False
    
    if (df['low'].iloc[-1] > df['high'].iloc[-3]) and (current_close > sma_val) and is_displacement:
        fvg_signal = "🟢 Boğa FVG (Trend & İtki)"
        is_valid_fvg = True
    elif (df['high'].iloc[-1] < df['low'].iloc[-3]) and (current_close < sma_val) and is_displacement:
        fvg_signal = "🔴 Ayı FVG (Trend & İtki)"
        is_valid_fvg = True

    current_price = float(df['close'].iloc[-1])
    entry, sl, tp1, tp2 = calculate_risk_reward(df, fvg_signal, current_price)

    return fvg_signal, is_valid_fvg, entry, sl, tp1, tp2

def scan_crypto_markets():
    exchange = ccxt.binance()
    symbols = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']
    current_prices = {}
    
    for symbol in symbols:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=100)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            last_close = float(df['close'].iloc[-1])
            prev_close = float(df['close'].iloc[-2])
            change = ((last_close - prev_close) / prev_close) * 100
            current_prices[symbol] = last_close
            
            analysis, is_fvg, entry, sl, tp1, tp2 = advanced_smc_analysis(df, '1h')
            
            msg = (
                f"🚀 *Pro Kripto Sinyal*\n\n"
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
                    f"• Hedef 1 (TP1): `{tp1:.4f}`\n"
                    f"• Hedef 2 (TP2): `{tp2:.4f}`"
                )
                log_new_signal(symbol, analysis, entry, sl, tp1, tp2)
            
            send_telegram_message(TELEGRAM_CHAT_ID, msg)
            time.sleep(2)
        except Exception as e:
            print(f"Kripto hata ({symbol}): {e}")
                
    return current_prices

def scan_traditional_markets():
    assets = {
        "BIST: THYAO": "THYAO.IS",
        "BIST: EREGL": "EREGL.IS",
        "Forex: EUR/USD": "EURUSD=X",
        "Emtia: Altın (XAUUSD)": "GC=F"
    }
    current_prices = {}
    
    for name, ticker in assets.items():
        try:
            data = yf.download(ticker, period="10d", interval="1h", progress=False)
            if data.empty or len(data) < 50:
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
            current_prices[name] = last_close
            
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
                log_new_signal(name, analysis, entry, sl, tp1, tp2)
            
            send_telegram_message(TELEGRAM_CHAT_ID, msg)
            time.sleep(2)
        except Exception as e:
            print(f"Piyasa hata ({name}): {e}")
            
    return current_prices

def bot_loop():
    time.sleep(10)
    while True:
        print("--- Gerçekçi Çözüm Tarama Başlatıldı ---")
        crypto_prices = scan_crypto_markets()
        market_prices = scan_traditional_markets()
        
        all_prices = {**crypto_prices, **market_prices}
        update_open_signals(all_prices)
        
        print("--- Tarama Tamamlandı ---\n")
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
                    text = message.get("text", "").strip()
                    
                    if text.startswith("/start"):
                        send_telegram_message(chat_id, "🤖 Gerçekçi Çözümlü SMC Bot aktif!\n• /istatistik -> Canlı başarı oranını gösterir.\n• /backtest -> Profesyonel test raporunu sunar.")
                    elif text.startswith("/istatistik"):
                        stats = get_performance_stats()
                        send_telegram_message(chat_id, stats)
                    elif text.startswith("/backtest"):
                        send_telegram_message(chat_id, "⏳ Gerçekçi backtest simülasyonu çalıştırılıyor...")
                        bt_result = run_backtest_simulation()
                        send_telegram_message(chat_id, bt_result)
        except Exception as e:
            print(f"Dinleme hatası: {e}")
        time.sleep(2)

threading.Thread(target=telegram_listener, daemon=True).start()
threading.Thread(target=bot_loop, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
                    
