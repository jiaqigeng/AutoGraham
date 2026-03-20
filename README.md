# AutoGraham

AutoGraham is a Python + Streamlit app for stock and company valuation.

## Main Flows

- `Market View`: visualize finance data for a ticker
- `Valuation Lab`: run deterministic Python valuation models with manual assumptions
- `AI Analyst`: let an AI workflow research the company, choose structured assumptions, run Python valuation functions, and explain the result

## Architecture

- `pages/`: Streamlit page entrypoints
- `workflows/`: application orchestration
- `valuation/`: deterministic DCF, DDM, and RIM math
- `agent/`: AI research, model selection, parameter estimation, explanation, and orchestration
- `data/`: Yahoo Finance fetching plus normalization helpers
- `ui_components/`: reusable Streamlit rendering blocks

## Run

```powershell
pip install -r requirements.txt
streamlit run app.py
```

## Test

```powershell
python -m unittest discover -s tests -p "test_*.py"
```
