"""
===============================================================================
SuperGrok Bot RDP Edition - Enhanced (Paper Trading + Real Trading + Trailing Stop)
Bot Trading Crypto berbasis Social Sentiment (Hybrid Python + Groq Cloud AI)

PERINGATAN PENTING:
- Groq (LLM) TIDAK bisa langsung mencari/mengakses X (Twitter). Groq hanya bisa
  menganalisis teks yang DIBERIKAN padanya. Untuk mendapatkan data X nyata,
  kamu perlu X API v2 (Bearer Token) atau scraper terpisah, lalu masukkan hasilnya
  ke Groq untuk dianalisis.
- Mode REAL TRADING menggunakan UANG ASLI dan sangat beresiko tinggi, khususnya
  memecoin (rugpull, likuiditas tipis, volatilitas ekstrem). Kode ini adalah
  TEMPLATE. Aktifkan REAL hanya jika sudah paham risiko dan telah menguji dengan
  PAPER TRADING terlebih dahulu.
- Trailing stop dieksekusi oleh Python (bukan Groq), berdasarkan data harga yang
  diambil dari yfinance (atau exchange jika diintegrasikan).

Arsitektur:
  - Python murni berjalan 24 jam di RDP: mengumpulkan data, menjalankan Groq AI,
    mengeksekusi BUY, dan mengelola trailing stop.
  - Groq Cloud API (llama3-8b-8192) sebagai otak analis teks (sentimen & deteksi viral).
  - Antarmuka: Dashboard web Streamlit tema gelap / cyberpunk.

Author: SuperGrok Bot RDP Edition
===============================================================================
"""

# -----------------------------------------------------------------------------
# PUSTAKA STANDAR
# -----------------------------------------------------------------------------
import os
import time
import json
import random
import threading
from datetime import datetime
from typing import List, Dict, Any, Optional

# Pustaka eksternal (harus diinstal terlebih dahulu via pip)
# pip install streamlit groq yfinance pandas python-dotenv
# Opsional untuk real trading: pip install ccxt requests
import streamlit as st
import yfinance as yf
import pandas as pd
from dotenv import load_dotenv

try:
    from groq import Groq
    GROQ_LIB_OK = True
except Exception:
    GROQ_LIB_OK = False

# CCXT (opsional, untuk real trading CEX). Diimpor bersembunyi agar tidak error
# jika belum diinstal dan pengguna masih menggunakan mode PAPER.
CCXT_AVAILABLE = False
try:
    import ccxt  # type: ignore
    CCXT_AVAILABLE = True
except Exception:
    CCXT_AVAILABLE = False

# -----------------------------------------------------------------------------
# KONFIGURASI HALAMAN STREAMLIT
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="SuperGrok Bot RDP Edition",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -----------------------------------------------------------------------------
# MUAT KONFIGURASI DARI .env
# -----------------------------------------------------------------------------
load_dotenv()

DEFAULT_SYMBOLS: List[str] = ["BTC-USD", "ETH-USD", "SOL-USD"]
INITIAL_VIRTUAL_BALANCE: float = 10000.0
SCAN_INTERVAL_SECONDS: int = 300          # 5 menit
GROQ_SLEEP_SECONDS: int = 2               # jeda anti rate-limit Groq gratis
SMA_WINDOW: int = 20                      # periode SMA
GROQ_MODEL: str = "llama3-8b-8192"

# Trading mode
TRADING_MODE: str = os.getenv("TRADING_MODE", "PAPER").upper()  # PAPER | REAL
TRAILING_STOP_PERCENT: float = float(os.getenv("TRAILING_STOP_PERCENT", "0.05"))
TRADE_AMOUNT_USD: float = float(os.getenv("TRADE_AMOUNT_USD", "100"))

# X API v2 (opsional)
X_API_BEARER_TOKEN: str = os.getenv("X_API_BEARER_TOKEN", "")
X_SEARCH_QUERY: str = os.getenv("X_SEARCH_QUERY", "BTC OR ETH OR SOL OR memecoin OR crypto")
X_MAX_RESULTS: int = int(os.getenv("X_MAX_RESULTS", "10"))

# Exchange (opsional, hanya untuk REAL)
EXCHANGE_ID: str = os.getenv("EXCHANGE_ID", "binance")
EXCHANGE_API_KEY: str = os.getenv("EXCHANGE_API_KEY", "")
EXCHANGE_API_SECRET: str = os.getenv("EXCHANGE_API_SECRET", "")
EXCHANGE_SANDBOX: bool = os.getenv("EXCHANGE_SANDBOX", "True").lower() == "true"

# -----------------------------------------------------------------------------
# BANNER PERINGATAN REAL TRADING (TAMPILKAN DI UI)
# -----------------------------------------------------------------------------
REAL_TRADING_WARNING = """
⚠️⚠️⚠️ PERINGATAN REAL TRADING ⚠️⚠️⚠️
Mode REAL TRADING menggunakan UANG ASLI.
• Groq TIDAK bisa langsung mencari di X; butuh X API v2 atau scraper terpisah.
• Memecoin sangat beresiko tinggi: rugpull, likuiditas tipis, volatilitas ekstrem.
• Trailing stop membantu melindungi laba, TAPI tidak menjamin profit.
• Aktifkan REAL hanya setelah menguji PAPER TRADING dan memahami risiko sepenuhnya.
• Anda sendiri bertanggung jawab atas segala kerugian finansial.
"""

