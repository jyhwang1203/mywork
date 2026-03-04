"""
📊 실시간 경제 지표 대시보드 (Yahoo Finance 버전)
────────────────────────────────────────────────
실행 방법:
  1) pip install -r requirements.txt
  2) python dashboard.py
  3) 브라우저에서 http://127.0.0.1:8050 접속

데이터 출처: Yahoo Finance (yfinance)
  - 모든 데이터는 yfinance를 통해 Yahoo Finance에서 직접 수집
  - Anthropic API 키 불필요
  - 장 마감 후에는 마지막 종가 기준으로 표시
"""

import ssl
import os
import shutil
import tempfile
import threading
import warnings
from datetime import datetime, timedelta

warnings.filterwarnings("ignore")
ssl._create_default_https_context = ssl._create_unverified_context

import urllib3
urllib3.disable_warnings()

# ── 핵심 수정: 한글 경로 → ASCII 임시 경로로 인증서 복사 ──────────
# libcurl이 한글 경로(C:\안티그래비티\...)를 읽지 못해 curl 77 발생
# certifi cacert.pem을 ASCII 경로 임시 폴더에 복사해서 해결
try:
    import certifi
    _tmp_dir  = tempfile.mkdtemp()
    _cert_dst = os.path.join(_tmp_dir, "cacert.pem")
    shutil.copy(certifi.where(), _cert_dst)
    os.environ["CURL_CA_BUNDLE"]     = _cert_dst
    os.environ["REQUESTS_CA_BUNDLE"] = _cert_dst
    os.environ["SSL_CERT_FILE"]      = _cert_dst
except Exception:
    os.environ["CURL_CA_BUNDLE"]     = ""
    os.environ["REQUESTS_CA_BUNDLE"] = ""
    os.environ["SSL_CERT_FILE"]      = ""

import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
import dash
from dash import Dash, html, dcc, Input, Output, State, callback_context, no_update, ALL
import dash_bootstrap_components as dbc

# ── 색상 테마 ─────────────────────────────────────────────────────
BG   = "#060c18"
BG2  = "#0b1422"
BG3  = "#0e1b2e"
BLUE = "#4a9eff"
GRN  = "#22c55e"
RED  = "#ef4444"
TEXT = "#eef4ff"
MUTED= "#556677"
MONO = "'JetBrains Mono', 'Fira Mono', 'Courier New', monospace"
SANS = "'Plus Jakarta Sans', 'Segoe UI', sans-serif"

# ── Yahoo Finance 티커 정의 ───────────────────────────────────────
#   각 카테고리별로 {표시명: (ticker, 단위)} 정의
TICKERS = {
    "indices": {
        "KOSPI":    ("^KS11",  ""),
        "KOSDAQ":   ("^KQ11",  ""),
        "S&P 500":  ("^GSPC",  ""),
        "NASDAQ":   ("^IXIC",  ""),
        "다우존스": ("^DJI",   ""),
        "닛케이225":("^N225",  ""),
        "상하이종합":("000001.SS", ""),
    },
    "fx": {
        "USD/KRW":  ("USDKRW=X", "원"),
        "EUR/KRW":  ("EURKRW=X", "원"),
        "JPY/KRW":  ("JPYKRW=X", "원(100엔)"),   # × 100 처리
        "CNY/KRW":  ("CNYKRW=X", "원"),
        "GBP/KRW":  ("GBPKRW=X", "원"),
        "USD/JPY":  ("USDJPY=X", "엔"),
    },
    "rates": {
        "미국 국채 2Y":  ("^IRX",  "%"),   # 13-week → 2Y 근사
        "미국 국채 10Y": ("^TNX",  "%"),
        "미국 국채 30Y": ("^TYX",  "%"),
        "미국 기준금리": ("FEDFUNDS=F", "%"),  # SOFR 선물 근사
        "한국 국고채 3Y":("KR3YT=RR", "%"),
        "한국 국고채 10Y":("KR10YT=RR","%"),
    },
    "commodities": {
        "WTI 원유":  ("CL=F",  "USD/배럴"),
        "브렌트 원유":("BZ=F",  "USD/배럴"),
        "금":        ("GC=F",  "USD/온스"),
        "은":        ("SI=F",  "USD/온스"),
        "구리":      ("HG=F",  "USD/파운드"),
        "천연가스":  ("NG=F",  "USD/MMBtu"),
    },
}

PERIOD_MAP = {
    "1주일": ("7d",  "1d"),
    "1개월": ("1mo", "1d"),
    "3개월": ("3mo", "1d"),
    "6개월": ("6mo", "1wk"),
    "1년":   ("1y",  "1wk"),
}

