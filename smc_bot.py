import ccxt
import requests
import pandas as pd
import yfinance as yf
import time
import threading
import os
import sqlite3
import io
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from datetime import datetime
from flask import Flask

TELEGRAM_BOT_TOKEN = "9147785620:AAGDSk6n_dppdsFt0xsGKlnoD8rCHfp3rdo"
TELEGRAM_CHAT_ID = "1709473407"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "bot_signals.db")

app = Flask(__name__)

@app.route('/')
def home():
    return "Anlık PnL Takipli Hedge Fund Terminali Aktif!"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, type TEXT, entry REAL, sl REAL, tp1 REAL, tp2 REAL, status TEXT, risk_amount REAL, score INTEGER, date TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS account (id INTEGER PRIMARY KEY, balance REAL)")
    cursor.execute("SELECT balance FROM account WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO account (id, balance) VALUES (1, 1000.0)")
    conn.commit()
    conn.close()

init_db()

def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.json()
    except Exception as e:
        print(f"Telegram bağlantı hatası: {e}")

def send_telegram_photo(chat_id, photo_bytes, caption):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    files = {'photo': ('equity.png', photo_bytes, 'image/png')}
    data = {'chat_id': chat_id, 'caption': caption, 'parse_mode': 'Markdown'}
    try:
        requests.post(url, data=data, files=files, timeout=15)
    except Exception as e:
        print(f"Telegram fotoğraf hatası: {e}")

def get_current_balance():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM account WHERE id = 1")
    b = cursor.fetchone()[0]
    conn.close()
    return b

def update_balance(amount_change):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM account WHERE id = 1")
    current = cursor.fetchone()[0]
    new_balance = current + amount_change
    cursor.execute("UPDATE account SET balance = ? WHERE id = 1", (new_balance,))
    conn.commit()
    conn.close()
    return new_balance

def log_new_signal(symbol, fvg_type, entry, sl, tp1, tp2, score):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM signals WHERE symbol = ? AND status = 'Acik'", (symbol,))
    if cursor.fetchone():
        conn.close()
        return
    current_bal = get_current_balance()
    risk_amount = current_bal * 0.02
    date_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    cursor.execute("INSERT INTO signals (symbol, type, entry, sl, tp1, tp2, status, risk_amount, score, date) VALUES (?, ?, ?, ?, ?, ?, 'Acik', ?, ?, ?)", (symbol, fvg_type, entry, sl, tp1, tp2, risk_amount, score, date_str))
    conn.commit()
    conn.close()

def update_open_signals(current_prices):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT id, symbol, type, sl, tp1, risk_amount FROM signals WHERE status = 'Acik'")
    open_sigs = cursor.fetchall()
    updated = False
    for sig in open_sigs:
        sig_id, sym, sig_type, sl, tp1, risk_amount = sig
        if sym in current_prices:
            price = current_prices[sym]
            is_bullish = "Boga" in sig_type or "Boğa" in sig_type
            if is_bullish:
                if price >= tp1:
                    profit = risk_amount * 2.5
                    new_bal = update_balance(profit)
                    cursor.execute("UPDATE signals SET status = 'Kazandi (TP1)' WHERE id = ?", (sig_id,))
                    send_telegram_message(TELEGRAM_CHAT_ID, f"🎯 *HEDEF ULAŞILDI!*\n• Varlık: `{sym}`\n• Durum: Kazandı 🟢\n• Net Kâr: `+${profit:.2f}`\n• Bakiye: `${new_bal:.2f}`")
                    updated = True
                elif price <= sl:
                    loss = risk_amount
                    new_bal = update_balance(-loss)
                    cursor.execute("UPDATE signals SET status = 'Kaybetti (SL)' WHERE id = ?", (sig_id,))
                    send_telegram_message(TELEGRAM_CHAT_ID, f"🛑 *STOP-LOSS!*\n• Varlık: `{sym}`\n• Durum: Kaybetti 🔴\n• Zarar: `-${loss:.2f}`\n• Bakiye: `${new_bal:.2f}`")
                    updated = True
            else:
                if price <= tp1:
                    profit = risk_amount * 2.5
                    new_bal = update_balance(profit)
                    cursor.execute("UPDATE signals SET status = 'Kazandi (TP1)' WHERE id = ?", (sig_id,))
                    send_telegram_message(TELEGRAM_CHAT_ID, f"🎯 *HEDEF ULAŞILDI!*\n• Varlık: `{sym}`\n• Durum: Kazandı 🟢\n• Net Kâr: `+${profit:.2f}`\n• Bakiye: `${new_bal:.2f}`")
                    updated = True
                elif price >= sl:
                    loss = risk_amount
                    new_bal = update_balance(-loss)
                    cursor.execute("UPDATE signals SET status = 'Kaybetti (SL)' WHERE id = ?", (sig_id,))
                    send_telegram_message(TELEGRAM_CHAT_ID, f"🛑 *STOP-LOSS!*\n• Varlık: `{sym}`\n• Durum: Kaybetti 🔴\n• Zarar: `-${loss:.2f}`\n• Bakiye: `${new_bal:.2f}`")
                    updated = True
    if updated:
        conn.commit()
    conn.close()

