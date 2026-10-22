"""Canonical prompts and public licensed copies from the frozen engineering catalog."""
from copy import deepcopy
from journey.catalog import Catalog as PublicCatalog
from journey.models import prompt_request
from mobile_admission.contract import canonical


class Catalog:
    def __init__(self):
        self._public = PublicCatalog()
        self._projection = self._public.projection()
        prompts = {item['id']: prompt_request(item) for item in self._public.prompts}
        for item in self._projection['prompts']:
            item['prompt'] = deepcopy(prompts[item['id']])
        self._accepted = frozenset(canonical(prompt) for prompt in prompts.values())

    def projection(self): return deepcopy(self._projection)
    def accepts(self, prompt): return canonical(prompt) in self._accepted
    def reference(self, word): return self._public.reference(word)
    def illustration(self, word): return self._public.illustration(word)