# -----------------------------------------------------------------------------
# CSS CYBERPUNK / TEMA GELAP
# -----------------------------------------------------------------------------
CYBERPUNK_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700&family=Share+Tech+Mono&display=swap');
:root {
    --neon-cyan: #00f3ff;
    --neon-magenta: #ff00ff;
    --neon-green: #0aff00;
    --neon-red: #ff0033;
    --bg-dark: #05050a;
    --bg-panel: #0a0a12;
    --border-neon: rgba(0, 243, 255, 0.35);
}
.stApp { background-color: var(--bg-dark); color: var(--neon-cyan); font-family: 'Share Tech Mono', monospace; }
h1, h2, h3 { font-family: 'Orbitron', sans-serif; color: var(--neon-cyan) !important; text-shadow: 0 0 8px var(--neon-cyan); }
[data-testid="stMetricValue"] { font-family: 'Orbitron', sans-serif; color: var(--neon-green) !important; }
section[data-testid="stSidebar"] { background-color: var(--bg-panel); border-right: 2px solid var(--border-neon); font-family: 'Share Tech Mono', monospace; }
.stButton > button {
    background: linear-gradient(45deg, var(--bg-panel), #1a1a2e);
    color: var(--neon-cyan); border: 1px solid var(--border-neon);
    font-family: 'Orbitron', sans-serif; font-weight: 700; text-transform: uppercase;
    transition: all 0.3s ease; box-shadow: 0 0 10px rgba(0, 243, 255, 0.2);
}
.stButton > button:hover { background: var(--neon-cyan); color: #000; box-shadow: 0 0 20px var(--neon-cyan); }
.stCheckbox > label { font-family: 'Orbitron', sans-serif; color: var(--neon-cyan); text-transform: uppercase; font-size: 0.9rem; }
[data-testid="stDataFrame"] { background: var(--bg-panel); border: 1px solid var(--border-neon); }
.log-entry { font-family: 'Share Tech Mono', monospace; font-size: 0.85rem; padding: 6px 10px; margin: 4px 0; border-left: 3px solid var(--border-neon); background: rgba(10, 10, 18, 0.6); border-radius: 0 6px 6px 0; color: #e0e0e0; }
.log-success { border-left-color: var(--neon-green); color: var(--neon-green); }
.log-warning { border-left-color: #ffaa00; color: #ffaa00; }
.log-error { border-left-color: var(--neon-red); color: var(--neon-red); }
.log-danger { border-left-color: var(--neon-red); color: var(--neon-red); font-weight: bold; }
.log-info { border-left-color: var(--neon-cyan); color: var(--neon-cyan); }
.warning-banner {
    background: rgba(255, 0, 51, 0.15);
    border: 2px solid var(--neon-red);
    border-radius: 8px;
    padding: 12px;
    color: var(--neon-red);
    font-family: 'Orbitron', sans-serif;
    font-weight: 700;
    text-transform: uppercase;
    text-align: center;
    margin-bottom: 1rem;
    box-shadow: 0 0 15px rgba(255, 0, 51, 0.2);
}
::-webkit-scrollbar { width: 8px; }
::-webkit-scrollbar-track { background: var(--bg-dark); }
::-webkit-scrollbar-thumb { background: var(--neon-cyan); border-radius: 4px; }
</style>
"""
st.markdown(CYBERPUNK_CSS, unsafe_allow_html=True)

# -----------------------------------------------------------------------------
# INISIALISASI STATE PERSISTEN STREAMLIT
# -----------------------------------------------------------------------------
def init_session_state() -> None:
    defaults: Dict[str, Any] = {
        "bot_running": False,
        "stop_event": threading.Event(),
        "scan_thread": None,
        "virtual_balance": INITIAL_VIRTUAL_BALANCE,
        "initial_balance": INITIAL_VIRTUAL_BALANCE,
        "total_trades": 0,
        "successful_trades": 0,
        "balance_history": [],
        "activity_logs": [],
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "last_scan_result": None,
        "symbols": DEFAULT_SYMBOLS.copy(),
        "sma_window": SMA_WINDOW,
        "scan_interval": SCAN_INTERVAL_SECONDS,
        "manual_scan_triggered": False,
        # Real trading safety
        "real_trading_enabled": False,
        "real_trading_confirm": False,
        # Positions & trailing stop
        "positions": {},            # symbol -> {entry_price, peak_price, trailing_stop, amount, opened_at, status}
        "trailing_stop_percent": TRAILING_STOP_PERCENT,
        "trade_amount_usd": TRADE_AMOUNT_USD,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_session_state()

# -----------------------------------------------------------------------------
# FUNGSI LOG ACTIVITY
# -----------------------------------------------------------------------------
def add_activity_log(message: str, log_type: str = "info") -> None:
    entry: Dict[str, str] = {
        "time": datetime.now().strftime("%H:%M:%S"),
        "message": message,
        "type": log_type,
    }
    st.session_state.activity_logs.insert(0, entry)
    if len(st.session_state.activity_logs) > 300:
        st.session_state.activity_logs = st.session_state.activity_logs[:300]


# -----------------------------------------------------------------------------
# A. DATA HARGA & INDIKATOR TEKNIS (Python Murni / yfinance)
# -----------------------------------------------------------------------------

def fetch_crypto_data(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Mengambil data harga crypto real-time dari Yahoo Finance (yfinance).
    Menghitung SMA20 dengan logika Python murni.
    """
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period="1d", interval="1m")
        if hist is None or hist.empty or len(hist) < SMA_WINDOW:
            return None
        close_prices: List[float] = hist["Close"].tolist()
        current_price: float = float(close_prices[-1])

        window_prices: List[float] = close_prices[-SMA_WINDOW:]
        sma_value: float = sum(window_prices) / len(window_prices)
        is_above_sma: bool = current_price > sma_value
        trend_status: str = "BULLISH" if is_above_sma else "BEARISH"

        return {
            "symbol": symbol,
            "current_price": round(current_price, 2),
            "sma20": round(sma_value, 2),
            "is_above_sma": is_above_sma,
            "trend_status": trend_status,
            "history": close_prices,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    except Exception as exc:
        add_activity_log(f"Gagal mengambil data {symbol}: {exc}", "error")
        return None


# -----------------------------------------------------------------------------
# B. SIMULATOR / FETCHER X (TWITTER)
# Catatan: Groq tidak bisa langsung mencari di X. Fungsi ini menyediakan:
#   1) Simulator tweet (default, aman untuk uji coba)
#   2) X API v2 fetcher (opsional, butuh Bearer Token)
# -----------------------------------------------------------------------------

def fetch_x_tweets_via_api() -> Optional[List[Dict[str, Any]]]:
    """
    Mengambil tweet nyata dari X API v2 (Recent Search).
    Butuh X_API_BEARER_TOKEN yang valid di .env.
    """
    if not X_API_BEARER_TOKEN or X_API_BEARER_TOKEN.startswith("your_"):
        return None
    try:
        import requests  # type: ignore
        url = "https://api.twitter.com/2/tweets/search/recent"
        headers = {"Authorization": f"Bearer {X_API_BEARER_TOKEN}"}
        params = {
            "query": X_SEARCH_QUERY,
            "max_results": X_MAX_RESULTS,
            "tweet.fields": "created_at,lang",
        }
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            add_activity_log(f"X API error {resp.status_code}: {resp.text[:100]}", "error")
            return None
        data = resp.json()
        tweets = []
        for i, tw in enumerate(data.get("data", []), start=1):
            tweets.append({
                "id": i,
                "text": tw.get("text", ""),
                "coin": "X",
                "sentiment": "netral",
                "created_at": tw.get("created_at", datetime.now().isoformat()),
                "source": "x_api_v2",
            })
        return tweets
    except Exception as exc:
        add_activity_log(f"Gagal memanggil X API: {exc}", "error")
        return None


def simulate_crypto_tweets(symbols: List[str]) -> List[Dict[str, Any]]:
    """
    Mensimulasikan tweet dunia nyata tentang crypto (fallback jika X API tidak tersedia).
    Variasi sentimen acak setiap pemindaian.
    """
    tweet_templates: Dict[str, List[str]] = {
        "BTC": [
            "Bitcoin melonjak amid institutional adoption yang kuat! #BTC",
            "BTC menembus resistance penting, bull run dimulai?",
            "Whale BTC pindahkan 10.000 BTC ke exchange, waspada tekanan jual.",
            "MicroStrategy beli lagi Bitcoin, sentimen sangat positif.",
            "BTC consolidation di area support, breakout ke atas?",
            "Bitcoin ETF mengalirkan dana masuk rekor minggu ini.",
            "BTCUSD di bawah SMA20, trend bearish masih terlihat.",
        ],
        "ETH": [
            "Ethereum siap untuk upgrade berikutnya, ETH lidere altcoin season.",
            "ETH turun setelah news regulasi, trader takut ambil risiko.",
            "Volume transaksi ETH naik drastis di DEX, aktivitas on-chain naik.",
            "Ethereum staking mencapai all-time high, komunitas positif.",
            "ETH di bawah tekanan jual besar, support area diuji.",
        ],
        "SOL": [
            "Solana network stabil, SOL melonjak 12% dalam 24 jam.",
            "SOL breakout dari segitiga bullish, target ke atas.",
            "Aktivitas memecoin di Solana mendorong volume transaksi naik.",
            "SOL correction parah, banyak trader cut loss.",
            "Solana DeFi TVL naik tertinggi tahun ini, sinyal positif SOL.",
        ],
    }
    positive_words = ["naik", "bullish", "moon", "buy", "strong", "profit", "breakout"]
    negative_words = ["turun", "bearish", "crash", "sell", "weak", "loss", "breakdown"]
    neutral_words = ["stabil", "sideways", "flat", "normal", "wait", "netral"]

    tweets: List[Dict[str, Any]] = []
    tweet_id = 1
    for coin in symbols:
        coin_key = coin.split("-")[0] if "-" in coin else coin
        templates = tweet_templates.get(coin_key, tweet_templates["BTC"])
        for _ in range(random.randint(3, 5)):
            base_text = random.choice(templates)
            sentiment_choice = random.choice(["positif", "negatif", "netral"])
            if sentiment_choice == "positif":
                text = f"{base_text} 🚀 #{random.choice(positive_words).upper()}"
            elif sentiment_choice == "negatif":
                text = f"{base_text} ⚠️ #{random.choice(negative_words).upper()}"
            else:
                text = f"{base_text} 📊 #{random.choice(neutral_words).upper()}"
            tweets.append({
                "id": tweet_id,
                "text": text,
                "coin": coin_key,
                "sentiment": sentiment_choice,
                "created_at": datetime.now().strftime("%H:%M:%S"),
                "source": "simulator",
            })
            tweet_id += 1

    random.shuffle(tweets)
    total = random.randint(10, 15)
    return tweets[:total]


def get_x_tweets(symbols: List[str]) -> List[Dict[str, Any]]:
    """
    Prioritas: X API v2 (nyata) jika tersedia, jika tidak fallback ke simulator.
    """
    api_tweets = fetch_x_tweets_via_api()
    if api_tweets:
        add_activity_log(f"Data X dari X API v2: {len(api_tweets)} tweet.", "info")
        return api_tweets
    tweets = simulate_crypto_tweets(symbols)
    add_activity_log(f"Simulator X (fallback): {len(tweets)} tweet.", "info")
    return tweets


# -----------------------------------------------------------------------------
# C. OTAK AI (GROQ CLOUD API - llama3-8b-8192)
# -----------------------------------------------------------------------------

def groq_analyze_sentiment(
    tweets: List[Dict[str, Any]],
    api_key: str,
    model: str = GROQ_MODEL,
) -> Optional[Dict[str, Any]]:
    """
    Mengirim kumpulan tweet ke Groq Cloud API.
    AI menyimpulkan 1 koin paling HITS/viral, sentimen, dan kesimpulan.
    """
    if not api_key or api_key.startswith("your_"):
        st.error("API Key Groq belum dikonfigurasi. Isi di sidebar atau .env.")
        return None
    if not GROQ_LIB_OK:
        st.error("Library groq belum terinstal. Jalankan: pip install groq")
        return None

    try:
        client = Groq(api_key=api_key)
        tweet_lines: List[str] = []
        for tw in tweets:
            tweet_lines.append(
                f"[Tweet {tw['id']}] [{tw.get('coin','?')}] [{tw.get('sentiment','?').upper()}] {tw.get('text','')}"
            )
        tweets_text = "\n".join(tweet_lines)

        prompt = f"""
Anda adalah analis crypto senior yang ahli membaca media sosial X (Twitter).
Berikut adalah kumpulan tweet terbaru tentang BTC, ETH, SOL, dan memecoin:

{tweets_text}

TUGAS:
1. Tentukan SATU koin yang paling HITS / VIRAL berdasarkan jumlah dan intensitas mention.
2. Deteksi skor sentimen koin tersebut: Pilih "Positif", "Negatif", atau "Netral".
3. Berikan kesimpulan ringkas (maksimal 2 kalimat) mengapa koin ini viral dan sentimen pasarnya.

BALAS SECARA STRICT DALAM FORMAT JSON (tanpa teks di luar JSON):
{{
  "coin": "BTC",
  "sentiment": "Positif",
  "is_hits": true,
  "conclusion": "Koin ini paling banyak disebutkan dan menunjukkan momentum bullish."
}}
"""

        time.sleep(GROQ_SLEEP_SECONDS)  # anti rate-limit gratis Groq

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Anda adalah analis crypto senior. Balas selalu dalam format JSON yang valid."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
            max_tokens=300,
        )

        raw_content: str = response.choices[0].message.content.strip()
        try:
            if raw_content.startswith("```"):
                raw_content = raw_content.split("```")[1]
                if raw_content.startswith("json"):
                    raw_content = raw_content[4:]
            raw_content = raw_content.strip()
            result: Dict[str, Any] = json.loads(raw_content)
            required_keys = ["coin", "sentiment", "is_hits", "conclusion"]
            for key in required_keys:
                if key not in result:
                    result[key] = "Tidak diketahui" if key != "is_hits" else False
            result["coin"] = str(result["coin"]).upper().replace("-USD", "")
            result["sentiment"] = str(result["sentiment"]).capitalize()
            result["is_hits"] = bool(result["is_hits"])
            result["conclusion"] = str(result["conclusion"])
            result["analyzed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            return result
        except json.JSONDecodeError:
            st.warning("Groq mengembalikan format non-JSON, menggunakan fallback.")
            return {
                "coin": "BTC",
                "sentiment": "Netral",
                "is_hits": False,
                "conclusion": f"Gagal memformat respons AI: {raw_content[:200]}...",
                "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
    except Exception as exc:
        st.error(f"Kesalahan saat memanggil Groq API: {exc}")
        return None


# -----------------------------------------------------------------------------
# TRAILING STOP MANAGER
# -----------------------------------------------------------------------------

class TrailingStopManager:
    """
    Mengelola posisi terbuka dan trailing stop.
    - Saat posisi dibuka: catat entry_price, peak_price, trailing_stop.
    - Saat harga naik: peak_price dan trailing_stop ikut naik.
    - Saat harga turun hingga menyentuh trailing_stop: trigger SELL.
    """
    def __init__(self, trailing_percent: float = 0.05):
        self.trailing_percent = trailing_percent
        self.positions: Dict[str, Dict[str, Any]] = {}

    def open_position(self, symbol: str, entry_price: float, amount: float) -> None:
        self.positions[symbol] = {
            "symbol": symbol,
            "entry_price": entry_price,
            "peak_price": entry_price,
            "trailing_stop": round(entry_price * (1 - self.trailing_percent), 4),
            "amount": amount,
            "opened_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "status": "OPEN",
        }

    def update(self, symbol: str, current_price: float) -> Optional[str]:
        """
        Memperiksa apakah trailing stop terpicu.
        Mengembalikan 'SELL_TRAILING_STOP' jika posisi harus ditutup, None jika masih open.
        """
        pos = self.positions.get(symbol)
        if not pos or pos["status"] != "OPEN":
            return None
        if current_price > pos["peak_price"]:
            pos["peak_price"] = current_price
            pos["trailing_stop"] = round(current_price * (1 - self.trailing_percent), 4)
        if current_price <= pos["trailing_stop"]:
            pos["status"] = "CLOSED_TRAILING_STOP"
            pos["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pos["exit_price"] = current_price
            return "SELL_TRAILING_STOP"
        return None

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self.positions.get(symbol)

    def close_position(self, symbol: str, reason: str) -> Optional[Dict[str, Any]]:
        pos = self.positions.get(symbol)
        if pos and pos["status"] == "OPEN":
            pos["status"] = "CLOSED_MANUAL"
            pos["closed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            pos["close_reason"] = reason
            return pos
        return None


# Inisialisasi manager di session state
if "trailing_manager" not in st.session_state:
    st.session_state.trailing_manager = TrailingStopManager(
        trailing_percent=st.session_state.trailing_stop_percent
    )


# -----------------------------------------------------------------------------
# D. SISTEM KEPUTUSAN & EKSEKUSI (Safe Trigger + Trailing Stop)
# -----------------------------------------------------------------------------

def execute_trading_decision(
    groq_result: Dict[str, Any],
    symbol_data: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Menerapkan Safe Trigger:
      - Jika Groq HITS + POSITIF:
          * Cek harga vs SMA20.
          * Di atas SMA20 → BUY (Paper atau Real jika diaktifkan).
          * Di bawah SMA20 → CANCELLED - TREND BEARISH.
      - Bukan HITS atau bukan POSITIF → WAIT.

    Juga menjalankan update trailing stop untuk posisi yang sudah OPEN.
    """
    coin = str(groq_result.get("coin", "")).upper()
    sentiment = str(groq_result.get("sentiment", "")).capitalize()
    is_hits = bool(groq_result.get("is_hits", False))
    conclusion = str(groq_result.get("conclusion", "-"))

    decision: Dict[str, Any] = {
        "coin": coin,
        "sentiment": sentiment,
        "is_hits": is_hits,
        "conclusion": conclusion,
        "action": "WAIT",
        "status": "TIDAK ADA TINDAKAN",
        "price": None,
        "sma20": None,
        "trailing_stop": None,
        "reason": "",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "mode": st.session_state.get("real_trading_enabled", False) and "REAL" or "PAPER",
    }

    # Update trailing stop untuk posisi OPEN yang ada
    for sym in list(st.session_state.positions.keys()):
        pos = st.session_state.positions.get(sym)
        if pos and pos.get("status") == "OPEN":
            # Ambil harga terkini untuk trailing check
            data_sym = None
            for s in st.session_state.symbols:
                if s.split("-")[0].upper() == sym:
                    data_sym = st.session_state.last_scan_result.get("symbol_data", {}).get(s) if st.session_state.last_scan_result else None
                    break
            if data_sym:
                trigger = st.session_state.trailing_manager.update(sym, data_sym["current_price"])
                if trigger == "SELL_TRAILING_STOP":
                    add_activity_log(
                        f"TRAILING STOP TERPICU {sym} @ ${data_sym['current_price']} | Peak: ${pos['peak_price']} | SL: ${pos['trailing_stop']}",
                        "warning",
                    )
                    # Jika REAL dan integrasi exchange ada, bisa dijalankan di sini
                    # Jika PAPER, hanya catat posisi tertutup
                    add_activity_log(f"Posisi {sym} ditutup oleh trailing stop.", "info")

    if not is_hits or sentiment != "Positif":
        decision["action"] = "WAIT"
        decision["status"] = "WAIT - BUKAN HITS ATAU SENTIMEN BUKAN POSITIF"
        decision["reason"] = f"Groq is_hits={is_hits}, sentiment={sentiment}. Tidak memicu BUY."
        return decision

    if symbol_data is None:
        decision["action"] = "WAIT"
        decision["status"] = "WAIT - DATA TEKNIS TIDAK TERSEDIA"
        decision["reason"] = f"Data harga untuk {coin} tidak tersedia."
        return decision

    price = symbol_data.get("current_price")
    sma20 = symbol_data.get("sma20")
    is_above_sma = bool(symbol_data.get("is_above_sma", False))
    decision["price"] = price
    decision["sma20"] = sma20
    decision["trailing_stop"] = round(price * (1 - st.session_state.trailing_stop_percent), 4) if price else None

    if is_above_sma and price is not None:
        decision["action"] = "BUY"
        decision["status"] = "BERHASIL - ORDER BUY DIEKSEKUSI"
        decision["reason"] = (
            f"Groq HITS+POSITIF dan harga {coin} (${price}) di atas SMA20 (${sma20}). "
            f"Trailing stop diatur di ${decision['trailing_stop']}."
        )

        amount = st.session_state.trade_amount_usd

        if st.session_state.get("real_trading_enabled", False):
            # =================================================================
            # BLOK REAL TRADING - HANYA DIAKTIFKAN SECARA EKSPLISIT DENGAN KONFIRMASI
            # Di sini kamu harus menambahkan integrasi exchange (ccxt / web3 / dll.)
            # Contoh dengan ccxt (tidak dijalankan otomatis tanpa konfirmasi lebih lanjut):
            # =================================================================
            add_activity_log(
                f"[REAL MODE] Siap BUY {coin} @ ${price} - integrasi exchange harus diimplementasi secara manual",
                "danger",
            )
            decision["status"] += " [REAL MODE - PERLU INTEGRASI EXCHANGE]"
            # Jika kamu sudah siap, implementasi order exchange di sini dengan ccxt.
            # Contoh:
            # exchange = ccxt.binance({"apiKey": ..., "secret": ...})
            # order = exchange.create_market_buy_order(f"{coin}/USDT", amount_usd / price)
        else:
            # =================================================================
            # PAPER TRADING (default, aman)
            # =================================================================
            st.session_state.virtual_balance = round(
                st.session_state.virtual_balance - amount, 2
            )
            st.session_state.total_trades += 1
            st.session_state.successful_trades += 1
            st.session_state.balance_history.append({
                "time": decision["timestamp"],
                "balance": st.session_state.virtual_balance,
            })

            # Buka posisi untuk trailing stop
            st.session_state.trailing_manager.open_position(coin, price, amount)
            st.session_state.positions[coin] = st.session_state.trailing_manager.get_position(coin)

            add_activity_log(
                f"PAPER BUY {coin} @ ${price} | SMA20: ${sma20} | Trailing SL: ${decision['trailing_stop']} | Saldo: ${st.session_state.virtual_balance}",
                "success",
            )
    else:
        decision["action"] = "CANCELLED"
        decision["status"] = "CANCELLED - TREND BEARISH"
        decision["reason"] = (
            f"Groq HITS+POSITIF tetapi harga {coin} (${price}) DI BAWAH SMA20 (${sma20}). "
            "Order dibatalkan demi keamanan modal."
        )
        add_activity_log(
            f"CANCELLED {coin} @ ${price} | SMA20: ${sma20} | Trend Bearish.",
            "warning",
        )

    return decision


def perform_single_scan() -> Optional[Dict[str, Any]]:
    add_activity_log("Memulai siklus pemindaian otomatis...", "info")

    symbols = st.session_state.symbols
    all_symbol_data: Dict[str, Dict[str, Any]] = {}
    for symbol in symbols:
        data = fetch_crypto_data(symbol)
        if data:
            all_symbol_data[symbol] = data
            add_activity_log(
                f"{symbol}: Harga ${data['current_price']} | SMA20 ${data['sma20']} | Tren {data['trend_status']}",
                "info",
            )
        else:
            add_activity_log(f"{symbol}: Gagal mengambil data harga.", "error")

    time.sleep(max(1, st.session_state.scan_interval // 10))

    tweets = get_x_tweets(symbols)

    api_key = st.session_state.groq_api_key or os.getenv("GROQ_API_KEY", "")
    groq_result = groq_analyze_sentiment(tweets, api_key)

    if groq_result is None:
        add_activity_log("Gagal mendapatkan analisis dari Groq API.", "error")
        return None

    coin = groq_result.get("coin", "Tidak diketahui")
    sentiment = groq_result.get("sentiment", "Tidak diketahui")
    is_hits = groq_result.get("is_hits", False)
    conclusion = groq_result.get("conclusion", "-")
    add_activity_log(
        f"GROQ: Koin {coin} | Sentimen {sentiment} | HITS: {is_hits} | {conclusion}",
        "info",
    )

    symbol_for_check = None
    for s in symbols:
        if s.split("-")[0].upper() == coin:
            symbol_for_check = s
            break
    symbol_data = all_symbol_data.get(symbol_for_check) if symbol_for_check else None

    decision = execute_trading_decision(groq_result, symbol_data)
    add_activity_log(
        f"PYTHON: {decision['action']} | {decision['status']} | {decision['reason'][:130]}",
        "success" if decision["action"] == "BUY" else ("warning" if decision["action"] == "CANCELLED" else "info"),
    )

    result: Dict[str, Any] = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tweets": tweets,
        "groq_result": groq_result,
        "decision": decision,
        "symbol_data": all_symbol_data,
    }
    st.session_state.last_scan_result = result
    return result


# -----------------------------------------------------------------------------
# E. PERULANGAN OTOMATIS (THREADING)
# -----------------------------------------------------------------------------

def bot_loop(stop_event: threading.Event) -> None:
    add_activity_log("Bot loop latar belakang dimulai (24/7 mode).", "success")
    while not stop_event.is_set():
        try:
            if st.session_state.bot_running:
                perform_single_scan()
            else:
                time.sleep(2)
                continue
            interval = int(st.session_state.scan_interval)
            elapsed = 0
            while elapsed < interval and not stop_event.is_set():
                time.sleep(1)
                elapsed += 1
        except Exception as exc:
            add_activity_log(f"Error dalam bot loop: {exc}", "error")
            time.sleep(5)
    add_activity_log("Bot loop latar belakang dihentikan.", "warning")


def start_bot() -> None:
    if st.session_state.bot_running:
        return
    api_key = st.session_state.groq_api_key or os.getenv("GROQ_API_KEY", "")
    if not api_key or api_key.startswith("your_"):
        st.error("API Key Groq harus diisi sebelum bot dapat berjalan.")
        return
    if st.session_state.get("real_trading_enabled", False) and not st.session_state.get("real_trading_confirm", False):
        st.error("Real trading memerlukan konfirmasi ekstra di sidebar.")
        return
    st.session_state.bot_running = True
    st.session_state.stop_event = threading.Event()
    thread = threading.Thread(target=bot_loop, args=(st.session_state.stop_event,), daemon=True)
    st.session_state.scan_thread = thread
    thread.start()
    add_activity_log("BOT DIMULAI: Otomatisasi RUNNING 24/7.", "success")


def stop_bot() -> None:
    if not st.session_state.bot_running:
        return
    st.session_state.bot_running = False
    st.session_state.stop_event.set()
    add_activity_log("Bot otomatis dimatikan oleh pengguna.", "warning")


# -----------------------------------------------------------------------------
# F. DASHBOARD STREAMLIT CYBERPUNK
# -----------------------------------------------------------------------------

def render_header() -> None:
    st.title("🤖 SuperGrok Bot RDP Edition")
    st.markdown(
        "<div style='font-family: Orbitron; color: #00f3ff; font-size: 1.1rem; "
        "text-shadow: 0 0 6px rgba(0,243,255,0.5); margin-bottom: 1rem;'>"
        "Bot Trading Crypto berbasis Social Sentiment • Hybrid Python + Groq Cloud AI • "
        "Trailing Stop • Dashboard Cyberpunk</div>",
        unsafe_allow_html=True,
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.header("⚙️ Kontrol Bot")
        status_text = "🟢 RUNNING 24/7" if st.session_state.bot_running else "🔴 STOPPED"
        st.markdown(f"**Status Bot:** `{status_text}`")

        mode_text = "🔴 REAL" if st.session_state.get("real_trading_enabled", False) else "🟢 PAPER"
        st.markdown(f"**Mode Trading:** `{mode_text}`")

        col_start, col_stop = st.columns(2)
        with col_start:
            if st.button("▶️ Start Bot", use_container_width=True):
                start_bot()
        with col_stop:
            if st.button("⏹️ Stop Bot", use_container_width=True):
                stop_bot()

        st.divider()

        st.subheader("🔑 API Key Groq")
        api_key_input = st.text_input(
            "Masukkan API Key Groq",
            value=st.session_state.groq_api_key,
            type="password",
        )
        if api_key_input:
            st.session_state.groq_api_key = api_key_input

        st.divider()

        # =====================================================================
        # REAL TRADING CONFIRM (DANGER ZONE)
        # =====================================================================
        if st.session_state.get("real_trading_enabled", False):
            st.markdown("<div class='warning-banner'>REAL TRADING AKTIF</div>", unsafe_allow_html=True)
        real_toggle = st.checkbox(
            "Aktifkan REAL TRADING (UANG ASLI)",
            value=st.session_state.get("real_trading_enabled", False),
            help="Nonaktifkan default. Hanya aktifkan jika paham risiko.",
        )
        if real_toggle != st.session_state.get("real_trading_enabled", False):
            st.session_state.real_trading_enabled = real_toggle
            st.session_state.real_trading_confirm = False

        if st.session_state.get("real_trading_enabled", False):
            confirm = st.text_input(
                "Ketik 'SETUJU' untuk mengaktifkan real trading",
                value="",
                type="password",
            )
            if confirm == "SETUJU":
                st.session_state.real_trading_confirm = True
                st.success("Konfirmasi real trading diterima (masih beresiko tinggi).")
            else:
                st.session_state.real_trading_confirm = False

        st.divider()

        st.subheader("🔄 Pemindaian Manual")
        if st.button("Scan Sekarang", use_container_width=True):
            st.session_state.manual_scan_triggered = True

        st.divider()

        st.subheader("📊 Pengaturan")
        interval = st.number_input(
            "Interval scan (detik)",
            min_value=60,
            max_value=3600,
            value=st.session_state.scan_interval,
            step=60,
        )
        st.session_state.scan_interval = interval

        sma = st.number_input(
            "Window SMA",
            min_value=5,
            max_value=100,
            value=st.session_state.sma_window,
            step=1,
        )
        st.session_state.sma_window = sma

        trail = st.number_input(
            "Trailing Stop % (contoh 0.05 = 5%)",
            min_value=0.001,
            max_value=0.50,
            value=st.session_state.trailing_stop_percent,
            step=0.001,
            format="%.3f",
        )
        st.session_state.trailing_stop_percent = trail
        if "trailing_manager" in st.session_state:
            st.session_state.trailing_manager.trailing_percent = trail

        amt = st.number_input(
            "Jumlah per order (USD)",
            min_value=1.0,
            max_value=10000.0,
            value=st.session_state.trade_amount_usd,
            step=1.0,
        )
        st.session_state.trade_amount_usd = amt

        st.divider()
        st.caption("💡 Jalankan di RDP port 8501. Akses dari browser pribadi via IP Publik RDP.")


def render_metrics() -> None:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            label="💰 Saldo Virtual",
            value=f"${st.session_state.virtual_balance:,.2f}",
            delta=f"${st.session_state.virtual_balance - st.session_state.initial_balance:,.2f}",
        )
    with col2:
        st.metric(
            label="✅ Transaksi Berhasil",
            value=st.session_state.successful_trades,
            delta=f"Total: {st.session_state.total_trades}",
        )
    with col3:
        mode_lbl = "REAL" if st.session_state.get("real_trading_enabled", False) else "PAPER"
        status_lbl = "RUNNING 24/7" if st.session_state.bot_running else "STOPPED"
        st.metric(label=f"🤖 Mode {mode_lbl}", value=status_lbl)
    with col4:
        open_positions = sum(1 for p in st.session_state.positions.values() if p.get("status") == "OPEN")
        st.metric(label="📈 Posisi Terbuka", value=open_positions)


def render_balance_chart() -> None:
    st.subheader("📈 Grafik Performa Saldo Virtual")
    if st.session_state.balance_history:
        df_chart = pd.DataFrame(st.session_state.balance_history)
        df_chart["balance"] = pd.to_numeric(df_chart["balance"], errors="coerce")
        st.line_chart(df_chart.set_index("time")["balance"], height=300)
    else:
        st.info("Belum ada data saldo. Grafik muncul setelah transaksi pertama.")


def render_positions_table() -> None:
    st.subheader("📋 Posisi Terbuka & Trailing Stop")
    positions = st.session_state.positions
    open_positions = {k: v for k, v in positions.items() if v.get("status") == "OPEN"}
    if not open_positions:
        st.info("Belum ada posisi terbuka. Posisi akan muncul setelah BUY dieksekusi.")
        return

    rows = []
    for sym, pos in open_positions.items():
        rows.append({
            "Simbol": sym,
            "Entry": f"${pos.get('entry_price', '-')}",
            "Peak": f"${pos.get('peak_price', '-')}",
            "Trailing SL": f"${pos.get('trailing_stop', '-')}",
            "Dibuka": pos.get("opened_at", "-"),
            "Status": pos.get("status", "-"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def render_activity_log() -> None:
    st.subheader("📜 Log Aktivitas Agen (Real-Time)")
    logs = st.session_state.activity_logs
    if not logs:
        st.info("Belum ada aktivitas. Mulai bot untuk melihat log proses berpikir LLM Groq dan tindakan BUY/Trailing Stop.")
        return
    log_html = ""
    for entry in logs[:60]:
        log_type = entry.get("type", "info")
        css_class = f"log-{log_type}"
        log_html += (
            f"<div class='log-entry {css_class}'>"
            f"<span style='color:#00f3ff;'>{entry['time']}</span> • "
            f"{entry['message']}"
            f"</div>"
        )
    st.markdown(log_html, unsafe_allow_html=True)
    if st.button("🗑️ Hapus Semua Log"):
        st.session_state.activity_logs = []
        st.rerun()


def render_last_scan_detail() -> None:
    result = st.session_state.last_scan_result
    if not result:
        return
    st.subheader("🔍 Detail Scan Terakhir")
    groq = result.get("groq_result", {})
    decision = result.get("decision", {})
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("**🧠 Analisis Groq AI**")
        st.write(f"**Koin Viral:** `{groq.get('coin', '-')}`")
        st.write(f"**Sentimen:** `{groq.get('sentiment', '-')}`")
        st.write(f"**HITS/Viral:** `{'Ya' if groq.get('is_hits') else 'Tidak'}`")
        st.write(f"**Kesimpulan:** {groq.get('conclusion', '-')}")
    with col_b:
        st.markdown("**🛡️ Keputusan Python + Trailing Stop**")
        st.write(f"**Aksi:** `{decision.get('action', '-')}`")
        st.write(f"**Status:** `{decision.get('status', '-')}`")
        st.write(f"**Harga:** `${decision.get('price', '-')}`")
        st.write(f"**SMA20:** `${decision.get('sma20', '-')}`")
        st.write(f"**Trailing SL:** `${decision.get('trailing_stop', '-')}`")
        st.write(f"**Mode:** `{decision.get('mode', '-')}`")
        st.write(f"**Alasan:** {decision.get('reason', '-')}")


# -----------------------------------------------------------------------------
# MAIN APP
# -----------------------------------------------------------------------------

def main() -> None:
    render_header()

    if st.session_state.get("real_trading_enabled", False):
        st.markdown(
            "<div class='warning-banner'>⚠️ REAL TRADING AKTIF - UANG ASLI DI PERBAYAHKAN ⚠️</div>",
            unsafe_allow_html=True,
        )

    render_sidebar()

    if st.session_state.get("manual_scan_triggered", False):
        st.session_state.manual_scan_triggered = False
        try:
            perform_single_scan()
            st.success("Pemindaian manual selesai. Lihat log aktivitas.")
        except Exception as exc:
            st.error(f"Gagal scan manual: {exc}")

    st.divider()
    render_metrics()
    st.divider()

    col_chart, col_detail = st.columns([2, 1])
    with col_chart:
        render_balance_chart()
        render_positions_table()
    with col_detail:
        render_last_scan_detail()

    st.divider()
    render_activity_log()


if __name__ == "__main__":
    main()

"""
===============================================================================
CARA INSTALASI & MENJALANKAN DI RDP
===============================================================================

1. Siapkan RDP (Windows atau Linux) dengan Python 3.9+ terinstal.

2. Clone repositori ini ke folder di RDP.

3. Instal pustaka yang diperlukan:

    pip install streamlit groq yfinance pandas python-dotenv requests

   Opsional (untuk real trading CEX di masa depan):
    pip install ccxt

4. Isi file `.env`:
   - GROQ_API_KEY: dapatkan di https://console.groq.com
   - X_API_BEARER_TOKEN: (opsional) dapatkan di https://developer.twitter.com
   - TRADING_MODE=PAPER (jangan ganti ke REAL kecuali paham risiko)

5. Jalankan Streamlit di RDP, bind ke semua interface, port 8501:

    streamlit run app.py --server.port 8501 --server.address 0.0.0.0

6. Buka browser di PC/HP pribadi:

    http://IP_PUBLIK_RDP:8501

Catatan:
- Groq TIDAK bisa langsung mencari di X. Jika ingin data X nyata, isi
  X_API_BEARER_TOKEN di .env, bot akan mengambil tweet lewat X API v2.
- Mode default adalah PAPER TRADING (simulasi aman).
- Trailing stop hanya bekerja pada posisi yang dibuka oleh bot ini.
- Untuk real trading, kamu harus menambahkan integrasi exchange (ccxt/web3)
  di blok yang telah disediakan di dalam perform_single_scan / execute_trading_decision.

===============================================================================
"""