def get_equity_curve_chart():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT date, status, risk_amount FROM signals WHERE status LIKE '%Kazandi%' OR status LIKE '%Kaybetti%' ORDER BY id ASC")
    rows = cursor.fetchall()
    conn.close()
    balances = [1000.0]
    current_b = 1000.0
    for r in rows:
        d, status, risk = r
        if "Kazandi" in status:
            current_b += (risk * 2.5)
        else:
            current_b -= risk
        balances.append(current_b)
    plt.figure(figsize=(8, 4))
    plt.plot(balances, marker='o', color='#2ecc71' if balances[-1] >= 1000 else '#e74c3c', linewidth=2)
    plt.title("Sanal Portföy Bakiye Eğrisi", fontsize=12, fontweight='bold', color='white')
    plt.xlabel("İşlem Sırası", color='white')
    plt.ylabel("Bakiye ($)", color='white')
    plt.grid(True, linestyle='--', alpha=0.3)
    ax = plt.gca()
    ax.set_facecolor('#1e1e1e')
    plt.gcf().patch.set_facecolor('#121212')
    ax.tick_params(colors='white')
    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', facecolor=plt.gcf().get_facecolor())
    buf.seek(0)
    plt.close()
    return buf.getvalue()

def get_active_signals_text():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, type, entry, sl, tp1, score, date FROM signals WHERE status = 'Acik'")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return "📂 *Aktif Pozisyon Yok*\n\nŞu an açık sinyal bulunmuyor."
    
    msg = "📂 *Açık Pozisyonlar ve Anlık PnL:*\n\n"
    ex = ccxt.binance()
    
    for r in rows:
        sym, stype, entry, sl, tp1, score, date = r
        score_val = score if score else 80
        fmt = ".4f" if entry < 1 else ".2f"
        
        # Anlık fiyatı çekip PnL hesaplayalım
        current_price = entry
        try:
            if "/" in sym:
                ticker = ex.fetch_ticker(sym)
                current_price = ticker['last']
            elif "BIST:" in sym or "Forex:" in sym or "Emtia:" in sym:
                # Basit simülasyon veya son bilinen fiyat
                current_price = entry 
        except:
            current_price = entry

        is_bullish = "Boga" in stype or "Boğa" in stype
        if is_bullish:
            pnl_pct = ((current_price - entry) / entry) * 100
        else:
            pnl_pct = ((entry - current_price) / entry) * 100
            
        pnl_emoji = "🟢" if pnl_pct >= 0 else "🔴"
        
        msg += f"• **{sym}** (`{stype}` | Skor: %{score_val})\n"
        msg += f"  - Giriş: `{entry:{fmt}}` | Anlık: `{current_price:{fmt}}`\n"
        msg += f"  - Durum: {pnl_emoji} `%{pnl_pct:+.2f}`\n"
        msg += f"  - Stop: `{sl:{fmt}}` | Hedef: `{tp1:{fmt}}`\n\n"
        
    return msg

def get_past_signals_text():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT symbol, type, entry, status, score, date FROM signals WHERE status != 'Acik' ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    conn.close()
    if not rows:
        return "📂 *Geçmiş İşlem Yok*\n\nHenüz sonuçlanmış bir işlem bulunmuyor."
    msg = "📂 *Son Sonuçlanan 10 İşlem:*\n\n"
    for r in rows:
        sym, stype, entry, status, score, date = r
        score_val = score if score else 80
        fmt = ".4f" if entry < 1 else ".2f"
        emoji = "🟢" if "Kazandi" in status or "Kazandı" in status else "🔴"
        msg += f"• **{sym}** (`{stype}` | Skor: %{score_val})\n  - Giriş: `{entry:{fmt}}` | Durum: {emoji} `{status}`\n  - Tarih: `{date}`\n\n"
    return msg

