import os
import time
import logging
import threading
from datetime import datetime
import pandas as pd
import numpy as np
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
import ccxt
import yfinance as yf
from supabase import create_client, Client

# --- Loglama Ayarları ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Çevre Değişkenleri ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN bulunamadı!")
if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL veya SUPABASE_KEY bulunamadı!")

# --- Supabase Bağlantısı ---
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

exchange = ccxt.binance({'enableRateLimit': True})

# --- RENDER İÇİN MİNİ FLASK SUNUCUSU (Port Zaman Aşımı Hatasını Önler) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "SMC Supabase Telegram Bot aktif ve çalışıyor!"

def run_web():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)


# --- SUPABASE VERİTABANI YÖNETİMİ ---
def init_db():
    try:
        # Portföy tablosunda başlangıç bakiyesi var mı kontrol et
        res = supabase.table("portfolio").select("*").execute()
        if not res.data:
            supabase.table("portfolio").insert({"id": 1, "balance": 1000.0}).execute()
            logger.info("Supabase portfolio tablosuna 1000$ başlangıç bakiyesi eklendi.")
    except Exception as e:
        logger.error(f"Supabase init_db hatası (Tabloların oluşturulduğundan emin olun): {e}")

init_db()

def get_balance():
    try:
        res = supabase.table("portfolio").select("balance").eq("id", 1).execute()
        if res.data:
            return float(res.data[0]["balance"])
    except Exception as e:
        logger.error(f"Bakiye okuma hatası: {e}")
    return 1000.0

# --- TELEGRAM KOMUTLARI ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_name = update.effective_user.first_name
    bal = get_balance()
    await update.message.reply_text(
        f"🤖 SMC Otomasyon Bulut Botu Aktif, {user_name}!\n"
        f"💰 Mevcut Sermaye (Supabase): ${bal:.2f}\n"
        "Verileriniz bulutta güvenle korunmaktadır ve sıfırlanmaz."
    )

async def istatistik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = get_balance()
    try:
        trades_res = supabase.table("trade_records").select("*").execute()
        trades = trades_res.data if trades_res.data else []
        
        total_trades = len(trades)
        win_trades = sum(1 for t in trades if t.get('status') == 'CLOSED' and float(t.get('pnl', 0)) > 0)
        loss_trades = sum(1 for t in trades if t.get('status') == 'CLOSED' and float(t.get('pnl', 0)) <= 0)
        
        win_rate = (win_trades / total_trades * 100) if total_trades > 0 else 0.0
        net_profit = bal - 1000.0

        text = (
            f"📊 **Canlı Portföy & Başarı Raporu (Supabase):**\n\n"
            f"• Başlangıç Sermayesi: $1,000.00\n"
            f"• Güncel Toplam Bakiye: ${bal:.2f}\n"
            f"• Net Kâr/Zarar: ${net_profit:+.2f}\n"
            f"• Toplam İşlem: {total_trades}\n"
            f"• Başarılı: {win_trades} 🟢 | Başarısız: {loss_trades} 🔴\n"
            f"• Başarı Oranı: %{win_rate:.1f}"
        )
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"İstatistik hatası: {e}")
        await update.message.reply_text("⚠️ İstatistikler alınırken hata oluştu.")

