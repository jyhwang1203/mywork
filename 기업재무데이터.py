"""
미국 주요 기업 재무 데이터 수집기 (yfinance)
=============================================
필요 라이브러리 설치:
    pip install yfinance pandas

사용법:
    python us_stock_financials.py
"""

import yfinance as yf
import pandas as pd

# ─────────────────────────────────────────
# 1. 분석할 기업 티커 목록
# ─────────────────────────────────────────
TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "META","NVDA","ONDS","IONQ","005930.KS", "000660.KS"]


def get_stock_price(ticker: yf.Ticker, symbol: str) -> pd.DataFrame:
    """주가/시세 데이터 (최근 1년, 일별)"""
    print(f"\n📈 [{symbol}] 주가 데이터 로드 중...")
    hist = ticker.history(period="1y")
    hist.index = hist.index.tz_localize(None)  # timezone 제거
    print(hist[["Open", "High", "Low", "Close", "Volume"]].tail(5).to_string())
    return hist


def get_financial_statements(ticker: yf.Ticker, symbol: str) -> dict:
    """재무제표 - 손익계산서 & 대차대조표"""
    print(f"\n📊 [{symbol}] 재무제표 로드 중...")

    # 손익계산서 (연간)
    income_stmt = ticker.financials  # 행: 항목, 열: 연도
    # 대차대조표 (연간)
    balance_sheet = ticker.balance_sheet

    # 주요 항목만 추출
    income_items = [
        "Total Revenue",
        "Gross Profit",
        "Operating Income",
        "Net Income",
        "EBITDA",
    ]
    balance_items = [
        "Total Assets",
        "Total Liabilities Net Minority Interest",
        "Stockholders Equity",
        "Total Debt",
        "Cash And Cash Equivalents",
    ]

    income_filtered = income_stmt.loc[
        income_stmt.index.intersection(income_items)
    ]
    balance_filtered = balance_sheet.loc[
        balance_sheet.index.intersection(balance_items)
    ]

    print("\n  [손익계산서 주요 항목 - 단위: USD]")
    print(income_filtered.to_string())
    print("\n  [대차대조표 주요 항목 - 단위: USD]")
    print(balance_filtered.to_string())

    return {"income_statement": income_filtered, "balance_sheet": balance_filtered}


def get_key_metrics(ticker: yf.Ticker, symbol: str) -> dict:
    """주요 재무 지표 (PER, EPS, ROE 등)"""
    print(f"\n🔑 [{symbol}] 주요 지표 로드 중...")
    info = ticker.info

    metrics = {
        "시가총액 (Market Cap)":          info.get("marketCap"),
        "현재 주가":                      info.get("currentPrice"),
        # ── EPS ──────────────────────────────────────
        "EPS - Trailing (과거 12개월)":   info.get("trailingEps"),
        "EPS - Forward (향후 12개월 예상)": info.get("forwardEps"),
        # ── PER ──────────────────────────────────────
        "PER - Trailing (과거 12개월)":   info.get("trailingPE"),
        "PER - Forward (향후 12개월 예상)": info.get("forwardPE"),
        # ── 기타 밸류에이션 ───────────────────────────
        "PBR (P/B Ratio)":               info.get("priceToBook"),
        "PSR (P/S Ratio)":               info.get("priceToSalesTrailing12Months"),
        "EV/EBITDA":                     info.get("enterpriseToEbitda"),
        # ── 수익성 ────────────────────────────────────
        "ROE (Return on Equity)":        info.get("returnOnEquity"),
        "ROA (Return on Assets)":        info.get("returnOnAssets"),
        "영업이익률 (Operating Margin)":  info.get("operatingMargins"),
        "순이익률 (Profit Margin)":       info.get("profitMargins"),
        # ── 재무 건전성 ───────────────────────────────
        "부채비율 (Debt/Equity)":         info.get("debtToEquity"),
        # ── 기타 ──────────────────────────────────────
        "52주 최고가":                    info.get("fiftyTwoWeekHigh"),
        "52주 최저가":                    info.get("fiftyTwoWeekLow"),
        "베타 (Beta)":                    info.get("beta"),
    }

    df = pd.DataFrame.from_dict(
        metrics, orient="index", columns=[symbol]
    )
    # 퍼센트 단위 변환
    for pct_key in ["ROE (Return on Equity)", "ROA (Return on Assets)",
                    "영업이익률 (Operating Margin)", "순이익률 (Profit Margin)"]:

        if df.loc[pct_key, symbol] is not None:
            df.loc[pct_key, symbol] = f"{df.loc[pct_key, symbol]*100:.2f}%"

    print(df.to_string())
    return metrics


