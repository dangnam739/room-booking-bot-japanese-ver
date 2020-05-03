from typing import Any, Dict, Optional, Text
from rasa.nlu.config import RasaNLUModelConfig
from rasa.nlu.extractors import EntityExtractor
from rasa.nlu.training_data import Message, TrainingData
from pha_helper import processing_nlu

class RegexEntityExtractor(EntityExtractor):
    name = 'regex_pha'
    provides = ["entities"]
    language_list = ["jp"]

    def __init__(
        self,
        component_config: Optional[Dict[Text, Text]] = None
    ) -> None:
        super(RegexEntityExtractor, self).__init__(component_config)

    def train(
        self,
        training_data: TrainingData,
        config: RasaNLUModelConfig,
        **kwargs: Any
    ) -> None:
        # since we are using premade PHA code
        pass

    def persist(self, file_name: Text, model_dir: Text) -> Optional[Dict[Text, Any]]:
        # We save nothing.
        pass

    def process(self, message: Message, **kwargs: Any) -> None:
        """Process an incoming message."""
        extracted = self.add_extractor_name(processing_nlu(message.text))
        message.set(
            "entities", message.get("entities", []) + extracted, add_to_output=True
        )
