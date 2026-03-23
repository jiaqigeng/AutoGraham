from __future__ import annotations

import streamlit as st


st.set_page_config(page_title="AutoGraham", layout="wide")

navigation = st.navigation(
	[
		st.Page("pages/1_Market_View.py", title="Market View", default=True),
		st.Page("pages/2_Valuation_Lab.py", title="Valuation Lab"),
		st.Page("pages/3_AI_Analyst.py", title="AI Analyst"),
	]
)
navigation.run()
