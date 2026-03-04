#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
글로벌 주가지수 대시보드 (Python/Streamlit 버전) - v3.2
에러 처리 강화 버전
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

# 미국 섹터 ETF
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

# 미국 스타일 ETF
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

# 대체투자 ETF
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

# 채권 ETF
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


def safe_get_price(series, index):
    """안전하게 가격을 추출하는 함수"""
    try:
        val = series.iloc[index]
        if hasattr(val, 'item'):
            return val.item()
        return float(val)
    except:
        return None


def calculate_returns(ticker, name, base_date=None, debug=False):
    """주식/지수의 수익률을 계산하는 함수"""
    try:
        # 기준일자 설정
        if base_date is None:
            end_date = datetime.now()
        else:
            end_date = datetime.combine(base_date, datetime.max.time())

        start_date = end_date - timedelta(days=365 * 5)

        # yfinance 다운로드
        try:
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
        except Exception as e:
            if debug:
                st.warning(f"다운로드 실패 ({ticker}): {str(e)}")
            return None

        # 데이터 유효성 검사
        if data is None or len(data) == 0:
            if debug:
                st.warning(f"데이터 없음: {ticker}")
            return None

        # 종가 데이터 추출 (다양한 컬럼 구조 처리)
        try:
            if isinstance(data.columns, pd.MultiIndex):
                # MultiIndex인 경우 (yfinance 최신 버전)
                close_prices = data['Close'].iloc[:, 0].dropna()
            elif 'Close' in data.columns:
                close_prices = data['Close'].dropna()
            else:
                if debug:
                    st.warning(f"Close 컬럼 없음: {ticker}, 컬럼: {data.columns.tolist()}")
                return None
        except Exception as e:
            if debug:
                st.warning(f"종가 추출 실패 ({ticker}): {str(e)}")
            return None

        if len(close_prices) < 2:
            if debug:
                st.warning(f"데이터 부족: {ticker}")
            return None

        # 현재 가격/날짜
        current_date = close_prices.index[-1]
        current_price = safe_get_price(close_prices, -1)

        if current_price is None:
            return None

        # 벨류에이션 지표
        per_str, pbr_str, div_yield_str, market_cap_str = "N/A", "N/A", "N/A", "N/A"
        try:
            ticker_info = yf.Ticker(ticker)
            info = ticker_info.info or {}

            per = info.get('trailingPE')
            if per and not pd.isna(per):
                per_str = f"{per:.2f}"

            pbr = info.get('priceToBook')
            if pbr and not pd.isna(pbr):
                pbr_str = f"{pbr:.2f}"

            div_yield = info.get('dividendYield')
            if div_yield and not pd.isna(div_yield):
                div_yield_str = f"{div_yield * 100:.2f}%"

            market_cap = info.get('marketCap')
            if market_cap and not pd.isna(market_cap):
                market_cap_str = f"${market_cap / 1e9:.1f}B"
        except:
            pass

        if debug:
            st.write(f"=== {name} ({ticker}) ===")
            st.write(f"기준 날짜: {current_date}, 가격: {current_price}")

        # 수익률 계산 함수
        def safe_return(current, base):
            if base is None or pd.isna(base) or base == 0:
                return 0.0
            ret = ((current - base) / base) * 100
            if pd.isna(ret) or abs(ret) == float('inf'):
                return 0.0
            return float(ret)

        # 각 기간별 수익률 계산
        daily_return = 0.0
        if len(close_prices) >= 2:
            prev_price = safe_get_price(close_prices, -2)
            daily_return = safe_return(current_price, prev_price)

        monthly_return = 0.0
        if len(close_prices) >= 31:
            monthly_return = safe_return(current_price, safe_get_price(close_prices, -31))

        quarterly_return = 0.0
        if len(close_prices) >= 64:
            quarterly_return = safe_return(current_price, safe_get_price(close_prices, -64))

        yearly_return = 0.0
        if len(close_prices) >= 253:
            yearly_return = safe_return(current_price, safe_get_price(close_prices, -253))

        three_yearly_return = 0.0
        if len(close_prices) >= 757:
            three_yearly_return = safe_return(current_price, safe_get_price(close_prices, -757))

        # MTD 계산
        mtd_return = 0.0
        try:
            current_ym = current_date.strftime("%Y-%m")
            month_data = close_prices[close_prices.index.strftime("%Y-%m") == current_ym]
            if len(month_data) >= 2:
                mtd_return = safe_return(current_price, safe_get_price(month_data, 0))
        except:
            pass

        # YTD 계산
        ytd_return = 0.0
        try:
            current_year = str(current_date.year)
            year_data = close_prices[close_prices.index.strftime("%Y") == current_year]
            if len(year_data) >= 2:
                ytd_return = safe_return(current_price, safe_get_price(year_data, 0))
            elif len(close_prices) >= 253:
                ytd_return = safe_return(current_price, safe_get_price(close_prices, -253))
        except:
            pass

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
            st.error(f"오류 ({name}): {str(e)}")
        return None


