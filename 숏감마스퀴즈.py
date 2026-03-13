import requests
import pandas as pd
import time


def get_directional_squeeze_candidates():
    print("🌍 [1/4] 코인게코 시가총액 스캔 중...")
    try:
        cg_url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=250&page=1"
        cg_data = requests.get(cg_url).json()
        mcap_dict = {str(item['symbol']).upper() + "USDT": item['market_cap'] for item in cg_data}
    except:
        mcap_dict = {}

    print("📈 [2/4] 바이낸스 24시간 거래량 스캔 중...")
    try:
        ticker_url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        ticker_data = requests.get(ticker_url).json()
        vol_dict = {item['symbol']: float(item['quoteVolume']) for item in ticker_data}
    except:
        vol_dict = {}

    print("🔍 [3/4] 바이낸스 펀딩비 양극단(롱/숏 쏠림) 추출 중...")
    try:
        funding_url = "https://fapi.binance.com/fapi/v1/premiumIndex"
        funding_data = requests.get(funding_url).json()
        df = pd.DataFrame(funding_data)
        df = df[df['symbol'].str.endswith('USDT')].copy()
        df['lastFundingRate'] = pd.to_numeric(df['lastFundingRate'])
        df['markPrice'] = pd.to_numeric(df['markPrice'])
        df['Funding Rate (%)'] = df['lastFundingRate'] * 100

        # 숏 스퀴즈 후보 (펀딩비 최하위 5개 = 숏 쏠림)
        short_squeeze_targets = df.sort_values(by='Funding Rate (%)', ascending=True).head(5)
        # 롱 스퀴즈/청산 후보 (펀딩비 최상위 5개 = 롱 쏠림)
        long_squeeze_targets = df.sort_values(by='Funding Rate (%)', ascending=False).head(5)

        target_list = pd.concat([short_squeeze_targets, long_squeeze_targets])
    except Exception as e:
        print(f"데이터 추출 실패: {e}")
        return

    print("📊 [4/4] 타겟 10종목 정밀 분석 (OI 및 롱/숏 비율) 진행 중...\n")

    results = []

    for index, row in target_list.iterrows():
        symbol = row['symbol']
        price = row['markPrice']
        funding_rate = row['Funding Rate (%)']

        # 1. 미결제약정(OI) 조회
        try:
            oi_url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={symbol}"
            oi_amount = float(requests.get(oi_url).json().get('openInterest', 0))
            oi_value = oi_amount * price
        except:
            oi_value = 0

        # 2. 롱/숏 비율 조회 (글로벌 계좌 기준, 최근 4시간)
        try:
            ls_url = f"https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol={symbol}&period=4h&limit=1"
            ls_data = requests.get(ls_url).json()
            if isinstance(ls_data, list) and len(ls_data) > 0:
                ls_ratio = float(ls_data[0]['longShortRatio'])
            else:
                ls_ratio = 1.0  # 데이터 없을 시 기본값
        except:
            ls_ratio = 1.0

        vol_24h = vol_dict.get(symbol, 0)
        mcap = mcap_dict.get(symbol, 0)

        # OI/시총 비율 계산 (시총이 있을 경우만)
        if mcap > 0:
            oi_mcap_ratio = (oi_value / mcap) * 100
            oi_mcap_str = f"{oi_mcap_ratio:.1f}%"
        else:
            oi_mcap_str = "N/A"

        # 스퀴즈 타입 분류
        squeeze_type = "🚀 숏 스퀴즈 (상승 폭발)" if funding_rate < 0 else "💥 롱 청산 (하락 폭발)"

        results.append({
            'Type': squeeze_type,
            'Symbol': symbol,
            'Funding (%)': round(funding_rate, 4),
            'L/S Ratio': round(ls_ratio, 2),
            'OI / Mcap (%)': oi_mcap_str,
            'OI Value ($)': f"${oi_value:,.0f}",
            '24h Vol ($)': f"${vol_24h:,.0f}"
        })
        time.sleep(0.3)  # API 과부하 방지

    # 데이터프레임 정리 및 출력
    final_df = pd.DataFrame(results)

    short_df = final_df[final_df['Type'].str.contains("숏")].drop(columns=['Type'])
    short_df.index = short_df.index + 1

    long_df = final_df[final_df['Type'].str.contains("롱")].drop(columns=['Type'])
    long_df.index = long_df.index + 1

    print("==========================================================================")
    print(" 🚀 [상승 폭발 대기] 숏 스퀴즈 후보 Top 5 (펀딩비 마이너스 극단) 🚀")
    print("==========================================================================")
    print(short_df.to_string())
    print("\n")
    print("==========================================================================")
    print(" 💥 [하락 폭발 대기] 롱 청산/스퀴즈 후보 Top 5 (펀딩비 플러스 극단) 💥")
    print("==========================================================================")
    print(long_df.to_string())
    print("==========================================================================")


if __name__ == "__main__":
    get_directional_squeeze_candidates()