def get_performance_stats():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM signals")
    total = cursor.fetchone()[0]
    current_bal = get_current_balance()
    net_profit_pct = ((current_bal - 1000.0) / 1000.0) * 100
    if total == 0:
        conn.close()
        return f"📊 *İstatistikler*\n• Başlangıç: $1000.00\n• Güncel Bakiye: ${current_bal:.2f}\n• Kâr: %{net_profit_pct:.2f}\n\nİşlem yok."
    cursor.execute("SELECT COUNT(*) FROM signals WHERE status LIKE '%Kazandi%'")
    won = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM signals WHERE status LIKE '%Kaybetti%'")
    lost = cursor.fetchone()[0]
    conn.close()
    closed = won + lost
    win_rate = (won / closed * 100) if closed > 0 else 0
    return f"📊 *Bakiye ve Performans*\n\n💰 Başlangıç: $1000.00\n💰 Güncel Bakiye: ${current_bal:.2f}\n📈 Net Kâr: %{net_profit_pct:+.2f}\n\n• Toplam Sinyal: {total}\n• Kazanan: {won} 🟢\n• Kaybeden: {lost} 🔴\n🏆 Başarı Oranı: %{win_rate:.1f}"

def run_backtest_simulation():
    try:
        data = yf.download("BTC-USD", period="1mo", interval="1h", progress=False)
        if data.empty or len(data) < 60:
            return "Backtest için yeterli veri yok."
        df = pd.DataFrame({'open': data['Open'].values.flatten(), 'high': data['High'].values.flatten(), 'low': data['Low'].values.flatten(), 'close': data['Close'].values.flatten(), 'volume': data['Volume'].values.flatten() if 'Volume' in data else 0})
        df['sma50'] = df['close'].rolling(50).mean()
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        df['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
        total_signals, won_trades, lost_trades, sim_balance = 0, 0, 0, 1000.0
        for i in range(50, len(df) - 35):
            prev_candle, prev_prev_candle = df.iloc[i-1], df.iloc[i-3]
            curr_close, sma_val, curr_atr = float(prev_candle['close']), float(df['sma50'].iloc[i-1]), float(df['atr'].iloc[i-1])
            if pd.isna(curr_atr) or curr_atr == 0: continue
            is_bullish = (float(prev_candle['low']) > float(prev_prev_candle['high'])) and (curr_close > sma_val)
            is_bearish = (float(prev_candle['high']) < float(prev_prev_candle['low'])) and (curr_close < sma_val)
            if is_bullish or is_bearish:
                total_signals += 1
                trade_result, risk_amt = "Acik", sim_balance * 0.02
                if is_bullish:
                    fvg_support, confirmed, entry = float(prev_prev_candle['high']), False, float(prev_prev_candle['high'])
                    for j in range(i, min(i + 35, len(df))):
                        if float(df.iloc[j]['low']) <= fvg_support and float(df.iloc[j]['close']) > float(df.iloc[j]['open']):
                            confirmed, entry = True, float(df.iloc[j]['close'])
                            break
                    if not confirmed: continue
                    sl, tp1 = entry - (1.5 * curr_atr), entry + (2.5 * (entry - (entry - (1.5 * curr_atr))))
                    for j in range(i, min(i + 35, len(df))):
                        if float(df.iloc[j]['high']) >= tp1: trade_result = "Kazandi"; break
                        elif float(df.iloc[j]['low']) <= sl: trade_result = "Kaybetti"; break
                else:
                    fvg_res, confirmed, entry = float(prev_prev_candle['low']), False, float(prev_prev_candle['low'])
                    for j in range(i, min(i + 35, len(df))):
                        if float(df.iloc[j]['high']) >= fvg_res and float(df.iloc[j]['close']) < float(df.iloc[j]['open']):
                            confirmed, entry = True, float(df.iloc[j]['close'])
                            break
                    if not confirmed: continue
                    sl, tp1 = entry + (1.5 * curr_atr), entry - (2.5 * (1.5 * curr_atr))
                    for j in range(i, min(i + 35, len(df))):
                        if float(df.iloc[j]['low']) <= tp1: trade_result = "Kazandi"; break
                        elif float(df.iloc[j]['high']) >= sl: trade_result = "Kaybetti"; break
                if trade_result == "Kazandi": won_trades += 1; sim_balance += (risk_amt * 2.5)
                elif trade_result == "Kaybetti": lost_trades += 1; sim_balance -= risk_amt
        closed = won_trades + lost_trades
        win_rate = (won_trades / closed * 100) if closed > 0 else 0
        net_ret = ((sim_balance - 1000.0) / 1000.0) * 100
        return f"👑 *Backtest Raporu*\n• Bakiye: `${sim_balance:.2f}`\n• Kâr: `%{net_ret:+.2f}`\n• Sinyal: {total_signals} | Kazanan: {won_trades} 🟢 | Kaybeden: {lost_trades} 🔴\n• Başarı Oranı: %{win_rate:.1f}"
    except Exception as e:
        return f"Backtest hatası: {e}"

def calculate_confidence_score(df_1h, df_4h, is_bullish):
    score = 70
    try:
        if 'volume' in df_1h.columns and len(df_1h) >= 20:
            avg_vol = df_1h['volume'].rolling(20).mean().iloc[-1]
            curr_vol = df_1h['volume'].iloc[-1]
            if not pd.isna(avg_vol) and avg_vol > 0 and curr_vol > (avg_vol * 1.5):
                score += 15
            elif not pd.isna(avg_vol) and avg_vol > 0 and curr_vol > avg_vol:
                score += 8
        if df_4h is not None and len(df_4h) >= 20:
            sma_4h = df_4h['close'].rolling(20).mean().iloc[-1]
            close_4h = df_4h['close'].iloc[-1]
            dist_pct = abs(close_4h - sma_4h) / sma_4h * 100
            if dist_pct > 1.0:
                score += 10
            else:
                score += 5
        score = min(max(score, 70), 98)
    except:
        score = 80
    return score

def advanced_smc_analysis(df_1h, df_4h=None):
    if len(df_1h) < 50: return "Yetersiz", False, 0, 0, 0, 0, 0
    
    if df_4h is not None and len(df_4h) >= 20:
        sma_4h = df_4h['close'].rolling(20).mean().iloc[-1]
        close_4h = df_4h['close'].iloc[-1]
        trend_4h_bullish = close_4h > sma_4h
    else:
        trend_4h_bullish = None

    df_1h['sma50'] = df_1h['close'].rolling(50).mean()
    high_low, high_close, low_close = df_1h['high'] - df_1h['low'], abs(df_1h['high'] - df_1h['close'].shift()), abs(df_1h['low'] - df_1h['close'].shift())
    df_1h['atr'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    cc, sma, atr = float(df_1h['close'].iloc[-1]), float(df_1h['sma50'].iloc[-1]), float(df_1h['atr'].iloc[-1]) if not pd.isna(df_1h['atr'].iloc[-1]) else float(df_1h['close'].iloc[-1]) * 0.01
    
    vol_ok = True
    if 'volume' in df_1h.columns and len(df_1h) >= 20:
        avg_vol = df_1h['volume'].rolling(20).mean().iloc[-1]
        curr_vol = df_1h['volume'].iloc[-1]
        if not pd.isna(avg_vol) and avg_vol > 0:
            vol_ok = curr_vol >= (avg_vol * 0.8)

    if float(df_1h['low'].iloc[-1]) > float(df_1h['high'].iloc[-3]) and cc > sma and vol_ok:
        if trend_4h_bullish is False:
            return "Denge", False, 0, 0, 0, 0, 0
        score = calculate_confidence_score(df_1h, df_4h, True)
        return "🟢 Boğa FVG", True, cc, cc - (1.5 * atr), cc + (2.5 * (1.5 * atr)), cc + (3.5 * (1.5 * atr)), score
    elif float(df_1h['high'].iloc[-1]) < float(df_1h['low'].iloc[-3]) and cc < sma and vol_ok:
        if trend_4h_bullish is True:
            return "Denge", False, 0, 0, 0, 0, 0
        score = calculate_confidence_score(df_1h, df_4h, False)
        return "🔴 Ayı FVG", True, cc, cc + (1.5 * atr), cc - (2.5 * (1.5 * atr)), cc - (3.5 * (1.5 * atr)), score
        
    return "Denge", False, 0, 0, 0, 0, 0

def scan_all_markets_manually():
    send_telegram_message(TELEGRAM_CHAT_ID, "🔍 *Anlık PnL Takipli Tarama Başlatıldı...*")
    cp, mp = scan_crypto_markets(), scan_traditional_markets()
    update_open_signals({**cp, **mp})
    send_telegram_message(TELEGRAM_CHAT_ID, "✅ *Tarama Tamamlandı!*")

def scan_crypto_markets():
    ex = ccxt.binance()
    ex.load_markets()
    symbols = [
        'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'BNB/USDT', 'XRP/USDT', 
        'ADA/USDT', 'AVAX/USDT', 'DOGE/USDT', 'DOT/USDT', 'MATIC/USDT', 
        'LINK/USDT', 'NEAR/USDT', 'UNI/USDT', 'ATOM/USDT', 'LTC/USDT', 
        'FTM/USDT', 'ICP/USDT', 'RENDER/USDT', 'SUI/USDT', 'APT/USDT'
    ]
    prices = {}
    for sym in symbols:
        try:
            df_1h = pd.DataFrame(ex.fetch_ohlcv(sym, '1h', limit=100), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df_4h = pd.DataFrame(ex.fetch_ohlcv(sym, '4h', limit=50), columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            
            lc, prices[sym] = float(df_1h['close'].iloc[-1]), float(df_1h['close'].iloc[-1])
            analysis, is_fvg, entry, sl, tp1, tp2, score = advanced_smc_analysis(df_1h, df_4h)
            if is_fvg:
                risk_amt = get_current_balance() * 0.02
                s_units = (risk_amt / abs(entry - sl)) if abs(entry - sl) > 0 else 0
                fmt = ".4f" if lc < 1 else ".2f"
                send_telegram_message(TELEGRAM_CHAT_ID, f"🚨 *KRİPTO SİNYAL: {sym}*\n• Fiyat: `{lc:{fmt}}`\n• Strateji: `{analysis}`\n• 🧠 *Yapay Zekâ Güven Skoru:* `%{score}`\n• Giriş: `{entry:{fmt}}` | SL: `{sl:{fmt}}` | TP: `{tp1:{fmt}}`\n• Boyut: `{s_units:.4f} adet`")
                log_new_signal(sym, analysis, entry, sl, tp1, tp2, score)
            time.sleep(0.5)
        except Exception as e: print(e)
    return prices

def scan_traditional_markets():
    assets = {
        "BIST: THYAO": "THYAO.IS", "BIST: EREGL": "EREGL.IS", "BIST: GARAN": "GARAN.IS",
        "BIST: ASELS": "ASELS.IS", "BIST: AKBNK": "AKBNK.IS", "BIST: KCHOL": "KCHOL.IS",
        "BIST: SAHOL": "SAHOL.IS", "BIST: TUPRS": "TUPRS.IS", "BIST: BIMAS": "BIMAS.IS",
        "BIST: YKBNK": "YKBNK.IS", "Forex: EUR/USD": "EURUSD=X", "Forex: GBP/USD": "GBPUSD=X",
        "Forex: USD/JPY": "USDJPY=X", "Forex: AUD/USD": "AUDUSD=X", "Forex: USD/CHF": "USDCHF=X",
        "Forex: USD/CAD": "USDCAD=X", "Emtia: Altın (XAUUSD)": "GC=F", "Emtia: Gümüş (XAGUSD)": "SI=F",
        "Emtia: Ham Petrol": "CL=F"
    }
    prices = {}
    for name, ticker in assets.items():
        try:
            data_1h = yf.download(ticker, period="10d", interval="1h", progress=False)
            data_4h = yf.download(ticker, period="1.mo", interval="4h", progress=False) if hasattr(yf, 'download') else pd.DataFrame()
            
            if data_1h.empty or len(data_1h) < 50: continue
            
            df_1h = pd.DataFrame({'open': data_1h['Open'].values.flatten(), 'high': data_1h['High'].values.flatten(), 'low': data_1h['Low'].values.flatten(), 'close': data_1h['Close'].values.flatten(), 'volume': data_1h['Volume'].values.flatten() if 'Volume' in data_1h else 0})
            df_4h = pd.DataFrame({'open': data_4h['Open'].values.flatten(), 'high': data_4h['High'].values.flatten(), 'low': data_4h
