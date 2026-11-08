import ccxt
import requests
import pandas as pd
import yfinance as yf
import time
import threading
import os
import sqlite3
from datetime import datetime
from flask import Flask

TELEGRAM_BOT_TOKEN = "9147785620:AAGDSk6n_dppdsFt0xsGKlnoD8rCHfp3rdo"
TELEGRAM_CHAT_ID = "1709473407"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "bot_signals.db")

app = Flask(__name__)

@app.route('/')
def home():
    return "Kalıcı Veritabanlı SMC Bot Kesintisiz Çalışıyor!"

def init_db():
    """Verilerin silinmemesi için SQLite veritabanı tablosu"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS signals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT,
            type TEXT,
            entry REAL,
            sl REAL,
            tp1 REAL,
            tp2 REAL,
            status TEXT,
            date TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Telegram bağlantı hatası: {e}")

def log_new_signal(symbol, fvg_type, entry, sl, tp1, tp2):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Aynı paritede açık sinyal var mı kontrol et
    cursor.execute("SELECT id FROM signals WHERE symbol = ? AND status = 'Açık'", (symbol,))
    if cursor.fetchone():
        conn.close()
        return
        
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute('''
        INSERT INTO signals (symbol, type, entry, sl, tp1, tp2, status, date)
        VALUES (?, ?, ?, ?, ?, ?, 'Açık', ?)
    ''', (symbol, fvg_type, entry, sl, tp1, tp2, date_str))
    conn.commit()
    conn.close()

def update_open_signals(current_prices):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, type, sl, tp1 FROM signals WHERE status = 'Açık'")
    open_sigs = cursor.fetchall()
    
    updated = False
    for sig in open_sigs:
        sig_id, sym, sig_type, sl, tp1 = sig
        if sym in current_prices:
            price = current_prices[sym]
            is_bullish = "Boğa" in sig_type
            
            if is_bullish:
                if price >= tp1:
                    cursor.execute("UPDATE signals SET status = 'Kazandı (TP1)' WHERE id = ?", (sig_id,))
                    send_telegram_message(TELEGRAM_CHAT_ID, f"🎯 *Hedef Başarıyla Ulaşıldı!*\nParite: `{sym}`\nDurum: Kazandı (TP1: {tp1:.4f})")
                    updated = True
                elif price <= sl:
                    cursor.execute("UPDATE signals SET status = 'Kaybetti (SL)' WHERE id = ?", (sig_id,))
                    send_telegram_message(TELEGRAM_CHAT_ID, f"🛑 *Stop-Loss Patladı!*\nParite: `{sym}`\nDurum: Kaybetti (SL: {sl:.4f})")
                    updated = True
            else:
                if price <= tp1:
                    cursor.execute("UPDATE signals SET status = 'Kazandı (TP1)' WHERE id = ?", (sig_id,))
                    send_telegram_message(TELEGRAM_CHAT_ID, f"🎯 *Hedef Başarıyla Ulaşıldı!*\nParite: `{sym}`\nDurum: Kazandı (TP1: {tp1:.4f})")
                    updated = True
                elif price >= sl:
                    cursor.execute("UPDATE signals SET status = 'Kaybetti (SL)' WHERE id = ?", (sig_id,))
                    send_telegram_message(TELEGRAM_CHAT_ID, f"🛑 *Stop-Loss Patladı!*\nParite: `{sym}`\nDurum: Kaybetti (SL: {sl:.4f})")
                    updated = True
                    
    if updated:
        conn.commit()
    conn.close()

def get_performance_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM signals")
    total = cursor.fetchone()[0]
    
    if total == 0:
        conn.close()
        return "📊 *Bot Performans İstatistiği*\n\nHenüz kaydedilmiş bir sinyal bulunmuyor."
        
    cursor.execute("SELECT COUNT(*) FROM signals WHERE status LIKE '%Kazandı%'")
    won = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM signals WHERE status LIKE '%Kaybetti%'")
    lost = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM signals WHERE status = 'Açık'")
    active = cursor.fetchone()[0]
    
    conn.close()
    
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
    try:
        data = yf.download("BTC-USD", period="1mo", interval="1h", progress=False)
        if data.empty or len(data) < 60:
            return "Backtest için yeterli veri alınamadı."

        df = pd.DataFrame({
            'open': data['Open'].values.flatten(),
            'high': data['High'].values.flatten(),
            'low': data['Low'].values.flatten(),
            'close': data['Close'].values.flatten(),
            'volume': data['Volume'].values.flatten() if 'Volume' in data else 0
        })
        
        df['sma50'] = df['close'].rolling(50).mean()
        
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = true_range.rolling(14).mean()
        
        total_signals = 0
        won_trades = 0
        lost_trades = 0

        for i in range(50, len(df) - 35):
            prev_candle = df.iloc[i-1]
            prev_prev_candle = df.iloc[i-3]
            curr_close = float(prev_candle['close'])
            sma_val = float(df['sma50'].iloc[i-1])
            curr_atr = float(df['atr'].iloc[i-1])
            
            if pd.isna(curr_atr) or curr_atr == 0:
                continue

            is_bullish_fvg = (float(prev_candle['low']) > float(prev_prev_candle['high'])) and (curr_close > sma_val)
            is_bearish_fvg = (float(prev_candle['high']) < float(prev_prev_candle['low'])) and (curr_close < sma_val)
            
            if is_bullish_fvg or is_bearish_fvg:
                total_signals += 1
                trade_result = "Açık"
                
                if is_bullish_fvg:
                    fvg_support = float(prev_prev_candle['high'])
                    confirmed = False
                    entry = fvg_support
                    
                    for j in range(i, min(i + 35, len(df))):
                        future_row = df.iloc[j]
                        if float(future_row['low']) <= fvg_support and float(future_row['close']) > float(future_row['open']):
                            confirmed = True
                            entry = float(future_row['close'])
                            break
                    
                    if not confirmed:
                        continue
                        
                    sl = entry - (1.5 * curr_atr)
                    tp1 = entry + (2.5 * (entry - sl))
                    
                    for j in range(i, min(i + 35, len(df))):
                        future_row = df.iloc[j]
                        if float(future_row['high']) >= tp1:
                            trade_result = "Kazandı"
                            break
                        elif float(future_row['low']) <= sl:
                            trade_result = "Kaybetti"
                            break

                elif is_bearish_fvg:
                    fvg_resistance = float(prev_prev_candle['low'])
                    confirmed = False
                    entry = fvg_resistance
                    
                    for j in range(i, min(i + 35, len(df))):
                        future_row = df.iloc[j]
                        if float(future_row['high']) >= fvg_resistance and float(future_row['close']) < float(future_row['open']):
                            confirmed = True
                            entry = float(future_row['close'])
                            break
                    
                    if not confirmed:
                        continue
                        
                    sl = entry + (1.5 * curr_atr)
                    tp1 = entry - (2.5 * (sl - entry))
                    
                    for j in range(i, min(i + 35, len(df))):
                        future_row = df.iloc[j]
                        if float(future_row['low']) <= tp1:
                            trade_result = "Kazandı"
                            break
                        elif float(future_row['high']) >= sl:
                            trade_result = "Kaybetti"
                            break

                if trade_result == "Kazandı":
                    won_trades += 1
                elif trade_result == "Kaybetti":
                    lost_trades += 1

        closed_trades = won_trades + lost_trades
        win_rate = (won_trades / closed_trades * 100) if closed_trades > 0 else 0
        
        return (
            f"👑 *ATR Onaylı Profesyonel Backtest (BTC)*\n\n"
            f"• Taranan Mum: `{len(df)} adet`\n"
            f"• Toplam Sinyal: `{total_signals}`\n"
            f"• Sonuçlanan: `{closed_trades}`\n"
            f"• Kazanan (TP): `{won_trades}` 🟢\n"
            f"• Kaybeden (SL): `{lost_trades}` 🔴\n"
            f"🏆 *Gerçekçi Başarı Oranı:* `%{win_rate:.1f}`"
        )
    except Exception as e:
        return f"Backtest hatası: {e}"

def advanced_smc_analysis(df, timeframe):
    if len(df) < 50:
        return "Yetersiz Veri", False, 0, 0, 0, 0

    df['sma50'] = df['close'].rolling(50).mean()
    
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()

    current_close = float(df['close'].iloc[-1])
    sma_val = float(df['sma50'].iloc[-1])
    atr = float(df['atr'].iloc[-1]) if not pd.isna(df['atr'].iloc[-1]) else current_close * 0.01

    fvg_signal = "Denge Bölgesi"
    is_valid_fvg = False
    
    if (float(df['low'].iloc[-1]) > float(df['high'].iloc[-3])) and (current_close > sma_val):
        fvg_signal = "🟢 Boğa FVG (ATR Onaylı)"
        is_valid_fvg = True
    elif (float(df['high'].iloc[-1]) < float(df['low'].iloc[-3])) and (current_close < sma_val):
        fvg_signal = "🔴 Ayı FVG (ATR Onaylı)"
        is_valid_fvg = True

    entry = current_close
    if "Boğa" in fvg_signal:
        sl = entry - (1.5 * atr)
        risk = entry - sl
        tp1 = entry + (2.5 * risk)
        tp2 = entry + (3.5 * risk)
    elif "Ayı" in fvg_signal:
        sl = entry + (1.5 * atr)
        risk = sl - entry
        tp1 = entry - (2.5 * risk)
        tp2 = entry - (3.5 * risk)
    else:
        sl, tp1, tp2 = 0, 0, 0

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
            
            if is_fvg:
                msg = (
                    f"🚀 *Pro Kripto Sinyal*\n\n"
                    f"📊 *Parite:* `{symbol}`\n"
                    f"💲 *Fiyat:* `{last_close}`\n"
                    f"📈 *Değişim:* `%{change:.2f}`\n"
                    f"🧠 *Analiz:* `{analysis}`\n\n"
                    f"🎯 *İşlem Seviyeleri (ATR):*\n"
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
            
            if is_fvg:
                msg = (
                    f"📈 *Pro Piyasa Sinyal*\n\n"
                    f"📊 *Varlık:* `{name}`\n"
                    f"💲 *Fiyat:* `{last_close:.2f}`\n"
                    f"📈 *Değişim:* `%{change:.2f}`\n"
                    f"🧠 *Analiz:* `{analysis}`\n\n"
                    f"🎯 *İşlem Seviyeleri (ATR):*\n"
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
    time.sleep(15)
    while True:
        print("--- Veritabanlı Tarama Başlatıldı ---")
        try:
            crypto_prices = scan_crypto_markets()
            market_prices = scan_traditional_markets()
            all_prices = {**crypto_prices, **market_prices}
            update_open_signals(all_prices)
        except Exception as e:
            print(f"Döngü hatası: {e}")
        print("--- Tarama Tamamlandı ---")
        time.sleep(600)

def telegram_listener():
    offset = 0
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            response = requests.get(url, timeout=35)
            data = response.json()
            
            if data.get("ok"):
                for result in data.get("result", []):
                    offset = result["update_id"] + 1
                    message = result.get("message", {})
                    chat_id = message.get("chat", {}).get("id")
                    text = message.get("text", "").strip()
                    
                    if text.startswith("/start"):
                        send_telegram_message(chat_id, "🤖 Kalıcı Veritabanlı SMC Bot aktif!\n• /istatistik -> Canlı başarı oranını gösterir.\n• /backtest -> Profesyonel test raporunu sunar.")
                    elif text.startswith("/istatistik"):
                        stats = get_performance_stats()
                        send_telegram_message(chat_id, stats)
                    elif text.startswith("/backtest"):
                        send_telegram_message(chat_id, "⏳ Profesyonel backtest simülasyonu çalıştırılıyor...")
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
    
