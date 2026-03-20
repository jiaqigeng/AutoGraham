from __future__ import annotations

import os
from typing import Any

try:
	from dotenv import load_dotenv
except ImportError:
	def load_dotenv(*args, **kwargs):
		return False

from agent.state import AgentRunState


DEFAULT_AGENT_MODEL = "gpt-4.1-mini"


def default_model_name() -> str:
	"""Return the model name used by the higher-level agent workflow."""

	return os.getenv("AUTOGRAHAM_AGENT_MODEL", DEFAULT_AGENT_MODEL)


def build_chat_model(model_name: str | None = None, temperature: float = 0.1):
	"""Create the chat model used by the subagents.

	This returns `None` when provider dependencies or credentials are unavailable so
	the rest of the workflow can fall back to deterministic heuristics.
	"""

	try:
		from langchain_openai import ChatOpenAI
	except ImportError:
		return None

	load_dotenv()
	api_key = os.getenv("OPENAI_API_KEY")
	if not api_key:
		return None

	return ChatOpenAI(
		model=model_name or default_model_name(),
		temperature=temperature,
		api_key=api_key,
	)


def response_text(response: Any) -> str:
	"""Normalize an LLM response object into plain text."""

	content = response.content if hasattr(response, "content") else str(response)
	if isinstance(content, list):
		return "\n".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
	return str(content)


def invoke_text_prompt(
	system_prompt: str,
	user_prompt: str,
	model_name: str | None = None,
	temperature: float = 0.1,
) -> str | None:
	"""Call the configured chat model and return text, or `None` if unavailable."""

	llm = build_chat_model(model_name=model_name, temperature=temperature)
	if llm is None:
		return None
	try:
		response = llm.invoke(
			[
				("system", system_prompt),
				("human", user_prompt),
			]
		)
	except Exception:
		return None
	return response_text(response).strip() or None


class AutoGrahamDeepAgent:
	"""Deep Agents style entrypoint for the AI Analyst workflow.

	TODO:
	- Add provider-specific tracing / observability hooks.
	- Upgrade this wrapper to use a native LangGraph runtime once the dependency is added.
	- Optionally expose streaming progress for the Streamlit UI.
	"""

	def __init__(self, model_name: str | None = None):
		self.model_name = model_name or default_model_name()

	def run(
		self,
		ticker: str,
		stock_data: Any,
		analysis_focus: str | None = None,
	) -> AgentRunState:
		from agent.graph import run_agent_graph

		state = AgentRunState(
			ticker=ticker.strip().upper(),
			model_name=self.model_name,
			analysis_focus=analysis_focus,
			stock_data=stock_data,
		)
		return run_agent_graph(state)
