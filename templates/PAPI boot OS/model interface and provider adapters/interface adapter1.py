# universal_ai/core/model_interface.py
from typing import List, Dict, Optional, Protocol

class ModelResponse(Dict):
    pass

class ModelInterface(Protocol):
    name: str
    def generate(self, messages: List[Dict], **kwargs) -> ModelResponse:
        ...

    def stream(self, messages: List[Dict], **kwargs):
        ...

    def metadata(self) -> Dict:
        ...
