"""
app.py
------
AutoGraham — AI-Assisted Value Investing Dashboard
Inspired by Benjamin Graham's principles of intrinsic value and margin of safety.

Run with:
    streamlit run app.py
"""

import os
import streamlit as st
from dotenv import load_dotenv

# Load API keys from .env if present
load_dotenv()

# ---------------------------------------------------------------------------
# Page configuration (must be first Streamlit call)
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AutoGraham — Value Investing Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Local utility imports
# ---------------------------------------------------------------------------
from utils.dcf import get_stock_data, calculate_dcf, get_dcf_projection_df
from utils.ai_agent import analyze_economic_moat, analyze_earnings
from utils.charts import (
    get_historical_multiples,
    plot_historical_multiples,
    plot_moat_radar,
    plot_dcf_bar,
)

# ---------------------------------------------------------------------------
# Caching wrappers — keep expensive calls out of every re-render
# ---------------------------------------------------------------------------

@st.cache_data(show_spinner=False)
def cached_get_stock_data(ticker: str) -> dict:
    return get_stock_data(ticker)


@st.cache_data(show_spinner=False)
def cached_get_historical_multiples(ticker: str) -> object:
    return get_historical_multiples(ticker)


@st.cache_data(show_spinner=False)
def cached_analyze_moat(company_name: str, sector: str, description: str) -> dict:
    return analyze_economic_moat(company_name, sector, description)


@st.cache_data(show_spinner=False)
def cached_analyze_earnings(company_name: str, sector: str, description: str) -> dict:
    return analyze_earnings(company_name, sector, description)


# ---------------------------------------------------------------------------
# Sidebar — ticker input & global settings
# ---------------------------------------------------------------------------

st.sidebar.title("AutoGraham 📈")
st.sidebar.markdown("*AI-Assisted Value Investing Dashboard*")
st.sidebar.divider()

ticker_input = st.sidebar.text_input(
    "Enter Ticker Symbol",
    value="AAPL",
    max_chars=10,
    help="e.g. AAPL, MSFT, GOOG",
).upper().strip()

st.sidebar.divider()
st.sidebar.markdown("#### DCF Assumptions")

growth_rate = st.sidebar.slider(
    "FCF Growth Rate (%)",
    min_value=0,
    max_value=30,
    value=10,
    step=1,
    help="Expected annual free cash flow growth over the projection period.",
) / 100

wacc = st.sidebar.slider(
    "WACC (%)",
    min_value=5,
    max_value=20,
    value=10,
    step=1,
    help="Weighted Average Cost of Capital used to discount future cash flows.",
) / 100

terminal_multiple = st.sidebar.slider(
    "Terminal Exit Multiple (x FCF)",
    min_value=5,
    max_value=40,
    value=20,
    step=1,
    help="The EV/FCF multiple applied to the final projected year's cash flow.",
)

st.sidebar.divider()
st.sidebar.markdown("#### AI Settings")
api_key_input = st.sidebar.text_input(
    "OpenAI API Key",
    type="password",
    value=os.environ.get("OPENAI_API_KEY", ""),
    help="Enter your OpenAI API key. Leave blank to skip AI analysis.",
)
if api_key_input:
    os.environ["OPENAI_API_KEY"] = api_key_input

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.title("AutoGraham — AI Value Investing Dashboard 📈")
st.markdown(
    "_Inspired by Benjamin Graham · Compare market price vs. intrinsic value_"
)
st.divider()

# ---------------------------------------------------------------------------
# Fetch data (cached)
# ---------------------------------------------------------------------------

if not ticker_input:
    st.warning("Please enter a ticker symbol in the sidebar.")
    st.stop()

with st.spinner(f"Fetching data for **{ticker_input}**…"):
    data = cached_get_stock_data(ticker_input)

if not data:
    st.error(
        f"❌ Could not retrieve data for **{ticker_input}**. "
        "Please verify the ticker symbol and try again."
    )
    st.stop()

info = data["info"]
company_name = info.get("longName") or ticker_input
sector = info.get("sector", "Unknown")
description = info.get("longBusinessSummary", "No description available.")
current_price = data["current_price"]
market_cap = data["market_cap"]
fcf = data["free_cash_flow"]
shares = data["shares_outstanding"]
debt = data["total_debt"]
cash_equiv = data["cash_and_equivalents"]

