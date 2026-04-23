# universal_ai/providers/gemini_provider.py
from typing import List, Dict
from universal_ai.core.model_interface import ModelResponse, ModelInterface

class GeminiProvider(ModelInterface):
    def __init__(self, model: str, api_key: str | None = None):
        self.model = model
        self.name = f"google:{model}"
        self.api_key = api_key

    def generate(self, messages: List[Dict], **kwargs) -> ModelResponse:
        return {"provider": self.name, "content": "[Gemini placeholder response]"}

    def stream(self, messages: List[Dict], **kwargs):
        yield {"delta": "Streaming not implemented"}

    def metadata(self) -> Dict:
        return {"provider": "google", "model": self.model}
