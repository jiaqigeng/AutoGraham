from __future__ import annotations

import streamlit as st


navigation = st.navigation(
    [
        st.Page("pages/financial_data.py", title="Financial Data", default=True),
        st.Page("pages/calculators.py", title="Calculators"),
        st.Page("pages/ai_analysis.py", title="AI Analysis"),
    ]
)

navigation.run()
