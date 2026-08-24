"""The decision loop: given what the agent currently perceives, decide the next action.
No implementation is wired in yet -- this is where a call to an LLM (e.g. the Claude API,
with vision + a voice transcript) will eventually live.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class AgentContext:
    """What the brain saw when it made a decision: a screenshot and/or a voice command."""

    screenshot_png: bytes | None
    voice_command: str | None


@dataclass(frozen=True)
class AgentAction:
    """Base marker for the concrete action dataclasses below. Intentionally data-only:
    deciding an action and executing it (via input_injector) are separate steps, so every
    action can be logged and, for anything destructive, confirmed before it runs."""


@dataclass(frozen=True)
class NoOp(AgentAction):
    pass


@dataclass(frozen=True)
class ClickAt(AgentAction):
    x: int
    y: int


@dataclass(frozen=True)
class TypeText(AgentAction):
    text: str


@dataclass(frozen=True)
class Speak(AgentAction):
    text: str


class AgentBrain(Protocol):
    async def decide_next_action(self, context: AgentContext) -> AgentAction: ...


class StubAgentBrain:
    """Never acts. Placeholder until a real brain is wired in."""

    async def decide_next_action(self, context: AgentContext) -> AgentAction:
        return NoOp()