# ---------------------------------------------------------------------------
# Quick summary row
# ---------------------------------------------------------------------------

col1, col2, col3, col4 = st.columns(4)
col1.metric("Company", company_name)
col2.metric("Sector", sector)
col3.metric(
    "Current Price",
    f"${current_price:,.2f}" if current_price else "N/A",
)
col4.metric(
    "Market Cap",
    f"${market_cap / 1e9:,.1f}B" if market_cap else "N/A",
)

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_dcf, tab_multiples, tab_moat, tab_earnings = st.tabs([
    "🔢 DCF Valuation",
    "📊 Historical Multiples",
    "🛡️ Economic Moat",
    "📰 Earnings & Cases",
])

# ===========================================================================
# TAB 1 — Dynamic DCF Valuation
# ===========================================================================
with tab_dcf:
    st.subheader("Discounted Cash Flow Valuation")
    st.markdown(
        "Adjust the **Growth Rate**, **WACC**, and **Terminal Multiple** in the "
        "sidebar to see the intrinsic value update in real time."
    )

    if fcf == 0:
        st.warning(
            "⚠️ Free cash flow data is not available for this ticker. "
            "DCF cannot be calculated."
        )
    else:
        dcf_result = calculate_dcf(
            free_cash_flow=fcf,
            shares_outstanding=shares,
            growth_rate=growth_rate,
            wacc=wacc,
            terminal_multiple=terminal_multiple,
            total_debt=debt or 0,
            cash=cash_equiv or 0,
        )

        if not dcf_result:
            st.error("DCF calculation failed. Check that shares outstanding and WACC are valid.")
        else:
            intrinsic = dcf_result["intrinsic_per_share"]

            # Margin of safety
            if current_price and intrinsic and intrinsic > 0:
                margin_of_safety = (intrinsic - current_price) / intrinsic * 100
            else:
                margin_of_safety = None

            # --- KPI row ---
            k1, k2, k3, k4 = st.columns(4)
            k1.metric(
                "Intrinsic Value / Share",
                f"${intrinsic:,.2f}",
                help="Estimated fair value per share based on the DCF model.",
            )
            k2.metric(
                "Current Market Price",
                f"${current_price:,.2f}",
            )
            if margin_of_safety is not None:
                delta_color = "normal" if margin_of_safety >= 0 else "inverse"
                k3.metric(
                    "Margin of Safety",
                    f"{margin_of_safety:.1f}%",
                    delta="Undervalued" if margin_of_safety >= 0 else "Overvalued",
                    delta_color=delta_color,
                )
            k4.metric(
                "TTM Free Cash Flow",
                f"${fcf / 1e9:,.2f}B" if abs(fcf) >= 1e9 else f"${fcf / 1e6:,.0f}M",
            )

            st.divider()

            # --- Assumptions summary ---
            with st.expander("📋 DCF Assumptions Summary", expanded=False):
                a1, a2, a3 = st.columns(3)
                a1.metric("FCF Growth Rate", f"{growth_rate * 100:.0f}%")
                a2.metric("WACC", f"{wacc * 100:.0f}%")
                a3.metric("Terminal Multiple", f"{terminal_multiple}x")

                st.caption(
                    f"Projection Period: 10 years | "
                    f"Total Debt: ${(debt or 0) / 1e9:,.1f}B | "
                    f"Cash: ${(cash_equiv or 0) / 1e9:,.1f}B"
                )

            # --- Chart ---
            st.plotly_chart(
                plot_dcf_bar(dcf_result["projected_fcfs"], dcf_result["pv_fcfs"]),
                use_container_width=True,
            )

            # --- Projection table ---
            with st.expander("📄 Projected FCF Table", expanded=False):
                proj_df = get_dcf_projection_df(
                    dcf_result["projected_fcfs"], dcf_result["pv_fcfs"]
                )
                st.dataframe(proj_df.style.format("${:,.1f}M"), use_container_width=True)