def get_dividend_info(ticker: yf.Ticker, symbol: str) -> pd.DataFrame:
    """배당 정보"""
    print(f"\n💰 [{symbol}] 배당 정보 로드 중...")
    info = ticker.info

    # 배당 요약
    print(f"  연간 배당금(DPS):  ${info.get('dividendRate', 'N/A')}")
    print(f"  배당 수익률:       {info.get('dividendYield', 0)*100:.2f}%" if info.get('dividendYield') else "  배당 수익률: N/A")
    print(f"  배당 성향(Payout): {info.get('payoutRatio', 'N/A')}")

    # 과거 배당 이력 (최근 8개)
    dividends = ticker.dividends
    if not dividends.empty:
        dividends.index = dividends.index.tz_localize(None)
        print(f"\n  최근 배당 이력:")
        print(dividends.tail(8).to_string())
    else:
        print("  배당 이력 없음")

    return dividends


def get_liquidity_and_assets(ticker: yf.Ticker, symbol: str) -> dict:
    """유동성 지표 & 자산/부채 상세 데이터"""
    print(f"\n🏦 [{symbol}] 유동성 & 자산/부채 데이터 로드 중...")
    info = ticker.info
    bs = ticker.balance_sheet  # 대차대조표 (연간)

    # ── ticker.info 기반 유동성 지표 ──────────────────────────────
    liquidity_info = {
        "유동비율 (Current Ratio)":   info.get("currentRatio"),      # 유동자산 / 유동부채
        "당좌비율 (Quick Ratio)":      info.get("quickRatio"),        # (유동자산 - 재고) / 유동부채
        "총 현금 (Total Cash)":       info.get("totalCash"),
        "주당 현금 (Cash Per Share)":  info.get("totalCashPerShare"),
        "총 부채 (Total Debt)":       info.get("totalDebt"),
        "순부채 (Net Debt)":          info.get("netDebt") if info.get("netDebt") else (
            (info.get("totalDebt") or 0) - (info.get("totalCash") or 0)
        ),
        "부채비율 D/E (Debt/Equity)":  info.get("debtToEquity"),
    }

    print("\n  [유동성 지표]")
    for k, v in liquidity_info.items():
        if v is not None:
            if "비율" in k:
                print(f"    {k}: {v:.2f}")
            elif isinstance(v, (int, float)) and abs(v) > 1_000:
                print(f"    {k}: ${v:,.0f}")
            else:
                print(f"    {k}: {v}")
        else:
            print(f"    {k}: N/A")

    # ── 대차대조표 기반 자산/부채 항목 ───────────────────────────
    asset_liability_items = [
        # 자산
        "Total Assets",
        "Current Assets",
        "Cash And Cash Equivalents",
        "Receivables",
        "Inventory",
        "Other Short Term Investments",
        # 부채
        "Total Liabilities Net Minority Interest",
        "Current Liabilities",
        "Accounts Payable",
        "Current Debt",
        "Long Term Debt",
        # 자본
        "Stockholders Equity",
        "Retained Earnings",
        "Common Stock",
    ]

    bs_filtered = bs.loc[bs.index.intersection(asset_liability_items)]

    # 운전자본(Working Capital) 직접 계산
    if "Current Assets" in bs.index and "Current Liabilities" in bs.index:
        working_capital = bs.loc["Current Assets"] - bs.loc["Current Liabilities"]
        working_capital.name = "Working Capital (운전자본)"
        bs_filtered = pd.concat([bs_filtered, working_capital.to_frame().T])

    print("\n  [자산/부채 상세 - 단위: USD, 최근 4개 연도]")
    print(bs_filtered.to_string())

    return {"liquidity": liquidity_info, "balance_detail": bs_filtered}