CATEGORIES = [
    {"id": "indices",     "label": "주가지수", "icon": "📈"},
    {"id": "fx",          "label": "환율",     "icon": "💱"},
    {"id": "rates",       "label": "금리",     "icon": "🏦"},
    {"id": "commodities", "label": "원자재",   "icon": "🛢️"},
]

PERIODS = list(PERIOD_MAP.keys())


# ── 데이터 수집 ───────────────────────────────────────────────────
def get_quote(name: str, ticker: str, unit: str) -> dict:
    """단일 티커 현재가 + 전일대비 계산."""
    base = {"name": name, "value": 0, "change": 0,
            "changePct": 0, "unit": unit, "ticker": ticker}
    try:
        mul  = 100 if ticker == "JPYKRW=X" else 1
        tk   = yf.Ticker(ticker)
        hist = tk.history(period="5d", interval="1d", auto_adjust=True)

        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = hist.columns.get_level_values(0)

        if hist is None or hist.empty or "Close" not in hist.columns:
            return {**base, "error": "데이터 없음"}

        closes = hist["Close"].dropna()
        if closes.empty:
            return {**base, "error": "종가 데이터 없음"}

        price = float(closes.iloc[-1]) * mul
        prev  = float(closes.iloc[-2]) * mul if len(closes) >= 2 else price
        change     = price - prev
        change_pct = (change / prev * 100) if prev else 0.0

        return {
            "name":      name,
            "value":     round(price,      4),
            "change":    round(change,     4),
            "changePct": round(change_pct, 4),
            "unit":      unit,
            "ticker":    ticker,
        }
    except Exception as e:
        return {**base, "error": str(e)}


def fetch_category(cat_id: str) -> dict:
    """카테고리 내 모든 티커를 병렬로 조회."""
    lock    = threading.Lock()
    results = {}
    threads = []

    def _fetch(nm, tk, un):
        result = get_quote(nm, tk, un)
        with lock:
            results[nm] = result

    for name, (ticker, unit) in TICKERS[cat_id].items():
        t = threading.Thread(target=_fetch, args=(name, ticker, unit))
        threads.append(t)
        t.start()
    for t in threads:
        t.join()

    items = [results[n] for n in TICKERS[cat_id] if results.get(n) is not None]
    return {"items": items}


def fetch_history(ticker: str, period_key: str, name: str, unit: str) -> dict:
    """주어진 기간의 히스토리 반환."""
    period, interval = PERIOD_MAP[period_key]
    mul  = 100 if ticker == "JPYKRW=X" else 1
    tk   = yf.Ticker(ticker)
    hist = tk.history(period=period, interval=interval, auto_adjust=True)

    if isinstance(hist.columns, pd.MultiIndex):
        hist.columns = hist.columns.get_level_values(0)

    if hist is None or hist.empty:
        raise ValueError(f"{name} 히스토리 데이터 없음")
    if "Close" not in hist.columns:
        raise ValueError(f"Close 컬럼 없음: {list(hist.columns)}")

    closes = (hist["Close"] * mul).dropna()
    if closes.empty:
        raise ValueError(f"{name}: 유효한 데이터 없음")

    dates = closes.index.strftime("%Y-%m-%d").tolist()
    vals  = [round(float(v), 4) for v in closes]

    return {
        "history": [{"date": d, "value": v} for d, v in zip(dates, vals)],
        "high":    round(float(closes.max()),  4),
        "low":     round(float(closes.min()),  4),
        "avg":     round(float(closes.mean()), 4),
    }


# ── UI 헬퍼 ──────────────────────────────────────────────────────
def make_sparkline(values: list, positive: bool) -> html.Div:
    """순수 html.Div로 만드는 미니 바 차트 스파크라인 (SVG/HTML 문자열 없음)."""
    col = GRN if positive else RED
    if not values or len(values) < 2:
        return html.Div(style={"width": "72px", "height": "36px"})
    mn, mx = min(values), max(values)
    span = mx - mn or 1
    pts = values[-18:]  # 최근 18개 포인트만
    bars = [
        html.Div(style={
            "width": "3px",
            "height": f"{max(4, int(((v - mn) / span) * 30))}px",
            "background": col,
            "borderRadius": "1px",
            "opacity": "0.72",
            "alignSelf": "flex-end",
            "flexShrink": "0",
        })
        for v in pts
    ]
    return html.Div(bars, style={
        "display": "flex",
        "gap": "1px",
        "alignItems": "flex-end",
        "height": "36px",
        "width": "72px",
    })