# ===========================================================================
# TAB 2 — Historical Multiple Reversion
# ===========================================================================
with tab_multiples:
    st.subheader("Historical Valuation Multiple Reversion")
    st.markdown(
        "Compare the stock's **current P/E and P/B** ratios against its 5-year "
        "history to identify whether the stock is historically cheap or expensive."
    )

    current_pe = info.get("trailingPE")
    current_pb = info.get("priceToBook")

    m1, m2 = st.columns(2)
    m1.metric("Current P/E (Trailing)", f"{current_pe:.1f}" if current_pe else "N/A")
    m2.metric("Current P/B", f"{current_pb:.1f}" if current_pb else "N/A")

    with st.spinner("Loading historical multiples…"):
        hist_df = cached_get_historical_multiples(ticker_input)

    fig_multiples = plot_historical_multiples(
        hist_df, current_pe, current_pb, ticker_input
    )
    st.plotly_chart(fig_multiples, use_container_width=True)

    if not hist_df.empty:
        with st.expander("📄 Historical Multiples Data", expanded=False):
            st.dataframe(hist_df.style.format("{:.1f}"), use_container_width=True)

# ===========================================================================
# TAB 3 — AI Economic Moat Analyzer
# ===========================================================================
with tab_moat:
    st.subheader("AI Economic Moat Analyzer 🛡️")
    st.markdown(
        "The AI scores the company's **competitive advantages** (moat) across "
        "five key dimensions on a scale from **1 (none)** to **5 (very strong)**."
    )

    if not os.environ.get("OPENAI_API_KEY"):
        st.warning(
            "⚠️ No OpenAI API key detected. Enter your key in the sidebar to "
            "enable AI analysis."
        )
    else:
        with st.spinner("Analyzing economic moat with AI…"):
            moat_scores = cached_analyze_moat(company_name, sector, description)

        fig_radar = plot_moat_radar(moat_scores, company_name)
        st.plotly_chart(fig_radar, use_container_width=True)

        # Score table
        st.markdown("##### Dimension Scores")
        score_cols = st.columns(len(moat_scores))
        score_labels = {1: "None", 2: "Weak", 3: "Moderate", 4: "Strong", 5: "Very Strong"}
        for col, (dim, score) in zip(score_cols, moat_scores.items()):
            col.metric(dim, f"{score}/5", score_labels.get(score, ""))

        st.caption(
            "Scores are AI-generated estimates based on publicly available information "
            "and should not be used as sole investment advice."
        )

# ===========================================================================
# TAB 4 — AI Earnings & Bull / Bear Case
# ===========================================================================
with tab_earnings:
    st.subheader("AI Earnings Analysis & Bull/Bear Cases 📰")
    st.markdown(
        "The AI summarizes recent **earnings tailwinds & headwinds** and generates "
        "a structured **Bull Case vs. Bear Case** for the stock."
    )

    if not os.environ.get("OPENAI_API_KEY"):
        st.warning(
            "⚠️ No OpenAI API key detected. Enter your key in the sidebar to "
            "enable AI analysis."
        )
    else:
        with st.spinner("Generating earnings analysis with AI…"):
            earnings_data = cached_analyze_earnings(company_name, sector, description)

        # Tailwinds / Headwinds
        tw_col, hw_col = st.columns(2)
        with tw_col:
            st.markdown("#### 🌬️ Tailwinds")
            for item in earnings_data.get("tailwinds", []):
                st.success(f"✅ {item}")

        with hw_col:
            st.markdown("#### ⚡ Headwinds")
            for item in earnings_data.get("headwinds", []):
                st.error(f"⚠️ {item}")

        st.divider()

        # Bull vs Bear case
        bull_col, bear_col = st.columns(2)
        with bull_col:
            st.markdown("#### 🐂 Bull Case")
            st.info(earnings_data.get("bull_case", "N/A"))

        with bear_col:
            st.markdown("#### 🐻 Bear Case")
            st.warning(earnings_data.get("bear_case", "N/A"))

        st.caption(
            "Analysis is AI-generated from the company's public business description. "
            "Not financial advice."
        )

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.divider()
st.markdown(
    "<small>AutoGraham is for educational purposes only. "
    "It is not investment advice. Always do your own research.</small>",
    unsafe_allow_html=True,
)
