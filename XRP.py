#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upbit Grid Trading Bot V8.2
━━━━━━━━━━━━━━━━━━━━━━━━━━━
[핵심 로직]
1. 수동 종목 선택 (MANUAL 모드)
2. 비대칭 그리드 (ASYMMETRIC_GRID)
3. 그리드당 금액 설정 방식
4. 지정가 1칸분 매수 → 체결가 기준 그리드 고정 생성
5. 계단식 매수 블럭 채우기 (현재가 아래 TOP 3)
6. 매도 방식: 원금만 회수 / 전량 매도
7. 매도 전략: GRID / TARGET / AVG_PLUS_ONE / TOP_FIXED
8. 손절가 (STOP_LOSS_PRICE): 전량 청산 → 봇 완전 종료
9. 강제 익절가 (HARD_TAKE_PROFIT_PRICE): 전량 청산 → 재진입
10. 그리드 상단 돌파 시 즉시 익절
11. 30분마다 텔레그램 성과 보고서
12. 프로그램 종료 시 모든 주문 유지
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

TELEGRAM_CONFIG = {
    'ENABLED': True,
    'BOT_TOKEN': '8521289560:AAEZA0Y8kW4JmCALP8VquSFjqGP4VwrPAUc',
    'CHAT_ID': '2017077172',
}