def get_growth_company_metrics(ticker: yf.Ticker, symbol: str) -> dict:
    """
    적자·성장 기업 전용 핵심 지표
    ─────────────────────────────────────────────────────────────
    ① 매출 성장률 (YoY)          - ticker.financials
    ② Cash Burn & Runway         - ticker.cashflow + ticker.info
    ③ EV / Sales                 - ticker.info
    ④ 매출 총이익률 (Gross Margin) - ticker.info / ticker.financials
    ⑤ SBC & Adjusted EBITDA      - ticker.cashflow
    ⚠ RPO(수주 잔고)은 yfinance 미지원 → SEC 10-Q 직접 확인 필요
    ─────────────────────────────────────────────────────────────
    """
    print(f"\n🚀 [{symbol}] 성장·적자 기업 핵심 지표 로드 중...")
    info = ticker.info
    financials = ticker.financials   # 손익계산서 (연간, 최신→과거 순)
    cashflow   = ticker.cashflow     # 현금흐름표 (연간)

    result = {}

    # ─────────────────────────────────────────────
    # ① 매출 성장률 (YoY) - 최근 2개 연도 비교
    # ─────────────────────────────────────────────
    print("\n  [① 매출 성장률 YoY]")
    if "Total Revenue" in financials.index and financials.shape[1] >= 2:
        rev = financials.loc["Total Revenue"].dropna()
        # 최신 연도(index 0)와 전년도(index 1) 비교
        latest_rev   = rev.iloc[0]
        previous_rev = rev.iloc[1]
        yoy_growth   = (latest_rev - previous_rev) / abs(previous_rev) * 100
        result["매출 성장률 YoY (%)"] = round(yoy_growth, 2)
        print(f"    최신 연도 매출: ${latest_rev:,.0f}")
        print(f"    전년도 매출:   ${previous_rev:,.0f}")
        print(f"    YoY 성장률:    {yoy_growth:.2f}%")
        if yoy_growth >= 50:
            print("    ✅ 고성장 (50% 이상) — 시장 지배력 확대 신호")
        else:
            print("    ⚠️  성장률 50% 미만 — 성장 속도 점검 필요")
    else:
        result["매출 성장률 YoY (%)"] = None
        print("    데이터 부족 (연도 수 < 2)")

    # ─────────────────────────────────────────────
    # ② Cash Burn Rate & Runway
    # ─────────────────────────────────────────────
    print("\n  [② Cash Burn & Runway]")
    total_cash = info.get("totalCash", 0)

    # 영업 현금 흐름(Operating Cash Flow)이 음수면 = 현금을 태우는 중
    annual_burn = None
    if "Operating Cash Flow" in cashflow.index:
        op_cf = cashflow.loc["Operating Cash Flow"].iloc[0]
        # 음수면 burn, 양수면 창출
        annual_burn = op_cf
        monthly_burn = op_cf / 12
        result["연간 영업 현금흐름 (OCF)"] = round(op_cf, 0)

        print(f"    연간 영업 현금흐름 (OCF): ${op_cf:,.0f}")
        if op_cf < 0:
            runway_months = abs(total_cash / monthly_burn) if monthly_burn != 0 else float("inf")
            result["Cash Runway (개월)"] = round(runway_months, 1)
            print(f"    총 현금:                  ${total_cash:,.0f}")
            print(f"    Cash Runway:              약 {runway_months:.1f}개월 ({runway_months/12:.1f}년)")
            if runway_months >= 24:
                print("    ✅ 런웨이 2년 이상 — 생존 리스크 낮음")
            else:
                print("    🚨 런웨이 2년 미만 — 유상증자 또는 추가 조달 가능성")
        else:
            result["Cash Runway (개월)"] = "흑자 전환 (무한대)"
            print("    ✅ OCF 양수 — 이미 현금을 창출 중 (Runway 무한)")
    else:
        result["연간 영업 현금흐름 (OCF)"] = None
        result["Cash Runway (개월)"] = None
        print("    현금흐름 데이터 없음")

    # ─────────────────────────────────────────────
    # ③ EV / Sales (P/E 대신 쓰는 적자 기업 밸류에이션)
    # ─────────────────────────────────────────────
    print("\n  [③ EV / Sales]")
    ev_to_revenue = info.get("enterpriseToRevenue")
    result["EV / Sales"] = ev_to_revenue
    if ev_to_revenue is not None:
        print(f"    EV/Sales: {ev_to_revenue:.2f}x")
        if ev_to_revenue > 20:
            print("    ⚠️  매우 높음 — 높은 성장 기대치가 이미 주가에 반영됨")
        elif ev_to_revenue > 10:
            print("    🔶 다소 높음 — 성장률로 정당화되는지 확인 필요")
        else:
            print("    ✅ 상대적으로 합리적인 수준")
    else:
        print("    데이터 없음")

    # ─────────────────────────────────────────────
    # ④ 매출 총이익률 (Gross Margin)
    # ─────────────────────────────────────────────
    print("\n  [④ 매출 총이익률 (Gross Margin)]")
    gross_margin = info.get("grossMargins")
    result["매출 총이익률 (Gross Margin)"] = gross_margin
    if gross_margin is not None:
        gm_pct = gross_margin * 100
        print(f"    Gross Margin: {gm_pct:.2f}%")
        if gm_pct > 0:
            print("    ✅ 플러스 마진 — 규모 확대 시 흑자 전환 가능 구조")
        else:
            print("    🚨 마이너스 마진 — 제품 원가 구조 개선 필요")
    else:
        print("    데이터 없음")

    # 연도별 Gross Margin 추이
    if "Gross Profit" in financials.index and "Total Revenue" in financials.index:
        gp  = financials.loc["Gross Profit"]
        rev = financials.loc["Total Revenue"]
        gm_trend = (gp / rev * 100).dropna()
        print("    연도별 Gross Margin 추이:")
        for date, val in gm_trend.items():
            print(f"      {date.year}: {val:.2f}%")

    # ─────────────────────────────────────────────
    # ⑤ SBC & Adjusted EBITDA
    # ─────────────────────────────────────────────
    print("\n  [⑤ SBC & Adjusted EBITDA]")
    sbc = None
    if "Stock Based Compensation" in cashflow.index:
        sbc = cashflow.loc["Stock Based Compensation"].iloc[0]
        result["SBC (주식 보상 비용)"] = round(sbc, 0)
        print(f"    SBC (주식 보상 비용): ${sbc:,.0f}")
        if info.get("marketCap"):
            sbc_to_mktcap = sbc / info["marketCap"] * 100
            print(f"    SBC / 시가총액 비율:  {sbc_to_mktcap:.2f}%")
            if sbc_to_mktcap > 5:
                print("    ⚠️  SBC 비중 높음 — 주주 희석 주의")
            else:
                print("    ✅ SBC 비중 합리적")
    else:
        result["SBC (주식 보상 비용)"] = None
        print("    SBC 데이터 없음")

    # Adjusted EBITDA = EBITDA + SBC (현금 지출 없는 비용 환원)
    if "EBITDA" in financials.index and sbc is not None:
        ebitda = financials.loc["EBITDA"].iloc[0]
        adj_ebitda = ebitda + sbc
        result["Adjusted EBITDA"] = round(adj_ebitda, 0)
        print(f"    GAAP EBITDA:          ${ebitda:,.0f}")
        print(f"    Adjusted EBITDA:      ${adj_ebitda:,.0f}")
        if adj_ebitda > ebitda:
            print("    ℹ️  SBC 제거 시 실질 운영 수익성이 더 양호함")
    else:
        result["Adjusted EBITDA"] = None

    print(f"\n  ⚠️  RPO(수주 잔고)는 yfinance 미지원 → SEC EDGAR 10-Q 참고")
    print(f"     https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={symbol}&type=10-Q")

    return result


