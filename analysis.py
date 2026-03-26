import requests
import pandas as pd
import numpy as np
import time


def get_krw_markets():
    url = "https://api.upbit.com/v1/market/all"
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            markets = [m['market'] for m in resp.json() if m['market'].startswith('KRW-')]
            return markets
    except Exception as e:
        print(f"Error fetching markets: {e}")
    return []


def get_top_volume_markets(markets, top_n=15):
    url = "https://api.upbit.com/v1/ticker"
    chunk_size = 100
    all_tickers = []

    for i in range(0, len(markets), chunk_size):
        chunk = markets[i:i + chunk_size]
        querystring = {"markets": ",".join(chunk)}
        headers = {"accept": "application/json"}
        try:
            resp = requests.get(url, headers=headers, params=querystring)
            if resp.status_code == 200:
                all_tickers.extend(resp.json())
        except Exception as e:
            print(f"Error fetching tickers: {e}")
        time.sleep(0.1)

    # 거래대금(acc_trade_price_24h) 기준으로 내림차순 정렬
    sorted_tickers = sorted(all_tickers, key=lambda x: x['acc_trade_price_24h'], reverse=True)
    top_markets = [t['market'] for t in sorted_tickers[:top_n]]
    return top_markets


def get_candles(market, unit='minutes/240', count=200):
    """
    unit: 'days', 'minutes/1', 'minutes/60', 'minutes/240' etc.
    """
    url = f"https://api.upbit.com/v1/candles/{unit}"
    querystring = {"market": market, "count": str(count)}
    headers = {"accept": "application/json"}

    try:
        resp = requests.get(url, headers=headers, params=querystring)
        if resp.status_code == 200:
            df = pd.DataFrame(resp.json())
            if df.empty:
                return df
            # Date 과거순 정렬
            df = df.iloc[::-1].reset_index(drop=True)
            return df
    except Exception as e:
        print(f"Error fetching candles for {market}: {e}")
    return pd.DataFrame()


# ---------------------------------------------------------
# 전략 1: 볼린저 밴드 상단 돌파 (upbit_scanner.py 기반)
# ---------------------------------------------------------
def check_bollinger_breakout(df):
    if len(df) < 20:
        return False

    df['ma20'] = df['trade_price'].rolling(window=20).mean()
    df['std'] = df['trade_price'].rolling(window=20).std()
    df['upper'] = df['ma20'] + (df['std'] * 2)
    df['lower'] = df['ma20'] - (df['std'] * 2)
    df['bandwidth'] = (df['upper'] - df['lower']) / df['ma20']

    # 현재 캔들이나 직전 캔들이 상단 밴드 돌파 확인
    last_close = df['trade_price'].iloc[-2]
    last_upper = df['upper'].iloc[-2]

    curr_close = df['trade_price'].iloc[-1]
    curr_upper = df['upper'].iloc[-1]

    breakout = (curr_close > curr_upper) or (last_close > last_upper and curr_close >= df['ma20'].iloc[-1])

    return breakout


# ---------------------------------------------------------
# 전략 2: 하락 추세선 돌파 (idea_scanner.py 아이디어1)
# ---------------------------------------------------------
def check_trendline_breakout(df):
    """
    최근 30~50 캔들 동안 뚜렷한 하락 추세 후 20이평 돌파(거래량 동반) 확인
    """
    if len(df) < 50:
        return False

    df['ma20'] = df['trade_price'].rolling(window=20).mean()
    df['ma50'] = df['trade_price'].rolling(window=50).mean()
    df['vol_ma20'] = df['candle_acc_trade_volume'].rolling(window=20).mean()

    # 50 이평선이 하락세인가? (과거 50이평 20개전 > 현재 50이평)
    is_downtrend = df['ma50'].iloc[-20] > df['ma50'].iloc[-2]

    # 현재 또는 직전 캔들이 20이평을 거래량(평소 1.5배 이상)을 동반하여 돌파했는가?
    curr = df.iloc[-1]
    prev = df.iloc[-2]

    breakout_curr = (curr['trade_price'] > curr['ma20']) and (df.iloc[-2]['trade_price'] < df.iloc[-2]['ma20'])
    breakout_prev = (prev['trade_price'] > prev['ma20']) and (df.iloc[-3]['trade_price'] < df.iloc[-3]['ma20'])

    strong_volume = curr['candle_acc_trade_volume'] > curr['vol_ma20'] * 1.5 or prev['candle_acc_trade_volume'] > prev[
        'vol_ma20'] * 1.5

    return is_downtrend and (breakout_curr or breakout_prev) and strong_volume


