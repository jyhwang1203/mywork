"""
Market Terminal — FastAPI 백엔드
================================
역할:
  1. Yahoo Finance API 프록시 (브라우저 CORS 우회)
  2. CNN Fear & Greed 프록시
  3. 인메모리 캐시 (TTL: 3분) → 과도한 외부 요청 방지
  4. 수익률 계산 (1D / 1W / 1M / YTD / 1Y)

실행:
  pip install fastapi uvicorn httpx
  uvicorn main:app --reload --port 8000

대시보드에서 연결:
  API_BASE = "http://localhost:8000"
"""

import asyncio
import time
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# ──────────────────────────────────────────────
# APP
# ──────────────────────────────────────────────
app = FastAPI(
    title="Market Terminal API",
    description="Yahoo Finance & CNN Fear/Greed proxy with caching",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # 개발용 전체 허용 (운영 시 도메인 지정)
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────
# CACHE
# ──────────────────────────────────────────────
CACHE: dict[str, dict] = {}
CACHE_TTL = 180  # 3분 (초)


def cache_get(key: str) -> Optional[dict]:
    entry = CACHE.get(key)
    if entry and (time.time() - entry["ts"]) < CACHE_TTL:
        return entry["data"]
    return None


def cache_set(key: str, data: dict):
    CACHE[key] = {"ts": time.time(), "data": data}


# ──────────────────────────────────────────────
# YAHOO FINANCE HELPER
# ──────────────────────────────────────────────
YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}

YAHOO_URLS = [
    "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
    "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}",
]


def _calc_pct(cur: float, prev: float) -> Optional[float]:
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 2)


def _nearest_close(history: list[dict], target_ts: float) -> Optional[float]:
    """타임스탬프에서 가장 가까운 종가 반환"""
    if not history:
        return None
    best = min(history, key=lambda h: abs(h["t"] - target_ts))
    return best["c"]


async def fetch_yahoo(symbol: str) -> dict:
    """Yahoo Finance에서 1년치 일봉 데이터를 받아 수익률을 계산해 반환"""
    params = {"interval": "1d", "range": "1y"}
    last_err = None

    async with httpx.AsyncClient(timeout=10.0, headers=YAHOO_HEADERS) as client:
        for url_tpl in YAHOO_URLS:
            url = url_tpl.format(symbol=symbol)
            try:
                r = await client.get(url, params=params)
                r.raise_for_status()
                json_data = r.json()

                result = json_data.get("chart", {}).get("result", [None])[0]
                if not result:
                    raise ValueError("No result in response")

                meta = result.get("meta", {})
                closes: list = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                timestamps: list = result.get("timestamp", [])

                # 유효 데이터만 추출
                history = [
                    {"t": timestamps[i] * 1000, "c": closes[i]}
                    for i in range(min(len(closes), len(timestamps)))
                    if closes[i] is not None
                ]

                cur: float = meta.get("regularMarketPrice") or (history[-1]["c"] if history else None)
                prev: float = meta.get("previousClose") or (history[-2]["c"] if len(history) >= 2 else None)

                now_ms = time.time() * 1000

                close_1w  = _nearest_close(history, now_ms - 7  * 86400 * 1000)
                close_1m  = _nearest_close(history, now_ms - 30 * 86400 * 1000)
                close_1y  = history[0]["c"] if history else None

                # YTD: 올해 1월 1일 기준
                jan1 = datetime(datetime.now().year, 1, 1, tzinfo=timezone.utc).timestamp() * 1000
                close_ytd = _nearest_close(history, jan1)

                return {
                    "symbol":   symbol,
                    "cur":      cur,
                    "prev":     prev,
                    "pct_1d":   _calc_pct(cur, prev),
                    "pct_1w":   _calc_pct(cur, close_1w),
                    "pct_1m":   _calc_pct(cur, close_1m),
                    "pct_ytd":  _calc_pct(cur, close_ytd),
                    "pct_1y":   _calc_pct(cur, close_1y),
                    "cached":   False,
                    "updated_at": datetime.utcnow().isoformat() + "Z",
                }

            except Exception as e:
                last_err = e
                continue  # 다음 Yahoo 엔드포인트 시도

    raise HTTPException(status_code=502, detail=f"Yahoo fetch failed for {symbol}: {last_err}")


# ──────────────────────────────────────────────
# ROUTES
# ──────────────────────────────────────────────

@app.get("/")
async def root():
    return {"status": "ok", "service": "Market Terminal API"}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "cache_entries": len(CACHE),
        "server_time": datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/quote/{symbol}")
async def get_quote(symbol: str):
    """
    단일 심볼 시세 조회
    GET /api/quote/%5EGSPC   (^GSPC → URL 인코딩)
    """
    cache_key = f"quote:{symbol}"
    cached = cache_get(cache_key)
    if cached:
        cached["cached"] = True
        return JSONResponse(cached)

    data = await fetch_yahoo(symbol)
    cache_set(cache_key, data)
    return JSONResponse(data)


@app.get("/api/quotes")
async def get_quotes(symbols: str = Query(..., description="콤마로 구분된 심볼 목록 (예: ^GSPC,^DJI)")):
    """
    복수 심볼 일괄 조회 (병렬 처리)
    GET /api/quotes?symbols=^KS11,^KQ11,^DJI,^GSPC
    """
    sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
    if not sym_list:
        raise HTTPException(status_code=400, detail="symbols 파라미터가 비어있습니다")
    if len(sym_list) > 30:
        raise HTTPException(status_code=400, detail="한 번에 최대 30개까지 요청 가능합니다")

    async def fetch_one(sym: str) -> dict:
        cache_key = f"quote:{sym}"
        cached = cache_get(cache_key)
        if cached:
            cached["cached"] = True
            return cached
        try:
            data = await fetch_yahoo(sym)
            cache_set(cache_key, data)
            return data
        except Exception as e:
            return {"symbol": sym, "error": str(e), "cached": False}

    results = await asyncio.gather(*[fetch_one(s) for s in sym_list])
    return JSONResponse({
        "count": len(results),
        "data": {r["symbol"]: r for r in results},
        "updated_at": datetime.utcnow().isoformat() + "Z",
    })


@app.get("/api/fear-greed")
async def get_fear_greed():
    """
    CNN Fear & Greed Index
    GET /api/fear-greed
    """
    cache_key = "fear_greed"
    cached = cache_get(cache_key)
    if cached:
        return JSONResponse({**cached, "cached": True})

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            r = await client.get(
                "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
                headers={"User-Agent": YAHOO_HEADERS["User-Agent"]},
            )
            r.raise_for_status()
            j = r.json()
            fg = j.get("fear_and_greed", {})
            data = {
                "score":         fg.get("score"),
                "rating":        fg.get("rating"),
                "previous_close": fg.get("previous_close"),
                "previous_1_week": fg.get("previous_1_week"),
                "cached":        False,
                "updated_at":    datetime.utcnow().isoformat() + "Z",
            }
            cache_set(cache_key, data)
            return JSONResponse(data)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Fear & Greed fetch failed: {e}")


@app.delete("/api/cache")
async def clear_cache():
    """캐시 전체 초기화 (개발·디버그용)"""
    count = len(CACHE)
    CACHE.clear()
    return {"cleared": count}