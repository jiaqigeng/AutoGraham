# AutoGraham

AutoGraham is a Streamlit-based equity research and valuation app that combines deterministic valuation models with an AI agent workflow. It brings market data, manual valuation tools, and an AI Analyst into one interface for evaluating a stock.

## Features

- Market View for live quote, company context, and earnings data
- Valuation Lab for manual DCF, DDM, and RIM analysis
- AI agent workflow with specialized skills for research, model selection, parameter planning, and written explanation
- Deterministic valuation engine with transparent assumptions
- Validation layer between AI outputs and valuation calculations

## AI Agent Workflow

The AI Analyst is built as a multi-step AI agent rather than a single prompt. It:

1. builds company context
2. extracts valuation-relevant facts
3. selects an appropriate valuation model
4. prepares a structured parameter payload
5. validates inputs
6. runs deterministic valuation logic
7. generates a research memo and explanation

This keeps the AI useful for research and reasoning while leaving the final valuation calculation to Python code.

The agent uses specialized skills and tools for different parts of the workflow, including company context building, valuation model selection, parameter planning, market data lookups, SEC filing hints, web research, validation, and deterministic valuation calculation.

## Tech Stack

- Python
- Streamlit
- OpenAI via `langchain-openai`
- LangChain tools
- Optional LangGraph orchestration
- Pydantic
- `yfinance`

## Getting Started

### Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Environment Variables

Create a local `.env` file:

```env
OPENAI_API_KEY=your_openai_api_key
AUTOGRAHAM_AGENT_MODEL=gpt-5.2
```

`OPENAI_API_KEY` enables the AI workflow. Manual valuation features remain usable without it.

### Run Locally

```powershell
streamlit run app.py
```

## Testing

```powershell
python -m unittest discover -s tests -p "test_*.py"
```

## Roadmap

- Add screenshots to the README
- Expand source attribution in the AI report
- Improve benchmarking for AI-assisted assumption generation

## License

This project is licensed under the MIT License. See `LICENSE` for details.
