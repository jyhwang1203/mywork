import requests
import time
import os
import sys
from datetime import datetime


# ============================================================
#  코인게코 심볼 → ID 매핑 (캐시)
# ============================================================
_cg_id_cache: dict[str, str | None] = {}


def get_coingecko_id(symbol: str) -> str | None:
    if symbol in _cg_id_cache:
        return _cg_id_cache[symbol]
    try:
        url = f"https://api.coingecko.com/api/v3/search?query={symbol}"
        data = requests.get(url, timeout=10).json()
        coins = data.get("coins", [])
        exact = [c for c in coins if c.get("symbol", "").upper() == symbol.upper()]
        if not exact:
            _cg_id_cache[symbol] = None
            return None
        ranked = [c for c in exact if c.get("market_cap_rank") is not None]
        if ranked:
            ranked.sort(key=lambda c: c["market_cap_rank"])
            result = ranked[0]["id"]
        else:
            result = exact[0]["id"]
        _cg_id_cache[symbol] = result
        return result
    except Exception:
        _cg_id_cache[symbol] = None
        return None


def get_market_cap(symbol: str) -> tuple[float, str | None]:
    cg_id = get_coingecko_id(symbol)
    if cg_id is None:
        return 0, None
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd&include_market_cap=true"
        data = requests.get(url, timeout=10).json()
        if cg_id in data:
            return data[cg_id].get("usd_market_cap", 0), cg_id
    except Exception:
        pass
    return 0, cg_id


# ============================================================
#  진단 엔진
# ============================================================
def diagnose(funding_rate, ls_ratio, oi_mcap_ratio, oi_vol_ratio, mcap):
    score = 0
    warnings = []

    if mcap <= 0:
        return {"score": 0, "direction": "판단불가", "confidence": "없음",
                "status": "🚫 시총 미확인", "warnings": ["시총 데이터 없음"]}

    # 펀딩비 (±30)
    if funding_rate < -0.1:      score += 30
    elif funding_rate < -0.05:   score += 20
    elif funding_rate < -0.01:   score += 10
    elif funding_rate > 0.1:     score -= 30
    elif funding_rate > 0.05:    score -= 20
    elif funding_rate > 0.01:    score -= 10

    # L/S (±25)
    if ls_ratio < 0.7:       score += 25
    elif ls_ratio < 0.9:     score += 15
    elif ls_ratio > 1.5:     score -= 25
    elif ls_ratio > 1.1:     score -= 15

    # OI/시총 증폭
    if oi_mcap_ratio > 30:    amp = 20
    elif oi_mcap_ratio > 15:  amp = 15
    elif oi_mcap_ratio > 10:  amp = 10
    else:                     amp = 0

    if oi_mcap_ratio > 15:
        warnings.append(f"OI/시총 {oi_mcap_ratio:.1f}%: 선물 과열")

    if score > 0:   score += amp
    elif score < 0: score -= amp

    # OI/거래량 (±15)
    if oi_vol_ratio > 1.5:    boost = 15
    elif oi_vol_ratio > 1.0:  boost = 10
    elif oi_vol_ratio > 0.5:  boost = 5
    else:                     boost = -5

    if score > 0:   score += boost
    elif score < 0: score -= boost

    # 함정 탐지
    if funding_rate < -0.03 and ls_ratio > 1.5:
        score = int(score * 0.5)
        warnings.append("⚠ 함정: 펀딩비↓ + L/S↑")
    if funding_rate > 0.03 and ls_ratio < 0.7:
        score = int(score * 0.5)
        warnings.append("⚠ 함정: 펀딩비↑ + L/S↓")

    score = max(-100, min(100, score))

    if score >= 60:    d, c, s = "숏스퀴즈", "강력", "🚨🚀 강력 숏 스퀴즈!"
    elif score >= 35:  d, c, s = "숏스퀴즈", "보통", "🔥 숏 스퀴즈 가능성↑"
    elif score >= 15:  d, c, s = "숏스퀴즈", "약함", "📈 약한 숏 스퀴즈"
    elif score <= -60: d, c, s = "롱청산", "강력", "🚨📉 강력 롱 청산!"
    elif score <= -35: d, c, s = "롱청산", "보통", "🔻 롱 청산 가능성↑"
    elif score <= -15: d, c, s = "롱청산", "약함", "📉 약한 롱 청산"
    else:              d, c, s = "중립", "없음", "⚖️ 중립"

    return {"score": score, "direction": d, "confidence": c, "status": s, "warnings": warnings}