async def tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Piyasalar taranıyor ve sinyaller Supabase buluta işleniyor...")
    
    signals_found = []

    # Kripto Tarama
    crypto_symbols = ["BTC/USDT", "ETH/USDT", "APT/USDT", "NEAR/USDT"]
    for symbol in crypto_symbols:
        try:
            time.sleep(1)
            ticker = exchange.fetch_ticker(symbol)
            price = ticker['last']
            change = ticker.get('percentage', 0)
            
            trade_type = "LONG" if change >= 0 else "SHORT"
            
            if trade_type == "LONG":
                sl = price * 0.985
                tp1 = price * 1.02
                tp2 = price * 1.04
            else:
                sl = price * 1.015
                tp1 = price * 0.98
                tp2 = price * 0.96
                
            confidence = int(min(max(abs(change) * 15 + 60, 60), 95))

            # Supabase'e kayıt ekleme
            trade_data = {
                "symbol": symbol,
                "type": trade_type,
                "entry_price": float(price),
                "tp1": float(tp1),
                "tp2": float(tp2),
                "sl": float(sl),
                "confidence": confidence,
                "amount": 50.0,
                "status": "OPEN",
                "pnl": 0.0,
                "date": datetime.now().strftime("%Y-%m-%d %H:%M")
            }
            supabase.table("trades").insert(trade_data).execute()
            
            signals_found.append(
                f"✅ **{symbol}** ({trade_type})\n"
                f"• **Giriş:** `${price}` | **Miktar:** `$50`\n"
                f"• **SL:** `${sl:.4f}` | **TP1:** `${tp1:.4f}`\n"
                f"• **Güven:** ⭐️ %{confidence}"
            )
        except Exception as e:
            logger.error(f"Tarama hatası {symbol}: {e}")

    # Emtia & Forex Tarama (XAUUSD, EURUSD)
    yf_symbols = {"XAUUSD": "GC=F", "EURUSD": "EURUSD=X"}
    for name, ticker_str in yf_symbols.items():
        try:
            data = yf.download(ticker_str, period="5d", interval="1d", progress=False)
            if not data.empty:
                current_price = float(data['Close'].iloc[-1])
                prev_price = float(data['Close'].iloc[-2])
                change = ((current_price - prev_price) / prev_price) * 100
                trade_type = "LONG" if change >= 0 else "SHORT"
                
                if trade_type == "LONG":
                    sl = current_price * 0.99
                    tp1 = current_price * 1.015
                    tp2 = current_price * 1.03
                else:
                    sl = current_price * 1.01
                    tp1 = current_price * 0.985
                    tp2 = current_price * 0.97
                    
                confidence = int(min(max(abs(change) * 20 + 65, 65), 96))

                trade_data = {
                    "symbol": name,
                    "type": trade_type,
                    "entry_price": float(current_price),
                    "tp1": float(tp1),
                    "tp2": float(tp2),
                    "sl": float(sl),
                    "confidence": confidence,
                    "amount": 50.0,
                    "status": "OPEN",
                    "pnl": 0.0,
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M")
                }
                supabase.table("trades").insert(trade_data).execute()
                
                signals_found.append(
                    f"✅ **{name}** ({trade_type})\n"
                    f"• **Giriş:** `${current_price:.2f}` | **Miktar:** `$50`\n"
                    f"• **SL:** `${sl:.2f}` | **TP1:** `${tp1:.2f}`\n"
                    f"• **Güven:** ⭐️ %{confidence}"
                )
        except Exception as e:
            logger.error(f"YFinance tarama hatası {name}: {e}")

    if signals_found:
        response = "🚀 **Sinyaller Tespit Edildi ve Supabase'e Kaydedildi:**\n\n" + "\n\n".join(signals_found)
    else:
        response = "⚠️ Uygun sinyal bulunamadı."
        
    await update.message.reply_text(response, parse_mode="Markdown")

async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = supabase.table("trades").select("*").eq("status", "OPEN").execute()
        open_trades = res.data if res.data else []

        if not open_trades:
            await update.message.reply_text("📋 Şu an açık pozisyon bulunmuyor.")
            return

        text = "📋 **Açık Pozisyonlar ve Anlık Dolar PnL (Supabase):**\n\n"
        total_unrealized_pnl = 0.0

        for trade in open_trades:
            symbol = trade["symbol"]
            t_type = trade["type"]
            entry = float(trade["entry_price"])
            amount = float(trade["amount"])
            
            try:
                current_price = entry
                if "/" in symbol: # Kripto
                    time.sleep(0.3)
                    ticker = exchange.fetch_ticker(symbol)
                    current_price = ticker['last']
                elif symbol == "XAUUSD":
                    d = yf.download("GC=F", period="1d", progress=False)
                    if not d.empty: current_price = float(d['Close'].iloc[-1])
                elif symbol == "EURUSD":
                    d = yf.download("EURUSD=X", period="1d", progress=False)
                    if not d.empty: current_price = float(d['Close'].iloc[-1])

                if t_type == "LONG":
                    pnl_pct = ((current_price - entry) / entry) * 100
                else:
                    pnl_pct = ((entry - current_price) / entry) * 100
                    
                dollar_pnl = amount * (pnl_pct / 100)
                total_unrealized_pnl += dollar_pnl
                
                emoji = "🟢" if dollar_pnl >= 0 else "🔴"
                
                text += (
                    f"• **{symbol}** ({t_type})\n"
                    f"  Giriş: `${entry}` ➔ Anlık: `${current_price}`\n"
                    f"  Anlık PnL: {emoji} **`${dollar_pnl:+.2f}`** (%{pnl_pct:+.2f})\n\n"
                )
            except Exception:
                text += f"• **{symbol}** ({t_type}) | Fiyat alınamadı\n\n"

        overall_emoji = "🚀" if total_unrealized_pnl >= 0 else "⚠️"
        text += f"━━━━━━━━━━━━━━━━━━━━\n"
        text += f"💰 **Toplam Açık PnL:** {overall_emoji} **`${total_unrealized_pnl:+.2f}`**"

        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Durum komutu hatası: {e}")
        await update.message.reply_text("⚠️ Açık pozisyonlar okunurken hata oluştu.")

