#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit Smart Grid Trading Bot V8.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[핵심 로직]
1. SmartPicker V3 — 시장 적응형 종목 선정 (AUTO 모드)
2. 수동 선택 모드 (MANUAL 모드)
3. 비대칭 그리드 (ASYMMETRIC_GRID)
4. 상승 라인 (TAKE_PROFIT_REDUCE_ENABLED)
5. 그리드당 금액 설정 방식
6. 지정가 1칸분 매수 → 체결가 기준 그리드 고정 생성
7. 계단식 매수 블럭 채우기
8. 매도 방식 선택 (KEEP_PROFIT_COINS 설정)
9. 트레일링 스탑 (TRAILING_STOP_ENABLED)
10. 그리드 상단 돌파 시 익절
11. 청산 후 처리
12. 30분마다 텔레그램 성과 보고서
13. 프로그램 종료 시 모든 주문 유지

[V8.1 추가]
14. 손절가 (STOP_LOSS_PRICE) — 설정 가격 도달 시 전량 청산 후 종료
15. 강제 익절가 (HARD_TAKE_PROFIT_PRICE) — 설정 가격 도달 시 전량 청산 후 재진입
"""

import time
import requests
import jwt
import uuid
import hashlib
import pandas as pd
import numpy as np
import json
import traceback
from urllib.parse import urlencode
from datetime import datetime, timedelta

# ============================================================================
# 🔐 설정
# ============================================================================
API_CONFIG = {
    'ACCESS_KEY': 'HVPCb3dfFrjajY4qeKMQstAF6ItBrWj5K07x3k5u',
    'SECRET_KEY': '3bxnJm4k3OCgAcD9IurTuZ1LaP85lAe5b0fpD7hB',
}
    x
TELEGRAM_CONFIG = {
    'ENABLED': True,
    'BOT_TOKEN': '8521289560:AAEZA0Y8kW4JmCALP8VquSFjqGP4VwrPAUc',
    'CHAT_ID': '2017077172',
}

CONFIG = {
    'ENABLE_REAL_TRADING': True,
    'SELECTION_MODE': 'AUTO',  # 'AUTO' 또는 'MANUAL'

    'GRID_AMOUNT': 10000.0,  # 그리드 1칸당 투자 금액 (원)
    'GRID_COUNT': 30,        # 그리드 칸수 (총 투자금 = GRID_AMOUNT × GRID_COUNT)
    'MAX_BUY_ORDERS': 3,     # 현재가 아래 최대 매수 주문 개수 (계단식 매수)
    'KEEP_PROFIT_COINS': True,

    # ── 손절/익절 설정 (V8.1 신규) ──────────────────────────────────
    # 두 가격 모두 0이면 기능 비활성화
    'STOP_LOSS_PRICE': 0,           # 손절가 (0 = 미설정): 도달 시 전량 청산 후 봇 완전 종료
    'HARD_TAKE_PROFIT_PRICE': 0,    # 강제 익절가 (0 = 미설정): 도달 시 전량 청산 후 재진입

    # ── 상승 라인 설정 (익절 준비) ──
    'TAKE_PROFIT_REDUCE_ENABLED': False,
    'TAKE_PROFIT_REDUCE_PRICE': 0,

    # ── 비대칭 그리드 설정 ──
    'ASYMMETRIC_GRID': False,
    'GRID_RANGE_DOWN': 0.10,
    'GRID_RANGE_UP': 0.075,

    # ── 트레일링 스탑 설정 ──
    'TRAILING_STOP_ENABLED': True,
    'TRAILING_STOP_PCT': 0.05,
    'TRAILING_ACTIVATION': 'UPPER_BREAK',

    # ── 그리드 범위 설정 ──
    'RANGE_PCT_MIN': 0.03,
    'RANGE_PCT_MAX': 0.1,
    'ATR_MULTIPLIER': 3.0,
    'INITIAL_BUY_GRIDS': 1,

    'EXCLUDE_COINS': ['BTC', 'USDT', 'USDC', 'STG', 'BUSD', 'DAI'],
    'MAX_PUMP_PCT': 0.30,

    'MIN_ORDER_AMOUNT': 5000,
    'MAX_ORDER_AMOUNT': 100000,
    'FEE_PCT': 0.0005,
    'API_TIMEOUT': 10,
    'POLL_INTERVAL': 5,
    'STATUS_INTERVAL': 60,
    'REPORT_INTERVAL': 1800,
    'COOLDOWN_AFTER_EXIT': 10,
    'ROTATION_SCAN_INTERVAL': 3600,
}


# ============================================================================
# 🎯 가격 유틸리티
# ============================================================================
def get_tick_size(price):
    if price >= 2000000:
        return 1000
    elif price >= 1000000:
        return 500
    elif price >= 500000:
        return 100
    elif price >= 100000:
        return 50
    elif price >= 10000:
        return 10
    elif price >= 1000:
        return 5
    elif price >= 100:
        return 1
    elif price >= 10:
        return 0.1
    elif price >= 1:
        return 0.01
    else:
        return 0.001


def round_to_tick(price, direction='nearest'):
    tick = get_tick_size(price)
    if direction == 'down':
        val = int(price / tick) * tick
    elif direction == 'up':
        val = int(price / tick) * tick
        if val < price:
            val += tick
    else:
        val = round(price / tick) * tick

    if 100 <= price < 1000:
        return int(round(val))
    elif tick >= 1:
        return int(val)
    else:
        dp = max(0, -int(np.floor(np.log10(tick))))
        return round(val, dp)


def format_price(p):
    if p >= 100:
        return f"{p:,.0f}"
    elif p >= 10:
        return f"{p:,.1f}"
    elif p >= 1:
        return f"{p:,.2f}"
    else:
        return f"{p:,.4f}"


def log(msg, level='INFO'):
    ts = datetime.now().strftime('%H:%M:%S')
    print(f"[{ts}] [{level}] {msg}")


# ============================================================================
# 🌐 Upbit API
# ============================================================================
class UpbitAPI:
    BASE_URL = "https://api.upbit.com/v1"

    @classmethod
    def _get_headers(cls, query=None):
        payload = {
            'access_key': API_CONFIG['ACCESS_KEY'],
            'nonce': str(uuid.uuid4()),
        }
        if query:
            query_string = urlencode(query).encode()
            m = hashlib.sha512()
            m.update(query_string)
            payload['query_hash'] = m.hexdigest()
            payload['query_hash_alg'] = 'SHA512'
        jwt_token = jwt.encode(payload, API_CONFIG['SECRET_KEY'], algorithm='HS256')
        if isinstance(jwt_token, bytes):
            jwt_token = jwt_token.decode('utf-8')
        return {'Authorization': f'Bearer {jwt_token}'}

    @classmethod
    def get_accounts(cls):
        try:
            res = requests.get(f"{cls.BASE_URL}/accounts", headers=cls._get_headers(), timeout=CONFIG['API_TIMEOUT'])
            data = res.json()
            if isinstance(data, dict) and 'error' in data:
                return None
            return data
        except:
            return None

    @classmethod
    def get_ticker(cls, market):
        try:
            res = requests.get(f"{cls.BASE_URL}/ticker", params={'markets': market}, timeout=CONFIG['API_TIMEOUT'])
            data = res.json()
            if isinstance(data, dict) and 'error' in data:
                return None
            return data
        except:
            return None

    @classmethod
    def get_candles(cls, market, count=100, interval=60):
        try:
            res = requests.get(f"{cls.BASE_URL}/candles/minutes/{interval}", params={'market': market, 'count': count},
                               timeout=CONFIG['API_TIMEOUT'])
            data = res.json()
            if isinstance(data, dict) and 'error' in data:
                return None
            return data
        except:
            return None

    @classmethod
    def place_order(cls, market, side, price, volume, ord_type='limit'):
        if not CONFIG['ENABLE_REAL_TRADING']:
            return {
                'uuid': f'sim-{uuid.uuid4().hex[:8]}',
                'state': 'wait',
                'side': side,
                'ord_type': ord_type,
                'price': str(price),
                'volume': str(volume),
                'market': market,
                '_sim': True,
            }

        query = {'market': market, 'side': side, 'ord_type': ord_type}
        if ord_type == 'limit':
            query['price'] = str(round_to_tick(price))
            query['volume'] = str(volume)
        elif ord_type == 'price':
            query['price'] = str(int(price))
        elif ord_type == 'market':
            query['volume'] = str(volume)

        try:
            res = requests.post(f"{cls.BASE_URL}/orders", json=query, headers=cls._get_headers(query),
                                timeout=CONFIG['API_TIMEOUT'])
            result = res.json()
            if 'error' in result:
                err = result['error']
                log(f"주문 실패 [{err.get('name', '')}]: {err.get('message', '')} | {query}", 'ERROR')
                return None
            return result
        except Exception as e:
            log(f"주문 네트워크 에러: {e}", 'ERROR')
            return None

    @classmethod
    def get_order(cls, order_uuid):
        if not CONFIG['ENABLE_REAL_TRADING']:
            return None
        try:
            query = {'uuid': order_uuid}
            res = requests.get(f"{cls.BASE_URL}/order", params=query, headers=cls._get_headers(query),
                               timeout=CONFIG['API_TIMEOUT'])
            data = res.json()
            if isinstance(data, dict) and 'error' in data:
                log(f"주문조회 에러: {data['error']}", 'DEBUG')
                return None
            return data
        except:
            return None

    @classmethod
    def cancel_order(cls, order_uuid):
        if not CONFIG['ENABLE_REAL_TRADING']:
            return True
        try:
            query = {'uuid': order_uuid}
            requests.delete(f"{cls.BASE_URL}/order", params=query, headers=cls._get_headers(query),
                            timeout=CONFIG['API_TIMEOUT'])
            return True
        except:
            return False

    @classmethod
    def wait_order_done(cls, order_uuid, timeout=60, poll=0.5):
        if not CONFIG['ENABLE_REAL_TRADING']:
            return None
        start = time.time()
        while time.time() - start < timeout:
            order = cls.get_order(order_uuid)
            if order:
                if order.get('state') == 'done':
                    return order
                if order.get('state') == 'cancel':
                    return None
            time.sleep(poll)
        return None

    @classmethod
    def get_account_balance(cls, currency):
        accounts = cls.get_accounts()
        if not accounts:
            return None
        for acc in accounts:
            if acc.get('currency') == currency:
                return {
                    'balance': float(acc.get('balance', 0)),
                    'avg_buy_price': float(acc.get('avg_buy_price', 0)),
                }
        return None

    @classmethod
    def get_open_orders(cls, market=None):
        if not CONFIG['ENABLE_REAL_TRADING']:
            return []
        try:
            query = {'state': 'wait'}
            if market:
                query['market'] = market
            res = requests.get(f"{cls.BASE_URL}/orders", params=query, headers=cls._get_headers(query),
                               timeout=CONFIG['API_TIMEOUT'])
            data = res.json()
            if isinstance(data, dict) and 'error' in data:
                return []
            return data
        except:
            return []


# ============================================================================
# 📱 텔레그램
# ============================================================================
class TelegramNotifier:
    def __init__(self):
        self.enabled = TELEGRAM_CONFIG['ENABLED']
        self.token = TELEGRAM_CONFIG['BOT_TOKEN']
        self.chat_id = TELEGRAM_CONFIG['CHAT_ID']

    def send(self, text):
        if not self.enabled:
            return
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, data={'chat_id': self.chat_id, 'text': text, 'parse_mode': 'HTML'}, timeout=5)
        except:
            pass

    def notify_start(self, data):
        grid_detail = "\n".join([f"  Lv.{i}: {format_price(p)}원" for i, p in enumerate(data['levels'])])
        regime_emoji = {'BULL': '🟢', 'BEAR': '🔴', 'NEUTRAL': '🟡'}.get(data.get('regime', ''), '⚪')
        mode_str = data.get('mode', 'AUTO')
        mode_emoji = '🎯' if mode_str == 'MANUAL' else '🤖'

        actual_grids = data.get('grid_count', 0)
        target_grids = data.get('target_grids', actual_grids)

        msg = (
            f"{mode_emoji} <b>그리드 봇 진입</b> [{mode_str}]\n"
            f"━━━━━━━━━━━━━━\n"
        )

        if mode_str == 'AUTO':
            msg += f"📡 시장: {regime_emoji} {data.get('regime', '?')}\n"
            msg += f"🎯 종목: {data['market']} ({data.get('score', 0):.1f}점)\n"
        else:
            msg += f"🎯 종목: {data['market']} (수동 선택)\n"

        msg += (
            f"💰 진입가: {format_price(data['entry_price'])}원\n"
            f"📦 초기매수: {data['init_qty']:.6f}개 ({format_price(data['init_cost'])}원)\n"
            f"📊 범위: {format_price(data['lower'])} ~ {format_price(data['upper'])} (±{data.get('range_pct', 0) * 100:.1f}%)\n"
            f"📝 사유: {data['reason']}\n"
            f"━━━━━━━━━━━━━━\n"
        )

        # 손절/익절가 표시
        sl = CONFIG.get('STOP_LOSS_PRICE', 0)
        htp = CONFIG.get('HARD_TAKE_PROFIT_PRICE', 0)
        if sl > 0:
            sl_pct = (sl / data['entry_price'] - 1) * 100
            msg += f"🔻 손절가: {format_price(sl)}원 ({sl_pct:+.1f}%) → 전량 청산 후 봇 종료\n"
        if htp > 0:
            htp_pct = (htp / data['entry_price'] - 1) * 100
            msg += f"🔺 강제 익절가: {format_price(htp)}원 ({htp_pct:+.1f}%) → 전량 청산 후 재진입\n"
        if sl > 0 or htp > 0:
            msg += f"━━━━━━━━━━━━━━\n"

        if actual_grids < target_grids:
            msg += f"📐 그리드: {actual_grids}칸 생성 (목표: {target_grids}칸)\n"
            msg += f"💡 계단식 매수로 효율 운영\n"
        else:
            msg += f"📐 그리드: {actual_grids}칸\n"

        msg += f"{grid_detail}"
        self.send(msg)

    def notify_trade(self, side, market, price, qty=0, profit=0):
        emoji = "🟢 매수" if side == 'BUY' else "🔴 매도"
        text = f"{emoji} | {market}\n가격: {format_price(price)}원"
        if qty > 0:
            text += f"\n수량: {qty:.6f}"
        if side == 'SELL':
            if CONFIG['KEEP_PROFIT_COINS']:
                if profit > 0:
                    text += f"\n💎 수익: +{profit:,.0f}원 (코인 보유)"
                else:
                    text += f"\n💰 원금 회수"
            else:
                text += f"\n손익: {profit:+,.0f}원"
        elif profit != 0:
            text += f"\n손익: {profit:+,.0f}원"
        self.send(text)

    def notify_exit(self, market, reason, total_profit, runtime):
        emoji = "🟢 익절" if total_profit >= 0 else "🔴 손절"
        self.send(
            f"{emoji} <b>익절 완료</b>\n"
            f"종목: {market}\n"
            f"사유: {reason}\n"
            f"총 손익: {total_profit:+,.0f}원 (평가)\n"
            f"운행: {runtime}\n"
            f"💎 보유 코인 유지"
        )

    def notify_liquidation(self, market, reason, total_profit, runtime, liquidation_type):
        """전량 청산 알림 (손절/강제익절 전용)"""
        if liquidation_type == 'STOP_LOSS':
            emoji = "🔻"
            title = "손절 청산"
        else:
            emoji = "🔺"
            title = "강제 익절 청산"
        self.send(
            f"{emoji} <b>{title} 완료</b>\n"
            f"종목: {market}\n"
            f"사유: {reason}\n"
            f"총 손익: {total_profit:+,.0f}원\n"
            f"운행: {runtime}\n"
            f"{'⛔ 봇 완전 종료' if liquidation_type == 'STOP_LOSS' else '🔁 재진입 대기 중'}"
        )

    def notify_reentry(self, market, reason):
        self.send(f"🔁 <b>재진입</b>\n종목: {market}\n사유: {reason}")

    def notify_report(self, d):
        extra = ""
        sl = CONFIG.get('STOP_LOSS_PRICE', 0)
        htp = CONFIG.get('HARD_TAKE_PROFIT_PRICE', 0)
        if sl > 0 or htp > 0:
            extra = f"━━━━━━━━━━━━━━\n"
            if sl > 0:
                dist = (d['current_price'] - sl) / d['current_price'] * 100
                extra += f"🔻 손절까지: {dist:.2f}% ({format_price(sl)}원)\n"
            if htp > 0:
                dist = (htp - d['current_price']) / d['current_price'] * 100
                extra += f"🔺 강제익절까지: {dist:.2f}% ({format_price(htp)}원)\n"

        self.send(
            f"📊 <b>성과 보고서</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"⏰ {d['timestamp']}\n"
            f"🎯 {d['market']} | {format_price(d['current_price'])}원\n"
            f"📈 진입가: {format_price(d['entry_price'])}원 ({d['price_change']:+.2f}%)\n"
            f"━━━━━━━━━━━━━━\n"
            f"💵 총 평가: {format_price(d['total_value'])}원\n"
            f"📊 손익: {d['total_pnl']:+,.0f}원 ({d['total_pnl_pct']:+.2f}%)\n"
            f"  ├ 실현: {d['realized']:+,.0f}원\n"
            f"  └ 평가: {d['unrealized']:+,.0f}원\n"
            f"━━━━━━━━━━━━━━\n"
            f"{extra}"
            f"🔄 거래: {d['trades']}건\n"
            f"📋 대기매수: {d['pending']}건 | 포지션: {d['positions']}건\n"
            f"💵 현금: {format_price(d['cash'])}원\n"
            f"⏱️ 운행: {d['runtime']}"
        )


# ============================================================================
# 🔍 Smart Picker V3
# ============================================================================
class SmartPicker:
    W_VOLUME = 0.40
    W_ALIGN = 0.30
    W_ATR = 0.20
    W_STABILITY = 0.10
    TOP_N = 3

    @classmethod
    def detect_market_regime(cls):
        try:
            candles = UpbitAPI.get_candles('KRW-BTC', count=100)
            if not candles or len(candles) < 60:
                return 'NEUTRAL', {'reason': 'BTC 데이터 부족'}

            df = pd.DataFrame(candles)[::-1].reset_index(drop=True)
            cp = df['trade_price'].astype(float)

            btc_ma5 = cp.rolling(5).mean().iloc[-1]
            btc_ma20 = cp.rolling(20).mean().iloc[-1]
            btc_ma60 = cp.rolling(60).mean().iloc[-1]
            btc_price = cp.iloc[-1]

            btc_align_score = 0
            if btc_ma5 > btc_ma20:
                btc_align_score += 30
            if btc_ma20 > btc_ma60:
                btc_align_score += 30
            if btc_price > btc_ma5:
                btc_align_score += 20
            if btc_price > btc_ma20:
                btc_align_score += 20

            btc_change_5h = (btc_price - cp.iloc[-6]) / cp.iloc[-6] * 100 if len(cp) >= 6 else 0
            btc_change_20h = (btc_price - cp.iloc[-21]) / cp.iloc[-21] * 100 if len(cp) >= 21 else 0

            info = {
                'btc_price': btc_price,
                'btc_align_score': btc_align_score,
                'btc_change_5h': btc_change_5h,
                'btc_change_20h': btc_change_20h,
                'ma5': btc_ma5,
                'ma20': btc_ma20,
                'ma60': btc_ma60,
            }

            if btc_align_score >= 70 and btc_change_20h > -2:
                regime = 'BULL'
            elif btc_align_score <= 30 or btc_change_20h < -5:
                regime = 'BEAR'
            else:
                regime = 'NEUTRAL'

            info['regime'] = regime
            return regime, info

        except Exception as e:
            log(f"시장 상태 판단 실패: {e}", 'WARN')
            return 'NEUTRAL', {'reason': str(e)}

    @classmethod
    def score_market(cls, market, ticker, regime='NEUTRAL'):
        details = {'volume': 0, 'align': 0, 'atr': 0, 'stability': 0, 'raw_atr_pct': 0}
        try:
            candles = UpbitAPI.get_candles(market, count=100)
            if not candles or len(candles) < 60:
                return 0, details, "데이터 부족 (60봉 미만)"

            df = pd.DataFrame(candles)[::-1].reset_index(drop=True)
            cp = df['trade_price'].astype(float)
            high = df['high_price'].astype(float)
            low = df['low_price'].astype(float)
            cur_price = cp.iloc[-1]

            vol_24h = ticker.get('acc_trade_price_24h', 0)
            vol_raw = min(100, (vol_24h / 5000e8) * 100)
            details['volume'] = vol_raw

            ma5 = cp.rolling(5).mean()
            ma10 = cp.rolling(10).mean()
            ma20 = cp.rolling(20).mean()
            ma60 = cp.rolling(60).mean()

            ma5_now = ma5.iloc[-1]
            ma10_now = ma10.iloc[-1]
            ma20_now = ma20.iloc[-1]
            ma60_now = ma60.iloc[-1]

            ma5_prev = ma5.iloc[-2] if len(ma5) >= 2 else ma5_now
            ma10_prev = ma10.iloc[-2] if len(ma10) >= 2 else ma10_now
            if ma5_prev >= ma10_prev and ma5_now < ma10_now:
                return 0, details, f"데드크로스 (MA5 {ma5_now:.1f} < MA10 {ma10_now:.1f})"
            if ma5_now < ma10_now:
                return 0, details, f"MA5<MA10 하락세 ({ma5_now:.1f} < {ma10_now:.1f})"

            align_raw = 0
            if ma5_now > ma20_now:
                align_raw += 25
            if ma20_now > ma60_now:
                align_raw += 25
            if cur_price > ma5_now:
                align_raw += 20
            if cur_price > ma20_now:
                align_raw += 15
            if cur_price > ma60_now:
                align_raw += 15
            align_raw = min(100, align_raw)
            details['align'] = align_raw

            if regime == 'BULL' and align_raw < 30:
                return 0, details, f"상승장 정배열 미달 ({align_raw:.0f}<30)"
            elif regime == 'BEAR' and align_raw < 70:
                return 0, details, f"하락장 정배열 미달 ({align_raw:.0f}<70)"
            elif regime == 'NEUTRAL' and align_raw < 50:
                return 0, details, f"중립장 정배열 미달 ({align_raw:.0f}<50)"

            tr = high - low
            atr_20 = tr.iloc[-20:].mean()
            atr_pct = (atr_20 / cur_price) * 100 if cur_price > 0 else 0
            details['raw_atr_pct'] = atr_pct

            if atr_pct > 25:
                return 0, details, f"ATR 과다 ({atr_pct:.1f}% > 25%)"
            elif 8 <= atr_pct <= 15:
                atr_raw = 100
            elif 5 <= atr_pct < 8:
                atr_raw = 60 + (atr_pct - 5) / 3 * 40
            elif 15 < atr_pct <= 25:
                atr_raw = max(0, 100 - (atr_pct - 15) / 10 * 100)
            elif 3 <= atr_pct < 5:
                atr_raw = 30 + (atr_pct - 3) / 2 * 30
            else:
                atr_raw = 10
            details['atr'] = atr_raw

            recent_high = high.iloc[-20:].max()
            recent_low = low.iloc[-20:].min()
            recent_avg = cp.iloc[-20:].mean()
            box_range_pct = ((recent_high - recent_low) / recent_avg) * 100 if recent_avg > 0 else 100

            if box_range_pct < 5:
                stab_raw = 100
            elif box_range_pct < 10:
                stab_raw = 60 + (10 - box_range_pct) / 5 * 40
            elif box_range_pct < 20:
                stab_raw = max(0, 60 - (box_range_pct - 10) / 10 * 60)
            else:
                stab_raw = 0
            details['stability'] = stab_raw

            cr = ticker.get('signed_change_rate', 0)
            if abs(cr) > CONFIG['MAX_PUMP_PCT']:
                return 0, details, f"급등/급락 ({cr * 100:+.1f}%)"

            total = (
                vol_raw * cls.W_VOLUME +
                align_raw * cls.W_ALIGN +
                atr_raw * cls.W_ATR +
                stab_raw * cls.W_STABILITY
            )

            align_txt = []
            if ma5_now > ma20_now > ma60_now:
                align_txt.append("완전정배열")
            elif ma5_now > ma20_now:
                align_txt.append("단기정배열")
            else:
                align_txt.append("역배열")

            reason = (
                f"거래액{vol_24h / 1e8:.0f}억 "
                f"{'|'.join(align_txt)} "
                f"ATR{atr_pct:.1f}% "
                f"박스{box_range_pct:.1f}%"
            )

            return total, details, reason

        except Exception as e:
            return 0, details, f"분석 실패: {e}"

    @classmethod
    def find_best(cls, exclude_market=None):
        regime, regime_info = cls.detect_market_regime()
        regime_emoji = {'BULL': '🟢', 'BEAR': '🔴', 'NEUTRAL': '🟡'}[regime]

        log(f"{'─' * 50}")
        log(f"📡 시장 상태: {regime_emoji} {regime}")
        if 'btc_price' in regime_info:
            log(f"   BTC: {format_price(regime_info['btc_price'])}원 "
                f"| 정배열: {regime_info['btc_align_score']}점 "
                f"| 5h: {regime_info['btc_change_5h']:+.1f}% "
                f"| 20h: {regime_info['btc_change_20h']:+.1f}%")
        threshold = {
            'BULL': '정배열 30점 이상 통과',
            'BEAR': '정배열 70점 이상만 통과 (엄격)',
            'NEUTRAL': '정배열 50점 이상 통과',
        }[regime]
        log(f"   필터: {threshold}")
        log(f"{'─' * 50}")

        try:
            mkts = requests.get("https://api.upbit.com/v1/market/all", timeout=CONFIG['API_TIMEOUT']).json()
            krw = [m['market'] for m in mkts if m['market'].startswith('KRW-')]
        except:
            log("마켓 목록 조회 실패", 'ERROR')
            return None

        tickers = UpbitAPI.get_ticker(','.join(krw))
        if not tickers:
            log("시세 조회 실패", 'ERROR')
            return None

        cands = [t for t in tickers
                 if t['market'].replace('KRW-', '') not in CONFIG['EXCLUDE_COINS']]
        if exclude_market:
            cands = [t for t in cands if t['market'] != exclude_market]
        top15 = sorted(cands, key=lambda x: x.get('acc_trade_price_24h', 0), reverse=True)[:15]

        scored = []
        log(f"📊 종목 스코어링 ({len(top15)}개 후보, 1시간봉 기준)...")
        log(f"   {'종목':>8s} | {'총점':>5s} | {'거래(40)':>8s} | {'정배열(30)':>8s} | {'ATR(20)':>8s} | {'안정(10)':>8s} | 사유")
        log(f"   {'─' * 85}")

        for t in top15:
            score, details, reason = cls.score_market(t['market'], t, regime)
            sym = t['market'].replace('KRW-', '')

            v = details['volume'] * cls.W_VOLUME
            a = details['align'] * cls.W_ALIGN
            r = details['atr'] * cls.W_ATR
            s = details['stability'] * cls.W_STABILITY

            status = "✅" if score > 0 else "❌"
            log(f"   {sym:>8s} | {score:5.1f} | {v:7.1f}({details['volume']:.0f}) | "
                f"{a:7.1f}({details['align']:.0f}) | {r:7.1f}({details['atr']:.0f}) | "
                f"{s:7.1f}({details['stability']:.0f}) | {status} {reason}")
            time.sleep(0.15)

            if score > 0:
                scored.append({
                    'market': t['market'],
                    'score': score,
                    'price': t['trade_price'],
                    'volume': t['acc_trade_price_24h'],
                    'reason': reason,
                    'details': details,
                    'regime': regime,
                })

        if not scored:
            log("❌ 통과 종목 없음! 시장 상황이 좋지 않습니다.", 'WARN')
            return None

        scored.sort(key=lambda x: x['score'], reverse=True)
        top_n = scored[:cls.TOP_N]

        log(f"\n🏆 TOP {len(top_n)} 종목:")
        for i, s in enumerate(top_n):
            sym = s['market'].replace('KRW-', '')
            log(f"   {i + 1}위: {sym} ({s['score']:.1f}점) — {s['reason']}")

        best = top_n[0]
        log(f"\n✅ 최종 선정: {best['market']} ({best['score']:.1f}점) [{regime_emoji} {regime}]")
        return best


# ============================================================================
# 🎯 수동 선택 모드
# ============================================================================
def manual_select_target():
    print("\n" + "=" * 55)
    print("🎯 수동 선택 모드")
    print("=" * 55)

    while True:
        market_input = input("\n종목 심볼을 입력하세요 (예: XRP, DOGE): ").strip().upper()
        if not market_input:
            print("❌ 종목을 입력해주세요.")
            continue

        market = f"KRW-{market_input}"
        ticker = UpbitAPI.get_ticker(market)
        if not ticker or not isinstance(ticker, list) or len(ticker) == 0:
            print(f"❌ '{market}' 종목을 찾을 수 없습니다. 다시 입력해주세요.")
            continue

        current_price = ticker[0]['trade_price']
        print(f"\n✅ {market} 현재가: {format_price(current_price)}원")
        break

    print("\n그리드 범위를 선택하세요:")
    print("  1) AUTO - 5분봉 ATR 기반 자동 계산")
    print("  2) MANUAL 대칭 - 위/아래 동일 (예: ±5%)")
    print("  3) MANUAL 비대칭 - 위/아래 다르게 (예: -10% / +7.5%)")

    while True:
        range_choice = input("\n선택 (1, 2, 또는 3): ").strip()
        if range_choice in ['1', '2', '3']:
            break
        print("❌ 1, 2, 또는 3을 입력해주세요.")

    range_down = 0
    range_up = 0

    if range_choice == '1':
        range_pct = calculate_auto_range(market, current_price)
        lower = current_price * (1 - range_pct)
        upper = current_price * (1 + range_pct)
        print(f"✅ 자동 계산 범위: ±{range_pct * 100:.1f}%")
        reason = f'수동 선택 (±{range_pct * 100:.1f}%)'

    elif range_choice == '2':
        while True:
            try:
                range_input = input(f"\n그리드 범위를 입력하세요 (예: 5 = ±5%): ").strip()
                range_pct = float(range_input) / 100
                if range_pct <= 0 or range_pct > 0.5:
                    print("❌ 0%보다 크고 50% 이하로 입력해주세요.")
                    continue
                lower = current_price * (1 - range_pct)
                upper = current_price * (1 + range_pct)
                print(f"✅ 설정 범위: ±{range_pct * 100:.1f}%")
                reason = f'수동 선택 (±{range_pct * 100:.1f}%)'
                break
            except ValueError:
                print("❌ 숫자를 입력해주세요.")

    else:
        while True:
            try:
                down_input = input(f"\n하단 범위 (%) (예: 10 = -10%): ").strip()
                range_down = float(down_input) / 100
                if range_down <= 0 or range_down > 0.5:
                    print("❌ 0%보다 크고 50% 이하로 입력해주세요.")
                    continue
                break
            except ValueError:
                print("❌ 숫자를 입력해주세요.")

        while True:
            try:
                up_input = input(f"상단 범위 (%) (예: 7.5 = +7.5%): ").strip()
                range_up = float(up_input) / 100
                if range_up <= 0 or range_up > 0.5:
                    print("❌ 0%보다 크고 50% 이하로 입력해주세요.")
                    continue
                break
            except ValueError:
                print("❌ 숫자를 입력해주세요.")

        lower = current_price * (1 - range_down)
        upper = current_price * (1 + range_up)
        range_pct = (range_down + range_up) / 2
        print(f"✅ 비대칭 설정: 하단 -{range_down * 100:.1f}% | 상단 +{range_up * 100:.1f}%")
        reason = f'비대칭 (-{range_down * 100:.1f}% / +{range_up * 100:.1f}%)'

    print(f"\n📊 그리드 범위:")
    print(f"  하단: {format_price(lower)}원 ({(lower / current_price - 1) * 100:+.1f}%)")
    print(f"  상단: {format_price(upper)}원 ({(upper / current_price - 1) * 100:+.1f}%)")

    confirm = input("\n진행하시겠습니까? (y/n): ").strip().lower()
    if confirm != 'y':
        print("❌ 취소되었습니다.")
        return None

    return {
        'market': market,
        'price': current_price,
        'range_pct': range_pct,
        'lower': lower,
        'upper': upper,
        'reason': reason,
        'score': 0,
        'regime': 'MANUAL',
        'mode': 'MANUAL',
    }


def calculate_auto_range(market, current_price):
    try:
        candles = UpbitAPI.get_candles(market, count=50, interval=5)
        if not candles or len(candles) < 20:
            log(f"  ⚠️ 5분봉 부족 → 기본 ±{CONFIG['RANGE_PCT_MIN'] * 100:.0f}%", 'WARN')
            return CONFIG['RANGE_PCT_MIN']

        df = pd.DataFrame(candles)[::-1].reset_index(drop=True)
        high = df['high_price'].astype(float)
        low = df['low_price'].astype(float)

        atr = (high - low).iloc[-20:].mean()
        atr_pct = atr / current_price if current_price > 0 else 0.02

        raw = atr_pct * CONFIG['ATR_MULTIPLIER']
        final = max(CONFIG['RANGE_PCT_MIN'], min(CONFIG['RANGE_PCT_MAX'], raw))

        log(f"  📐 5분봉 ATR: {atr_pct * 100:.2f}% × {CONFIG['ATR_MULTIPLIER']:.0f} = {raw * 100:.1f}% → 적용: ±{final * 100:.1f}%")
        return final

    except Exception as e:
        log(f"  ⚠️ ATR 계산 실패: {e} → 기본 ±{CONFIG['RANGE_PCT_MIN'] * 100:.0f}%", 'WARN')
        return CONFIG['RANGE_PCT_MIN']


# ============================================================================
# 🧹 프로그램 종료 시 완전 정리
# ============================================================================
def cleanup_all():
    log("\n" + "=" * 55)
    log("🛑 프로그램 종료 - 모든 주문 및 포지션 유지")
    log("=" * 55)

    if CONFIG['ENABLE_REAL_TRADING']:
        notifier = TelegramNotifier()
        notifier.send(
            f"🛑 <b>프로그램 종료</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"💡 모든 주문 유지\n"
            f"💰 보유 코인 유지\n"
            f"\n※ 거래는 계속 진행됩니다"
        )

    log("✅ 종료 완료 - 모든 주문은 계속 실행됩니다")
    log("=" * 55)
    log("\n" + "=" * 55)
    log("✅ 정리 완료")
    log("=" * 55)


# ============================================================================
# 🤖 Grid Trading Bot V8.1 — 핵심 엔진
# ============================================================================
class GridTradingBot:
    EMPTY = 'EMPTY'
    BUY_PENDING = 'BUY_PENDING'
    FILLED = 'FILLED'

    def __init__(self, target, grid_amount, grid_count, available_cash=None):
        self.market = target['market']
        self.grid_unit = grid_amount
        self.grid_count = grid_count
        self.capital = grid_amount * grid_count

        if available_cash is not None:
            self.cash = available_cash
            if available_cash < self.capital:
                max_possible = int(available_cash / grid_amount)
                log(f"💰 현재 잔고로 {max_possible}칸 운영 가능 (계단식 매수로 효율적 운영)")
        else:
            self.cash = self.capital

        self.reason = target.get('reason', '')
        self.mode = target.get('mode', 'AUTO')
        self.start_time = datetime.now()
        self.active = True
        self.notifier = TelegramNotifier()

        self.current_price = target['price']
        self.entry_price = None
        self.initial_qty = 0.0
        self.initial_cost = 0.0

        self.grid_levels = []
        self.actual_grid_count = grid_count
        self.lower = target.get('lower', 0)
        self.upper = target.get('upper', 0)

        self.levels = {}
        self.total_profit = 0.0
        self.profit_coins = 0.0
        self.trade_count = 0
        self.last_report_time = time.time()
        self.last_rotation_scan = time.time()
        self.current_score = target.get('score', 0)

        # 트레일링 스탑 상태
        self.trailing_mode = False
        self.trailing_high = 0.0
        self.trailing_entry_price = 0.0

        # 상승 라인 상태
        self.take_profit_reduce_triggered = False
        self.take_profit_reduce_line = 0
        self.original_grid_amount = grid_amount

        # ── V8.1: 손절/강제익절 설정 ──────────────────────────────
        self.stop_loss_price = CONFIG.get('STOP_LOSS_PRICE', 0)
        self.hard_take_profit_price = CONFIG.get('HARD_TAKE_PROFIT_PRICE', 0)
        self._hard_exit_triggered = False  # 중복 발동 방지

        if self.stop_loss_price > 0:
            log(f"🔻 손절가 설정: {format_price(self.stop_loss_price)}원 (도달 시 전량 청산 → 봇 종료)")
        if self.hard_take_profit_price > 0:
            log(f"🔺 강제 익절가 설정: {format_price(self.hard_take_profit_price)}원 (도달 시 전량 청산 → 재진입)")

        if 'range_pct' in target:
            self.range_pct = target['range_pct']
        else:
            self.range_pct = 0.05

    # ════════════════════════════════════════════════════════════
    # STEP 1: 시장가 매수
    # ════════════════════════════════════════════════════════════
    def execute_initial_buy(self):
        buy_amount = int(self.grid_unit * CONFIG['INITIAL_BUY_GRIDS'])

        if buy_amount < CONFIG['MIN_ORDER_AMOUNT']:
            log(f"❌ 초기 매수금액({format_price(buy_amount)}원) < 최소주문({CONFIG['MIN_ORDER_AMOUNT']}원). 자본 부족!", 'ERROR')
            return False

        ticker = UpbitAPI.get_ticker(self.market)
        if ticker and isinstance(ticker, list) and len(ticker) > 0:
            self.current_price = ticker[0]['trade_price']
            log(f"📡 최신 시세: {format_price(self.current_price)}원 (스크리닝 대비 갱신)")
        else:
            log("⚠️ 시세 갱신 실패, 스크리닝 가격 사용", 'WARN')

        buy_price = round_to_tick(self.current_price * 1.003, 'up')
        buy_qty = round((buy_amount * (1 - CONFIG['FEE_PCT'])) / buy_price, 8)

        log(f"💰 초기 지정가 매수: {format_price(buy_price)}원 × {buy_qty:.6f} (≈{format_price(buy_amount)}원)")

        if CONFIG['ENABLE_REAL_TRADING']:
            res = UpbitAPI.place_order(self.market, 'bid', buy_price, buy_qty, 'limit')
            if not res or 'uuid' not in res:
                log("❌ 지정가 매수 주문 실패!", 'ERROR')
                return False

            order_uuid = res['uuid']
            log(f"  주문 접수: {order_uuid}")

            time.sleep(1)
            done = UpbitAPI.wait_order_done(order_uuid, timeout=30, poll=0.5)

            if done:
                avg_price = self._extract_avg_price(done)
                executed_vol = float(done.get('executed_volume', 0))
                if avg_price and executed_vol > 0:
                    actual_cost = avg_price * executed_vol
                    self._set_entry(avg_price, executed_vol, actual_cost)
                    return True
                else:
                    log("❌ 체결 정보 확인 실패", 'ERROR')
                    return False
            else:
                log("⚠️ 30초 내 미체결, 주문 취소 후 재시도...", 'WARN')
                UpbitAPI.cancel_order(order_uuid)
                return False
        else:
            self._set_entry(self.current_price, round((buy_amount * (1 - CONFIG['FEE_PCT'])) / self.current_price, 8),
                            buy_amount)
            log(f"✅ [SIM] 지정가 매수 체결")
            return True

    def _extract_avg_price(self, order_data):
        if 'avg_price' in order_data:
            try:
                return float(order_data['avg_price'])
            except (ValueError, TypeError):
                pass

        if 'trades' in order_data and order_data['trades']:
            try:
                trades = order_data['trades']
                total_price = sum(float(t.get('price', 0)) * float(t.get('volume', 0)) for t in trades)
                total_volume = sum(float(t.get('volume', 0)) for t in trades)
                if total_volume > 0:
                    return total_price / total_volume
            except (ValueError, TypeError, KeyError):
                pass

        if 'price' in order_data:
            try:
                price = float(order_data['price'])
                if price > 0:
                    return price
            except (ValueError, TypeError):
                pass

        log("⚠️ 체결가 추출 실패, 현재가 사용", 'WARN')
        return self.current_price

    def _set_entry(self, price, qty, cost):
        self.entry_price = price
        self.initial_qty = qty
        self.initial_cost = cost
        self.cash -= cost
        log(f"✅ 체결: {format_price(price)}원 × {qty:.6f} = {format_price(cost)}원 | 잔금: {format_price(self.cash)}원")

    # ════════════════════════════════════════════════════════════
    # STEP 2: 5분봉 ATR 기반 동적 범위 + 그리드 구성
    # ════════════════════════════════════════════════════════════
    def _calculate_range_from_atr(self):
        try:
            candles = UpbitAPI.get_candles(self.market, count=50, interval=5)
            if not candles or len(candles) < 20:
                log(f"  ⚠️ 5분봉 부족 → 기본 ±{CONFIG['RANGE_PCT_MIN'] * 100:.0f}%", 'WARN')
                return CONFIG['RANGE_PCT_MIN']

            df = pd.DataFrame(candles)[::-1].reset_index(drop=True)
            high = df['high_price'].astype(float)
            low = df['low_price'].astype(float)
            cur = df['trade_price'].astype(float).iloc[-1]

            atr = (high - low).iloc[-20:].mean()
            atr_pct = atr / cur if cur > 0 else 0.02

            raw = atr_pct * CONFIG['ATR_MULTIPLIER']
            final = max(CONFIG['RANGE_PCT_MIN'], min(CONFIG['RANGE_PCT_MAX'], raw))

            log(f"  📐 5분봉 ATR: {atr_pct * 100:.2f}% × {CONFIG['ATR_MULTIPLIER']:.0f} = {raw * 100:.1f}% → 적용: ±{final * 100:.1f}%")
            return final

        except Exception as e:
            log(f"  ⚠️ ATR 계산 실패: {e} → 기본 ±{CONFIG['RANGE_PCT_MIN'] * 100:.0f}%", 'WARN')
            return CONFIG['RANGE_PCT_MIN']

    def build_grid(self):
        if self.mode != 'MANUAL':
            self.range_pct = self._calculate_range_from_atr()

        if self.mode == 'MANUAL' and self.lower > 0 and self.upper > 0:
            log(f"  📌 수동 설정 범위 사용: {format_price(self.lower)} ~ {format_price(self.upper)}")
            initial_lower = round_to_tick(self.lower, 'down')
            initial_upper = round_to_tick(self.upper, 'up')

            if self.entry_price < initial_lower:
                log(f"  ⚠️ 진입가({format_price(self.entry_price)}원) < 하단({format_price(initial_lower)}원) → 하단 확장")
                initial_lower = round_to_tick(self.entry_price * 0.98, 'down')
            elif self.entry_price > initial_upper:
                log(f"  ⚠️ 진입가({format_price(self.entry_price)}원) > 상단({format_price(initial_upper)}원) → 상단 확장")
                initial_upper = round_to_tick(self.entry_price * 1.02, 'up')
        else:
            if CONFIG.get('ASYMMETRIC_GRID', False):
                range_down = CONFIG.get('GRID_RANGE_DOWN', 0.10)
                range_up = CONFIG.get('GRID_RANGE_UP', 0.075)
                initial_lower = round_to_tick(self.entry_price * (1 - range_down), 'down')
                initial_upper = round_to_tick(self.entry_price * (1 + range_up), 'up')
                log(f"  📐 비대칭 그리드: 하단 -{range_down * 100:.1f}% | 상단 +{range_up * 100:.1f}%")
            else:
                initial_lower = round_to_tick(self.entry_price * (1 - self.range_pct), 'down')
                initial_upper = round_to_tick(self.entry_price * (1 + self.range_pct), 'up')

        tick = get_tick_size(self.entry_price)
        min_range_needed = tick * self.grid_count
        current_range = initial_upper - initial_lower

        if current_range < min_range_needed:
            shortage = min_range_needed - current_range
            expand_lower = round_to_tick(initial_lower - (shortage / 2), 'down')
            expand_upper = round_to_tick(initial_upper + (shortage / 2), 'up')
            log(f"  📐 틱 사이즈 제약: 범위 확장 필요 ({current_range}원 → {min_range_needed}원)")
            log(f"     {format_price(initial_lower)}~{format_price(initial_upper)} → {format_price(expand_lower)}~{format_price(expand_upper)}")
            self.lower = expand_lower
            self.upper = expand_upper
        else:
            self.lower = initial_lower
            self.upper = initial_upper

        desired = self.grid_count + 1
        raw = np.linspace(self.lower, self.upper, desired)
        levels = sorted(set(round_to_tick(p) for p in raw))

        unique_levels = []
        for p in levels:
            if not unique_levels or p > unique_levels[-1]:
                unique_levels.append(p)

        final_levels = [unique_levels[0]]
        for p in unique_levels[1:]:
            if p >= final_levels[-1] + tick:
                final_levels.append(p)

        attempts = 0
        while len(final_levels) < desired and attempts < 5:
            new = list(final_levels)
            for i in range(len(final_levels) - 1):
                if len(new) >= desired:
                    break
                gap = final_levels[i + 1] - final_levels[i]
                if gap >= tick * 2:
                    mid = round_to_tick((final_levels[i] + final_levels[i + 1]) / 2)
                    if mid not in new and mid > final_levels[i] and mid < final_levels[i + 1]:
                        new.append(mid)
            final_levels = sorted(set(new))
            attempts += 1

        self.grid_levels = final_levels
        actual_count = len(final_levels) - 1

        if actual_count < 2:
            log(f"❌ 그리드 수 부족 ({actual_count}칸) - 범위가 너무 좁거나 틱 사이즈가 큼", 'ERROR')
            return False

        if actual_count < self.grid_count:
            log(f"⚠️ 그리드 {self.grid_count}칸 요청 → {actual_count}칸 생성 (틱 사이즈 제약)", 'WARN')

        for i in range(actual_count):
            self.levels[i] = {
                'state': self.EMPTY,
                'buy_uuid': None, 'buy_price': self.grid_levels[i], 'buy_qty': 0,
                'sell_uuid': None, 'sell_price': self.grid_levels[i + 1],
            }

        if CONFIG.get('TAKE_PROFIT_REDUCE_ENABLED', False):
            user_price = CONFIG.get('TAKE_PROFIT_REDUCE_PRICE', 0)
            if user_price > 0:
                self.take_profit_reduce_line = round_to_tick(user_price, 'up')
                gain_pct = (self.take_profit_reduce_line / self.entry_price - 1) * 100
                log(f"📈 상승 라인 설정: {format_price(self.take_profit_reduce_line)}원 (진입가 대비 +{gain_pct:.1f}%)")
            else:
                self.take_profit_reduce_line = 0
        else:
            self.take_profit_reduce_line = 0

        # 손절/익절가 유효성 검증 (진입가 기준 경고)
        if self.stop_loss_price > 0 and self.stop_loss_price >= self.entry_price:
            log(f"⚠️ 손절가({format_price(self.stop_loss_price)}원)가 진입가({format_price(self.entry_price)}원) 이상입니다!", 'WARN')
        if self.hard_take_profit_price > 0 and self.hard_take_profit_price <= self.entry_price:
            log(f"⚠️ 강제 익절가({format_price(self.hard_take_profit_price)}원)가 진입가({format_price(self.entry_price)}원) 이하입니다!", 'WARN')

        self._print_grid()
        return True

    # ════════════════════════════════════════════════════════════
    # STEP 3: 초기 보유분 배치 + 매수 블럭 채우기
    # ════════════════════════════════════════════════════════════
    def place_initial_orders(self):
        log("📋 초기 주문 배치...")

        sell_level_idx = None
        for i in range(len(self.grid_levels)):
            if self.grid_levels[i] > self.entry_price:
                sell_level_idx = i
                break

        if sell_level_idx is None:
            log(f"  ❌ 초기 포지션 배치 불가: 진입가보다 높은 레벨이 없음", 'ERROR')
            return
        if sell_level_idx == 0:
            log(f"  ❌ 초기 포지션 배치 불가: 진입가가 그리드 하단보다 낮음", 'ERROR')
            return

        buy_level_idx = sell_level_idx - 1
        buy_price = self.grid_levels[buy_level_idx]
        sell_price = self.grid_levels[sell_level_idx]

        if sell_price <= self.entry_price:
            log(f"  ❌ 매도가({format_price(sell_price)}) <= 진입가({format_price(self.entry_price)})", 'ERROR')
            return

        lv = self.levels[buy_level_idx]
        lv['state'] = self.FILLED
        lv['buy_price'] = self.entry_price
        lv['buy_qty'] = self.initial_qty
        lv['sell_price'] = sell_price

        spread = sell_price - self.entry_price
        spread_pct = (spread / self.entry_price) * 100
        log(f"  📦 초기보유 → Lv.{buy_level_idx} FILLED")
        log(f"     매수: {format_price(self.entry_price)}원 → 매도: {format_price(sell_price)}원")
        log(f"     스프레드: {format_price(spread)}원 ({spread_pct:.2f}%)")

        self._place_sell(buy_level_idx)
        self._fill_buys_below_price()

        filled = sum(1 for l in self.levels.values() if l['state'] == self.FILLED)
        pending = sum(1 for l in self.levels.values() if l['state'] == self.BUY_PENDING)
        log(f"📋 초기 배치 완료: 포지션 {filled}건, 대기매수 {pending}건")

    def _fill_buys_below_price(self):
        max_orders = CONFIG.get('MAX_BUY_ORDERS', 3)

        all_below_price = []
        for i in range(len(self.levels)):
            lv = self.levels[i]
            if lv['buy_price'] <= self.current_price:
                all_below_price.append((i, lv['buy_price'], lv['state']))

        if not all_below_price:
            return

        all_below_price.sort(key=lambda x: x[1], reverse=True)
        ideal_indices = set(idx for idx, _, _ in all_below_price[:max_orders])

        current_buy_orders = []
        for i in range(len(self.levels)):
            lv = self.levels[i]
            if lv['state'] == self.BUY_PENDING:
                current_buy_orders.append((i, lv['buy_price']))

        cancelled = 0
        for idx, price in current_buy_orders:
            if price > self.current_price:
                lv = self.levels[idx]
                if lv['buy_uuid']:
                    UpbitAPI.cancel_order(lv['buy_uuid'])
                    log(f"  ❎ Lv.{idx} 매수 취소 (현재가 {format_price(self.current_price)}원보다 높음)")
                self.cash += self.grid_unit
                lv['state'] = self.EMPTY
                lv['buy_uuid'] = None
                lv['buy_qty'] = 0
                cancelled += 1
            elif idx not in ideal_indices:
                lv = self.levels[idx]
                if lv['buy_uuid']:
                    UpbitAPI.cancel_order(lv['buy_uuid'])
                    log(f"  ❎ Lv.{idx} 매수 취소 (현재가에서 멀어짐)")
                self.cash += self.grid_unit
                lv['state'] = self.EMPTY
                lv['buy_uuid'] = None
                lv['buy_qty'] = 0
                cancelled += 1

        current_count = sum(1 for lv in self.levels.values() if lv['state'] == self.BUY_PENDING)
        if current_count >= max_orders:
            return

        slots_available = max_orders - current_count
        candidates = []
        for idx, price, state in all_below_price:
            if state == self.EMPTY and idx in ideal_indices:
                candidates.append((idx, price))
        candidates = candidates[:slots_available]

        if not candidates:
            return

        placed = 0
        skipped_low_cash = 0

        if cancelled > 0:
            log(f"  🔄 재조정: {cancelled}개 취소 → {len(candidates)}개 재배치")
        else:
            log(f"  📊 현재 매수 주문: {current_count}개 → {len(candidates)}개 추가 배치 (최대 {max_orders}개)")

        for idx, buy_price in candidates:
            lv = self.levels[idx]
            if self.cash < CONFIG['MIN_ORDER_AMOUNT']:
                skipped_low_cash += 1
                continue

            price = lv['buy_price']
            unit = min(self.grid_unit, self.cash)
            qty = round((unit * (1 - CONFIG['FEE_PCT'])) / price, 8)

            if qty * price < CONFIG['MIN_ORDER_AMOUNT']:
                skipped_low_cash += 1
                continue

            res = UpbitAPI.place_order(self.market, 'bid', price, qty, 'limit')
            if res and 'uuid' in res:
                lv['state'] = self.BUY_PENDING
                lv['buy_uuid'] = res['uuid']
                lv['buy_qty'] = qty
                self.cash -= unit
                placed += 1
                log(f"  🟢 Lv.{idx} 매수 배치: {format_price(price)}원 × {qty:.6f}")

        if placed > 0:
            final_count = current_count + placed
            log(f"  ✅ {placed}개 매수 주문 배치 완료 (총 {final_count}/{max_orders}개)")
        if skipped_low_cash > 0:
            log(f"  💰 잔고 부족으로 {skipped_low_cash}칸 스킵 (현금: {format_price(self.cash)}원)")

    def _place_sell(self, idx):
        lv = self.levels[idx]
        sell_price = lv['sell_price']
        buy_price = lv['buy_price']
        original_qty = lv['buy_qty']

        tick = get_tick_size(buy_price)
        if sell_price <= buy_price:
            log(f"  ❌ Lv.{idx} 매도 불가: 매도가({format_price(sell_price)}) <= 매수가({format_price(buy_price)})", 'ERROR')
            return

        if CONFIG['KEEP_PROFIT_COINS']:
            buy_amount = buy_price * original_qty
            sell_qty = round(buy_amount / sell_price, 8)
            profit_qty = original_qty - sell_qty

            if sell_qty * sell_price < CONFIG['MIN_ORDER_AMOUNT']:
                log(f"  ⚠️ Lv.{idx} 매도 스킵: 주문금액 부족", 'WARN')
                return

            res = UpbitAPI.place_order(self.market, 'ask', sell_price, sell_qty, 'limit')
            if res and 'uuid' in res:
                lv['sell_uuid'] = res['uuid']
                lv['sell_qty'] = sell_qty
                spread = sell_price - buy_price
                spread_pct = (spread / buy_price) * 100
                profit_value = profit_qty * sell_price
                log(f"  🔴 Lv.{idx} 매도 배치: {format_price(sell_price)}원 × {sell_qty:.6f} (원금 회수)")
                log(f"     원금: {format_price(buy_amount)}원 | 수익: {profit_qty:.6f}개 (≈{format_price(profit_value)}원 보유)")
                log(f"     스프레드: {format_price(spread)}원 ({spread_pct:.2f}%)")
            else:
                log(f"  ❌ Lv.{idx} 매도 배치 실패", 'ERROR')
        else:
            sell_qty = original_qty
            if sell_qty * sell_price < CONFIG['MIN_ORDER_AMOUNT']:
                log(f"  ⚠️ Lv.{idx} 매도 스킵: 주문금액 부족", 'WARN')
                return

            res = UpbitAPI.place_order(self.market, 'ask', sell_price, sell_qty, 'limit')
            if res and 'uuid' in res:
                lv['sell_uuid'] = res['uuid']
                lv['sell_qty'] = sell_qty
                spread = sell_price - buy_price
                spread_pct = (spread / buy_price) * 100
                log(f"  🔴 Lv.{idx} 매도 배치: {format_price(sell_price)}원 × {sell_qty:.6f} (전량)")
                log(f"     스프레드: {format_price(spread)}원 ({spread_pct:.2f}%)")
            else:
                log(f"  ❌ Lv.{idx} 매도 배치 실패", 'ERROR')

    def _check_orders_real(self):
        for i, lv in list(self.levels.items()):
            if lv['state'] == self.BUY_PENDING and lv['buy_uuid']:
                order = UpbitAPI.get_order(lv['buy_uuid'])
                if not order:
                    continue
                if order.get('state') == 'done':
                    lv['buy_qty'] = float(order.get('executed_volume', lv['buy_qty']))
                    lv['buy_price'] = float(order.get('avg_price', lv['buy_price']))
                    lv['state'] = self.FILLED
                    lv['buy_uuid'] = None
                    self.trade_count += 1
                    log(f"🟢 체결 Lv.{i}: {format_price(lv['buy_price'])}원 × {lv['buy_qty']:.6f}")
                    self.notifier.notify_trade('BUY', self.market, lv['buy_price'], lv['buy_qty'])
                    self._place_sell(i)
                elif order.get('state') == 'cancel':
                    self.cash += self.grid_unit
                    lv['state'] = self.EMPTY
                    lv['buy_uuid'] = None

            elif lv['state'] == self.FILLED and lv['sell_uuid']:
                order = UpbitAPI.get_order(lv['sell_uuid'])
                if not order:
                    continue
                if order.get('state') == 'done':
                    sell_p = float(order.get('avg_price', lv['sell_price']))
                    executed_qty = float(order.get('executed_volume', lv.get('sell_qty', lv['buy_qty'])))

                    buy_amount = lv['buy_price'] * lv['buy_qty']
                    revenue = sell_p * executed_qty * (1 - CONFIG['FEE_PCT'])

                    if CONFIG['KEEP_PROFIT_COINS']:
                        profit_qty = lv['buy_qty'] - executed_qty
                        profit_value = profit_qty * sell_p
                        if profit_qty > 0:
                            self.profit_coins += profit_qty
                            log(f"💎 수익 코인 누적: +{profit_qty:.6f}개 (≈{format_price(profit_value)}원) | 총 {self.profit_coins:.6f}개")
                        self.cash += revenue
                        self.total_profit += profit_value
                        self.trade_count += 1
                        log(f"🔴 체결 Lv.{i}: {format_price(sell_p)}원 × {executed_qty:.6f} → 원금 회수 {format_price(revenue)}원")
                        self.notifier.notify_trade('SELL', self.market, sell_p, executed_qty, profit_value)
                    else:
                        profit = revenue - buy_amount
                        self.cash += revenue
                        self.total_profit += profit
                        self.trade_count += 1
                        log(f"🔴 체결 Lv.{i}: {format_price(sell_p)}원 × {executed_qty:.6f} → {profit:+,.0f}원")
                        self.notifier.notify_trade('SELL', self.market, sell_p, executed_qty, profit)

                    lv['state'] = self.EMPTY
                    lv['sell_uuid'] = None
                    lv['buy_qty'] = 0
                    if 'sell_qty' in lv:
                        del lv['sell_qty']

    def _check_orders_sim(self):
        for i, lv in list(self.levels.items()):
            if lv['state'] == self.BUY_PENDING:
                if self.current_price <= lv['buy_price']:
                    lv['state'] = self.FILLED
                    lv['buy_uuid'] = None
                    self.trade_count += 1
                    log(f"🟢 [SIM] 체결 Lv.{i}: {format_price(lv['buy_price'])}원")
                    self.notifier.notify_trade('BUY', self.market, lv['buy_price'], lv['buy_qty'])
                    self._place_sell(i)

            elif lv['state'] == self.FILLED and lv['sell_uuid']:
                if self.current_price >= lv['sell_price']:
                    sell_qty = lv.get('sell_qty', lv['buy_qty'])
                    buy_amount = lv['buy_price'] * lv['buy_qty']
                    revenue = lv['sell_price'] * sell_qty * (1 - CONFIG['FEE_PCT'])

                    if CONFIG['KEEP_PROFIT_COINS']:
                        profit_qty = lv['buy_qty'] - sell_qty
                        profit_value = profit_qty * lv['sell_price']
                        if profit_qty > 0:
                            self.profit_coins += profit_qty
                            log(f"💎 [SIM] 수익 코인 누적: +{profit_qty:.6f}개 | 총 {self.profit_coins:.6f}개")
                        self.cash += revenue
                        self.total_profit += profit_value
                        self.trade_count += 1
                        log(f"🔴 [SIM] 체결 Lv.{i}: {format_price(lv['sell_price'])}원 × {sell_qty:.6f} → 원금 회수")
                        self.notifier.notify_trade('SELL', self.market, lv['sell_price'], sell_qty, profit_value)
                    else:
                        profit = revenue - buy_amount
                        self.cash += revenue
                        self.total_profit += profit
                        self.trade_count += 1
                        log(f"🔴 [SIM] 체결 Lv.{i}: {format_price(lv['sell_price'])}원 × {sell_qty:.6f} → {profit:+,.0f}원")
                        self.notifier.notify_trade('SELL', self.market, lv['sell_price'], sell_qty, profit)

                    lv['state'] = self.EMPTY
                    lv['sell_uuid'] = None
                    lv['buy_qty'] = 0
                    if 'sell_qty' in lv:
                        del lv['sell_qty']

    def check_orders(self):
        if CONFIG['ENABLE_REAL_TRADING']:
            self._check_orders_real()
        else:
            self._check_orders_sim()

    def refresh_grid(self):
        self._fill_buys_below_price()

    # ════════════════════════════════════════════════════════════
    # V8.1 신규: 손절/강제익절 체크 + 전량 청산
    # ════════════════════════════════════════════════════════════
    def check_hard_exit(self):
        """
        손절가 / 강제 익절가 도달 여부 체크.

        반환값:
          'STOP_LOSS'         — 손절가 도달 → 전량 청산 → 봇 완전 종료
          'HARD_TAKE_PROFIT'  — 강제 익절가 도달 → 전량 청산 → 재진입
          None                — 해당 없음
        """
        if self._hard_exit_triggered:
            return None

        # ── 손절 체크 (아래로 돌파) ──
        if self.stop_loss_price > 0 and self.current_price <= self.stop_loss_price:
            self._hard_exit_triggered = True
            sl_loss_pct = (self.current_price - self.entry_price) / self.entry_price * 100
            log(f"")
            log(f"{'━' * 55}")
            log(f"🔻 손절가 도달! {format_price(self.current_price)}원 ≤ {format_price(self.stop_loss_price)}원")
            log(f"   진입가: {format_price(self.entry_price)}원 | 손실: {sl_loss_pct:.2f}%")
            log(f"   → 전량 청산 후 봇 완전 종료")
            log(f"{'━' * 55}")
            return self._execute_full_liquidation('STOP_LOSS')

        # ── 강제 익절 체크 (위로 돌파) ──
        if self.hard_take_profit_price > 0 and self.current_price >= self.hard_take_profit_price:
            self._hard_exit_triggered = True
            tp_gain_pct = (self.current_price - self.entry_price) / self.entry_price * 100
            log(f"")
            log(f"{'━' * 55}")
            log(f"🔺 강제 익절가 도달! {format_price(self.current_price)}원 ≥ {format_price(self.hard_take_profit_price)}원")
            log(f"   진입가: {format_price(self.entry_price)}원 | 수익: +{tp_gain_pct:.2f}%")
            log(f"   → 전량 청산 후 재진입 대기")
            log(f"{'━' * 55}")
            return self._execute_full_liquidation('HARD_TAKE_PROFIT')

        return None

    def _execute_full_liquidation(self, liquidation_type):
        """
        전량 청산:
          1. 미체결 매수 주문 전량 취소
          2. 미체결 매도 주문 전량 취소
          3. 보유 코인 전량 시장가 매도
          4. 수익 코인 (profit_coins) 도 함께 매도
        """
        log(f"⚡ 전량 청산 시작 ({'손절' if liquidation_type == 'STOP_LOSS' else '강제 익절'})...")

        # ── 1. 모든 미체결 매수 주문 취소 ──
        cancelled_buy = 0
        for i, lv in self.levels.items():
            if lv['state'] == self.BUY_PENDING and lv['buy_uuid']:
                UpbitAPI.cancel_order(lv['buy_uuid'])
                self.cash += self.grid_unit
                lv['state'] = self.EMPTY
                lv['buy_uuid'] = None
                lv['buy_qty'] = 0
                cancelled_buy += 1
        if cancelled_buy:
            log(f"  ❎ 매수 주문 {cancelled_buy}건 취소")

        # ── 2. 모든 미체결 매도 주문 취소 ──
        cancelled_sell = 0
        for i, lv in self.levels.items():
            if lv['state'] == self.FILLED and lv['sell_uuid']:
                UpbitAPI.cancel_order(lv['sell_uuid'])
                lv['sell_uuid'] = None
                cancelled_sell += 1
        if cancelled_sell:
            log(f"  ❎ 매도 주문 {cancelled_sell}건 취소")

        # ── 3. 보유 코인 집계 ──
        grid_holding_qty = sum(lv['buy_qty'] for lv in self.levels.values() if lv['state'] == self.FILLED)
        total_holding_qty = grid_holding_qty + self.profit_coins

        log(f"  📦 보유: 그리드 {grid_holding_qty:.6f}개 + 수익코인 {self.profit_coins:.6f}개 = 총 {total_holding_qty:.6f}개")

        # ── 4. 전량 시장가 매도 ──
        actual_sell_price = self.current_price
        if total_holding_qty > 0:
            if CONFIG['ENABLE_REAL_TRADING']:
                log(f"  🔴 전량 시장가 매도 주문: {total_holding_qty:.6f}개")
                res = UpbitAPI.place_order(self.market, 'ask', 0, total_holding_qty, 'market')

                if res and 'uuid' in res:
                    time.sleep(1)
                    done = UpbitAPI.wait_order_done(res['uuid'], timeout=60, poll=0.5)
                    if done:
                        avg_price = float(done.get('avg_price', self.current_price))
                        executed_vol = float(done.get('executed_volume', total_holding_qty))
                        revenue = avg_price * executed_vol * (1 - CONFIG['FEE_PCT'])
                        actual_sell_price = avg_price

                        cost_basis = (self.entry_price or self.current_price) * total_holding_qty
                        profit = revenue - cost_basis

                        self.cash += revenue
                        self.total_profit += profit

                        log(f"  ✅ 청산 체결: {format_price(avg_price)}원 × {executed_vol:.6f}")
                        log(f"  💰 회수: {format_price(revenue)}원 | 손익: {profit:+,.0f}원")
                    else:
                        log(f"  ⚠️ 청산 주문 미체결 (타임아웃 60초)", 'WARN')
                else:
                    log(f"  ❌ 청산 주문 실패!", 'ERROR')
            else:
                # 시뮬레이션
                revenue = self.current_price * total_holding_qty * (1 - CONFIG['FEE_PCT'])
                cost_basis = (self.entry_price or self.current_price) * total_holding_qty
                profit = revenue - cost_basis
                self.cash += revenue
                self.total_profit += profit
                log(f"  ✅ [SIM] 청산: {format_price(self.current_price)}원 × {total_holding_qty:.6f} → {profit:+,.0f}원")
        else:
            log(f"  ℹ️ 보유 코인 없음 (그리드 운영 중 미체결 상태)")

        # ── 5. 상태 초기화 ──
        for lv in self.levels.values():
            lv['state'] = self.EMPTY
            lv['buy_qty'] = 0
            lv['buy_uuid'] = None
            lv['sell_uuid'] = None
            if 'sell_qty' in lv:
                del lv['sell_qty']
        self.profit_coins = 0.0
        self.trailing_mode = False

        runtime = str(datetime.now() - self.start_time).split('.')[0]
        log(f"⚡ 전량 청산 완료 | 총 손익: {self.total_profit:+,.0f}원 | 운행: {runtime}")

        self.notifier.notify_liquidation(
            market=self.market,
            reason=f"{'손절가' if liquidation_type == 'STOP_LOSS' else '강제 익절가'} {format_price(self.stop_loss_price if liquidation_type == 'STOP_LOSS' else self.hard_take_profit_price)}원 도달",
            total_profit=self.total_profit,
            runtime=runtime,
            liquidation_type=liquidation_type,
        )

        self.active = False
        return liquidation_type

    # ════════════════════════════════════════════════════════════
    # 그리드 이탈 확인 - 익절만
    # ════════════════════════════════════════════════════════════
    def check_boundary(self):
        if self.current_price > self.upper:
            if CONFIG['TRAILING_STOP_ENABLED'] and CONFIG['TRAILING_ACTIVATION'] == 'UPPER_BREAK':
                if not self.trailing_mode:
                    self.activate_trailing_mode()
                    return None
            else:
                log(f"📈 상단 돌파! {format_price(self.current_price)}원 > {format_price(self.upper)}원 → 익절")
                return 'TAKE_PROFIT'
        return None

    def check_take_profit_reduce(self):
        if not CONFIG.get('TAKE_PROFIT_REDUCE_ENABLED', False):
            return
        if self.take_profit_reduce_triggered:
            return
        if self.take_profit_reduce_line <= 0:
            return

        if self.current_price >= self.take_profit_reduce_line:
            self.take_profit_reduce_triggered = True
            gain_pct = (self.current_price / self.entry_price - 1) * 100

            log(f"📈 상승 라인 도달!")
            log(f"   진입가: {format_price(self.entry_price)}원")
            log(f"   현재가: {format_price(self.current_price)}원 (+{gain_pct:.2f}%)")

            old_amount = self.grid_unit
            self.grid_unit = self.grid_unit / 2

            log(f"💎 익절 준비 모드 활성화")
            log(f"   칸당 금액: {format_price(old_amount)}원 → {format_price(self.grid_unit)}원 (50% 축소)")

            cancelled = 0
            for i, lv in self.levels.items():
                if lv['state'] == self.BUY_PENDING and lv['buy_uuid']:
                    UpbitAPI.cancel_order(lv['buy_uuid'])
                    self.cash += old_amount
                    lv['state'] = self.EMPTY
                    lv['buy_uuid'] = None
                    lv['buy_qty'] = 0
                    cancelled += 1

            if cancelled > 0:
                log(f"   ❎ {cancelled}개 매수 주문 취소 완료")

            self.notifier.send(
                f"📈 <b>상승 라인 도달</b>\n"
                f"종목: {self.market}\n"
                f"진입: {format_price(self.entry_price)}원\n"
                f"현재: {format_price(self.current_price)}원 (+{gain_pct:.2f}%)\n"
                f"💎 칸당 금액: {format_price(old_amount)}원 → {format_price(self.grid_unit)}원\n"
                f"익절 준비 모드 활성화"
            )

    def activate_trailing_mode(self):
        self.trailing_mode = True
        self.trailing_high = self.current_price
        self.trailing_entry_price = self.current_price

        log(f"🎯 트레일링 스탑 활성화!")
        log(f"   진입가: {format_price(self.trailing_entry_price)}원")
        log(f"   추적 시작: {format_price(self.trailing_high)}원")
        log(f"   스탑 설정: 최고점 -{CONFIG['TRAILING_STOP_PCT'] * 100:.1f}%")

        cancelled_buy = 0
        cancelled_sell = 0

        for i, lv in self.levels.items():
            if lv['state'] == self.BUY_PENDING and lv['buy_uuid']:
                UpbitAPI.cancel_order(lv['buy_uuid'])
                self.cash += self.grid_unit
                lv['state'] = self.EMPTY
                lv['buy_uuid'] = None
                cancelled_buy += 1
            if lv['state'] == self.FILLED and lv['sell_uuid']:
                UpbitAPI.cancel_order(lv['sell_uuid'])
                lv['sell_uuid'] = None
                cancelled_sell += 1

        log(f"   📋 주문 취소: 매수 {cancelled_buy}건, 매도 {cancelled_sell}건")

        self.notifier.send(
            f"🎯 <b>트레일링 스탑 활성화</b>\n"
            f"종목: {self.market}\n"
            f"진입: {format_price(self.trailing_entry_price)}원\n"
            f"추적: {format_price(self.trailing_high)}원\n"
            f"스탑: 최고점 -{CONFIG['TRAILING_STOP_PCT'] * 100:.1f}%"
        )

    def check_trailing_stop(self):
        if not self.trailing_mode:
            return None

        if self.current_price > self.trailing_high:
            old_high = self.trailing_high
            self.trailing_high = self.current_price
            stop_price = self.trailing_high * (1 - CONFIG['TRAILING_STOP_PCT'])
            gain_from_entry = (self.trailing_high / self.trailing_entry_price - 1) * 100
            log(f"📈 최고점 갱신: {format_price(old_high)}원 → {format_price(self.trailing_high)}원 (+{gain_from_entry:.2f}%)")
            log(f"   스탑 라인: {format_price(stop_price)}원")

        stop_price = self.trailing_high * (1 - CONFIG['TRAILING_STOP_PCT'])

        if self.current_price <= stop_price:
            drawdown = (1 - self.current_price / self.trailing_high) * 100
            total_gain = (self.current_price / self.trailing_entry_price - 1) * 100

            log(f"🛑 트레일링 스탑 발동!")
            log(f"   최고점: {format_price(self.trailing_high)}원")
            log(f"   현재가: {format_price(self.current_price)}원 (-{drawdown:.2f}%)")
            log(f"   총 수익: +{total_gain:.2f}%")

            return self.execute_trailing_stop()

        return None

    def execute_trailing_stop(self):
        total_holding = sum(lv['buy_qty'] for lv in self.levels.values() if lv['state'] == self.FILLED)
        total_holding += self.profit_coins

        if total_holding == 0:
            log("⚠️ 보유 코인 없음, 익절 처리", 'WARN')
            self.trailing_mode = False
            return 'TAKE_PROFIT'

        if CONFIG['ENABLE_REAL_TRADING']:
            log(f"  🔴 전량 시장가 매도: {total_holding:.6f}개")
            res = UpbitAPI.place_order(self.market, 'ask', 0, total_holding, 'market')

            if res and 'uuid' in res:
                time.sleep(1)
                done = UpbitAPI.wait_order_done(res['uuid'], timeout=30, poll=0.5)

                if done:
                    avg_price = float(done.get('avg_price', self.current_price))
                    executed_vol = float(done.get('executed_volume', 0))
                    revenue = avg_price * executed_vol * (1 - CONFIG['FEE_PCT'])
                    total_gain = (avg_price / self.trailing_entry_price - 1) * 100
                    profit_value = revenue - (self.trailing_entry_price * total_holding)

                    self.cash += revenue
                    self.total_profit += profit_value

                    log(f"  ✅ 매도 체결: {format_price(avg_price)}원 × {executed_vol:.6f}")
                    log(f"  💰 수익: {format_price(profit_value)}원 (+{total_gain:.2f}%)")

                    self.notifier.send(
                        f"🛑 <b>트레일링 스탑 체결</b>\n"
                        f"종목: {self.market}\n"
                        f"진입: {format_price(self.trailing_entry_price)}원\n"
                        f"최고: {format_price(self.trailing_high)}원\n"
                        f"매도: {format_price(avg_price)}원\n"
                        f"수익: {format_price(profit_value)}원 (+{total_gain:.2f}%)"
                    )
        else:
            revenue = self.current_price * total_holding
            profit_value = revenue - (self.trailing_entry_price * total_holding)
            total_gain = (self.current_price / self.trailing_entry_price - 1) * 100
            self.cash += revenue
            self.total_profit += profit_value
            log(f"  ✅ [SIM] 매도: {format_price(self.current_price)}원 × {total_holding:.6f}")
            log(f"  💰 수익: {format_price(profit_value)}원 (+{total_gain:.2f}%)")

        for lv in self.levels.values():
            lv['state'] = self.EMPTY
            lv['buy_qty'] = 0

        self.profit_coins = 0
        self.trailing_mode = False

        return 'TAKE_PROFIT'

    def check_rotation(self):
        if self.mode == 'MANUAL':
            return None

        now = time.time()
        if now - self.last_rotation_scan < CONFIG['ROTATION_SCAN_INTERVAL']:
            return None

        self.last_rotation_scan = now
        log(f"🔍 정기 종목 스캔 (매 {CONFIG['ROTATION_SCAN_INTERVAL'] // 60}분)...")

        if not self.entry_price or self.current_price <= self.entry_price:
            pnl_pct = ((self.current_price - self.entry_price) / self.entry_price * 100) if self.entry_price else 0
            log(f"  ↳ 현재 손실 중 ({pnl_pct:+.2f}%) → 교체 스킵")
            return None

        pnl_pct = (self.current_price - self.entry_price) / self.entry_price * 100
        log(f"  ↳ 현재 수익 중 ({pnl_pct:+.2f}%) → 더 좋은 종목 탐색...")

        cur_ticker = UpbitAPI.get_ticker(self.market)
        if cur_ticker and isinstance(cur_ticker, list) and len(cur_ticker) > 0:
            regime, _ = SmartPicker.detect_market_regime()
            cur_score, _, cur_reason = SmartPicker.score_market(self.market, cur_ticker[0], regime)
            self.current_score = cur_score

        best = SmartPicker.find_best()
        if not best:
            return None

        best_market = best['market']
        best_score = best['score']

        if best_market == self.market:
            log(f"  ↳ 현재 종목이 여전히 1위 ({best_score:.1f}점) → 유지")
            return None

        if best_score > self.current_score:
            sym_cur = self.market.replace('KRW-', '')
            sym_new = best_market.replace('KRW-', '')
            log(f"  🔄 교체 감지! {sym_cur}({self.current_score:.1f}점) → {sym_new}({best_score:.1f}점)")
            self.notifier.send(
                f"🔄 <b>종목 교체 감지</b>\n"
                f"현재: {sym_cur} ({self.current_score:.1f}점, {pnl_pct:+.2f}%)\n"
                f"교체: {sym_new} ({best_score:.1f}점)\n"
                f"→ 수익 실현 후 교체 진행"
            )
            return 'ROTATION'
        else:
            log(f"  ↳ 대안({best_market}: {best_score:.1f}점) ≤ 현재({self.current_score:.1f}점) → 유지")
            return None

    def exit_all(self, reason):
        """
        기존 익절: 주문만 취소, 보유 코인 유지
        """
        log(f"⏹️ 익절 처리 시작: {reason}")

        cancelled_buy = 0
        for i, lv in self.levels.items():
            if lv['state'] == self.BUY_PENDING and lv['buy_uuid']:
                UpbitAPI.cancel_order(lv['buy_uuid'])
                self.cash += self.grid_unit
                lv['state'] = self.EMPTY
                lv['buy_uuid'] = None
                cancelled_buy += 1
                log(f"  ❎ Lv.{i} 매수 주문 취소")

        cancelled_sell = 0
        for i, lv in self.levels.items():
            if lv['state'] == self.FILLED and lv['sell_uuid']:
                UpbitAPI.cancel_order(lv['sell_uuid'])
                lv['sell_uuid'] = None
                cancelled_sell += 1
                log(f"  ❎ Lv.{i} 매도 주문 취소")

        total_holding_qty = sum(lv['buy_qty'] for lv in self.levels.values() if lv['state'] == self.FILLED)
        total_holding_value = total_holding_qty * self.current_price

        unrealized_profit = 0
        for i, lv in self.levels.items():
            if lv['state'] == self.FILLED:
                current_value = self.current_price * lv['buy_qty']
                cost = lv['buy_price'] * lv['buy_qty']
                unrealized_profit += (current_value - cost)

        self.total_profit += unrealized_profit

        if total_holding_qty > 0:
            log(f"  💎 보유 코인 유지: {total_holding_qty:.6f}개 (평가금액: {format_price(total_holding_value)}원)")
            log(f"  💰 평가 손익: {unrealized_profit:+,.0f}원")

        for lv in self.levels.values():
            if lv['state'] == self.BUY_PENDING:
                lv['state'] = self.EMPTY
            lv['buy_uuid'] = None
            lv['sell_uuid'] = None

        runtime = str(datetime.now() - self.start_time).split('.')[0]
        log(f"⏹️ 익절 완료 | 취소: 매수 {cancelled_buy}건, 매도 {cancelled_sell}건")
        log(f"   💎 보유 코인: {total_holding_qty:.6f}개 + 수익 {self.profit_coins:.6f}개")
        log(f"   손익: {self.total_profit:+,.0f}원 | 거래: {self.trade_count}건 | {runtime}")

        self.notifier.notify_exit(self.market, reason, self.total_profit, runtime)
        self.active = False

    # ════════════════════════════════════════════════════════════
    # 유틸리티
    # ════════════════════════════════════════════════════════════
    def _get_price_level(self):
        for i in range(len(self.levels)):
            if self.current_price < self.grid_levels[i + 1]:
                return i
        return len(self.levels)

    def get_total_value(self):
        coin_val = sum(lv['buy_qty'] * self.current_price
                       for lv in self.levels.values() if lv['state'] == self.FILLED)
        pending_val = sum(self.grid_unit
                          for lv in self.levels.values() if lv['state'] == self.BUY_PENDING)
        return self.cash + coin_val + pending_val

    def get_unrealized(self):
        unr = 0
        for lv in self.levels.values():
            if lv['state'] == self.FILLED and lv['buy_qty'] > 0:
                unr += (self.current_price * lv['buy_qty'] * (1 - CONFIG['FEE_PCT'])) - (
                    lv['buy_price'] * lv['buy_qty'])
        return unr

    def update_price(self):
        ticker = UpbitAPI.get_ticker(self.market)
        if ticker and isinstance(ticker, list) and len(ticker) > 0:
            self.current_price = ticker[0]['trade_price']
            return True
        return False

    def generate_report(self):
        total = self.get_total_value()
        pnl = total - self.capital
        return {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'market': self.market,
            'current_price': self.current_price,
            'entry_price': self.entry_price or 0,
            'price_change': (
                (self.current_price - self.entry_price) / self.entry_price * 100) if self.entry_price else 0,
            'total_value': total,
            'total_pnl': pnl,
            'total_pnl_pct': (pnl / self.capital * 100) if self.capital else 0,
            'realized': self.total_profit,
            'unrealized': self.get_unrealized(),
            'trades': self.trade_count,
            'pending': sum(1 for l in self.levels.values() if l['state'] == self.BUY_PENDING),
            'positions': sum(1 for l in self.levels.values() if l['state'] == self.FILLED),
            'cash': self.cash,
            'runtime': str(datetime.now() - self.start_time).split('.')[0],
        }

    def maybe_send_report(self):
        now = time.time()
        if now - self.last_report_time >= CONFIG['REPORT_INTERVAL']:
            self.notifier.notify_report(self.generate_report())
            self.last_report_time = now
            log("📊 성과 보고서 발송")

    def print_status(self):
        total = self.get_total_value()
        pnl = total - self.capital
        pct = (pnl / self.capital * 100) if self.capital else 0
        rt = str(datetime.now() - self.start_time).split('.')[0]

        filled = sum(1 for l in self.levels.values() if l['state'] == self.FILLED)
        pending = sum(1 for l in self.levels.values() if l['state'] == self.BUY_PENDING)
        empty = sum(1 for l in self.levels.values() if l['state'] == self.EMPTY)
        plvl = self._get_price_level()

        print(f"\n{'─' * 55}")

        # 손절/익절가 표시
        sl = self.stop_loss_price
        htp = self.hard_take_profit_price
        if sl > 0 or htp > 0:
            if sl > 0:
                sl_dist = (self.current_price - sl) / self.current_price * 100
                print(f"🔻 손절가: {format_price(sl)}원 (현재 -{sl_dist:.2f}% 위)")
            if htp > 0:
                htp_dist = (htp - self.current_price) / self.current_price * 100
                print(f"🔺 강제익절가: {format_price(htp)}원 (목표까지 +{htp_dist:.2f}%)")
            print(f"{'─' * 55}")

        if self.take_profit_reduce_triggered:
            print(f"💎 익절 준비 모드 | 칸당: {format_price(self.grid_unit)}원 (50% 축소)")
            print(f"{'─' * 55}")

        if self.trailing_mode:
            stop_price = self.trailing_high * (1 - CONFIG['TRAILING_STOP_PCT'])
            gain = (self.current_price / self.trailing_entry_price - 1) * 100
            print(f"🎯 TRAILING MODE | 최고: {format_price(self.trailing_high)}원 | 스탑: {format_price(stop_price)}원")
            print(f"   진입: {format_price(self.trailing_entry_price)}원 | 수익: +{gain:.2f}%")
            print(f"{'─' * 55}")

        print(f"📊 {self.market} | {format_price(self.current_price)}원 (Lv.{plvl}) | {rt}")
        print(f"   💰 평가: {format_price(total)}원 ({pnl:+,.0f}원, {pct:+.2f}%)")
        print(f"   📈 실현: {self.total_profit:+,.0f}원 | 거래: {self.trade_count}건")
        print(f"   📋 FILLED:{filled} | BUY:{pending} | EMPTY:{empty} | 현금:{self.cash:,.0f}원")

        if not self.trailing_mode:
            for i in range(len(self.levels) - 1, -1, -1):
                lv = self.levels[i]
                st = lv['state']
                marker = "◀ NOW" if i == plvl else ""
                if st == self.FILLED:
                    sym = "🟦"
                elif st == self.BUY_PENDING:
                    sym = "🟩"
                else:
                    sym = "⬜"
                print(
                    f"   {sym} Lv.{i:>2d} {format_price(self.grid_levels[i]):>10s} ~ {format_price(self.grid_levels[i + 1]):>10s} {marker}")
        else:
            print(f"   🎯 트레일링 모드: 최고점 추적 중...")

        print(f"{'─' * 55}")

    def _print_grid(self):
        mode_emoji = '🎯' if self.mode == 'MANUAL' else '🤖'
        mode_text = '수동 선택' if self.mode == 'MANUAL' else '자동 선정'

        actual_grids = len(self.levels)
        target_grids = self.grid_count

        print(f"\n{'=' * 55}")
        print(f"{mode_emoji} Grid Bot V8.1 | {'실전' if CONFIG['ENABLE_REAL_TRADING'] else '시뮬레이션'} | {mode_text}")
        print(f"{'=' * 55}")
        print(f"  🎯 {self.market} | 진입: {format_price(self.entry_price)}원")
        print(f"  📝 {self.reason}")
        print(f"  📏 {format_price(self.lower)} ~ {format_price(self.upper)} (±{self.range_pct * 100:.1f}%)")

        # 손절/익절가 표시
        sl = self.stop_loss_price
        htp = self.hard_take_profit_price
        if sl > 0:
            sl_pct = (sl / self.entry_price - 1) * 100
            print(f"  🔻 손절가: {format_price(sl)}원 ({sl_pct:+.1f}%) → 전량 청산 + 봇 종료")
        if htp > 0:
            htp_pct = (htp / self.entry_price - 1) * 100
            print(f"  🔺 강제 익절가: {format_price(htp)}원 ({htp_pct:+.1f}%) → 전량 청산 + 재진입")

        if actual_grids < target_grids:
            print(f"  📐 {actual_grids}칸 (목표: {target_grids}칸) | 칸당 {format_price(self.grid_unit)}원 | 총 {format_price(self.capital)}원")
        else:
            print(f"  📐 {actual_grids}칸 | 칸당 {format_price(self.grid_unit)}원 | 총 {format_price(self.capital)}원")

        print(f"{'─' * 55}")
        for i, p in enumerate(self.grid_levels):
            tag = " ◀ 진입" if i > 0 and self.grid_levels[i - 1] <= self.entry_price < p else ""
            print(f"  Lv.{i:>2d}: {format_price(p):>10s}원{tag}")
        print(f"{'=' * 55}\n")


# ============================================================================
# 🚀 메인 루프
# ============================================================================
def run_bot_cycle(target, grid_amount, grid_count):
    if grid_amount < CONFIG['MIN_ORDER_AMOUNT']:
        log(f"❌ 그리드당 금액({format_price(grid_amount)}원) < 최소주문({CONFIG['MIN_ORDER_AMOUNT']}원)!", 'ERROR')
        return 'LOW_CAPITAL', 0, grid_amount * grid_count

    available_cash = None
    if CONFIG['ENABLE_REAL_TRADING']:
        krw_balance = UpbitAPI.get_account_balance('KRW')
        if krw_balance:
            available_cash = krw_balance['balance']
            log(f"💰 실제 KRW 잔고: {format_price(available_cash)}원")
        else:
            log("⚠️ KRW 잔고 조회 실패, 설정값 사용", 'WARN')

    total_capital = grid_amount * grid_count

    if available_cash is not None and available_cash < total_capital:
        log(f"💡 현재 잔고: {format_price(available_cash)}원 (목표: {format_price(total_capital)}원)")
        log(f"   → 현재가 아래 3개씩만 매수하므로 문제없이 운영 가능")

    bot = GridTradingBot(target, grid_amount, grid_count, available_cash)

    if not bot.execute_initial_buy():
        log("초기 매수 실패", 'ERROR')
        return 'BUY_FAIL', 0, total_capital

    if not bot.build_grid():
        log("그리드 구성 실패", 'ERROR')
        return 'GRID_FAIL', 0, total_capital

    bot.place_initial_orders()
    bot.notifier.notify_start({
        'market': bot.market, 'entry_price': bot.entry_price,
        'init_qty': bot.initial_qty, 'init_cost': bot.initial_cost,
        'lower': bot.lower, 'upper': bot.upper, 'reason': bot.reason,
        'grid_count': len(bot.levels),
        'target_grids': grid_count,
        'levels': bot.grid_levels,
        'regime': target.get('regime', ''), 'score': target.get('score', 0),
        'range_pct': bot.range_pct,
        'mode': bot.mode,
    })

    last_status = time.time()
    log("🔄 그리드 운영 시작")

    try:
        while bot.active:
            time.sleep(CONFIG['POLL_INTERVAL'])

            if not bot.update_price():
                time.sleep(3)
                continue

            bot.check_orders()

            # ── V8.1: 손절/강제익절 체크 (최우선) ──────────────────
            hard_exit = bot.check_hard_exit()
            if hard_exit:
                report = bot.generate_report()
                bot.notifier.notify_report(report)
                return hard_exit, bot.total_profit, bot.cash
            # ────────────────────────────────────────────────────────

            bot.check_take_profit_reduce()

            if bot.trailing_mode:
                trailing_result = bot.check_trailing_stop()
                if trailing_result:
                    report = bot.generate_report()
                    bot.notifier.notify_report(report)
                    return trailing_result, bot.total_profit, bot.cash

            boundary = bot.check_boundary()
            if boundary:
                report = bot.generate_report()
                bot.notifier.notify_report(report)
                reason_str = "상단 돌파 익절"
                bot.exit_all(reason_str)
                return boundary, bot.total_profit, bot.cash

            rotation = bot.check_rotation()
            if rotation == 'ROTATION':
                report = bot.generate_report()
                bot.notifier.notify_report(report)
                bot.exit_all("더 높은 점수 종목으로 교체")
                return 'ROTATION', bot.total_profit, bot.cash

            bot.refresh_grid()
            bot.maybe_send_report()

            if time.time() - last_status >= CONFIG['STATUS_INTERVAL']:
                bot.print_status()
                last_status = time.time()

    except KeyboardInterrupt:
        log("\n⚠️ Ctrl+C 감지 → 프로그램 종료 (주문 유지)", 'WARN')
        raise

    return 'MANUAL', bot.total_profit, bot.cash


def main():
    print(r"""
    ╔══════════════════════════════════════════╗
    ║   Upbit Smart Grid Bot V8.1             ║
    ║   손절/익절 전량 청산 기능 추가           ║
    ╚══════════════════════════════════════════╝
    """)

    # 모드 선택
    print("\n운영 모드를 선택하세요:")
    print("  1) AUTO - 시장 분석 기반 자동 종목 선정")
    print("  2) MANUAL - 종목과 범위 직접 선택")
    while True:
        mode_choice = input("\n선택 (1 또는 2): ").strip()
        if mode_choice == '1':
            CONFIG['SELECTION_MODE'] = 'AUTO'
            break
        elif mode_choice == '2':
            CONFIG['SELECTION_MODE'] = 'MANUAL'
            break
        else:
            print("❌ 1 또는 2를 입력해주세요.")

    # 매도 방식 선택
    print("\n매도 방식을 선택하세요:")
    print("  1) 원금만 회수 - 수익은 코인으로 보유 (복리 효과)")
    print("  2) 전량 매도 - 모든 코인 매도하여 현금 회수")
    while True:
        sell_choice = input("\n선택 (1 또는 2): ").strip()
        if sell_choice == '1':
            CONFIG['KEEP_PROFIT_COINS'] = True
            print("✅ 원금만 회수 모드")
            break
        elif sell_choice == '2':
            CONFIG['KEEP_PROFIT_COINS'] = False
            print("✅ 전량 매도 모드")
            break
        else:
            print("❌ 1 또는 2를 입력해주세요.")

    # 트레일링 스탑 선택
    print("\n트레일링 스탑을 사용하시겠습니까?")
    print("  1) 사용 (추천)")
    print("  2) 사용 안 함 (상단 돌파 시 즉시 익절)")
    while True:
        trail_choice = input("\n선택 (1 또는 2): ").strip()
        if trail_choice == '1':
            CONFIG['TRAILING_STOP_ENABLED'] = True
            print("\n트레일링 스탑 하락률을 선택하세요:")
            print("  1) 3% (빠른 매도)")
            print("  2) 5% (균형형, 추천)")
            print("  3) 7% (긴 호흡)")
            while True:
                pct_choice = input("\n선택 (1, 2, 또는 3): ").strip()
                if pct_choice == '1':
                    CONFIG['TRAILING_STOP_PCT'] = 0.03
                    print("✅ 트레일링 스탑: 최고점 -3%")
                    break
                elif pct_choice == '2':
                    CONFIG['TRAILING_STOP_PCT'] = 0.05
                    print("✅ 트레일링 스탑: 최고점 -5%")
                    break
                elif pct_choice == '3':
                    CONFIG['TRAILING_STOP_PCT'] = 0.07
                    print("✅ 트레일링 스탑: 최고점 -7%")
                    break
                else:
                    print("❌ 1, 2, 또는 3을 입력해주세요.")
            break
        elif trail_choice == '2':
            CONFIG['TRAILING_STOP_ENABLED'] = False
            print("✅ 트레일링 스탑 비활성화")
            break
        else:
            print("❌ 1 또는 2를 입력해주세요.")

    # 상승 라인 선택
    print("\n상승 라인을 설정하시겠습니까?")
    print("  1) 설정")
    print("  2) 설정 안 함")
    while True:
        tp_choice = input("\n선택 (1 또는 2): ").strip()
        if tp_choice == '1':
            CONFIG['TAKE_PROFIT_REDUCE_ENABLED'] = True
            while True:
                try:
                    price_input = input("\n상승 라인 가격을 입력하세요 (예: 2500): ").strip()
                    tp_price = float(price_input)
                    if tp_price <= 0:
                        print("❌ 0보다 큰 가격을 입력해주세요.")
                        continue
                    CONFIG['TAKE_PROFIT_REDUCE_PRICE'] = tp_price
                    print(f"✅ 상승 라인: {format_price(tp_price)}원")
                    break
                except ValueError:
                    print("❌ 숫자를 입력해주세요.")
            break
        elif tp_choice == '2':
            CONFIG['TAKE_PROFIT_REDUCE_ENABLED'] = False
            CONFIG['TAKE_PROFIT_REDUCE_PRICE'] = 0
            print("✅ 상승 라인 미설정")
            break
        else:
            print("❌ 1 또는 2를 입력해주세요.")

    # ── V8.1 신규: 손절가 설정 ────────────────────────────────────────
    print("\n" + "=" * 55)
    print("🔻 손절가를 설정하시겠습니까?")
    print("   설정 가격 이하 도달 시: 전량 시장가 청산 → 봇 완전 종료")
    print("  1) 설정")
    print("  2) 설정 안 함")
    while True:
        sl_choice = input("\n선택 (1 또는 2): ").strip()
        if sl_choice == '1':
            while True:
                try:
                    sl_input = input("\n손절가를 입력하세요 (예: 1800): ").strip()
                    sl_price = float(sl_input)
                    if sl_price <= 0:
                        print("❌ 0보다 큰 가격을 입력해주세요.")
                        continue
                    CONFIG['STOP_LOSS_PRICE'] = sl_price
                    print(f"✅ 손절가: {format_price(sl_price)}원 (도달 시 전량 청산 → 봇 종료)")
                    break
                except ValueError:
                    print("❌ 숫자를 입력해주세요.")
            break
        elif sl_choice == '2':
            CONFIG['STOP_LOSS_PRICE'] = 0
            print("✅ 손절가 미설정")
            break
        else:
            print("❌ 1 또는 2를 입력해주세요.")

    # ── V8.1 신규: 강제 익절가 설정 ──────────────────────────────────
    print("\n🔺 강제 익절가를 설정하시겠습니까?")
    print("   설정 가격 이상 도달 시: 전량 시장가 청산 → 그리드 재진입")
    print("  (기존 상단 돌파 익절과 다름: 코인 보유 X, 완전 청산 후 재시작)")
    print("  1) 설정")
    print("  2) 설정 안 함")
    while True:
        htp_choice = input("\n선택 (1 또는 2): ").strip()
        if htp_choice == '1':
            while True:
                try:
                    htp_input = input("\n강제 익절가를 입력하세요 (예: 2800): ").strip()
                    htp_price = float(htp_input)
                    if htp_price <= 0:
                        print("❌ 0보다 큰 가격을 입력해주세요.")
                        continue
                    CONFIG['HARD_TAKE_PROFIT_PRICE'] = htp_price
                    print(f"✅ 강제 익절가: {format_price(htp_price)}원 (도달 시 전량 청산 → 재진입)")
                    break
                except ValueError:
                    print("❌ 숫자를 입력해주세요.")
            break
        elif htp_choice == '2':
            CONFIG['HARD_TAKE_PROFIT_PRICE'] = 0
            print("✅ 강제 익절가 미설정")
            break
        else:
            print("❌ 1 또는 2를 입력해주세요.")

    print("=" * 55)

    mode = "🔴 실전" if CONFIG['ENABLE_REAL_TRADING'] else "🟡 시뮬레이션"
    mode_text = "🤖 자동 선정" if CONFIG['SELECTION_MODE'] == 'AUTO' else "🎯 수동 선택"
    total_capital = CONFIG['GRID_AMOUNT'] * CONFIG['GRID_COUNT']

    log(f"모드: {mode} | {mode_text}")
    log(f"그리드당 금액: {CONFIG['GRID_AMOUNT']:,.0f}원 | 그리드 수: {CONFIG['GRID_COUNT']}칸 | 총 투자금: {total_capital:,.0f}원")
    log(f"매도: {'원금만 회수' if CONFIG['KEEP_PROFIT_COINS'] else '전량 매도'} | 트레일링: {'ON' if CONFIG['TRAILING_STOP_ENABLED'] else 'OFF'}")

    sl = CONFIG.get('STOP_LOSS_PRICE', 0)
    htp = CONFIG.get('HARD_TAKE_PROFIT_PRICE', 0)
    if sl > 0:
        log(f"🔻 손절가: {format_price(sl)}원 → 전량 청산 후 봇 완전 종료")
    if htp > 0:
        log(f"🔺 강제 익절가: {format_price(htp)}원 → 전량 청산 후 재진입")

    if CONFIG['ENABLE_REAL_TRADING']:
        if not UpbitAPI.get_accounts():
            log("❌ API 인증 실패!", 'ERROR')
            return
        log("✅ API 인증 성공")

    notifier = TelegramNotifier()
    session_profit = 0
    cycle = 0
    target = None

    try:
        while True:
            cycle += 1
            log(f"\n{'═' * 55}")
            log(f"🔄 사이클 #{cycle} | 칸당 {CONFIG['GRID_AMOUNT']:,.0f}원 × {CONFIG['GRID_COUNT']}칸 = {total_capital:,.0f}원 | 누적손익: {session_profit:+,.0f}원")
            log(f"{'═' * 55}")

            if target is None:
                if CONFIG['SELECTION_MODE'] == 'AUTO':
                    target = SmartPicker.find_best()
                    if not target:
                        log("적합한 종목 없음, 60초 후 재스크리닝...")
                        time.sleep(60)
                        continue
                else:
                    target = manual_select_target()
                    if not target:
                        log("종목 선택 취소, 재시작...")
                        continue

            exit_reason, profit, remaining_cash = run_bot_cycle(target, CONFIG['GRID_AMOUNT'], CONFIG['GRID_COUNT'])
            session_profit += profit

            log(f"사이클 #{cycle} 종료: {exit_reason} | 손익: {profit:+,.0f}원 | 잔금: {format_price(remaining_cash)}원")

            # ── V8.1: 손절 → 완전 종료 ──────────────────────────────
            if exit_reason == 'STOP_LOSS':
                log(f"🔻 손절가 청산 완료 → 봇 완전 종료")
                log(f"   누적 손익: {session_profit:+,.0f}원")
                notifier.send(
                    f"⛔ <b>봇 완전 종료</b>\n"
                    f"사유: 손절가 도달 청산\n"
                    f"누적 손익: {session_profit:+,.0f}원\n"
                    f"총 사이클: {cycle}회"
                )
                break  # 봇 루프 탈출 → 완전 종료

            # ── V8.1: 강제 익절 → 재진입 ────────────────────────────
            if exit_reason == 'HARD_TAKE_PROFIT':
                log(f"🔺 강제 익절 청산 완료 → {CONFIG['COOLDOWN_AFTER_EXIT']}초 후 재진입...")
                notifier.send(
                    f"🔁 <b>강제 익절 후 재진입 대기</b>\n"
                    f"종목: {target['market'] if target else '?'}\n"
                    f"누적 손익: {session_profit:+,.0f}원\n"
                    f"재진입까지: {CONFIG['COOLDOWN_AFTER_EXIT']}초"
                )
                target = None  # 다음 루프에서 종목 재선택
                time.sleep(CONFIG['COOLDOWN_AFTER_EXIT'])
                continue

            if exit_reason == 'BUY_FAIL' or exit_reason == 'GRID_FAIL':
                log("30초 후 재시도...")
                time.sleep(30)
                continue

            if exit_reason == 'LOW_CAPITAL':
                log("❌ 자본 부족으로 봇을 종료합니다.", 'ERROR')
                break

            if exit_reason == 'ROTATION':
                log("🔄 종목 교체 → 즉시 재스크리닝...")
                target = None
                time.sleep(3)
                continue

            # MANUAL 모드 처리
            if CONFIG['SELECTION_MODE'] == 'MANUAL':
                if exit_reason == 'TAKE_PROFIT':
                    sym = target['market'].replace('KRW-', '')
                    log(f"🟢 익절 완료 → {sym} 같은 조건으로 자동 재진입...")
                    notifier.send(
                        f"🔁 <b>자동 재진입</b> [MANUAL]\n"
                        f"종목: {target['market']}\n"
                        f"사유: 익절 후 재진입"
                    )
                    time.sleep(CONFIG['COOLDOWN_AFTER_EXIT'])
                    continue
                else:
                    print("\n" + "=" * 55)
                    print("다시 진행하시겠습니까?")
                    print("  1) 계속 (새 종목 선택)")
                    print("  2) 종료")
                    choice = input("\n선택 (1 또는 2): ").strip()
                    if choice != '1':
                        log("사용자 선택으로 봇을 종료합니다.")
                        break
                    target = None
                    continue

            # AUTO 모드 처리
            target = None
            log(f"⏳ {CONFIG['COOLDOWN_AFTER_EXIT']}초 후 재진입 스크리닝...")
            time.sleep(CONFIG['COOLDOWN_AFTER_EXIT'])

    except KeyboardInterrupt:
        log("\n⚠️ 프로그램 종료 요청")

    finally:
        cleanup_all()

    log(f"\n📊 최종 결산: 총 {cycle} 사이클 | 누적 손익: {session_profit:+,.0f}원")
    print("프로그램을 종료합니다. 👋")


if __name__ == '__main__':
    main()