def compare_metrics(results: dict, growth_results: dict) -> pd.DataFrame:
    """여러 기업 주요 지표 비교 테이블 생성"""
    print("\n" + "="*70)
    print("📋 기업 간 주요 재무 지표 비교")
    print("="*70)

    compare_keys = {
        "현재 주가":              "currentPrice",
        # ── 밸류에이션 ──────────────────────────────
        "EPS - Trailing":        "trailingEps",
        "EPS - Forward":         "forwardEps",
        "PER - Trailing":        "trailingPE",
        "PER - Forward":         "forwardPE",
        "PBR":                   "priceToBook",
        "EV/EBITDA":             "enterpriseToEbitda",
        # ── 적자·성장 기업 전용 ───────────────────────
        "EV / Sales":            "enterpriseToRevenue",
        "Gross Margin":          "grossMargins",
        # ── 수익성 ──────────────────────────────────
        "ROE":                   "returnOnEquity",
        "영업이익률":             "operatingMargins",
        "순이익률":               "profitMargins",
        # ── 유동성 & 재무 건전성 ─────────────────────
        "유동비율":               "currentRatio",
        "당좌비율":               "quickRatio",
        "총 현금":                "totalCash",
        "총 부채":                "totalDebt",
        "부채비율 D/E":           "debtToEquity",
        # ── 기타 ────────────────────────────────────
        "베타":                   "beta",
        "배당 수익률":            "dividendYield",
    }

    pct_keys   = {"returnOnEquity", "operatingMargins", "profitMargins",
                  "dividendYield", "grossMargins"}
    money_keys = {"totalCash", "totalDebt"}

    table = {}
    for symbol, info in results.items():
        table[symbol] = {}
        for label, key in compare_keys.items():
            val = info.get(key)
            if val is not None and key in pct_keys:
                table[symbol][label] = f"{val*100:.2f}%"
            elif val is not None and key in money_keys:
                table[symbol][label] = f"${val:,.0f}"
            elif val is not None:
                table[symbol][label] = round(val, 2)
            else:
                table[symbol][label] = "N/A"

        # 성장 기업 지표 — growth_results에서 직접 주입
        gr = growth_results.get(symbol, {})
        table[symbol]["매출 성장률 YoY (%)"] = (
            f"{gr['매출 성장률 YoY (%)']:.2f}%"
            if gr.get("매출 성장률 YoY (%)") is not None else "N/A"
        )
        table[symbol]["Cash Runway (개월)"] = gr.get("Cash Runway (개월)", "N/A")
        table[symbol]["SBC"] = (
            f"${gr['SBC (주식 보상 비용)']:,.0f}"
            if gr.get("SBC (주식 보상 비용)") is not None else "N/A"
        )
        table[symbol]["Adj. EBITDA"] = (
            f"${gr['Adjusted EBITDA']:,.0f}"
            if gr.get("Adjusted EBITDA") is not None else "N/A"
        )

    df = pd.DataFrame(table)
    print(df.to_string())
    return df


