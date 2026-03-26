import streamlit as st
import pandas as pd
import sqlite3
import json
import os
from datetime import datetime
import time

# Page config
st.set_page_config(page_title="Multi-Grid Trading Bot V8.2", layout="wide", page_icon="📈")
st.title("📈 Multi-Coin Grid Trading Bot Dashboard (V8.2)")

DB_PATH = os.path.join(os.path.dirname(__file__), 'bot_data.db')

def get_connection():
    return sqlite3.connect(DB_PATH)

def fetch_all(query):
    conn = get_connection()
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(query)
    rows = c.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def execute_query(query, params=()):
    conn = get_connection()
    c = conn.cursor()
    c.execute(query, params)
    conn.commit()
    conn.close()

# ── Sidebar: Control Panel ──
st.sidebar.header("🛠️ 새 봇 추가 (New Bot)")

with st.sidebar.form("new_bot_form"):
    st.markdown("### 🛠️ 새 봇 추가 (New Bot)")
    strategy_type = st.radio("전략 선택 (Strategy)", ["GRID (그리드)", "BREAKOUT (볼린저 돌파)"])

    market = st.text_input("마켓 심볼 (예: KRW-XRP)", value="KRW-XRP")

    if strategy_type.startswith("GRID"):
        col1, col2 = st.columns(2)
        grid_amount = col1.number_input("그리드당 금액 (원)", value=10000, step=1000)
        grid_count = col2.number_input("그리드 개수", value=20, step=5)

        mode_btn = st.selectbox("수익금 처리", ["원금만 회수 (수익은 코인으로 보유)", "전량 매도 (복리 X, 풀현금화)"])
        keep_profit = True if "코인으로" in mode_btn else False

        sell_mode_str = st.selectbox("매도 전략", ["GRID (기본 다음칸 매도)", "TARGET (목표가 도달 시 전량 청산)", "AVG_PLUS_ONE (평단가+1칸)", "TOP_FIXED (최상단 고정)"])
        sell_mode = sell_mode_str.split()[0]

        target_price = 0.0
        if sell_mode == "TARGET":
            target_price = st.number_input("목표가 (원)", min_value=0.0, step=1.0)

        st.markdown("---")
        sl = st.number_input("손절가 (0=미사용)", min_value=0.0, step=1.0)
        htp = st.number_input("강제 익절가 (0=미사용)", min_value=0.0, step=1.0)

        st.markdown("---")
        range_type = st.radio("그리드 범위/간격 설정", ["간격 설정 (예: 1%)", "AUTO (5분봉 ATR)", "대칭 범위 (예: ±5%)", "비대칭 범위"])

        # ... (생량된 기존 그리드 설정 로직)
        range_pct, down_pct, up_pct, grid_spacing_pct = 0.05, 0.10, 0.075, 0.01
        is_asym, is_manual, is_spacing = False, False, False
        if "대칭" in range_type: is_manual, range_pct = True, st.number_input("상하단 범위 (%)", value=5.0)/100
        elif "비대칭" in range_type: is_manual, is_asym = True, True; down_pct, up_pct = st.number_input("하단(%)", 10.0)/100, st.number_input("상단(%)", 7.5)/100
        elif "간격" in range_type: is_spacing, grid_spacing_pct = True, st.number_input("그리드 간격 (%)", 1.0)/100
    else:
        # BREAKOUT 전략 설정
        st.markdown("---")
        st.info("볼린저 밴드 돌파 + MA120 필터 전략 (1:3 손익비)")
        grid_amount = st.number_input("총 투자 금액 (원)", value=100000, step=10000)
        col_br1, col_br2 = st.columns(2)
        sl = col_br1.number_input("손절가 (Stop Loss)", value=0.0, help="진입 직전 저가를 입력하세요.")
        htp = col_br2.number_input("익절가 (Take Profit)", value=0.0, help="손익비 3R 목표가를 입력하세요.")
        # 더미 데이터 (그리드 설정과 구조 유지용)
        grid_count, keep_profit, sell_mode, target_price = 1, True, "TARGET", 0.0
        is_asym, down_pct, up_pct, grid_spacing_pct, is_spacing, is_manual = False, 0, 0, 0, False, False

    submit_btn = st.form_submit_button("봇 가동 시작 🚀")

    if submit_btn:
        config_data = {
            'STRATEGY_TYPE': 'BREAKOUT' if strategy_type.startswith("BREAKOUT") else 'GRID',
            'GRID_AMOUNT': grid_amount,
            'GRID_COUNT': grid_count,
            'KEEP_PROFIT_COINS': keep_profit,
            'SELL_MODE': sell_mode,
            'SELL_TARGET_PRICE': target_price,
            'STOP_LOSS_PRICE': sl,
            'HARD_TAKE_PROFIT_PRICE': htp,
            'ASYMMETRIC_GRID': is_asym,
            'GRID_RANGE_DOWN': down_pct,
            'GRID_RANGE_UP': up_pct,
            'GRID_SPACING_PCT': grid_spacing_pct,
            'RANGE_PCT_MIN': 0.03, 'RANGE_PCT_MAX': 0.1,
        }
        if config_data['STRATEGY_TYPE'] == 'GRID':
            config_data['INITIAL_BUY_GRIDS'] = initial_buy_grids
            if is_spacing: config_data['mode'] = 'SPACING'
            elif is_manual and not is_asym:
                config_data['mode'] = 'MANUAL'
                config_data['range_pct'] = range_pct
            elif is_manual and is_asym: config_data['mode'] = 'MANUAL'
            else: config_data['mode'] = 'AUTO'
        else:
            config_data['mode'] = 'BREAKOUT'

        json_str = json.dumps(config_data)
        execute_query("INSERT INTO commands (action, market, params) VALUES ('START', ?, ?)", (market.upper(), json_str))
        st.sidebar.success(f"{market} 봇 추가 명령을 엔진에 전송했습니다.")