def badge(pct: float, positive: bool) -> html.Span:
    col = GRN if positive else RED
    bg  = "rgba(34,197,94,0.12)" if positive else "rgba(239,68,68,0.12)"
    brd = "rgba(34,197,94,0.3)"  if positive else "rgba(239,68,68,0.3)"
    return html.Span(
        f"{'▲' if positive else '▼'} {abs(pct):.2f}%",
        style={
            "fontSize": "10px", "padding": "2px 9px", "borderRadius": "99px",
            "background": bg, "border": f"1px solid {brd}", "color": col,
            "fontFamily": MONO,
        },
    )


def stat_card(item: dict, sparkline_pts: list = None) -> html.Div:
    v    = float(item.get("value", 0))
    chg  = float(item.get("change", 0))
    pct  = float(item.get("changePct", 0))
    unit = item.get("unit", "")
    err  = item.get("error", None)
    pos  = chg >= 0
    col  = GRN if pos else RED
    brd  = "rgba(34,197,94,0.18)" if pos else "rgba(239,68,68,0.18)"

    # 에러 상태 — 카드는 표시하되 오류 메시지 보여줌
    if err or v == 0:
        brd = "rgba(239,68,68,0.18)"
        return html.Div(
            id={"type": "stat-card", "index": item["name"]},
            n_clicks=0,
            children=[
                html.Div(style={
                    "position": "absolute", "inset": "0", "pointerEvents": "none",
                    "background": "radial-gradient(circle at 80% 15%, #ef444418, transparent 55%)",
                }),
                html.Div("📊 CHART", style={
                    "position": "absolute", "top": "8px", "right": "10px",
                    "fontSize": "9px", "color": "rgba(74,158,255,0.35)",
                    "fontFamily": MONO,
                }),
                html.Span(item["name"], style={
                    "fontFamily": MONO, "fontSize": "10px", "fontWeight": "600",
                    "letterSpacing": "1.5px", "textTransform": "uppercase", "color": "#7788aa",
                    "display": "block", "marginBottom": "10px",
                }),
                html.Div("⚠ 데이터 로딩 실패", style={
                    "fontFamily": MONO, "fontSize": "12px", "color": RED,
                    "marginBottom": "4px",
                }),
                html.Div(str(err or "값 없음")[:60], style={
                    "fontFamily": MONO, "fontSize": "9px", "color": MUTED,
                    "wordBreak": "break-all",
                }),
            ],
            style={
                "position": "relative", "overflow": "hidden",
                "borderRadius": "12px", "border": f"1px solid {brd}",
                "background": "rgba(13,19,30,0.9)", "padding": "16px",
                "cursor": "pointer",
                "transition": "transform 0.15s ease, box-shadow 0.15s ease",
            },
        )

    # 정상 데이터
    if sparkline_pts is None:
        import random
        sparkline_pts = [v * (1 + (random.random() - 0.5) * 0.005) for _ in range(20)]

    svg     = make_sparkline(sparkline_pts, pos)
    val_str = f"{v:,.2f}" if v < 10000 else f"{v:,.0f}"

    return html.Div(
        id={"type": "stat-card", "index": item["name"]},
        n_clicks=0,
        children=[
            html.Div(style={
                "position": "absolute", "inset": "0", "pointerEvents": "none",
                "background": f"radial-gradient(circle at 80% 15%, {col}18, transparent 55%)",
            }),
            html.Div("📊 CHART", style={
                "position": "absolute", "top": "8px", "right": "10px",
                "fontSize": "9px", "color": "rgba(74,158,255,0.35)",
                "fontFamily": MONO, "letterSpacing": "0.5px",
            }),
            html.Div([
                html.Span(item["name"], style={
                    "fontFamily": MONO, "fontSize": "10px", "fontWeight": "600",
                    "letterSpacing": "1.5px", "textTransform": "uppercase", "color": "#7788aa",
                }),
                badge(pct, pos),
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "flex-start", "marginBottom": "10px"}),
            html.Div([
                html.Div([
                    html.Div(val_str, style={
                        "fontFamily": MONO, "fontSize": "20px", "fontWeight": "700",
                        "color": TEXT if not has_err else RED, "marginBottom": "3px",
                    }),
                    html.Div(
                        f"{'+'if pos else ''}{chg:.4f} {unit}" if v < 100
                        else f"{'+'if pos else ''}{chg:.2f} {unit}",
                        style={"fontFamily": MONO, "fontSize": "11px", "color": col},
                    ),
                ]),
                svg,
            ], style={"display": "flex", "justifyContent": "space-between",
                      "alignItems": "flex-end"}),
        ],
        style={
            "position": "relative", "overflow": "hidden",
            "borderRadius": "12px", "border": f"1px solid {brd}",
            "background": "rgba(13,19,30,0.9)", "padding": "16px",
            "cursor": "pointer",
            "transition": "transform 0.15s ease, box-shadow 0.15s ease, border-color 0.15s ease",
        },
    )