# ============================================================
#  데이터 수집
# ============================================================
def fetch_coin_data(symbol: str, mcap_cache: dict) -> dict | None:
    """단일 코인 데이터 수집. mcap_cache를 사용하여 코인게코 호출 최소화."""
    bsym = symbol + "USDT"
    try:
        # 바이낸스 데이터 (4개 API 호출)
        fd = requests.get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={bsym}", timeout=8).json()
        if "code" in fd:
            return None

        price = float(fd["markPrice"])
        funding = float(fd["lastFundingRate"]) * 100

        oi_amt = float(requests.get(
            f"https://fapi.binance.com/fapi/v1/openInterest?symbol={bsym}", timeout=8
        ).json().get("openInterest", 0))
        oi_val = oi_amt * price

        vol = float(requests.get(
            f"https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={bsym}", timeout=8
        ).json().get("quoteVolume", 0))

        ls_data = requests.get(
            f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            f"?symbol={bsym}&period=4h&limit=1", timeout=8
        ).json()
        ls = float(ls_data[0]["longShortRatio"]) if isinstance(ls_data, list) and ls_data else 1.0

        # 시가총액 (캐시 우선, 없으면 조회 후 캐시)
        if symbol in mcap_cache:
            mcap, cg_id = mcap_cache[symbol]
        else:
            mcap, cg_id = get_market_cap(symbol)
            mcap_cache[symbol] = (mcap, cg_id)
            time.sleep(1.2)  # 코인게코 rate limit

        oi_mcap = (oi_val / mcap * 100) if mcap > 0 else 0
        oi_vol = (oi_val / vol) if vol > 0 else 0

        diag = diagnose(funding, ls, oi_mcap, oi_vol, mcap)

        return {
            "symbol": symbol, "price": price, "funding": funding,
            "ls": ls, "oi_val": oi_val, "vol": vol, "mcap": mcap,
            "oi_mcap": oi_mcap, "oi_vol": oi_vol, "diagnosis": diag,
        }
    except Exception:
        return None


# ============================================================
#  화면 렌더링
# ============================================================
def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")


def fmt_money(v):
    if v >= 1e9:   return f"${v/1e9:.1f}B"
    if v >= 1e6:   return f"${v/1e6:.1f}M"
    if v >= 1e3:   return f"${v/1e3:.1f}K"
    return f"${v:.0f}"


def fmt_price(p):
    if p >= 100:     return f"${p:,.2f}"
    if p >= 1:       return f"${p:,.4f}"
    if p >= 0.001:   return f"${p:,.6f}"
    return f"${p:.8f}"


def score_bar(score, width=20):
    center = width // 2
    filled = int(abs(score) / 100 * center)
    filled = min(center, max(0, filled))
    if score > 0:
        return "░" * center + "▶" + "█" * filled + "░" * (center - filled)
    elif score < 0:
        return "░" * (center - filled) + "█" * filled + "◀" + "░" * center
    return "░" * center + "●" + "░" * center


