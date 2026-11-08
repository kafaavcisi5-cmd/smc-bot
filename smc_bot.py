import os
import time
import logging
import ccxt
import yfinance as yf
import pandas as pd
import numpy as np
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

# Logging ayarları
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# 1. VERİTABANI BAĞLANTISI (SUPABASE)
# ==========================================
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    logger.warning("DATABASE_URL çevre değişkeni bulunamadı! Yerel SQLite veritabanına bağlanılıyor.")

engine = create_engine(DATABASE_URL) if DATABASE_URL else create_engine("sqlite:///bot_local.db")
Base = declarative_base()

class TradeRecord(Base):
    __tablename__ = 'trade_records'
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    action = Column(String, nullable=False)  # BUY / SELL
    price = Column(Float, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

# ==========================================
# 2. MAKSİMUM GENİŞLETİLMİŞ PARİTE LİSTELERİ
# ==========================================
CRYPTO_SYMBOLS = [
    'BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'XRP/USDT', 'AVAX/USDT', 
    'ADA/USDT', 'DOGE/USDT', 'LINK/USDT', 'DOT/USDT', 'NEAR/USDT', 
    'MATIC/USDT', 'UNI/USDT', 'ATOM/USDT', 'LTC/USDT', 'FTM/USDT', 
    'ARB/USDT', 'OP/USDT', 'SUI/USDT', 'INJ/USDT', 'RNDR/USDT',
    'SHIB/USDT', 'PEPE/USDT', 'TIA/USDT', 'APT/USDT',
    'FET/USDT', 'ICP/USDT', 'FIL/USDT', 'GRT/USDT',
    'STX/USDT', 'IMX/USDT', 'ALGO/USDT', 'KAS/USDT',
    'AXS/USDT', 'SAND/USDT', 'MANA/USDT', 'CRV/USDT', 'AAVE/USDT'
]

FOREX_SYMBOLS = [
    'EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X', 
    'USDCAD=X', 'NZDUSD=X', 'USDCHF=X', 'EURGBP=X', 
    'EURJPY=X', 'GBPJPY=X', 'GC=F'  # GC=F -> Ons Altın (XAUUSD)
]

BIST_SYMBOLS = [
    'THYAO.IS', 'EREGL.IS', 'GARAN.IS', 'AKBNK.IS', 'SISE.IS',
    'KCHOL.IS', 'SAHOL.IS', 'ASELS.IS', 'BIMAS.IS', 'TUPRS.IS',
    'YKBNK.IS', 'ISCTR.IS', 'PETKM.IS'
]

# ==========================================
# 3. FVG (FAIR VALUE GAP) VE TREND STRATEJİSİ
# ==========================================
def calculate_fvg_and_trend(df):
    try:
        if len(df) < 10:
            return None

        highs = df['High'].values
        lows = df['Low'].values
        closes = df['Close'].values

        sma_trend = closes[-1] > np.mean(closes[-20:])

        for i in range(len(df) - 3, len(df) - 1):
            if i < 2:
                continue
            if lows[i+1] > highs[i-1] and sma_trend:
                return "BUY"
            elif highs[i+1] < lows[i-1] and not sma_trend:
                return "SELL"

        return None
    except Exception as e:
        logger.error(f"FVG hesaplama hatası: {e}")
        return None

def save_trade_to_db(symbol, action, price):
    try:
        session = Session()
        new_trade = TradeRecord(symbol=symbol, action=action, price=price)
        session.add(new_trade)
        session.commit()
        session.close()
        logger.info(f"İşlem veritabanına kaydedildi -> {symbol} | {action} | {price}")
    except Exception as e:
        logger.error(f"Veritabanı kayıt hatası: {e}")

# ==========================================
# 4. PİYASA TARAMA DÖNGÜSÜ
# ==========================================
def scan_markets():
    logger.info("Genişletilmiş piyasa taraması başlatılıyor...")
    
    # Kripto Taraması
    exchange = ccxt.binance()
    for symbol in CRYPTO_SYMBOLS:
        try:
            ohlcv = exchange.fetch_ohlcv(symbol, timeframe='1h', limit=50)
            df = pd.DataFrame(ohlcv, columns=['Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume'])
            signal = calculate_fvg_and_trend(df)
            if signal:
                current_price = float(df['Close'].iloc[-1])
                save_trade_to_db(symbol, signal, current_price)
                logger.info(f"Sinyal Yakalandı (Kripto): {symbol} - {signal}")
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"Kripto tarama hatası ({symbol}): {e}")

    # Forex ve Ons Altın Taraması
    for symbol in FOREX_SYMBOLS:
        try:
            data = yf.download(symbol, interval='1h', period='5d', progress=False)
            if not data.empty and len(data) > 10:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                signal = calculate_fvg_and_trend(data)
                if signal:
                    current_price = float(data['Close'].iloc[-1])
                    save_trade_to_db(symbol, signal, current_price)
                    logger.info(f"Sinyal Yakalandı (Forex): {symbol} - {signal}")
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"Forex tarama hatası ({symbol}): {e}")

    # BİST Taraması
    for symbol in BIST_SYMBOLS:
        try:
            data = yf.download(symbol, interval='1h', period='5d', progress=False)
            if not data.empty and len(data) > 10:
                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)
                signal = calculate_fvg_and_trend(data)
                if signal:
                    current_price = float(data['Close'].iloc[-1])
                    save_trade_to_db(symbol, signal, current_price)
                    logger.info(f"Sinyal Yakalandı (BİST): {symbol} - {signal}")
            time.sleep(0.3)
        except Exception as e:
            logger.error(f"BİST tarama hatası ({symbol}): {e}")

# ==========================================
# 5. TELEGRAM KOMUTLARI
# ==========================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Bot aktif!\n"
        "Genişletilmiş dev havuz (Kripto, Forex/Altın, BİST) ile 1h FVG ve Trend taramaları sorunsuz çalışıyor."
    )

async def durum(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        session = Session()
        count = session.query(TradeRecord).count()
        session.close()
        await update.message.reply_text(f"📊 Sistem Sağlık Durumu: Çalışıyor.\nBulut Veritabanındaki Toplam Kayıt: {count}")
    except Exception as e:
        await update.message.reply_text(f"Durum sorgulanırken hata oluştu: {e}")

async def tara(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Manuel tarama başlatıldı, geniş havuz inceleniyor...")
    scan_markets()
    await update.message.reply_text("✅ Tarama tamamlandı.")

# ==========================================
# 6. ANA ÇALIŞTIRMA BLOĞU
# ==========================================
def main():
    TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN çevre değişkeni bulunamadı!")
        return

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("durum", durum))
    application.add_handler(CommandHandler("tara", tara))

    logger.info("Bot başlatıldı, Telegram dinleniyor...")
    application.run_polling()

if __name__ == "__main__":
    main()
