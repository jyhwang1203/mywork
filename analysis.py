"""
업비트 정배열 스캐너
================================
거래량 상위 20개 KRW 코인 중 1시간봉 / 일봉 정배열 종목 탐색

1시간봉 조건 (완전 정배열): 현재가 > MA5 > MA10 > MA20 > MA60 > MA120
일봉 조건   (중기 추세)   : MA20 > MA60 > MA120  &  현재가 > MA60

설치:
    pip install requests pandas tabulate colorama

실행:
    python upbit_scanner.py
"""

import time
import sys

import requests
import pandas as pd
from tabulate import tabulate
from colorama import Fore, Style, init

init(autoreset=True)

BASE_URL = "https://api.upbit.com/v1"
TOP_N = 20
CANDLE_COUNT = 200
REQUEST_DELAY = 0.12  # 업비트 API Rate Limit 방어 (초)


# ──────────────────────────────────────────────
# 업비트 API 유틸
# ──────────────────────────────────────────────

def get_krw_markets() -> list[str]:
    """KRW 마켓 종목 코드 목록 반환"""
    res = requests.get(f"{BASE_URL}/market/all", params={"isDetails": False})
    res.raise_for_status()
    return [m["market"] for m in res.json() if m["market"].startswith("KRW-")]


def get_tickers(markets: list[str]) -> list[dict]:
    """현재가 + 거래대금 조회 (한 번에 최대 100개)"""
    result = []
    chunk_size = 100
    for i in range(0, len(markets), chunk_size):
        chunk = ",".join(markets[i : i + chunk_size])
        res = requests.get(f"{BASE_URL}/ticker", params={"markets": chunk})
        res.raise_for_status()
        result.extend(res.json())
    return result


def get_candles(market: str, unit: str, count: int = CANDLE_COUNT) -> list[dict]:
    """
    unit: 'day' | 'hours' (60분봉)
    """
    if unit == "day":
        url = f"{BASE_URL}/candles/days"
    else:
        url = f"{BASE_URL}/candles/minutes/60"

    res = requests.get(url, params={"market": market, "count": count})
    res.raise_for_status()
    return res.json()  # 최신 → 오래된 순


# ──────────────────────────────────────────────
# 이동평균 / 정배열 계산
# ──────────────────────────────────────────────

def calc_ma(prices: list[float], period: int) -> float | None:
    if len(prices) < period:
        return None
    return sum(prices[:period]) / period


def check_jeongbae_full(candles: list[dict]) -> dict:
    """
    완전 정배열 (1시간봉용)
    조건: 현재가 > MA5 > MA10 > MA20 > MA60 > MA120
    """
    prices = [c["trade_price"] for c in candles]
    current = prices[0]
    ma5   = calc_ma(prices, 5)
    ma10  = calc_ma(prices, 10)
    ma20  = calc_ma(prices, 20)
    ma60  = calc_ma(prices, 60)
    ma120 = calc_ma(prices, 120)

    if any(v is None for v in [ma5, ma10, ma20, ma60, ma120]):
        return {"ok": False, "reason": "데이터 부족"}

    ok = current > ma5 > ma10 > ma20 > ma60 > ma120
    return {
        "ok": ok,
        "mode": "완전정배열",
        "current": current,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "ma120": ma120,
    }


def check_jeongbae_mid(candles: list[dict]) -> dict:
    """
    중기 추세 정배열 (일봉용)
    조건: MA20 > MA60 > MA120  +  현재가 > MA60
    → 단기 변동에 흔들리지 않고 중기 추세의 방향성만 확인
    """
    prices = [c["trade_price"] for c in candles]
    current = prices[0]
    ma5   = calc_ma(prices, 5)
    ma10  = calc_ma(prices, 10)
    ma20  = calc_ma(prices, 20)
    ma60  = calc_ma(prices, 60)
    ma120 = calc_ma(prices, 120)

    if any(v is None for v in [ma5, ma10, ma20, ma60, ma120]):
        return {"ok": False, "reason": "데이터 부족"}

    # 핵심 조건: 중기 이평선 정배열 + 가격이 중기선 위
    ok = ma20 > ma60 > ma120 and current > ma60
    return {
        "ok": ok,
        "mode": "중기추세",
        "current": current,
        "ma5": ma5,
        "ma10": ma10,
        "ma20": ma20,
        "ma60": ma60,
        "ma120": ma120,
        # 세부 조건 플래그
        "cond_price_above_ma60": current > ma60,
        "cond_ma20_ma60":        ma20 > ma60,
        "cond_ma60_ma120":       ma60 > ma120,
    }


# ──────────────────────────────────────────────
# 출력 헬퍼
# ──────────────────────────────────────────────

def fmt_price(v: float) -> str:
    if v >= 1_000:
        return f"{v:,.0f}"
    elif v >= 1:
        return f"{v:,.2f}"
    else:
        return f"{v:.6f}"


