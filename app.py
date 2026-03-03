import streamlit as st
import yfinance as yf


st.set_page_config(page_title="AutoGraham", page_icon="🤖", layout="wide")


@st.cache_data(ttl=3600)
def fetch_company_info(ticker: str) -> dict:
	stock = yf.Ticker(ticker)
	info = stock.info

	company_name = info.get("longName")
	sector = info.get("sector")
	current_price = info.get("currentPrice")

	if not company_name or current_price is None:
		raise ValueError("Invalid ticker or missing company data.")

	return {
		"longName": company_name,
		"sector": sector or "N/A",
		"currentPrice": current_price,
	}


st.sidebar.title("AutoGraham 🤖")
ticker = st.sidebar.text_input("Enter Stock Ticker", value="AAPL").strip().upper()


st.title("AutoGraham 🤖")

try:
	company_data = fetch_company_info(ticker)
	st.subheader(f"{company_data['longName']} ({ticker})")
	st.write(f"**Sector:** {company_data['sector']}")
	st.write(f"**Current Price:** ${company_data['currentPrice']}")
except Exception:
	st.error("Invalid ticker symbol or data unavailable. Please try another ticker.")


tab_dcf, tab_multiple, tab_moat, tab_bull_bear = st.tabs(
	[
		"🧮 Dynamic DCF",
		"📈 Multiple Reversion",
		"🏰 Moat Analyzer",
		"⚖️ Bull/Bear Case",
	]
)

with tab_dcf:
	st.header("🧮 Dynamic DCF")
	st.info("This tab will include a real-time, slider-driven DCF valuation model.")

with tab_multiple:
	st.header("📈 Multiple Reversion")
	st.info("This tab will visualize historical valuation multiples vs. current levels.")

with tab_moat:
	st.header("🏰 Moat Analyzer")
	st.info("This tab will show AI-scored economic moat dimensions in a radar chart.")

with tab_bull_bear:
	st.header("⚖️ Bull/Bear Case")
	st.info("This tab will present AI-generated bull and bear investment narratives.")
