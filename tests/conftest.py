"""Shared test helpers."""


class FakeLLM:
    """Stands in for the Gemini chat model: returns a preset ScopeDecision (or raises).

    Captures the prompt it was invoked with, so tests can assert on prompt content.
    No API key, no network.
    """

    def __init__(self, result=None, exc: Exception | None = None):
        self.result = result
        self.exc = exc
        self.calls: list = []  # the message lists passed to invoke()

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        self.calls.append(messages)
        if self.exc is not None:
            raise self.exc
        return self.result