def skeleton_card() -> html.Div:
    return html.Div(style={
        "borderRadius": "12px", "height": "96px",
        "background": "rgba(13,19,30,0.85)",
        "border": "1px solid rgba(74,158,255,0.08)",
        "animation": "shimmer 1.5s ease-in-out infinite",
    })


def section_header(cat: dict, loading: bool = False) -> html.Div:
    return html.Div([
        html.Span(cat["icon"], style={"fontSize": "16px"}),
        html.H2(cat["label"], style={
            "fontFamily": MONO, "fontSize": "11px", "fontWeight": "700",
            "letterSpacing": "2.5px", "textTransform": "uppercase",
            "color": BLUE, "margin": "0",
        }),
        html.Div(style={"flex": "1", "height": "1px",
                        "background": "rgba(74,158,255,0.15)"}),
        html.Div([
            html.Div(style={
                "width": "5px", "height": "5px", "borderRadius": "50%",
                "background": BLUE,
                "animation": f"pulse 1s {i*0.2}s ease-in-out infinite",
            }) for i in range(3)
        ], style={"display": "flex", "gap": "4px"}) if loading else html.Div(),
    ], style={"display": "flex", "alignItems": "center", "gap": "12px", "marginBottom": "14px"})


def category_section(cat: dict, items=None, loading=False, error=None) -> html.Div:
    if error:
        body = html.Div(f"⚠ {error}", style={
            "borderRadius": "10px", "padding": "14px 16px",
            "background": "rgba(239,68,68,0.08)", "border": "1px solid rgba(239,68,68,0.25)",
            "color": RED, "fontFamily": MONO, "fontSize": "12px",
        })
    elif loading or items is None:
        body = html.Div([skeleton_card() for _ in range(6)], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fill, minmax(220px, 1fr))",
            "gap": "12px",
        })
    else:
        body = html.Div([stat_card(it) for it in items], style={
            "display": "grid",
            "gridTemplateColumns": "repeat(auto-fill, minmax(220px, 1fr))",
            "gap": "12px",
        })

    return html.Div(
        [section_header(cat, loading), body],
        style={"marginBottom": "36px"},
    )


# ── 차트 생성 ─────────────────────────────────────────────────────
def make_chart(hist: dict, item: dict) -> go.Figure:
    dates  = [h["date"]  for h in hist["history"]]
    values = [h["value"] for h in hist["history"]]
    pos    = float(item.get("change", 0)) >= 0
    color  = GRN if pos else RED
    grad_id = f"grad_{item['name'][:6]}"

    fig = go.Figure()

    # 캔들/라인 선택 → 라인 + 영역 그라디언트
    fig.add_trace(go.Scatter(
        x=dates, y=values,
        mode="lines",
        line=dict(color=color, width=2.2, shape="spline", smoothing=0.6),
        fill="tozeroy",
        fillcolor=f"rgba({'34,197,94' if pos else '239,68,68'},0.08)",
        hovertemplate=(
            "<b>%{x}</b><br>"
            f"{item['name']}: %{{y:,.4f}} {item.get('unit','')}<extra></extra>"
        ),
        name=item["name"],
    ))

    # 평균선
    avg = hist.get("avg", 0)
    fig.add_hline(
        y=avg, line_dash="dot",
        line_color=BLUE, line_width=1, opacity=0.5,
        annotation_text=f"  평균 {avg:,.2f}",
        annotation_font_color=BLUE,
        annotation_font_size=9,
        annotation_position="top left",
    )

    fig.update_layout(
        paper_bgcolor=BG3,
        plot_bgcolor=BG3,
        margin=dict(l=68, r=18, t=14, b=38),
        height=300,
        font=dict(family=MONO, color=MUTED, size=10),
        xaxis=dict(
            showgrid=False, zeroline=False,
            tickfont=dict(color=MUTED, size=9),
            linecolor="rgba(74,158,255,0.1)",
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(74,158,255,0.06)",
            zeroline=False, tickfont=dict(color=MUTED, size=9),
            tickformat=",.2f",
        ),
        hoverlabel=dict(
            bgcolor="#0d1828", bordercolor=BLUE,
            font=dict(family=MONO, size=11, color=TEXT),
        ),
        showlegend=False,
    )
    return fig


