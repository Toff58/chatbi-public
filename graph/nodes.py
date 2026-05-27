from typing import Literal

from graph.agent import ChatBIAgentApp
from graph.state import ChatBIState


RouteName = Literal["informational", "enum_lookup", "failure", "run_agent"]


class ChatBIWorkflowNodes:
    """LangGraph node adapter around the ChatBI agent runtime."""

    def __init__(self, runtime: ChatBIAgentApp | None = None) -> None:
        self.runtime = runtime or ChatBIAgentApp()

    def retrieve_context(self, state: ChatBIState) -> dict:
        return self.runtime.retrieve_context(state)

    def preflight_guardrails(self, state: ChatBIState) -> dict:
        return self.runtime.preflight_guardrails(state)

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