# ── Main Dashboard ──
tab1, tab2 = st.tabs(["📊 대시보드 (Dashboard)", "🔍 실시간 전략 스캔 (Live Scan)"])

with tab1:
    if st.button("🔄 새로고침"):
        st.rerun()

# 1. Active Bots View
bots = fetch_all("SELECT * FROM active_bots ORDER BY updated_at DESC")

if not bots:
    st.info("현재 가동 중인 봇이 없습니다. 왼쪽 사이드바에서 새 종목을 추가해보세요.")
else:
    st.subheader("💡 가동 중인 봇 현황")

    bot_list = []
    for b in bots:
        try:
            cfg = json.loads(b['config']) if b['config'] else {}
            stt = json.loads(b['state']) if b['state'] else {}

            # 전략별 포지션 요약 방식 변경
            strategy = cfg.get('STRATEGY_TYPE', 'GRID')
            if strategy == 'GRID':
                filled = sum(1 for v in stt.values() if isinstance(v, str) and v == 'FILLED')
                pending = sum(1 for v in stt.values() if isinstance(v, str) and v == 'BUY_PENDING')
                empty = sum(1 for v in stt.values() if isinstance(v, str) and v == 'EMPTY')
                position_summary = f"주문 {pending} / 체결 {filled} / 빈칸 {empty}"
            else:
                position_summary = f"실전전략 ({stt.get('state', 'UNKNOWN')}) - 수량: {stt.get('qty', 0):.4f}"

            target_p = cfg.get('HARD_TAKE_PROFIT_PRICE', 0)
            if target_p == 0: target_p = cfg.get('SELL_TARGET_PRICE', 0)
            sl_val = cfg.get('STOP_LOSS_PRICE', 0)

            bot_list.append({
                '전략': strategy,
                '마켓': b['market'],
                '상태': b['status'],
                '현재가': f"{b['current_price']:,.2f}" if b['current_price'] else "-",
                '진입가': f"{b['entry_price']:,.2f}" if b['entry_price'] else "-",
                '목표/익절가': f"{target_p:,.2f}" if target_p > 0 else "-",
                '손절가': f"{sl_val:,.2f}" if sl_val > 0 else "-",
                '총 수익': f"{int(b['total_profit'] or 0):,}원",
                '포지션': position_summary
            })
        except:
            pass

    if bot_list:
        df = pd.DataFrame(bot_list)
        # 🟢 '상태' 열에서 RUNNING이나 STARTING인 봇들만 필터링하여 상단 테이블에 표시
        active_df = df[df['상태'].isin(['RUNNING', 'STARTING'])]
        if not active_df.empty:
            st.dataframe(active_df, use_container_width=True)
        else:
            st.info("현재 요약할 활성 봇이 없습니다.")

    st.markdown("---")
    st.subheader("⚙️ 봇 개별 제어 및 설정 확인")

    # 활성 봇들만 필터링하여 제어 패널에 표시
    active_bots = [b for b in bots if b['status'] in ('RUNNING', 'STARTING')]

    if active_bots:
        cols = st.columns(len(active_bots))
        for i, b in enumerate(active_bots):
            with cols[i]:
                st.markdown(f"### {b['market']}")
                pnl = int(b['total_profit'] or 0)
                st.metric(label="총 실현수익", value=f"{pnl:,}원")

                with st.expander("🔍 봇 세팅 조건 보기"):
                    try:
                        cfg = json.loads(b['config'])
                        st.json(cfg)
                    except:
                        st.write("설정 정보를 불러올 수 없습니다.")

                col_a, col_b = st.columns(2)
                if col_a.button("⏹️ 소프트 종료", key=f"stop_{b['market']}"):
                    execute_query("INSERT INTO commands (action, market) VALUES ('STOP', ?)", (b['market'],))
                    execute_query("UPDATE active_bots SET status = 'STOPPING' WHERE market = ?", (b['market'],))
                    st.success("소프트 종료 명령 전송!")
                    time.sleep(1)
                    st.rerun()

                if col_b.button("🚨 전량 강제청산", type="primary", key=f"liq_{b['market']}"):
                    execute_query("INSERT INTO commands (action, market) VALUES ('LIQUIDATE', ?)", (b['market'],))
                    execute_query("UPDATE active_bots SET status = 'STOPPING' WHERE market = ?", (b['market'],))
                    st.success("청산 명령 전송!")
                    time.sleep(1)
                    st.rerun()
    else:
        st.info("현재 제어 가능한 활성(RUNNING) 상태의 봇이 없습니다. 정지/청산된 봇의 성과는 위 요약표에서 확인 가능합니다.")

    # 과거 내역 보기 (정지/청산/에러난 봇들)
    stopped_bots = [b for b in bots if b['status'] not in ('RUNNING', 'STARTING')]
    if stopped_bots:
        with st.expander("📁 종료 / 청산된 봇 과거 기록 보기"):
            for b in stopped_bots:
                st.markdown(f"**{b['market']} ({b['status']})** - 최종 수익: {int(b['total_profit'] or 0):,}원")
                try:
                    cfg = json.loads(b['config'])
                    st.json(cfg)
                except:
                    pass
                st.markdown("---")