def render_dashboard(results: list[dict], prev_results: dict, cycle: int,
                     interval: int, symbols: list[str]):
    """실시간 대시보드를 렌더링합니다."""

    clear_screen()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 점수 절대값 기준 정렬
    results.sort(key=lambda x: abs(x["diagnosis"]["score"]), reverse=True)

    print("=" * 110)
    print(f" 🕵️‍♂️ 실시간 스퀴즈 모니터링 대시보드 v4.0")
    print(f"    갱신 주기: {interval}초 | 사이클: #{cycle} | 마지막 갱신: {now}")
    print(f"    감시 중: {', '.join(symbols)}")
    print("=" * 110)

    # 헤더
    print(
        f" {'#':>3} │ {'코인':<7} │ {'가격':>13} │ {'변동':>7} │"
        f" {'펀딩비':>8} │ {'L/S':>5} │ {'OI/시총':>7} │"
        f" {'OI/Vol':>6} │ {'점수':>5} │ {'게이지':<22}│ {'진단'}"
    )
    print("─" * 110)

    alerts = []  # 이번 사이클에서 발생한 알림

    for rank, d in enumerate(results, 1):
        sym = d["symbol"]
        diag = d["diagnosis"]

        # 가격 변동 계산
        prev = prev_results.get(sym)
        if prev and prev["price"] > 0:
            pct_change = (d["price"] - prev["price"]) / prev["price"] * 100
            if pct_change > 0:
                chg_str = f"\033[32m+{pct_change:.2f}%\033[0m"  # 초록
            elif pct_change < 0:
                chg_str = f"\033[31m{pct_change:.2f}%\033[0m"   # 빨강
            else:
                chg_str = "  0.00%"
        else:
            pct_change = 0
            chg_str = "   NEW"

        # 점수 변동 감지 → 알림
        if prev:
            score_diff = diag["score"] - prev["diagnosis"]["score"]
            if abs(score_diff) >= 15:
                direction = "⬆" if score_diff > 0 else "⬇"
                alerts.append(
                    f"  🔔 [{sym}] 점수 급변: {prev['diagnosis']['score']:+d} → "
                    f"{diag['score']:+d} ({direction}{abs(score_diff)})"
                )

        # OI/시총
        oi_mcap_str = f"{d['oi_mcap']:.1f}%" if d["mcap"] > 0 else "  N/A"

        # 점수 색상
        sc = diag["score"]
        if sc >= 35:
            score_str = f"\033[32m{sc:>+5d}\033[0m"
        elif sc <= -35:
            score_str = f"\033[31m{sc:>+5d}\033[0m"
        else:
            score_str = f"{sc:>+5d}"

        bar = score_bar(sc)

        print(
            f" {rank:>3} │ {sym:<7} │ {fmt_price(d['price']):>13} │ {chg_str:>7} │"
            f" {d['funding']:>+7.3f}% │ {d['ls']:>5.2f} │ {oi_mcap_str:>7} │"
            f" {d['oi_vol']:>5.2f}x │ {score_str} │ {bar}│ {diag['status']}"
        )

    print("─" * 110)

    # 경고 모음
    all_warnings = []
    for d in results:
        for w in d["diagnosis"]["warnings"]:
            all_warnings.append(f"  [{d['symbol']}] {w}")

    if all_warnings:
        print("\n ⚠️  경고:")
        for w in all_warnings:
            print(f"   {w}")

    # 점수 급변 알림
    if alerts:
        print("\n 🔔 이번 사이클 알림:")
        for a in alerts:
            print(f"   {a}")

    # 상위 코인 요약
    top = results[:3] if len(results) >= 3 else results
    print(f"\n 🎯 Top {len(top)} 주목:")
    for i, d in enumerate(top, 1):
        diag = d["diagnosis"]
        print(f"    {i}. [{d['symbol']}] {diag['score']:+d}점 → {diag['status']}")

    print(f"\n 💡 Ctrl+C로 모니터링 종료 | 다음 갱신까지 {interval}초")
    print("=" * 110)


# ============================================================
#  자동 스캔: 바이낸스 전체에서 펀딩비 극단값 상위 N개 선별
# ============================================================
def scan_top_funding(top_n: int = 20) -> list[str]:
    """바이낸스 전체 선물에서 펀딩비 절대값 상위 종목 심볼 반환."""
    try:
        data = requests.get("https://fapi.binance.com/fapi/v1/premiumIndex", timeout=15).json()
        pairs = []
        for item in data:
            sym = item.get("symbol", "")
            if sym.endswith("USDT"):
                rate = float(item.get("lastFundingRate", 0)) * 100
                pairs.append({"symbol": sym.replace("USDT", ""), "rate": rate})
        pairs.sort(key=lambda x: abs(x["rate"]), reverse=True)
        return [p["symbol"] for p in pairs[:top_n]]
    except Exception:
        return []