def fmt_vol(v: float) -> str:
    if v >= 1e12:
        return f"{v/1e12:.1f}조"
    elif v >= 1e8:
        return f"{v/1e8:.0f}억"
    else:
        return f"{v:,.0f}"


def colored_check(flag: bool) -> str:
    return Fore.GREEN + "✅ 정배열" if flag else Fore.RED + "❌ 비정배열"


def print_ma_detail(label: str, info: dict, color: str):
    if not info.get("ok") and info.get("reason"):
        print(f"  {color}{label}: {info['reason']}{Style.RESET_ALL}")
        return

    mode = info.get("mode", "완전정배열")
    print(f"  {color}{label} [{mode}]:{Style.RESET_ALL}")

    if mode == "중기추세":
        # 중기 조건 플래그만 강조
        conds = [
            ("현재가 > MA60",  info.get("cond_price_above_ma60")),
            ("MA20 > MA60",    info.get("cond_ma20_ma60")),
            ("MA60 > MA120",   info.get("cond_ma60_ma120")),
        ]
        for name, passed in conds:
            mark = Fore.GREEN + "✅" if passed else Fore.RED + "❌"
            print(f"    {mark} {name}{Style.RESET_ALL}")

    lines = [
        ("현재가", info["current"]),
        ("MA5",   info["ma5"]),
        ("MA10",  info["ma10"]),
        ("MA20",  info["ma20"]),
        ("MA60",  info["ma60"]),
        ("MA120", info["ma120"]),
    ]
    for i, (name, val) in enumerate(lines):
        if i < len(lines) - 1:
            nxt = lines[i + 1][1]
            arrow = Fore.GREEN + " ▲" if val > nxt else Fore.RED + " ▼"
        else:
            arrow = ""
        print(f"    {name:>6}: {fmt_price(val):>15}{arrow}{Style.RESET_ALL}")


def print_coin_result(rank: int, coin: dict):
    market   = coin["market"]
    ticker   = coin["ticker"]
    price    = ticker["trade_price"]
    chg      = ticker["signed_change_rate"] * 100
    vol      = ticker["acc_trade_price_24h"]
    h_info   = coin["hour"]
    d_info   = coin["day"]

    both  = h_info["ok"] and d_info["ok"]
    h_only = h_info["ok"] and not d_info["ok"]
    d_only = not h_info["ok"] and d_info["ok"]

    if both:
        header_color = Fore.GREEN
        label = "★ 1시간봉 + 일봉 모두 정배열"
    elif h_only:
        header_color = Fore.YELLOW
        label = "⏱ 1시간봉만 정배열"
    elif d_only:
        header_color = Fore.CYAN
        label = "📅 일봉만 정배열"
    else:
        return  # 미정배열은 별도 테이블로 처리

    sym = market.replace("KRW-", "")
    chg_str = (Fore.GREEN if chg >= 0 else Fore.RED) + f"{chg:+.2f}%"

    print(f"\n{header_color}{'─'*60}")
    print(f"  [{rank:02d}] {sym:>10}  현재가: {fmt_price(price):>15}원  {chg_str}")
    print(f"       24h 거래대금: {fmt_vol(vol)}원    {label}{Style.RESET_ALL}")
    print_ma_detail("1시간봉", h_info, Fore.YELLOW)
    print_ma_detail("일  봉", d_info, Fore.CYAN)


# ──────────────────────────────────────────────
# 메인
# ──────────────────────────────────────────────