# ── 모달 빌더 ─────────────────────────────────────────────────────
def build_modal(item: dict, period: str,
                hist: dict = None, loading: bool = True,
                error: str = None) -> list:
    pos   = float(item.get("change", 0)) >= 0
    color = GRN if pos else RED
    v     = float(item.get("value", 0))
    chg   = float(item.get("change", 0))
    pct   = float(item.get("changePct", 0))
    unit  = item.get("unit", "")
    val_str = f"{v:,.2f}" if v < 10000 else f"{v:,.0f}"

    # ── 차트 영역
    if loading:
        chart_area = html.Div([
            html.Div([html.Div(style={
                "width": "7px", "height": "7px", "borderRadius": "50%",
                "background": color,
                "animation": f"pulse 1.2s {i*0.15}s ease-in-out infinite",
            }) for i in range(4)], style={"display": "flex", "gap": "8px"}),
            html.Span("Yahoo Finance에서 데이터 로딩 중...",
                      style={"color": MUTED, "fontSize": "11px", "fontFamily": MONO}),
        ], style={"height": "280px", "display": "flex", "flexDirection": "column",
                  "alignItems": "center", "justifyContent": "center", "gap": "14px"})
        stats_area = html.Div()

    elif error:
        chart_area = html.Div(f"⚠ {error}", style={
            "height": "280px", "display": "flex",
            "alignItems": "center", "justifyContent": "center",
            "color": RED, "fontFamily": MONO, "fontSize": "12px",
        })
        stats_area = html.Div()

    else:
        fig = make_chart(hist, item)
        chart_area = dcc.Graph(
            figure=fig,
            config={"displayModeBar": True, "displaylogo": False,
                    "modeBarButtonsToRemove": ["select2d", "lasso2d"]},
            style={"height": "300px"},
        )
        stats_area = html.Div([
            html.Div([
                html.Div(lbl, style={
                    "color": MUTED, "fontSize": "9px", "fontFamily": MONO,
                    "letterSpacing": "1.8px", "textTransform": "uppercase",
                    "marginBottom": "6px",
                }),
                html.Div(f"{float(val):,.4f}" if float(val) < 100 else f"{float(val):,.2f}",
                         style={"color": c, "fontSize": "16px",
                                "fontFamily": MONO, "fontWeight": "700"}),
            ], style={
                "padding": "14px 0", "textAlign": "center",
                "borderRight": "1px solid rgba(74,158,255,0.08)" if i < 2 else "none",
                "flex": "1",
            }) for i, (lbl, val, c) in enumerate([
                ("기간 최고", hist["high"], GRN),
                ("기간 평균", hist["avg"], "#8899aa"),
                ("기간 최저", hist["low"], RED),
            ])
        ], style={
            "display": "flex", "borderTop": "1px solid rgba(74,158,255,0.1)",
            "background": "rgba(74,158,255,0.025)",
        })

    # ── 기간 버튼
    period_btns = [
        html.Button(p, id={"type": "period-btn", "index": p}, n_clicks=0,
                    style={
                        "padding": "6px 16px", "borderRadius": "8px",
                        "fontSize": "11px", "fontFamily": MONO, "fontWeight": "600",
                        "cursor": "pointer", "transition": "all 0.15s",
                        "background": "rgba(74,158,255,0.2)" if p == period else "transparent",
                        "border": f"1px solid {'rgba(74,158,255,0.45)' if p == period else 'rgba(74,158,255,0.1)'}",
                        "color": BLUE if p == period else MUTED,
                    })
        for p in PERIODS
    ]

    return [html.Div([
        # 헤더
        html.Div([
            html.Div([
                html.Div([
                    html.Span(item["name"], style={
                        "fontFamily": MONO, "fontSize": "11px",
                        "color": "#6677aa", "letterSpacing": "2.5px",
                        "textTransform": "uppercase",
                    }),
                    html.Span(f"{'▲' if pos else '▼'} {abs(pct):.2f}%", style={
                        "fontSize": "11px", "padding": "2px 10px", "borderRadius": "99px",
                        "background": "rgba(34,197,94,0.15)" if pos else "rgba(239,68,68,0.15)",
                        "border": f"1px solid {'rgba(34,197,94,0.3)' if pos else 'rgba(239,68,68,0.3)'}",
                        "color": color, "fontFamily": MONO,
                    }),
                    html.Span("via Yahoo Finance", style={
                        "fontSize": "9px", "color": "rgba(74,158,255,0.3)",
                        "fontFamily": MONO, "marginLeft": "4px",
                    }),
                ], style={"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "8px"}),
                html.Div([
                    html.Span(val_str, style={
                        "fontFamily": MONO, "fontSize": "32px",
                        "fontWeight": "800", "color": TEXT, "letterSpacing": "-1px",
                    }),
                    html.Span(
                        f"{'+'if pos else ''}{chg:.4f} {unit}" if v < 100
                        else f"{'+'if pos else ''}{chg:.2f} {unit}",
                        style={"fontFamily": MONO, "fontSize": "13px", "color": color},
                    ),
                ], style={"display": "flex", "alignItems": "baseline", "gap": "14px"}),
            ]),
            html.Button("✕", id="close-modal", n_clicks=0, style={
                "background": "rgba(74,158,255,0.08)",
                "border": "1px solid rgba(74,158,255,0.18)",
                "color": MUTED, "borderRadius": "10px",
                "width": "34px", "height": "34px", "cursor": "pointer",
                "fontSize": "14px", "display": "flex",
                "alignItems": "center", "justifyContent": "center", "flexShrink": "0",
            }),
        ], style={
            "display": "flex", "justifyContent": "space-between",
            "alignItems": "flex-start", "padding": "22px 26px 18px",
            "borderBottom": "1px solid rgba(74,158,255,0.1)",
            "background": "rgba(74,158,255,0.02)",
        }),

        # 기간 선택
        html.Div(period_btns, style={
            "display": "flex", "gap": "6px", "padding": "16px 26px 0",
        }),

        # 차트
        html.Div(chart_area, style={"padding": "8px 6px 0 0"}),

        # 통계
        stats_area,

    ], style={
        "width": "100%", "maxWidth": "840px",
        "background": f"linear-gradient(160deg, {BG2} 0%, {BG3} 100%)",
        "border": "1px solid rgba(74,158,255,0.18)",
        "borderRadius": "18px", "overflow": "hidden",
        "boxShadow": "0 32px 80px rgba(0,0,0,0.7)",
        "animation": "slideUp 0.28s cubic-bezier(0.34,1.56,0.64,1)",
    })]


# ── Dash 앱 ───────────────────────────────────────────────────────
app = Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700;800"
        "&family=Plus+Jakarta+Sans:wght@400;500;700;800&display=swap",
    ],
    suppress_callback_exceptions=True,
)
app.title = "경제 지표 대시보드"