# ---------------------------------------------------------
# 전략 3: 폭락 후 거래량 V자 반등 (idea_scanner.py 아이디어3)
# ---------------------------------------------------------
def check_v_shape_rebound(df):
    """
    분봉/시간봉상 폭락 후 최저점(또는 직후)에서 3배 이상 거래량이 터지며 V자 반등 중인지 확인
    """
    if len(df) < 30:
        return False

    df['vol_ma20'] = df['candle_acc_trade_volume'].rolling(window=20).mean()
    recent_df = df.iloc[-20:]

    min_idx = recent_df['low_price'].idxmin()
    min_candle = recent_df.loc[min_idx]

    # 최저점 캔들의 거래량이 20이평 거래량의 3배 이상인가?
    if min_candle['candle_acc_trade_volume'] > min_candle['vol_ma20'] * 3.0:
        curr_price = df.iloc[-1]['trade_price']
        if curr_price > min_candle['low_price'] * 1.03:  # 최저점 대비 3% 이상 상승
            return True

    # 혹은 그다음 캔들에서 양봉 뜨면서 거래량 터졌을 수도 있음
    if min_idx + 1 in recent_df.index:
        next_candle = recent_df.loc[min_idx + 1]
        if next_candle['candle_acc_trade_volume'] > next_candle['vol_ma20'] * 3.0 and next_candle['trade_price'] > \
                next_candle['opening_price']:
            curr_price = df.iloc[-1]['trade_price']
            if curr_price > min_candle['low_price'] * 1.03:
                return True

    return False


# ---------------------------------------------------------
# 전체 스캐너 실행 함수
# ---------------------------------------------------------
def scan_combined():
    all_markets = get_krw_markets()
    print(f"전체 원화 마켓 개수: {len(all_markets)}")

    # 거래량 탑 15 종목 필터링 (사용자 요청 기준)
    top_n_count = 15
    markets = get_top_volume_markets(all_markets, top_n=top_n_count)
    print(f"\n[거래대금 TOP {top_n_count} 종목]")
    print(", ".join(markets))

    # 결과 저장 리스트
    res_bollinger_daily = []
    res_bollinger_4h = []
    res_idea1_trendline = []
    res_idea3_vshape = []

    print("\n조건 필터링 복합 스캔 시작... 잠시만 기다려주세요.\n")
    for market in markets:
        time.sleep(0.1)

        # 1. 일봉 데이터 (볼린저 밴드용)
        df_daily = get_candles(market, 'days', 100)

        # 2. 4시간봉 데이터 (다용도)
        time.sleep(0.1)
        df_4h = get_candles(market, 'minutes/240', 100)

        # 3. 1시간봉 데이터 (아이디어 스캔용)
        time.sleep(0.1)
        df_1h = get_candles(market, 'minutes/60', 100)

        # --- 조건 검사 ---
        # 1) 볼린저 밴드
        if not df_daily.empty and check_bollinger_breakout(df_daily):
            res_bollinger_daily.append(market)
        if not df_4h.empty and check_bollinger_breakout(df_4h):
            res_bollinger_4h.append(market)

        # 2) 하락 추세선 돌파
        if (not df_1h.empty and check_trendline_breakout(df_1h)) or (
                not df_4h.empty and check_trendline_breakout(df_4h)):
            res_idea1_trendline.append(market)

        # 3) 역대급 거래량 V자 반등
        if (not df_1h.empty and check_v_shape_rebound(df_1h)) or (not df_4h.empty and check_v_shape_rebound(df_4h)):
            res_idea3_vshape.append(market)

    # 최종 출력
    print("=" * 60)
    print(f"============== 스캔 완료 (TOP {top_n_count} 핉터링) ==============")
    print("=" * 60)

    print("\n1. [볼린저 밴드] 상단 돌파 (upbit_scanner 논리)")
    print(f"  - 일봉 기준: {', '.join(res_bollinger_daily) if res_bollinger_daily else '없음'}")
    print(f"  - 4시간봉 기준: {', '.join(res_bollinger_4h) if res_bollinger_4h else '없음'}")

    print("\n2. [유튜브 아이디어 1] 추세선 돌파 매매")
    print(f"  - 1시간/4시간봉 기준: {', '.join(res_idea1_trendline) if res_idea1_trendline else '없음'}")

    print("\n3. [유튜브 아이디어 3] 역대급 거래량 V자 반등")
    print(f"  - 1시간/4시간봉 기준: {', '.join(res_idea3_vshape) if res_idea3_vshape else '없음'}")

    print("\n* 유의: 위 결과는 보조 지표를 활용한 자동 필터링 결과이므로, 반드시 실 차트를 확인 후 매매를 결정하세요 *")


if __name__ == "__main__":
    scan_combined()