# ============================================================
#  메인
# ============================================================
def main():
    print("=" * 62)
    print(" 🕵️‍♂️ 실시간 스퀴즈 모니터링 대시보드 v4.0")
    print("=" * 62)

    print("\n 📋 모드를 선택하세요:\n")
    print("    [1] 직접 입력한 코인 실시간 모니터링")
    print("    [2] 자동 스캔 — 펀딩비 극단값 상위 종목 실시간 감시")
    print("    [3] 단일 코인 1회 상세 진단 (v3 호환)")
    print()

    mode = input(" 👉 모드 (1/2/3): ").strip()

    if mode == "1":
        raw = input("\n 👉 코인 심볼 (쉼표 구분, 예: BTC,ETH,SOL,ENSO): ").strip()
        if not raw:
            print(" ❌ 심볼을 입력하세요.")
            return
        symbols = list(dict.fromkeys([s.strip().upper() for s in raw.split(",") if s.strip()]))

    elif mode == "2":
        n_str = input("\n 👉 상위 몇 개 종목? (기본: 20): ").strip()
        top_n = int(n_str) if n_str.isdigit() and int(n_str) > 0 else 20
        print(f"\n 🔍 바이낸스 전체 선물에서 펀딩비 극단값 상위 {top_n}개 스캔 중...")
        symbols = scan_top_funding(top_n)
        if not symbols:
            print(" ❌ 스캔 실패. 네트워크를 확인하세요.")
            return
        print(f"    선별 완료: {', '.join(symbols)}")

    elif mode == "3":
        # 단일 코인 1회 진단 (v3 호환 모드)
        target = input("\n 👉 코인 심볼: ").strip().upper()
        if not target:
            print(" ❌ 심볼을 입력하세요.")
            return
        print(f"\n [{target}] 데이터 수집 중...\n")
        mcap_cache = {}
        data = fetch_coin_data(target, mcap_cache)
        if data is None:
            print(f" ❌ {target} 데이터를 가져올 수 없습니다.")
            return
        # 상세 리포트 출력
        d = data["diagnosis"]
        print("=" * 62)
        print(f" 📊 [{target}] 심층 진단 리포트")
        print("=" * 62)
        print(f" 가격: {fmt_price(data['price'])}  |  펀딩비: {data['funding']:+.4f}%  |  L/S: {data['ls']:.2f}")
        print(f" OI: {fmt_money(data['oi_val'])}  |  거래량: {fmt_money(data['vol'])}  |  시총: {fmt_money(data['mcap']) if data['mcap'] > 0 else 'N/A'}")
        print(f" OI/시총: {data['oi_mcap']:.1f}%  |  OI/Vol: {data['oi_vol']:.2f}x")
        print("-" * 62)
        print(f" 점수: {d['score']:+d}/100  |  방향: {d['direction']}  |  신뢰도: {d['confidence']}")
        print(f" 진단: {d['status']}")
        if d["warnings"]:
            print("-" * 62)
            for w in d["warnings"]:
                print(f" ⚠️  {w}")
        print("=" * 62)
        return

    else:
        print(" ❌ 1, 2, 3 중 하나를 입력하세요.")
        return

    # 갱신 주기
    int_str = input(f"\n ⏱️  갱신 주기 (초, 기본: 30): ").strip()
    interval = int(int_str) if int_str.isdigit() and int(int_str) >= 10 else 30

    print(f"\n 🚀 실시간 모니터링을 시작합니다! ({len(symbols)}개 코인, {interval}초 간격)")
    print(f"    첫 번째 데이터 수집 중... (시가총액은 첫 사이클에서만 조회합니다)\n")

    mcap_cache = {}  # 시가총액 캐시 (첫 사이클에서 수집, 이후 재사용)
    prev_map = {}    # 이전 사이클 데이터 (변동 추적용)
    cycle = 0

    try:
        while True:
            cycle += 1
            results = []

            for i, sym in enumerate(symbols, 1):
                # 첫 사이클이 아니면 진행 표시 (clear 전이므로 안 보임, 하지만 긴 수집 시 유용)
                data = fetch_coin_data(sym, mcap_cache)
                if data:
                    results.append(data)

            if results:
                render_dashboard(results, prev_map, cycle, interval, symbols)

                # 현재 결과를 prev_map에 저장 (다음 사이클 비교용)
                prev_map = {d["symbol"]: d for d in results}
            else:
                print(f"\n ❌ 사이클 #{cycle}: 데이터 수집 실패. {interval}초 후 재시도...")

            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\n 🛑 모니터링을 종료합니다. 수고하셨습니다!")
        sys.exit(0)


if __name__ == "__main__":
    main()