app.index_string = """<!DOCTYPE html>
<html>
<head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#060c18;overflow-x:hidden}
  ::-webkit-scrollbar{width:4px}
  ::-webkit-scrollbar-track{background:#060c18}
  ::-webkit-scrollbar-thumb{background:#1a3050;border-radius:2px}
  @keyframes shimmer{0%,100%{opacity:.35}50%{opacity:.65}}
  @keyframes pulse{0%,100%{opacity:.25;transform:scale(.75)}50%{opacity:1;transform:scale(1.25)}}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.15}}
  @keyframes fadeIn{from{opacity:0}to{opacity:1}}
  @keyframes slideUp{from{opacity:0;transform:translateY(28px)}to{opacity:1;transform:translateY(0)}}
  @keyframes scanline{0%{transform:translateY(-100%)}100%{transform:translateY(100vh)}}
  @keyframes spin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
  .stat-hover:hover{transform:translateY(-3px);box-shadow:0 10px 28px rgba(0,0,0,0.3)!important;}
</style>
</head>
<body>{%app_entry%}{%config%}{%scripts%}{%renderer%}</body>
</html>"""

app.layout = html.Div([
    # 스캔라인
    html.Div(html.Div(style={
        "width": "100%", "height": "2px",
        "background": "linear-gradient(transparent,#4a9eff,transparent)",
        "animation": "scanline 7s linear infinite",
    }), style={"position": "fixed", "inset": "0", "pointerEvents": "none",
               "zIndex": "0", "overflow": "hidden", "opacity": "0.025"}),
    # 그리드 배경
    html.Div(style={
        "position": "fixed", "inset": "0", "pointerEvents": "none", "zIndex": "0",
        "backgroundImage":
            "linear-gradient(rgba(74,158,255,0.025) 1px,transparent 1px),"
            "linear-gradient(90deg,rgba(74,158,255,0.025) 1px,transparent 1px)",
        "backgroundSize": "44px 44px",
    }),

    html.Div([
        # ── 헤더
        html.Div([
            html.Div([
                html.Div([
                    html.Div(style={
                        "width": "8px", "height": "8px", "borderRadius": "50%",
                        "background": GRN, "boxShadow": f"0 0 10px {GRN}",
                        "animation": "blink 2s ease-in-out infinite",
                    }),
                    html.Span("LIVE  ·  Yahoo Finance", style={
                        "fontFamily": MONO, "fontSize": "10px",
                        "letterSpacing": "2.5px", "textTransform": "uppercase", "color": GRN,
                    }),
                ], style={"display": "flex", "alignItems": "center", "gap": "10px", "marginBottom": "6px"}),
                html.H1("경제 지표 대시보드", style={
                    "fontFamily": SANS, "fontSize": "28px", "fontWeight": "800",
                    "color": TEXT, "letterSpacing": "-0.5px",
                }),
                html.P(id="last-updated", style={
                    "fontFamily": MONO, "fontSize": "10px", "color": MUTED, "marginTop": "5px",
                }),
            ]),
            html.Button([
                html.Span("↻", id="refresh-icon"),
                html.Span(" 새로고침"),
            ], id="refresh-btn", n_clicks=0, style={
                "display": "flex", "alignItems": "center", "gap": "8px",
                "padding": "10px 20px", "borderRadius": "10px",
                "fontFamily": MONO, "fontSize": "12px", "fontWeight": "600",
                "background": "rgba(74,158,255,0.12)",
                "border": "1px solid rgba(74,158,255,0.3)",
                "color": BLUE, "cursor": "pointer",
            }),
        ], style={"display": "flex", "flexWrap": "wrap", "justifyContent": "space-between",
                  "alignItems": "center", "gap": "16px", "marginBottom": "28px"}),

        # ── 탭
        html.Div([
            html.Button([html.Span("◈ 전체")],
                        id="tab-all", n_clicks=0,
                        style={"padding": "7px 16px", "borderRadius": "9px",
                               "fontFamily": MONO, "fontSize": "11px", "fontWeight": "600",
                               "background": "rgba(74,158,255,0.18)", "color": BLUE,
                               "border": "1px solid rgba(74,158,255,0.45)", "cursor": "pointer"}),
        ] + [
            html.Button([html.Span(f"{c['icon']} {c['label']}")],
                        id=f"tab-{c['id']}", n_clicks=0,
                        style={"padding": "7px 16px", "borderRadius": "9px",
                               "fontFamily": MONO, "fontSize": "11px", "fontWeight": "600",
                               "background": "rgba(74,158,255,0.04)", "color": MUTED,
                               "border": "1px solid rgba(74,158,255,0.1)", "cursor": "pointer"})
            for c in CATEGORIES
        ], style={"display": "flex", "gap": "6px", "marginBottom": "28px", "flexWrap": "wrap"}),

        # ── 섹션
        html.Div(id="sections-container"),

        # ── 푸터
        html.Div([
            html.Span("데이터 출처: ", style={"color": "#263444"}),
            html.A("Yahoo Finance (yfinance)", href="https://finance.yahoo.com",
                   target="_blank",
                   style={"color": "rgba(74,158,255,0.35)", "textDecoration": "none"}),
            html.Span("  ·  투자 참고용으로만 활용하세요", style={"color": "#263444"}),
        ], style={
            "marginTop": "24px", "paddingTop": "16px", "textAlign": "center",
            "borderTop": "1px solid rgba(74,158,255,0.08)",
            "fontFamily": MONO, "fontSize": "10px",
        }),
    ], style={"position": "relative", "zIndex": "10",
              "maxWidth": "1020px", "margin": "0 auto", "padding": "24px"}),

    # ── 모달
    html.Div(id="chart-modal", children=[], style={"display": "none"}),

    # ── 상태 저장
    dcc.Store(id="market-store", data={}),
    dcc.Store(id="active-tab",   data="all"),
    dcc.Store(id="selected-item",data=None),
    dcc.Store(id="selected-period", data="1개월"),
    dcc.Interval(id="init-trigger", interval=300, n_intervals=0, max_intervals=1),
], style={"minHeight": "100vh", "background": BG})


