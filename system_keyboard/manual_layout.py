"""Manual label fallback for compositors without layout detection."""
from .layouts import Layout


class ManualLayout:
    def __init__(self):
        self.layout = Layout('us')
        self.language = 'us'

    def switch(self):
        language = 'ru' if self.language == 'us' else 'us'
        replacement = Layout(language)
        self.layout.close()
        self.layout = replacement
        self.language = language

    def labels(self, modifiers=()):
        return self.layout.labels(modifiers)

    def close(self):
        self.layout.close()
