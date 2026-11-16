"""Shared test helpers."""


class FakeLLM:
    """Stands in for the Gemini chat model in both roles - no API key, no network.

    * scope (structured):  with_structured_output(...).invoke(msgs) -> `result` (or raises `exc`)
    * generate (plain)  :  invoke(msgs) -> object with .content = `answer` (or raises `answer_exc`)
    Captures prompts in `calls` (scope) and `answer_calls` (generate).
    """

    def __init__(self, result=None, exc=None, answer="FAKE STEPS", answer_exc=None):
        self.result, self.exc = result, exc
        self.answer, self.answer_exc = answer, answer_exc
        self.calls: list = []
        self.answer_calls: list = []

    def with_structured_output(self, schema):
        outer = self

        class _Structured:
            def invoke(self, messages):
                outer.calls.append(messages)
                if outer.exc is not None:
                    raise outer.exc
                return outer.result

        return _Structured()

    def invoke(self, messages):
        self.answer_calls.append(messages)
        if self.answer_exc is not None:
            raise self.answer_exc

        class _Reply:
            content = self.answer

        return _Reply()


class FakeIndex:
    """Stands in for ManualIndex: returns preset (chunk, score) hits, records every search."""

    def __init__(self, hits=None):
        self.hits = hits or []
        self.searches: list = []  # (query, allowed_names, top_k)

    def search(self, query, allowed_names, top_k=3):
        self.searches.append((query, set(allowed_names), top_k))
        return self.hits[:top_k]