# 2. Command Log View
st.markdown("---")
st.subheader("📋 전체 명령 로그")

col_log_1, col_log_2 = st.columns([8, 2])
with col_log_2:
    if st.button("🗑️ 모든 로그 지우기"):
        execute_query("DELETE FROM commands")
        st.success("명령 로그가 모두 초기화되었습니다.")
        time.sleep(1)
        st.rerun()

cmds = fetch_all("SELECT id, action, market, status, message, created_at FROM commands ORDER BY id DESC LIMIT 10")
if cmds:
    st.dataframe(pd.DataFrame(cmds), use_container_width=True)
else:
    st.info("명령 로그가 비어있습니다.")

with tab2:
    st.subheader("🔍 볼린저 밴드 + MA120 전략 실시간 스캔")
    st.info("비트코인 시황과 주도주를 분석하여 최적의 진입/손절/익절가를 제안합니다.")

    if st.button("🚀 지금 스캔 시작"):
        with st.spinner("시장 데이터를 분석 중입니다..."):
            # full_strategy_scanner.py의 로직을 여기에 통합하거나 시스템 명령으로 실행
            import sys
            sys.path.append(os.path.join(os.path.dirname(__file__), '../../research'))
            try:
                # 간단한 연동을 위해 subprocess 사용하거나 직접 임포트
                import subprocess
                cmd_path = os.path.join(os.path.dirname(__file__), '../../research/full_strategy_scanner.py')
                result = subprocess.run([sys.executable, cmd_path], capture_with_output=True, text=True, encoding='utf-8')
                st.text_area("스캔 리포트", value=result.stdout, height=400)

                if "🎯 종목:" in result.stdout:
                    st.success("진입 가능한 종목이 발견되었습니다! 왼쪽 사이드바에서 [볼린저 돌파] 전략을 선택하고 위 가이드대로봇을 가동하세요.")
            except Exception as e:
                st.error(f"스캔 중 오류 발생: {e}")

# (파일 끝까지 유지...)
