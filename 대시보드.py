#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
글로벌 주가지수 대시보드 (Python/Streamlit 버전) - v3.0
벨류에이션 지표 추가 (PER, PBR, 배당수익률, 시가총액)
"""

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta
import time

# 페이지 설정
st.set_page_config(
    page_title="📊 글로벌 주가지수 대시보드",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# 주요 국가 주가지수
# ============================================================
INDICES = {
    "🇰🇷 한국 (KOSPI)": "^KS11",
    "🇺🇸 미국 (S&P 500)": "^GSPC",
    "🇺🇸 미국 (다우존스)": "^DJI",
    "🇺🇸 미국 (나스닥)": "^IXIC",
    "🇯🇵 일본 (닛케이)": "^N225",
    "🇨🇳 중국 (상하이)": "000001.SS",
    "🇭🇰 홍콩 (항셍)": "^HSI",
    "🇬🇧 영국 (FTSE 100)": "^FTSE",
    "🇩🇪 독일 (DAX)": "^GDAXI",
    "🇫🇷 프랑스 (CAC 40)": "^FCHI"
}

# ============================================================
# 미국 섹터 ETF
# ============================================================
US_SECTORS = {
    "🏭 기술 (Technology)": "XLK",
    "🏥 헬스케어 (Healthcare)": "XLV",
    "💰 금융 (Financials)": "XLF",
    "🏪 임의소비재 (Consumer Discretionary)": "XLY",
    "🛒 필수소비재 (Consumer Staples)": "XLP",
    "⚡ 에너지 (Energy)": "XLE",
    "🏗️ 산업재 (Industrials)": "XLI",
    "📡 통신서비스 (Communication)": "XLC",
    "🏘️ 부동산 (Real Estate)": "XLRE",
    "🔧 원자재 (Materials)": "XLB",
    "⚙️ 유틸리티 (Utilities)": "XLU"
}

# ============================================================
# 미국 스타일 ETF
# ============================================================
US_STYLES = {
    "📈 대형주 성장 (Large Growth)": "IVW",
    "💎 대형주 가치 (Large Value)": "IVE",
    "📊 중형주 성장 (Mid Growth)": "IWP",
    "💼 중형주 가치 (Mid Value)": "IWS",
    "🚀 소형주 성장 (Small Growth)": "IWO",
    "💵 소형주 가치 (Small Value)": "IWN",
    "🌟 성장주 (Growth)": "VUG",
    "💰 가치주 (Value)": "VTV",
    "📉 고배당 (High Dividend)": "VYM",
    "⚡ 모멘텀 (Momentum)": "MTUM"
}

# ============================================================
# 대체투자 ETF
# ============================================================
ALTERNATIVES = {
    "🥇 금 (Gold)": "GLD",
    "🥈 은 (Silver)": "SLV",
    "💎 원자재 종합 (Commodities)": "DBC",
    "🛢️ 원유 (Oil)": "USO",
    "⛽ 천연가스 (Natural Gas)": "UNG",
    "🌾 농산물 (Agriculture)": "DBA",
    "🏘️ 리츠 (REIT)": "VNQ",
    "🏢 부동산 (Real Estate)": "IYR",
    "🏗️ 인프라 (Infrastructure)": "IGF",
    "🚧 건설/인프라 (Construction)": "PAVE",
    "🌲 목재 (Timber)": "WOOD",
    "💧 수자원 (Water)": "PHO"
}

# ============================================================
# 채권 ETF
# ============================================================
BONDS = {
    "🏦 미국 국채 20년+ (Long-Term)": "TLT",
    "📊 미국 국채 7-10년 (Mid-Term)": "IEF",
    "📈 미국 국채 1-3년 (Short-Term)": "SHY",
    "💼 종합 채권 (Aggregate)": "AGG",
    "🏢 투자등급 회사채 (Investment Grade)": "LQD",
    "⚡ 하이일드 채권 (High Yield)": "HYG",
    "💰 정크본드 (Junk Bond)": "JNK",
    "📉 물가연동채 (TIPS)": "TIP",
    "🌍 신흥국 채권 (Emerging Market)": "EMB",
    "💵 단기 국채 (T-Bills)": "BIL",
    "🏛️ 지방채 (Municipal)": "MUB",
    "🌐 글로벌 채권 (Global)": "BNDX"
}


# ============================================================
# 수익률 계산 함수
# ============================================================
def calculate_returns(ticker, name, debug=False):
    """주식/지수의 수익률을 계산하는 함수"""
    try:
        # 데이터 가져오기 (5년치)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365 * 5)

        data = yf.download(ticker, start=start_date, end=end_date, progress=False)

        if data is None or len(data) == 0:
            return None

        # 종가 데이터 추출
        close_prices = data['Close'].dropna()

        if len(close_prices) < 2:
            return None

        # 현재 가격/날짜
        current_date = close_prices.index[-1]
        current_price = close_prices.iloc[-1].item()

        # ============================================================
        # 벨류에이션 지표 가져오기
        # ============================================================
        try:
            ticker_info = yf.Ticker(ticker)
            info = ticker_info.info

            # PER (Trailing P/E)
            per = info.get('trailingPE', None)
            if per is not None and not pd.isna(per):
                per_str = f"{per:.2f}"
            else:
                per_str = "N/A"

            # PBR (Price to Book)
            pbr = info.get('priceToBook', None)
            if pbr is not None and not pd.isna(pbr):
                pbr_str = f"{pbr:.2f}"
            else:
                pbr_str = "N/A"

            # 배당수익률
            div_yield = info.get('dividendYield', None)
            if div_yield is not None and not pd.isna(div_yield):
                div_yield_str = f"{div_yield * 100:.2f}%"
            else:
                div_yield_str = "N/A"

            # 시가총액 (억 달러)
            market_cap = info.get('marketCap', None)
            if market_cap is not None and not pd.isna(market_cap):
                market_cap_str = f"${market_cap / 1e9:.1f}B"
            else:
                market_cap_str = "N/A"

        except Exception as e:
            if debug:
                st.write(f"벨류에이션 지표 로딩 실패: {str(e)}")
            per_str = "N/A"
            pbr_str = "N/A"
            div_yield_str = "N/A"
            market_cap_str = "N/A"

        if debug:
            st.write(f"\n=== {name} ({ticker}) ===")
            st.write(f"현재 날짜: {current_date}")
            st.write(f"현재 가격: {current_price}")
            st.write(f"PER: {per_str}, PBR: {pbr_str}, 배당: {div_yield_str}")
            st.write(f"전체 데이터 개수: {len(close_prices)}")

        # 안전한 수익률 계산 함수
        def safe_return(current, base):
            if base is None or pd.isna(base) or base == 0:
                return 0.0
            ret = ((current - base) / base) * 100
            if pd.isna(ret) or ret == float('inf') or ret == float('-inf'):
                return 0.0
            return float(ret)

        # 전일대비 (1거래일 전)
        if len(close_prices) >= 2:
            prev_price = close_prices.iloc[-2].item()
            daily_return = safe_return(current_price, prev_price)
        else:
            daily_return = 0.0

        # 월간 (30거래일 전)
        if len(close_prices) >= 31:
            month_ago_price = close_prices.iloc[-31].item()
            monthly_return = safe_return(current_price, month_ago_price)
        else:
            monthly_return = 0.0

        # 분기 (63거래일 전)
        if len(close_prices) >= 64:
            quarter_ago_price = close_prices.iloc[-64].item()
            quarterly_return = safe_return(current_price, quarter_ago_price)
        else:
            quarterly_return = 0.0

        # 1년 (252거래일 전)
        if len(close_prices) >= 253:
            year_ago_price = close_prices.iloc[-253].item()
            yearly_return = safe_return(current_price, year_ago_price)
        else:
            yearly_return = 0.0

        # 3년 (756거래일 전)
        if len(close_prices) >= 757:
            three_year_ago_price = close_prices.iloc[-757].item()
            three_yearly_return = safe_return(current_price, three_year_ago_price)
        else:
            three_yearly_return = 0.0

        # MTD: 이번 달 첫 거래일
        current_ym = current_date.strftime("%Y-%m")
        month_data = close_prices[close_prices.index.strftime("%Y-%m") == current_ym]

        if len(month_data) >= 2:
            mtd_price = month_data.iloc[0].item()
            mtd_return = safe_return(current_price, mtd_price)
        elif len(month_data) == 1:
            # 이번 달 데이터가 1개면 전월 마지막
            prev_month = (current_date.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            prev_month_data = close_prices[close_prices.index.strftime("%Y-%m") == prev_month]
            if len(prev_month_data) > 0:
                mtd_price = prev_month_data.iloc[-1].item()
                mtd_return = safe_return(current_price, mtd_price)
            else:
                mtd_return = 0.0
        else:
            mtd_return = 0.0

        # YTD: 올해 첫 거래일
        current_year = str(current_date.year)
        year_data = close_prices[close_prices.index.strftime("%Y") == current_year]

        if len(year_data) >= 2:
            # 올해 첫 거래일 가격
            ytd_price = year_data.iloc[0].item()
            ytd_return = safe_return(current_price, ytd_price)

            if debug:
                st.write("YTD 방법 1 사용 (올해 첫 거래일)")
                st.write(f"올해 데이터 개수: {len(year_data)}")
                st.write(f"YTD 기준가: {ytd_price}")
                st.write(f"YTD 수익률: {ytd_return}%")
        else:
            # 방법 2: 작년 마지막 거래일 사용
            last_year = str(int(current_year) - 1)
            last_year_data = close_prices[close_prices.index.strftime("%Y") == last_year]

            if len(last_year_data) > 0:
                ytd_price = last_year_data.iloc[-1].item()
                ytd_return = safe_return(current_price, ytd_price)

                if debug:
                    st.write("YTD 방법 2 사용 (작년 마지막 거래일)")
                    st.write(f"YTD 기준가: {ytd_price}")
                    st.write(f"YTD 수익률: {ytd_return}%")
            else:
                # 방법 3: 252거래일 전 가격 사용
                if len(close_prices) >= 253:
                    ytd_price = close_prices.iloc[-253].item()
                    ytd_return = safe_return(current_price, ytd_price)
                else:
                    ytd_return = 0.0

        # 결과 반환
        return {
            "국가/지수": name,
            "현재지수": f"{current_price:.2f}",
            "PER": per_str,
            "PBR": pbr_str,
            "배당수익률": div_yield_str,
            "시가총액": market_cap_str,
            "전일대비": f"{daily_return:+.2f}%",
            "월간": f"{monthly_return:+.2f}%",
            "MTD": f"{mtd_return:+.2f}%",
            "분기": f"{quarterly_return:+.2f}%",
            "YTD": f"{ytd_return:+.2f}%",
            "1년": f"{yearly_return:+.2f}%",
            "3년": f"{three_yearly_return:+.2f}%",
            "daily_num": daily_return,
            "monthly_num": monthly_return,
            "mtd_num": mtd_return,
            "quarterly_num": quarterly_return,
            "ytd_num": ytd_return,
            "yearly_num": yearly_return,
            "three_yearly_num": three_yearly_return
        }

    except Exception as e:
        if debug:
            st.error(f"Error loading {name}: {str(e)}")
        return None


# ============================================================
# 데이터 로드 함수
# ============================================================
@st.cache_data(ttl=1800)  # 30분 캐시
def load_data(tickers_dict, debug=False):
    """여러 티커의 데이터를 로드하는 함수"""
    data_list = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    total = len(tickers_dict)
    for i, (name, ticker) in enumerate(tickers_dict.items()):
        status_text.text(f"로딩 중... {name}")
        progress_bar.progress((i + 1) / total)

        result = calculate_returns(ticker, name, debug)
        if result is not None:
            data_list.append(result)

    progress_bar.empty()
    status_text.empty()

    if len(data_list) > 0:
        return pd.DataFrame(data_list)
    return None


# ============================================================
# 차트 생성 함수
# ============================================================
def create_bar_chart(df, column_name, num_column, title):
    """수평 막대 차트를 생성하는 함수"""
    if df is None or len(df) == 0:
        return None

    # 데이터 정렬
    chart_data = df.sort_values(by=num_column, ascending=True)

    # 색상 설정
    colors = ['green' if x >= 0 else 'red' for x in chart_data[num_column]]

    # 차트 생성
    fig = go.Figure(data=[
        go.Bar(
            y=chart_data['국가/지수'],
            x=chart_data[num_column],
            orientation='h',
            marker=dict(color=colors),
            text=[f"{x:+.2f}%" for x in chart_data[num_column]],
            textposition='outside'
        )
    ])

    fig.update_layout(
        title=title,
        xaxis_title="수익률 (%)",
        yaxis_title="",
        height=max(400, len(chart_data) * 30),
        showlegend=False
    )

    return fig


# ============================================================
# 메인 앱
# ============================================================
def main():
    st.title("📊 글로벌 주가지수 대시보드 v3.0")
    st.caption("💹 벨류에이션 지표 추가: PER, PBR, 배당수익률, 시가총액")

    # 사이드바
    with st.sidebar:
        st.header("설정")

        tab_selection = st.radio(
            "카테고리 선택",
            ["글로벌 지수", "미국 섹터", "미국 스타일", "대체투자", "채권"]
        )

        st.divider()

        if st.button("🔄 새로고침", width='stretch'):
            st.cache_data.clear()
            st.rerun()

        auto_refresh = st.checkbox("자동 새로고침 (30초)")
        debug_mode = st.checkbox("디버그 모드")

        if auto_refresh:
            time.sleep(30)
            st.rerun()

    # 데이터 선택
    if tab_selection == "글로벌 지수":
        tickers_dict = INDICES
        category_name = "글로벌 지수"
    elif tab_selection == "미국 섹터":
        tickers_dict = US_SECTORS
        category_name = "미국 섹터"
    elif tab_selection == "미국 스타일":
        tickers_dict = US_STYLES
        category_name = "미국 스타일"
    elif tab_selection == "대체투자":
        tickers_dict = ALTERNATIVES
        category_name = "대체투자"
    else:  # 채권
        tickers_dict = BONDS
        category_name = "채권"

    # 데이터 로드
    st.info(f"업데이트 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    df = load_data(tickers_dict, debug_mode)

    if df is None or len(df) == 0:
        st.error("데이터를 불러올 수 없습니다.")
        return

    # 요약 통계
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        up_count = (df['daily_num'] > 0).sum()
        st.metric("상승 개수", f"{up_count}개", delta="↑")

    with col2:
        down_count = (df['daily_num'] < 0).sum()
        st.metric("하락 개수", f"{down_count}개", delta="↓")

    with col3:
        avg_daily = df['daily_num'].mean()
        st.metric("평균 전일대비", f"{avg_daily:+.2f}%")

    with col4:
        avg_ytd = df['ytd_num'].mean()
        st.metric("평균 YTD", f"{avg_ytd:+.2f}%")

    # 테이블 표시
    st.subheader(f"📈 {category_name} 현황")

    # 벨류에이션 지표 포함한 컬럼 표시
    display_columns = ['국가/지수', '현재지수', 'PER', 'PBR', '배당수익률', '시가총액',
                       '전일대비', '월간', 'MTD', '분기', 'YTD', '1년', '3년']
    st.dataframe(df[display_columns], width='stretch', hide_index=True)

    # 차트 탭
    st.subheader("📊 수익률 비교 차트")

    tab1, tab2, tab3, tab4 = st.tabs(["전일대비", "YTD", "1년 수익률", "3년 수익률"])

    with tab1:
        fig = create_bar_chart(df, '전일대비', 'daily_num', '전일대비 수익률 (%)')
        if fig:
            st.plotly_chart(fig, width='stretch')

    with tab2:
        fig = create_bar_chart(df, 'YTD', 'ytd_num', 'YTD 수익률 (%)')
        if fig:
            st.plotly_chart(fig, width='stretch')

    with tab3:
        fig = create_bar_chart(df, '1년', 'yearly_num', '1년 수익률 (%)')
        if fig:
            st.plotly_chart(fig, width='stretch')

    with tab4:
        fig = create_bar_chart(df, '3년', 'three_yearly_num', '3년 수익률 (%)')
        if fig:
            st.plotly_chart(fig, width='stretch')


if __name__ == "__main__":
    main()