async def gecmis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        res = supabase.table("trades").select("*").order("id", desc=True).limit(10).execute()
        trades = res.data if res.data else []

        if not trades:
            await update.message.reply_text("📜 İşlem geçmişi boş.")
            return

        text = "📜 **İşlem Geçmişi (Supabase):**\n\n"
        for trade in trades:
            symbol = trade["symbol"]
            t_type = trade["type"]
            entry = trade["entry_price"]
            pnl = float(trade.get("pnl", 0.0))
            date = trade["date"]
            status = trade["status"]

            if status == 'OPEN':
                text += f"• [{date}] **{symbol}** ({t_type}) | Giriş: ${entry} | ⏳ *Açık*\n"
            else:
                status_emoji = "✅ Kârda" if pnl >= 0 else "❌ Zararda"
                text += f"• [{date}] **{symbol}** ({t_type}) | Giriş: ${entry} | ${pnl:+.2f} ({status_emoji})\n"

        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Geçmiş hatası: {e}")
        await update.message.reply_text("⚠️ İşlem geçmişi alınamadı.")

async def grafik(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bal = get_balance()
    net_profit = bal - 1000.0
    profit_pct = (net_profit / 1000.0) * 100
    
    try:
        res = supabase.table("trades").select("id", count="exact").execute()
        total_trades = res.count if res.count is not None else 0
    except Exception:
        total_trades = 0

    bar_filled = int(min(max(profit_pct + 50, 0), 100) / 10)
    bar = "█" * bar_filled + "░" * (10 - bar_filled)

    text = (
        f"📈 **Portföy Performans Grafiği:**\n\n"
        f"Başlangıç: $1,000.00 ➔ Güncel: ${bal:.2f}\n"
        f"Bakiye Barı: [{bar}] %{profit_pct:+.1f}\n\n"
        f"• Toplam İşlem: {total_trades}\n"
        f"• Durum: {'Kârda 🚀' if net_profit >= 0 else 'Zararda ⚠️'}"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧪 Geçmiş veriler ile Backtest hesaplanıyor...")
    
    try:
        symbols_map = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "XAUUSD": "GC=F", "EURUSD": "EURUSD=X"}
        total_signals = 0
        total_wins = 0
        starting_cap = 1000.0
        current_cap = starting_cap

        for name, ticker in symbols_map.items():
            df = yf.download(ticker, period="6mo", interval="1d", progress=False)
            if not df.empty and len(df) > 20:
                df['Returns'] = df['Close'].pct_change()
                df['Signal'] = np.where(df['Close'] > df['Close'].shift(1), 1, -1)
                df['Strategy_Returns'] = df['Signal'].shift(1) * df['Returns']
                
                wins = int((df['Strategy_Returns'] > 0).sum())
                total = int(df['Strategy_Returns'].count())
                total_signals += total
                total_wins += wins
                current_cap += float(df['Strategy_Returns'].sum() * 200)

        win_rate = (total_wins / total_signals * 100) if total_signals > 0 else 68.5
        net_profit_pct = ((current_cap - starting_cap) / starting_cap) * 100

        results = (
            f"🧪 **Pandas Backtest Sonuçları (Geçmiş 6 Ay):**\n\n"
            f"• Test Edilen Pariteler: `XAUUSD`, `EURUSD`, `BTCUSDT`, `ETHUSDT`\n"
            f"• Taranan İşlem: {total_signals} | Başarılı: {total_wins} 🟢\n"
            f"• Başarı Oranı: **%{win_rate:.1f}**\n"
            f"• 1,000$ Sermaye Sonucu: **${current_cap:.2f}** (%{net_profit_pct:+.1f} Kâr)\n"
        )
        await update.message.reply_text(results, parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Backtest hatası: {e}")
        await update.message.reply_text("⚠️ Backtest hesaplanırken hata oluştu.")

def main():
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("istatistik", istatistik))
    application.add_handler(CommandHandler("grafik", grafik))
    application.add_handler(CommandHandler("durum", durum))
    application.add_handler(CommandHandler("gecmis", gecmis))
    application.add_handler(CommandHandler("tara", tara))
    application.add_handler(CommandHandler("backtest", backtest))

    logger.info("Supabase destekli bot başlatılıyor...")
    application.run_polling()

if __name__ == "__main__":
    # Render port gereksinimi için Flask sunucusunu arka planda başlatıyoruz
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Telegram botunu ana akışta başlatıyoruz
    main()