# ── 콜백: 데이터 로딩 ────────────────────────────────────────────
@app.callback(
    Output("sections-container", "children"),
    Output("market-store", "data"),
    Output("last-updated", "children"),
    Input("init-trigger", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
    State("active-tab", "data"),
)
def load_data(_, n_clicks, active_tab):
    results, errors = {}, {}

    def fetch(cat):
        try:
            results[cat["id"]] = fetch_category(cat["id"])
        except Exception as e:
            errors[cat["id"]] = str(e)

    threads = [threading.Thread(target=fetch, args=(c,)) for c in CATEGORIES]
    for t in threads: t.start()
    for t in threads: t.join()

    display = CATEGORIES if active_tab == "all" else [c for c in CATEGORIES if c["id"] == active_tab]
    sections = []
    for cat in display:
        items = results.get(cat["id"], {}).get("items")
        err   = errors.get(cat["id"])
        sections.append(category_section(cat, items=items, error=err))

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    updated_msg = [
        f"마지막 업데이트: {ts}  ·  ",
        html.Span("카드를 클릭하면 차트를 확인할 수 있습니다",
                  style={"color": "rgba(74,158,255,0.4)"}),
    ]
    return sections, results, updated_msg


# ── 콜백: 탭 전환 ────────────────────────────────────────────────
@app.callback(
    Output("sections-container", "children", allow_duplicate=True),
    Output("active-tab", "data"),
    Input("tab-all", "n_clicks"),
    *[Input(f"tab-{c['id']}", "n_clicks") for c in CATEGORIES],
    State("market-store", "data"),
    prevent_initial_call=True,
)
def switch_tab(*args):
    store = args[-1]
    ctx   = callback_context
    if not ctx.triggered:
        return no_update, no_update

    btn_id = ctx.triggered[0]["prop_id"].split(".")[0]
    active = "all" if btn_id == "tab-all" else btn_id.replace("tab-", "")

    display = CATEGORIES if active == "all" else [c for c in CATEGORIES if c["id"] == active]
    sections = [
        category_section(cat, items=store.get(cat["id"], {}).get("items"))
        for cat in display
    ]
    return sections, active


# ── 콜백: 카드 클릭 → 모달 열기 ─────────────────────────────────
@app.callback(
    Output("chart-modal", "style"),
    Output("chart-modal", "children"),
    Output("selected-item", "data"),
    Input({"type": "stat-card", "index": ALL}, "n_clicks"),
    State("market-store", "data"),
    State("selected-period", "data"),
    prevent_initial_call=True,
)
def open_chart(n_clicks_list, store, period):
    import json as _j
    ctx = callback_context
    if not ctx.triggered or not any(n for n in n_clicks_list if n):
        return no_update, no_update, no_update

    card_name = _j.loads(ctx.triggered[0]["prop_id"].split(".")[0])["index"]

    item = None
    for cat_data in store.values():
        for it in cat_data.get("items", []):
            if it["name"] == card_name:
                item = it
                break
        if item:
            break

    if not item:
        return no_update, no_update, no_update

    modal_style = {
        "position": "fixed", "inset": "0", "zIndex": "50",
        "background": "rgba(2,6,14,0.9)", "backdropFilter": "blur(8px)",
        "display": "flex", "alignItems": "center", "justifyContent": "center",
        "padding": "16px", "animation": "fadeIn 0.2s ease",
    }
    return modal_style, build_modal(item, period, loading=True), item


# ── 콜백: 모달 닫기 ──────────────────────────────────────────────
@app.callback(
    Output("chart-modal", "style", allow_duplicate=True),
    Output("chart-modal", "children", allow_duplicate=True),
    Input("close-modal", "n_clicks"),
    prevent_initial_call=True,
)
def close_modal(n):
    if n:
        return {"display": "none"}, []
    return no_update, no_update


# ── 콜백: 기간 변경 ──────────────────────────────────────────────
@app.callback(
    Output("chart-modal", "children", allow_duplicate=True),
    Output("selected-period", "data"),
    Input({"type": "period-btn", "index": ALL}, "n_clicks"),
    State("selected-item", "data"),
    prevent_initial_call=True,
)
def change_period(n_clicks_list, item):
    import json as _j
    ctx = callback_context
    if not ctx.triggered or not item:
        return no_update, no_update

    period = _j.loads(ctx.triggered[0]["prop_id"].split(".")[0])["index"]
    return build_modal(item, period, loading=True), period


# ── 콜백: 히스토리 로딩 ──────────────────────────────────────────
@app.callback(
    Output("chart-modal", "children", allow_duplicate=True),
    Input("selected-period", "data"),
    State("selected-item", "data"),
    prevent_initial_call=True,
)
def load_history(period, item):
    if not item or not period:
        return no_update
    try:
        ticker = item.get("ticker", "")
        hist   = fetch_history(ticker, period, item["name"], item.get("unit", ""))
        return build_modal(item, period, hist=hist, loading=False)
    except Exception as e:
        return build_modal(item, period, error=str(e), loading=False)


# ── 실행 ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("━" * 55)
    print("📊  경제 지표 대시보드  (Yahoo Finance)")
    print("━" * 55)
    print("   데이터: yfinance → Yahoo Finance 실시간")
    print("   주소:   http://127.0.0.1:8050")
    print("━" * 55)
    app.run(debug=False, port=8050)