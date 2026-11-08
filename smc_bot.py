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
    return "Pro Trend Filtreli SMC Bot Aktif!"

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
    """SMA 50 Trend Filtreli Gerçekçi Backtest Simülasyonu"""
    try:
        data = yf.download("BTC-USD", period="2mo", interval="1h", progress=False)
        if data.empty or len(data) < 60:
            return "Backtest için yeterli veri alınamadı."

        df = pd.DataFrame({
            'open': data['Open'].values.flatten(),
            'high': data['High'].values.flatten(),
            'low': data['Low'].values.flatten(),
            'close': data['Close'].values.flatten(),
            'volume': data['Volume'].values.flatten() if 'Volume' in data else 0
        })
        
        # Trend Göstergesi (SMA 50)
        df['sma50'] = df['close'].rolling(50).mean()
        
        total_signals = 0
        won_trades = 0
        lost_trades = 0

        for i in range(50, len(df) - 20):
            window_df = df.iloc[i-25:i].copy()
            current_close = float(df['close'].iloc[i-1])
            sma_val = float(df['sma50'].iloc[i-1])
            
            avg_volume = window_df['volume'].iloc[-21:-1].mean()
            current_volume = window_df['volume'].iloc[-1]
            is_high_volume = current_volume > (avg_volume * 1.1)

            # Trend Filtreli FVG Kontrolü
            is_bullish_fvg = (window_df['low'].iloc[-1] > window_df['high'].iloc[-3]) and (current_close > sma_val)
            is_bearish_fvg = (window_df['high'].iloc[-1] < window_df['low'].iloc[-3]) and (current_close < sma_val)
            
            if (is_bullish_fvg or is_bearish_fvg) and is_high_volume:
                total_signals += 1
                entry = current_close
                recent_low = window_df['low'].iloc[-5:-1].min()
                recent_high = window_df['high'].iloc[-5:-1].max()
                
                if is_bullish_fvg:
                    sl = recent_low - (recent_low * 0.01)
                    risk = entry - sl
                    if risk <= 0: risk = entry * 0.01
                    tp1 = entry + (risk * 2)
                    
                    future_candles = df.iloc[i:i+20]
                    trade_result = "Açık"
                    for _, row in future_candles.iterrows():
                        if row['high'] >= tp1:
                            trade_result = "Kazandı"
                            break
                        elif row['low'] <= sl:
                            trade_result = "Kaybetti"
                            break
                    if trade_result == "Kazandı": won_trades += 1
                    elif trade_result == "Kaybetti": lost_trades += 1

                elif is_bearish_fvg:
                    sl = recent_high + (recent_high * 0.01)
                    risk = sl - entry
                    if risk <= 0: risk = entry * 0.01
                    tp1 = entry - (risk * 2)
                    
                    future_candles = df.iloc[i:i+20]
                    trade_result = "Açık"
                    for _, row in future_candles.iterrows():
                        if row['low'] <= tp1:
                            trade_result = "Kazandı"
                            break
                        elif row['high'] >= sl:
                            trade_result = "Kaybetti"
                            break
                    if trade_result == "Kazandı": won_trades += 1
                    elif trade_result == "Kaybetti": lost_trades += 1

        closed_trades = won_trades + lost_trades
        win_rate = (won_trades / closed_trades * 100) if closed_trades > 0 else 0
        
        return (
            f"📈 *Trend Filtreli Backtest Raporu (BTC)*\n\n"
            f"• Taranan Mum: `{len(df)} adet`\n"
            f"• Toplam Sinyal: `{total_signals}`\n"
            f"• Sonuçlanan: `{closed_trades}`\n"
            f"• Kazanan (TP): `{won_trades}` 🟢\n"
            f"• Kaybeden (SL): `{lost_trades}` 🔴\n"
            f"🏆 *Trend Filtreli Başarı Oranı:* `%{win_rate:.1f}`"
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
        tp1 = entry + (risk * 2)
        tp2 = entry + (risk * 3)
        return entry, stop_loss, tp1, tp2
    elif "Ayı" in fvg_type:
        entry = current_price
        stop_loss = recent_high + (recent_high * 0.01)
        risk = stop_loss - entry
        if risk <= 0: risk = entry * 0.01
        tp1 = entry - (risk * 2)
        tp2 = entry - (risk * 3)
        return entry, stop_loss, tp1, tp2
    return current_price, 0, 0, 0

def advanced_smc_analysis(df, timeframe):
    if len(df) < 50:
        return "Yetersiz Veri", False, 0, 0, 0, 0

    df['sma50'] = df['close'].rolling(50).mean()
    current_close = float(df['close'].iloc[-1])
    sma_val = float(df['sma50'].iloc[-1])

    if 'volume' in df.columns:
        avg_volume = df['volume'].iloc[-21:-1].mean()
        current_volume = df['volume'].iloc[-1]
    