CONFIG = {
    'ENABLE_REAL_TRADING': True,

    'GRID_AMOUNT': 20000.0,
    'GRID_COUNT': 40,
    'MAX_BUY_ORDERS': 3,
    'KEEP_PROFIT_COINS': True,

    # ── 매도 전략 ───────────────────────────────────────────────────
    'SELL_MODE': 'GRID',
    'SELL_TARGET_PRICE': 0,

    # ── 비대칭 그리드 설정 ──
    'ASYMMETRIC_GRID': False,
    'GRID_RANGE_DOWN': 0.10,
    'GRID_RANGE_UP': 0.075,

    # ── 손절/익절 설정 ───────────────────────────────────────────────
    'STOP_LOSS_PRICE': 0,
    'HARD_TAKE_PROFIT_PRICE': 0,

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
        actual_grids = data.get('grid_count', 0)
        target_grids = data.get('target_grids', actual_grids)

        sell_mode_str = CONFIG.get('SELL_MODE', 'GRID')
        if sell_mode_str == 'TARGET':
            sell_mode_str += f" (목표가 {format_price(CONFIG.get('SELL_TARGET_PRICE', 0))}원)"

        msg = (
            f"🎯 <b>그리드 봇 진입</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎯 종목: {data['market']}\n"
            f"💰 진입가: {format_price(data['entry_price'])}원\n"
            f"📦 초기매수: {data['init_qty']:.6f}개 ({format_price(data['init_cost'])}원)\n"
            f"📊 범위: {format_price(data['lower'])} ~ {format_price(data['upper'])} (±{data.get('range_pct', 0) * 100:.1f}%)\n"
            f"💹 매도전략: {sell_mode_str}\n"
            f"📝 사유: {data['reason']}\n"
            f"━━━━━━━━━━━━━━\n"
        )

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
        else:
            msg += f"📐 그리드: {actual_grids}칸\n"
        msg += grid_detail
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
        """전량 청산 알림 (손절/강제익절/목표가 전용)"""
        if liquidation_type == 'STOP_LOSS':
            emoji = "🔻"
            title = "손절 청산"
        elif liquidation_type == 'TARGET_PRICE_EXIT':
            emoji = "🎯"
            title = "목표가 달성 청산"
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

        # ── 손절/강제익절 설정 ──────────────────────────────────────
        self.stop_loss_price = CONFIG.get('STOP_LOSS_PRICE', 0)
        self.hard_take_profit_price = CONFIG.get('HARD_TAKE_PROFIT_PRICE', 0)
        self._hard_exit_triggered = False
        self._sell_target_triggered = False

        if self.stop_loss_price > 0:
            log(f"🔻 손절가 설정: {format_price(self.stop_loss_price)}원 (도달 시 전량 청산 → 봇 종료)")
        if self.hard_take_profit_price > 0:
            log(f"🔺 강제 익절가 설정: {format_price(self.hard_take_profit_price)}원 (도달 시 전량 청산 → 재진입)")

        # ── 매도 전략 ───────────────────────────────────────────────
        self.sell_mode = CONFIG.get('SELL_MODE', 'GRID')
        sell_mode_labels = {
            'GRID':        '그리드 다음 칸',
            'TARGET':      f"목표가 {format_price(CONFIG.get('SELL_TARGET_PRICE', 0))}원",
            'AVG_PLUS_ONE':'평균매수가 +1칸',
            'TOP_FIXED':   '그리드 상단 고정',
        }
        log(f"💹 매도 전략: {sell_mode_labels.get(self.sell_mode, self.sell_mode)}")

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

    # ════════════════════════════════════════════════════════════
    # 매도 전략 헬퍼
    # ════════════════════════════════════════════════════════════
    def _get_avg_buy_price(self):
        """현재 FILLED 레벨 전체의 가중 평균 매수가"""
        total_cost = sum(lv['buy_price'] * lv['buy_qty']
                         for lv in self.levels.values()
                         if lv['state'] == self.FILLED and lv['buy_qty'] > 0)
        total_qty = sum(lv['buy_qty']
                        for lv in self.levels.values()
                        if lv['state'] == self.FILLED and lv['buy_qty'] > 0)
        return total_cost / total_qty if total_qty > 0 else 0

    def _get_avg_plus_one_price(self):
        """평균 매수가 바로 위 첫 번째 그리드 레벨 가격"""
        avg = self._get_avg_buy_price()
        if avg <= 0:
            return self.grid_levels[-1]
        for level_price in self.grid_levels:
            if level_price > avg:
                return level_price
        return self.grid_levels[-1]

    def _resolve_sell_price(self, idx):
        """
        SELL_MODE 에 따라 실제 사용할 매도 가격 반환.
        GRID        → 레벨 dict의 sell_price (다음 칸)
        TARGET      → CONFIG['SELL_TARGET_PRICE']
        AVG_PLUS_ONE→ 현재 평균 매수가 바로 위 칸
        TOP_FIXED   → self.upper (그리드 최상단)
        """
        lv = self.levels[idx]
        mode = self.sell_mode

        if mode == 'TARGET':
            tp = CONFIG.get('SELL_TARGET_PRICE', 0)
            return round_to_tick(tp) if tp > 0 else lv['sell_price']

        elif mode == 'AVG_PLUS_ONE':
            return self._get_avg_plus_one_price()

        elif mode == 'TOP_FIXED':
            return round_to_tick(self.upper)

        else:  # GRID (기본)
            return lv['sell_price']

    def _refresh_avg_sells(self):
        """
        AVG_PLUS_ONE 모드 전용.
        새 매수 체결로 평균 매수가가 바뀌면 기존 매도 주문을 전부 취소하고
        새 평균+1 가격으로 재배치한다.
        """
        if self.sell_mode != 'AVG_PLUS_ONE':
            return

        new_sell_price = self._get_avg_plus_one_price()
        avg = self._get_avg_buy_price()
        changed = 0

        for i, lv in self.levels.items():
            if lv['state'] != self.FILLED:
                continue
            if lv.get('sell_price') == new_sell_price and lv.get('sell_uuid'):
                continue  # 이미 올바른 가격의 주문 있음 → 스킵

            # 기존 주문 취소
            if lv.get('sell_uuid'):
                UpbitAPI.cancel_order(lv['sell_uuid'])
                lv['sell_uuid'] = None
                if 'sell_qty' in lv:
                    del lv['sell_qty']

            # 새 가격 설정 후 재배치
            lv['sell_price'] = new_sell_price
            self._place_sell(i)
            changed += 1

        if changed > 0:
            log(f"  🔄 [AVG+1] 매도가 갱신 {changed}건: {format_price(new_sell_price)}원 "
                f"(평균매수가 {format_price(avg)}원)")

    # ════════════════════════════════════════════════════════════
    # 매도 주문 배치
    # ════════════════════════════════════════════════════════════
    def _place_sell(self, idx):
        lv = self.levels[idx]
        # ── 매도 전략에 따라 실제 매도 가격 결정 ──
        sell_price = self._resolve_sell_price(idx)
        lv['sell_price'] = sell_price          # 체결 감지용으로 최신화
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
                    self._refresh_avg_sells()  # AVG_PLUS_ONE: 평균가 변경 → 전체 매도 재조정
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
                    self._refresh_avg_sells()  # AVG_PLUS_ONE: 평균가 변경 → 전체 매도 재조정

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
    # TARGET 매도 모드: 목표가 감시
    # ════════════════════════════════════════════════════════════
    def check_sell_target(self):
        """
        SELL_MODE == 'TARGET' 전용.
        현재가 ≥ 목표가 도달 시 전량 청산 후 재진입.
        개별 지정가 매도도 목표가에 걸려 있으므로 자연 체결될 수 있으나,
        남은 포지션을 확실히 정리하기 위해 전량 청산 처리한다.
        """
        if self.sell_mode != 'TARGET':
            return None
        if self._sell_target_triggered:
            return None

        target = CONFIG.get('SELL_TARGET_PRICE', 0)
        if target <= 0:
            return None

        if self.current_price >= target:
            self._sell_target_triggered = True
            gain_pct = ((self.current_price - (self.entry_price or self.current_price))
                        / (self.entry_price or self.current_price) * 100)
            log(f"")
            log(f"{'━' * 55}")
            log(f"🎯 목표가 달성! {format_price(self.current_price)}원 ≥ {format_price(target)}원")
            log(f"   진입가: {format_price(self.entry_price)}원 | 수익: +{gain_pct:.2f}%")
            log(f"   → 전량 청산 후 재진입")
            log(f"{'━' * 55}")
            return self._execute_full_liquidation('TARGET_PRICE_EXIT')

        return None

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
            log(f"   → 전량 청산 후 재진입")
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
        log(f"⚡ 전량 청산 시작 ({'손절' if liquidation_type == 'STOP_LOSS' else ('목표가 달성' if liquidation_type == 'TARGET_PRICE_EXIT' else '강제 익절')})...")

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

        runtime = str(datetime.now() - self.start_time).split('.')[0]
        log(f"⚡ 전량 청산 완료 | 총 손익: {self.total_profit:+,.0f}원 | 운행: {runtime}")

        self.notifier.notify_liquidation(
            market=self.market,
            reason=(
                f"손절가 {format_price(self.stop_loss_price)}원 도달" if liquidation_type == 'STOP_LOSS'
                else f"목표가 {format_price(CONFIG.get('SELL_TARGET_PRICE', 0))}원 도달" if liquidation_type == 'TARGET_PRICE_EXIT'
                else f"강제 익절가 {format_price(self.hard_take_profit_price)}원 도달"
            ),
            total_profit=self.total_profit,
            runtime=runtime,
            liquidation_type=liquidation_type,
        )

        self.active = False
        return liquidation_type

    # ════════════════════════════════════════════════════════════
    # 그리드 이탈 확인 - 상단 돌파 즉시 익절
    # ════════════════════════════════════════════════════════════
    def check_boundary(self):
        if self.current_price > self.upper:
            log(f"📈 상단 돌파! {format_price(self.current_price)}원 > {format_price(self.upper)}원 → 익절")
            return 'TAKE_PROFIT'
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

        # 매도 전략 표시
        mode_labels = {
            'GRID': '그리드 다음 칸',
            'TARGET': f"목표가 {format_price(CONFIG.get('SELL_TARGET_PRICE', 0))}원",
            'AVG_PLUS_ONE': f"평균매수가+1칸 (현재 {format_price(self._get_avg_plus_one_price())}원)",
            'TOP_FIXED': f"최상단 고정 ({format_price(self.upper)}원)",
        }
        print(f"💹 매도전략: {mode_labels.get(self.sell_mode, self.sell_mode)}")

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

        print(f"📊 {self.market} | {format_price(self.current_price)}원 (Lv.{plvl}) | {rt}")
        print(f"   💰 평가: {format_price(total)}원 ({pnl:+,.0f}원, {pct:+.2f}%)")
        print(f"   📈 실현: {self.total_profit:+,.0f}원 | 거래: {self.trade_count}건")
        print(f"   📋 FILLED:{filled} | BUY:{pending} | EMPTY:{empty} | 현금:{self.cash:,.0f}원")

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
            print(f"   {sym} Lv.{i:>2d} {format_price(self.grid_levels[i]):>10s} ~ {format_price(self.grid_levels[i + 1]):>10s} {marker}")

        print(f"{'─' * 55}")

    def _print_grid(self):
        actual_grids = len(self.levels)
        target_grids = self.grid_count

        print(f"\n{'=' * 55}")
        print(f"🎯 Grid Bot V8.2 | {'실전' if CONFIG['ENABLE_REAL_TRADING'] else '시뮬레이션'}")
        print(f"{'=' * 55}")
        print(f"  🎯 {self.market} | 진입: {format_price(self.entry_price)}원")
        print(f"  📝 {self.reason}")
        print(f"  📏 {format_price(self.lower)} ~ {format_price(self.upper)} (±{self.range_pct * 100:.1f}%)")

        sell_mode_disp = {
            'GRID':         '그리드 다음 칸',
            'TARGET':       f"목표가 {format_price(CONFIG.get('SELL_TARGET_PRICE', 0))}원 → 달성 시 전량 청산 후 재진입",
            'AVG_PLUS_ONE': '평균 매수가 +1칸 (매수 체결마다 자동 갱신)',
            'TOP_FIXED':    f"최상단 고정 ({format_price(self.upper)}원)",
        }
        print(f"  💹 매도전략: {sell_mode_disp.get(self.sell_mode, self.sell_mode)}")

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
        'range_pct': bot.range_pct,
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

            # ── TARGET 매도 모드: 목표가 감시 ───────────────────────
            sell_target_result = bot.check_sell_target()
            if sell_target_result:
                report = bot.generate_report()
                bot.notifier.notify_report(report)
                return sell_target_result, bot.total_profit, bot.cash

            # ── 손절/강제익절 체크 ───────────────────────────────────
            hard_exit = bot.check_hard_exit()
            if hard_exit:
                report = bot.generate_report()
                bot.notifier.notify_report(report)
                return hard_exit, bot.total_profit, bot.cash

            boundary = bot.check_boundary()
            if boundary:
                report = bot.generate_report()
                bot.notifier.notify_report(report)
                bot.exit_all("상단 돌파 익절")
                return boundary, bot.total_profit, bot.cash

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
    ║   Upbit Grid Trading Bot V8.2           ║
    ║   수동 종목 선택 | 다양한 매도 전략       ║
    ╚══════════════════════════════════════════╝
    """)

    # 매도 방식 선택
    print("\n매도 방식을 선택하세요:")
    print("  1) 원금만 회수 - 수익은 코인으로 보유 (복리 효과)")
    print("  2) 전량 매도   - 모든 코인 매도하여 현금 회수")
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

    # 매도 전략 선택
    print("\n" + "=" * 55)
    print("📐 매도 전략을 선택하세요:")
    print("  1) GRID      - 매수 레벨 바로 위 칸 매도 (기본, 그리드 순환)")
    print("  2) TARGET    - 목표가 고정 → 달성 시 전량 청산 후 재진입")
    print("  3) AVG+1     - 평균 매수가 바로 위 칸 (물탈수록 매도가 내려옴)")
    print("  4) TOP_FIXED - 그리드 최상단 고정 (수익 극대화)")
    print("=" * 55)
    while True:
        sm_choice = input("\n선택 (1~4): ").strip()
        if sm_choice == '1':
            CONFIG['SELL_MODE'] = 'GRID'
            print("✅ GRID 모드")
            break
        elif sm_choice == '2':
            CONFIG['SELL_MODE'] = 'TARGET'
            while True:
                try:
                    tp_val = float(input("\n목표가를 입력하세요 (예: 3200): ").strip())
                    if tp_val <= 0:
                        print("❌ 0보다 큰 가격을 입력해주세요.")
                        continue
                    CONFIG['SELL_TARGET_PRICE'] = tp_val
                    print(f"✅ TARGET 모드 - 목표가 {format_price(tp_val)}원")
                    break
                except ValueError:
                    print("❌ 숫자를 입력해주세요.")
            break
        elif sm_choice == '3':
            CONFIG['SELL_MODE'] = 'AVG_PLUS_ONE'
            print("✅ AVG+1 모드")
            break
        elif sm_choice == '4':
            CONFIG['SELL_MODE'] = 'TOP_FIXED'
            print("✅ TOP_FIXED 모드")
            break
        else:
            print("❌ 1~4 중 선택해주세요.")

    # 손절가 설정
    print("\n" + "=" * 55)
    print("🔻 손절가를 설정하시겠습니까?")
    print("   도달 시: 전량 시장가 청산 → 봇 완전 종료")
    print("  1) 설정   2) 설정 안 함")
    while True:
        sl_choice = input("\n선택 (1 또는 2): ").strip()
        if sl_choice == '1':
            while True:
                try:
                    sl_price = float(input("\n손절가를 입력하세요 (예: 1800): ").strip())
                    if sl_price <= 0:
                        print("❌ 0보다 큰 가격을 입력해주세요.")
                        continue
                    CONFIG['STOP_LOSS_PRICE'] = sl_price
                    print(f"✅ 손절가: {format_price(sl_price)}원")
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

    # 강제 익절가 설정
    print("\n🔺 강제 익절가를 설정하시겠습니까?")
    print("   도달 시: 전량 시장가 청산 → 재진입")
    print("  1) 설정   2) 설정 안 함")
    while True:
        htp_choice = input("\n선택 (1 또는 2): ").strip()
        if htp_choice == '1':
            while True:
                try:
                    htp_price = float(input("\n강제 익절가를 입력하세요 (예: 2800): ").strip())
                    if htp_price <= 0:
                        print("❌ 0보다 큰 가격을 입력해주세요.")
                        continue
                    CONFIG['HARD_TAKE_PROFIT_PRICE'] = htp_price
                    print(f"✅ 강제 익절가: {format_price(htp_price)}원")
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
    total_capital = CONFIG['GRID_AMOUNT'] * CONFIG['GRID_COUNT']

    log(f"모드: {mode}")
    log(f"그리드당: {CONFIG['GRID_AMOUNT']:,.0f}원 × {CONFIG['GRID_COUNT']}칸 = {total_capital:,.0f}원")
    log(f"매도방식: {'원금만 회수' if CONFIG['KEEP_PROFIT_COINS'] else '전량 매도'} | "
        f"매도전략: {CONFIG['SELL_MODE']}"
        + (f" (목표가: {format_price(CONFIG['SELL_TARGET_PRICE'])}원)" if CONFIG['SELL_MODE'] == 'TARGET' else ""))
    sl = CONFIG.get('STOP_LOSS_PRICE', 0)
    htp = CONFIG.get('HARD_TAKE_PROFIT_PRICE', 0)
    if sl > 0:
        log(f"🔻 손절가: {format_price(sl)}원 → 전량 청산 후 봇 종료")
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
            log(f"🔄 사이클 #{cycle} | {total_capital:,.0f}원 | 누적손익: {session_profit:+,.0f}원")
            log(f"{'═' * 55}")

            if target is None:
                target = manual_select_target()
                if not target:
                    log("종목 선택 취소, 재시작...")
                    continue

            exit_reason, profit, remaining_cash = run_bot_cycle(target, CONFIG['GRID_AMOUNT'], CONFIG['GRID_COUNT'])
            session_profit += profit

            log(f"사이클 #{cycle} 종료: {exit_reason} | 손익: {profit:+,.0f}원 | 잔금: {format_price(remaining_cash)}원")

            # 손절 → 봇 완전 종료
            if exit_reason == 'STOP_LOSS':
                log(f"🔻 손절가 청산 완료 → 봇 완전 종료")
                log(f"   누적 손익: {session_profit:+,.0f}원")
                notifier.send(
                    f"⛔ <b>봇 완전 종료</b>\n"
                    f"사유: 손절가 도달 청산\n"
                    f"누적 손익: {session_profit:+,.0f}원\n"
                    f"총 사이클: {cycle}회"
                )
                break

            # 강제 익절 → 재진입
            if exit_reason == 'HARD_TAKE_PROFIT':
                sym = target['market'].replace('KRW-', '') if target else '?'
                log(f"🔺 강제 익절 청산 완료 → {CONFIG['COOLDOWN_AFTER_EXIT']}초 후 재진입...")
                notifier.send(
                    f"🔺 <b>강제 익절 후 재진입 대기</b>\n"
                    f"종목: {sym}\n"
                    f"누적 손익: {session_profit:+,.0f}원\n"
                    f"재진입까지: {CONFIG['COOLDOWN_AFTER_EXIT']}초"
                )
                # target 유지 → 같은 종목 재진입
                time.sleep(CONFIG['COOLDOWN_AFTER_EXIT'])
                continue

            # TARGET 목표가 달성 → 재진입
            if exit_reason == 'TARGET_PRICE_EXIT':
                sym = target['market'].replace('KRW-', '') if target else '?'
                log(f"🎯 목표가 달성 청산 완료 → {CONFIG['COOLDOWN_AFTER_EXIT']}초 후 재진입...")
                notifier.send(
                    f"🎯 <b>목표가 달성 후 재진입 대기</b>\n"
                    f"종목: {sym}\n"
                    f"목표가: {format_price(CONFIG.get('SELL_TARGET_PRICE', 0))}원\n"
                    f"누적 손익: {session_profit:+,.0f}원\n"
                    f"재진입까지: {CONFIG['COOLDOWN_AFTER_EXIT']}초"
                )
                # target 유지 → 같은 종목/조건 재진입
                time.sleep(CONFIG['COOLDOWN_AFTER_EXIT'])
                continue

            if exit_reason in ('BUY_FAIL', 'GRID_FAIL'):
                log("30초 후 재시도...")
                time.sleep(30)
                continue

            if exit_reason == 'LOW_CAPITAL':
                log("❌ 자본 부족으로 봇을 종료합니다.", 'ERROR')
                break

            # 상단 돌파 익절 → 새 종목 선택
            if exit_reason == 'TAKE_PROFIT':
                sym = target['market'].replace('KRW-', '')
                log(f"🟢 익절 완료 ({sym}) → {CONFIG['COOLDOWN_AFTER_EXIT']}초 후 재진입...")
                notifier.send(
                    f"🔁 <b>익절 후 재진입 대기</b>\n"
                    f"종목: {sym}\n"
                    f"누적 손익: {session_profit:+,.0f}원"
                )
                target = None  # 새 종목 선택
                time.sleep(CONFIG['COOLDOWN_AFTER_EXIT'])
                continue

            # 기타 종료 → 사용자 확인
            print("\n" + "=" * 55)
            print("계속 진행하시겠습니까?")
            print("  1) 계속 (새 종목 선택)   2) 종료")
            choice = input("\n선택 (1 또는 2): ").strip()
            if choice != '1':
                log("사용자 선택으로 봇을 종료합니다.")
                break
            target = None

    except KeyboardInterrupt:
        log("\n⚠️ 프로그램 종료 요청")

    finally:
        cleanup_all()

    log(f"\n📊 최종 결산: 총 {cycle} 사이클 | 누적 손익: {session_profit:+,.0f}원")
    print("프로그램을 종료합니다. 👋")


if __name__ == '__main__':
    main()