def load_data(tickers_dict, base_date=None, debug=False):
    """여러 티커의 데이터를 로드"""
    data_list = []
    failed_list = []

    progress_bar = st.progress(0)
    status_text = st.empty()

    total = len(tickers_dict)
    for i, (name, ticker) in enumerate(tickers_dict.items()):
        status_text.text(f"로딩 중... {name}")
        progress_bar.progress((i + 1) / total)

        result = calculate_returns(ticker, name, base_date, debug)
        if result is not None:
            data_list.append(result)
        else:
            failed_list.append(name)

    progress_bar.empty()
    status_text.empty()

    if failed_list:
        st.warning(f"⚠️ 로딩 실패: {', '.join(failed_list)}")

    if len(data_list) > 0:
        return pd.DataFrame(data_list)
    return None


def create_bar_chart(df, column_name, num_column, title):
    """수평 막대 차트 생성"""
    if df is None or len(df) == 0:
        return None

    chart_data = df.sort_values(by=num_column, ascending=True)
    colors = ['green' if x >= 0 else 'red' for x in chart_data[num_column]]

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


def main():
    st.title("📊 글로벌 주가지수 대시보드 v3.2")
    st.caption("💹 에러 처리 강화 + 기준일자 선택")

    with st.sidebar:
        st.header("설정")

        st.subheader("📅 기준일자")
        date_option = st.radio("기준일자 선택", ["오늘", "직접 선택"], horizontal=True)

        if date_option == "오늘":
            base_date = None
            display_date = datetime.now().strftime('%Y-%m-%d')
        else:
            base_date = st.date_input(
                "날짜 선택",
                value=datetime.now().date(),
                max_value=datetime.now().date(),
                min_value=datetime.now().date() - timedelta(days=365 * 5)
            )
            display_date = base_date.strftime('%Y-%m-%d')

        st.info(f"📌 기준일: **{display_date}**")
        st.divider()

        tab_selection = st.radio(
            "카테고리 선택",
            ["글로벌 지수", "미국 섹터", "미국 스타일", "대체투자", "채권"]
        )

        st.divider()

        if st.button("🔄 새로고침", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        debug_mode = st.checkbox("디버그 모드")

    # 데이터 선택
    category_map = {
        "글로벌 지수": INDICES,
        "미국 섹터": US_SECTORS,
        "미국 스타일": US_STYLES,
        "대체투자": ALTERNATIVES,
        "채권": BONDS
    }
    tickers_dict = category_map[tab_selection]

    st.info(f"📅 기준일자: **{display_date}** | 업데이트: {datetime.now().strftime('%H:%M:%S')}")

    df = load_data(tickers_dict, base_date, debug_mode)

    if df is None or len(df) == 0:
        st.error("데이터를 불러올 수 없습니다. 잠시 후 다시 시도해주세요.")
        return

    # 요약 통계
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("상승", f"{(df['daily_num'] > 0).sum()}개", delta="↑")
    with col2:
        st.metric("하락", f"{(df['daily_num'] < 0).sum()}개", delta="↓")
    with col3:
        st.metric("평균 전일대비", f"{df['daily_num'].mean():+.2f}%")
    with col4:
        st.metric("평균 YTD", f"{df['ytd_num'].mean():+.2f}%")

    # 테이블
    st.subheader(f"📈 {tab_selection} 현황")
    display_columns = ['국가/지수', '현재지수', 'PER', 'PBR', '배당수익률', '시가총액',
                       '전일대비', '월간', 'MTD', '분기', 'YTD', '1년', '3년']
    st.dataframe(df[display_columns], use_container_width=True, hide_index=True)

    # 차트
    st.subheader("📊 수익률 비교 차트")
    tab1, tab2, tab3, tab4 = st.tabs(["전일대비", "YTD", "1년", "3년"])

    with tab1:
        fig = create_bar_chart(df, '전일대비', 'daily_num', '전일대비 수익률 (%)')
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    with tab2:
        fig = create_bar_chart(df, 'YTD', 'ytd_num', 'YTD 수익률 (%)')
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    with tab3:
        fig = create_bar_chart(df, '1년', 'yearly_num', '1년 수익률 (%)')
        if fig:
            st.plotly_chart(fig, use_container_width=True)
    with tab4:
        fig = create_bar_chart(df, '3년', 'three_yearly_num', '3년 수익률 (%)')
        if fig:
            st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()