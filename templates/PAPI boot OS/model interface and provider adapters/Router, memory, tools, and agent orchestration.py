# universal_ai/core/router.py
from typing import List, Dict, Optional
from universal_ai.core.model_interface import ModelInterface
from universal_ai.utils.logging import get_logger

logger = get_logger(__name__)

class RoutingStrategy:
    def select(self, models: List[ModelInterface], context: List[Dict]) -> List[ModelInterface]:
        return models  # naive: fan-out to all

class Router:
    def __init__(self, models: List[ModelInterface], strategy: Optional[RoutingStrategy] = None):
        self.models = models
        self.strategy = strategy or RoutingStrategy()

    def generate(self, messages: List[Dict], **kwargs) -> List[Dict]:
        selected = self.strategy.select(self.models, messages)
        results = []
        for m in selected:
            try:
                resp = m.generate(messages, **kwargs)
                results.append(resp)
            except Exception as e:
                logger.exception(f"Model {m.name} failed: {e}")
                results.append({"provider": m.name, "error": str(e)})
        return results
