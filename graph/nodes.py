from typing import Literal

from graph.agent import ChatBIAgentApp
from graph.state import ChatBIState


RouteName = Literal["question_cache", "informational", "enum_lookup", "failure", "run_agent"]


class ChatBIWorkflowNodes:
    """LangGraph node adapter around the ChatBI agent runtime."""

    def __init__(self, runtime: ChatBIAgentApp | None = None) -> None:
        self.runtime = runtime or ChatBIAgentApp()

    def retrieve_context(self, state: ChatBIState) -> dict:
        return self.runtime.retrieve_context(state)

    def resolve_followup_question(self, state: ChatBIState) -> dict:
        return self.runtime.resolve_followup_question(state)

    def preflight_guardrails(self, state: ChatBIState) -> dict:
        return self.runtime.preflight_guardrails(state)

    def lookup_question_cache(self, state: ChatBIState) -> dict:
        return self.runtime.lookup_question_cache(state)

    def respond_question_cache(self, state: ChatBIState) -> ChatBIState:
        return self.runtime.respond_question_cache(state)

    def respond_informational(self, state: ChatBIState) -> ChatBIState:
        return self.runtime.respond_informational(state)

    def respond_enum_lookup(self, state: ChatBIState) -> ChatBIState:
        return self.runtime.respond_enum_lookup(state)

    def respond_failure(self, state: ChatBIState) -> ChatBIState:
        return self.runtime.respond_failure(state)

    def run_sql_agent(self, state: ChatBIState) -> ChatBIState:
        return self.runtime.run_sql_agent(state)


def route_after_preflight(state: ChatBIState) -> RouteName:
    route = state.get("_route") or "run_agent"
    if route == "informational":
        return "informational"
    if route == "enum_lookup":
        return "enum_lookup"
    if route == "failure":
        return "failure"
    if route == "run_agent":
        return "run_agent"
    return "failure"


def route_after_cache_lookup(state: ChatBIState) -> Literal["question_cache", "preflight"]:
    if state.get("_route") == "question_cache":
        return "question_cache"
    return "preflight"