def main():
    print(Fore.CYAN + Style.BRIGHT + """
╔══════════════════════════════════════════════════╗
║        업비트 정배열 스캐너  v1.1                ║
║  거래량 상위 20개 KRW 코인 · 1시간봉 + 일봉     ║
║  1시간봉: 현재가>MA5>MA10>MA20>MA60>MA120        ║
║  일  봉: MA20>MA60>MA120 & 현재가>MA60 (중기)    ║
╚══════════════════════════════════════════════════╝
""" + Style.RESET_ALL)

    # 1. KRW 마켓 목록
    print("📡 KRW 마켓 목록 조회 중...", end="", flush=True)
    markets = get_krw_markets()
    print(f" {len(markets)}개 종목 확인")

    # 2. 거래대금 조회 → 상위 20개
    print("💰 24h 거래대금 조회 중...", end="", flush=True)
    tickers = get_tickers(markets)
    tickers.sort(key=lambda x: x["acc_trade_price_24h"], reverse=True)
    top20 = tickers[:TOP_N]
    print(f" 완료 → 상위 {TOP_N}개 선정")

    print(f"\n상위 {TOP_N}개 코인:")
    for i, t in enumerate(top20, 1):
        sym = t["market"].replace("KRW-", "")
        print(f"  {i:2}. {sym:<10} | 거래대금: {fmt_vol(t['acc_trade_price_24h'])}원")

    # 3. 각 코인 캔들 분석
    print(f"\n🕯️  캔들 데이터 분석 시작 (총 {TOP_N}개 × 2 타임프레임)\n")

    results = []
    for i, t in enumerate(top20, 1):
        market = t["market"]
        sym = market.replace("KRW-", "")
        sys.stdout.write(f"\r  분석 중... [{i:2}/{TOP_N}] {sym:<10}")
        sys.stdout.flush()

        try:
            hour_candles = get_candles(market, "hours")
            time.sleep(REQUEST_DELAY)
            day_candles = get_candles(market, "day")
            time.sleep(REQUEST_DELAY)

            h_info = check_jeongbae_full(hour_candles)   # 1시간봉: 완전 정배열
            d_info = check_jeongbae_mid(day_candles)    # 일봉: 중기 추세 정배열
        except Exception as e:
            h_info = {"ok": False, "reason": str(e)}
            d_info = {"ok": False, "reason": str(e)}

        results.append({
            "rank": i,
            "market": market,
            "ticker": t,
            "hour": h_info,
            "day": d_info,
        })

    print(f"\r  분석 완료! {TOP_N}개 코인 처리됨.         \n")

    # ── 결과 출력 ──────────────────────────────

    both_list  = [r for r in results if r["hour"]["ok"] and r["day"]["ok"]]
    h_only_list = [r for r in results if r["hour"]["ok"] and not r["day"]["ok"]]
    d_only_list = [r for r in results if not r["hour"]["ok"] and r["day"]["ok"]]
    none_list  = [r for r in results if not r["hour"]["ok"] and not r["day"]["ok"]]

    # ── ① 두 조건 모두 정배열
    print(Fore.GREEN + Style.BRIGHT + f"\n{'═'*60}")
    print(f"  ✅ 1시간봉 + 일봉 모두 정배열  ({len(both_list)}개)")
    print(f"{'═'*60}" + Style.RESET_ALL)
    if both_list:
        for coin in both_list:
            print_coin_result(coin["rank"], coin)
    else:
        print(Fore.WHITE + "  해당 종목 없음")

    # ── ② 1시간봉만
    print(Fore.YELLOW + Style.BRIGHT + f"\n{'═'*60}")
    print(f"  ⏱ 1시간봉만 정배열  ({len(h_only_list)}개)")
    print(f"{'═'*60}" + Style.RESET_ALL)
    if h_only_list:
        for coin in h_only_list:
            print_coin_result(coin["rank"], coin)
    else:
        print(Fore.WHITE + "  해당 종목 없음")

    # ── ③ 일봉만
    print(Fore.CYAN + Style.BRIGHT + f"\n{'═'*60}")
    print(f"  📅 일봉만 정배열  ({len(d_only_list)}개)")
    print(f"{'═'*60}" + Style.RESET_ALL)
    if d_only_list:
        for coin in d_only_list:
            print_coin_result(coin["rank"], coin)
    else:
        print(Fore.WHITE + "  해당 종목 없음")

    # ── ④ 전체 요약 테이블
    print(Fore.WHITE + Style.BRIGHT + f"\n{'═'*60}")
    print("  📋 전체 분석 결과 요약")
    print(f"{'═'*60}" + Style.RESET_ALL)

    table_data = []
    for r in results:
        sym  = r["market"].replace("KRW-", "")
        t    = r["ticker"]
        chg  = t["signed_change_rate"] * 100
        chg_str = f"{chg:+.2f}%"
        h_str = Fore.GREEN + "✅" if r["hour"]["ok"] else Fore.RED + "❌"
        d_str = Fore.GREEN + "✅" if r["day"]["ok"]  else Fore.RED + "❌"
        table_data.append([
            r["rank"],
            sym,
            f"{fmt_price(t['trade_price'])}원",
            chg_str,
            f"{fmt_vol(t['acc_trade_price_24h'])}원",
            h_str + Style.RESET_ALL,
            d_str + Style.RESET_ALL,
        ])

    headers = ["순위", "코인", "현재가", "등락률", "24h 거래대금", "1시간봉", "일봉"]
    print(tabulate(table_data, headers=headers, tablefmt="rounded_outline"))

    # ── 최종 요약
    print(f"""
{Fore.WHITE + Style.BRIGHT}📊 스캔 완료 요약
{Style.RESET_ALL}  전체 분석 : {len(results)}개
  {Fore.GREEN}✅ 양봉 정배열 (둘 다) : {len(both_list)}개{Style.RESET_ALL}
  {Fore.YELLOW}⏱ 1시간봉만 정배열   : {len(h_only_list)}개{Style.RESET_ALL}
  {Fore.CYAN}📅 일봉만 정배열      : {len(d_only_list)}개{Style.RESET_ALL}
  {Fore.RED}❌ 비정배열           : {len(none_list)}개{Style.RESET_ALL}
""")


if __name__ == "__main__":
    main()