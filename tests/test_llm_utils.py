from __future__ import annotations

from types import ModuleType
import unittest
from unittest.mock import MagicMock
from unittest.mock import patch

from agent.llm_utils import build_chat_model


class BuildChatModelTests(unittest.TestCase):
	def test_build_chat_model_disables_langchain_verbose_fallback(self) -> None:
		fake_langchain_openai = ModuleType("langchain_openai")
		fake_langchain_openai.ChatOpenAI = MagicMock()

		with patch("agent.llm_utils.load_dotenv"), patch(
			"agent.llm_utils.os.getenv",
			side_effect=lambda key, default=None: {
				"OPENAI_API_KEY": "test-key",
				"AUTOGRAHAM_AGENT_MODEL": "gpt-test",
			}.get(key, default),
		), patch.dict("sys.modules", {"langchain_openai": fake_langchain_openai}):
			build_chat_model()

		fake_langchain_openai.ChatOpenAI.assert_called_once_with(
			model="gpt-test",
			temperature=0.1,
			api_key="test-key",
			verbose=False,
		)


if __name__ == "__main__":
	unittest.main()
