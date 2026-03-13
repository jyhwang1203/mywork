import asyncio
from google import genai
from google.genai import types
from telegram import Bot

# --- 설정 정보 ---
GEMINI_API_KEY = "AIzaSyA81oYP30yHHnzAYuSuYsA9yd7hiGfl-XU"
TELEGRAM_TOKEN = "8355910620:AAEEjtdDcHYIg93X9JmH5GdUZ7urglOpvAo"
CHAT_ID = "2017077172"

client = genai.Client(api_key=GEMINI_API_KEY)

async def generate_financial_report():
    """가독성을 극대화한 단문/공백 중심의 시황 보고서를 생성합니다."""

    prompt = """
**[필수 검색 프로세스]**


**[작성 가이드라인]**
1. **톤앤매너:** 냉철한 개조식 (~함, ~임). 문장은 25자 이내 단문.
2. **가독성:** 섹션 간 2줄 빈 줄, 항목 간 1줄 빈 줄 필수.
3. **포맷:** 이모지 활용
[Role & Context]
You are a Senior Strategist and member of the Global Investment Committee (GIC) at a Tier-1 asset management firm. Your mission is to analyze the divergence between the official 'House View' and the underlying 'Institutional Narrative'. Maintain 'Data-driven Rigor' in your market analysis.

[Task: 2026 Global Macro & Market Pulse]
Produce an institutional-grade market wrap for [Insert Date, 2026].

[Core Methodology]

Strict Closing Data Protocol: Every single price, yield, and index value MUST be based on the PREVIOUS DAY'S CLOSE.

Mandatory Search Command: Search for "[Asset Name] closing price on [Insert Date - 1 day]".

Priority Sources: * Global: Yahoo Finance, CNBC, Bloomberg.

Korea-Specific: Naver Finance, KRX (Korea Exchange).

Verification: Cross-check the closing price against at least two sources. If there is a discrepancy, prioritize the primary exchange's official closing record.

Error Handling: If the previous day's closing price is unavailable, you MUST state "Data as of [Latest Available Closing Date]" and explain why. Never use intraday/live prices as closing data.

Source Rigor & Attribution: Every key data point must be attributed (e.g., Bloomberg Terminal, BII Weekly).

The Hidden Hand (Philosophical Perspective): Interpret market movements as outcomes of 'Liquidity Traps' and 'Behavioral Engineering' by mega-capital.

Data Grounding: Leverage 10Y Real Yields, Term Premiums, and 5y5y Forward Inflation Swaps. Cite the specific source for these metrics based on your search.

[Report Structure]

Executive Summary: The Trinity of Forces

Identify the three primary drivers (e.g., Fiscal Dominance, AI CapEx Utility, Energy Geopolitics).

Recent Economic Indicators & Shadow Implications

Analyze recent high-impact releases. Decipher the gap between headline data and 'Smart Money' reaction.

Asset Allocation & Flow Analysis

Equities: Regional divergence (US vs. Asia/Europe). Focus on closing-basis trends.

Fixed Income: 'The Great Re-pricing'. Impact of Curve Steeping/Flattening on capital costs.

Alts & Digital: The 'remonetization' of Gold, the volatility of WTI & Natural Gas, and Ripple (XRP) institutional adoption.

Macro Divergence: House View Contrast

Contrast BlackRock’s vs. J.P. Morgan’s latest stances based on verified search results.

Data Dashboard (Detailed Tables - ALL PREVIOUS CLOSE BASIS)

Table 1: Equity Indices (S&P 500, Nasdaq, KOSPI, Nikkei 225, Stoxx 600).

Table 2: Macro & Commodities (US 10Y Yield, KR 10Y Yield, DXY, KRW/USD, WTI Oil, Gold, Natural Gas, Ripple (XRP)).

Mandatory Columns: [Asset], [Closing Price/Yield], [D-1 Change %], [YTD %], [Source], [Closing Date].

The Strategic 'So What?'

Definitive tactical conclusion: What to 'Trim' and what to 'Add' immediately based on the closing setup.

[Tone & Style]

High Signal-to-Noise Ratio. Use sophisticated terminology (R-star, Convexity, Fiscal Dominance).

Maintain a cynical yet logically rigorous tone.
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        return response.text
    except Exception as e:
        return f"❌ 시황 생성 실패: {e}"

async def main():
    print("🚀 가독성 특화 시황 분석 시작...")

    report = await generate_financial_report()

    try:
        bot = Bot(token=TELEGRAM_TOKEN)
        await bot.send_message(chat_id=CHAT_ID, text=report, parse_mode='HTML')
        print("✅ 전송 완료!")
    except Exception as e:
        print(f"❌ 전송 오류: {e}")
        # 예외 상황 대비 일반 텍스트 재시도
        try:
            clean_text = report.replace('<b>','').replace('</b>','').replace('<pre>','').replace('</pre>','').replace('<code>','').replace('</code>','').replace('<blockquote>','').replace('</blockquote>','')
            await bot.send_message(chat_id=CHAT_ID, text=f"[안전모드 전송]\n\n{clean_text}")
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())