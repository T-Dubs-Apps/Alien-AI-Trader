# universal_ai/providers/openai_provider.py
import os
from typing import List, Dict
from universal_ai.core.model_interface import ModelResponse, ModelInterface

class OpenAIProvider(ModelInterface):
    def __init__(self, model: str, api_key: str | None = None):
        self.model = model
        self.name = f"openai:{model}"
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")

    def generate(self, messages: List[Dict], **kwargs) -> ModelResponse:
        # Pseudocode: replace with actual SDK call
        # resp = openai.chat.completions.create(model=self.model, messages=messages, **kwargs)
        # return {"provider": self.name, "content": resp.choices[0].message.content, "raw": resp}
        return {"provider": self.name, "content": "[OpenAI placeholder response]"}

    def stream(self, messages: List[Dict], **kwargs):
        yield {"delta": "Streaming not implemented"}

    def metadata(self) -> Dict:
        return {"provider": "openai", "model": self.model}
