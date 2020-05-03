import re
import typing
from typing import List, Text, Any, Dict

from rasa.nlu.tokenizers.tokenizer import Token, Tokenizer
from rasa.nlu.training_data import Message

from rasa.nlu.constants import TOKENS_NAMES, MESSAGE_ATTRIBUTES

from sudachipy import dictionary
from sudachipy import tokenizer


class SudachiTokenizer(Tokenizer):
    provides = [TOKENS_NAMES[attribute] for attribute in MESSAGE_ATTRIBUTES]

    def __init__(self, component_config: Dict[Text, Any]=None)->None:
        super().__init__(component_config)

        self.tokenizer_obj = dictionary.Dictionary().create()
        self.mode = tokenizer.Tokenizer.SplitMode.A


    @classmethod
    def required_packages(cls) -> List[Text]:
        return ["sudachipy"]

    def tokenize(self, message: Message, attribute: Text) -> List[Token]:
        text = message.get(attribute)
        words = [m.surface() for m in self.tokenizer_obj.tokenize(text, self.mode)]

        return self._convert_words_to_tokens(words, text)