# ─────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────
def main():
    all_info    = {}
    all_growth  = {}

    for symbol in TICKERS:
        print("\n" + "="*70)
        print(f"🏢  {symbol} 데이터 수집 시작")
        print("="*70)

        ticker = yf.Ticker(symbol)

        # 1) 주가 데이터
        get_stock_price(ticker, symbol)

        # 2) 재무제표
        get_financial_statements(ticker, symbol)

        # 3) 주요 지표 (PER, EPS, ROE 등)
        get_key_metrics(ticker, symbol)

        # 4) 배당 정보
        get_dividend_info(ticker, symbol)

        # 5) 유동성 & 자산/부채
        get_liquidity_and_assets(ticker, symbol)

        # 6) 성장·적자 기업 전용 지표
        growth = get_growth_company_metrics(ticker, symbol)
        all_growth[symbol] = growth

        # 비교용 info 저장
        all_info[symbol] = ticker.info

    # 7) 기업 간 통합 비교 테이블
    compare_df = compare_metrics(all_info, all_growth)

    # CSV 저장
    compare_df.to_csv("us_stock_comparison.csv", encoding="utf-8-sig")
    print("\n\n✅ 비교 테이블이 'us_stock_comparison.csv'로 저장되었습니다.")


if __name__ == "__main__":
    main()