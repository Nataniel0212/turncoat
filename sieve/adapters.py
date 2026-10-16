"""Local Python adapter for an agent's own orchestration and tool policy.

An adapter exports run_agent(context) -> str. Its model calls go through the
metered Nebius client, and its tools use Turncoat's synthetic environment so the
verdict still comes from actions. Loading Python executes trusted local code;
this interface is intentionally not exposed by the public web API.
"""
from __future__ import annotations

import copy
import importlib.util
import sys
import uuid
from pathlib import Path

from .target_agent import TargetRun

MAX_MODEL_TURNS = 12
MAX_TOOL_CALLS = 100


class AgentLimit(Exception):
    """An adapter hit a per-run cap. The run ends with the actions taken so far,
    like the built-in loop's step cap, instead of aborting the whole campaign."""


class AgentContext:
    def __init__(self, client, cfg, meter, scenario, env, attempt, phase, on_event):
        self.system_prompt = scenario.system_prompt
        self.task = scenario.user_task
        # A private copy: an adapter that edits its tool list must not change the
        # shared scenario seen by later campaigns and the built-in loop.
        self.tools = copy.deepcopy(scenario.tools)
        self.model = cfg.model_target
        self._client, self._meter = client, meter
        self._scenario, self._env = scenario, env
        self._attempt, self._phase = attempt, phase
        self._emit = on_event or (lambda _event: None)
        self._calls = 0
        self._tool_calls = 0

    def chat(self, messages: list[dict], *, enable_thinking: bool = False,
             temperature: float = 0.3, max_tokens: int = 8192):
        """Same LLMResult as the built-in loop, with cost and event accounting.
        The campaign's BudgetedClient refuses the call once the budget is spent."""
        if self._calls >= MAX_MODEL_TURNS:
            raise AgentLimit(f"{MAX_MODEL_TURNS} model turns")
        if not 1 <= max_tokens <= 8192:
            raise ValueError("Adapter max_tokens must be between 1 and 8192")
        self._calls += 1
        result = self._client.chat(
            model=self.model, messages=messages, tools=self.tools,
            max_tokens=max_tokens, enable_thinking=enable_thinking,
            force_nonempty=True, temperature=temperature)
        self._meter.record(self._phase, self._attempt, result)
        return result

    def execute_tool(self, name: str, arguments: dict) -> str:
        """Execute against synthetic state and emit the same trace as the demo.

        As in the built-in loop, a bad call (an invented tool name, which fake
        tool-call injections invite, or malformed arguments) returns an error
        string for the model instead of aborting the campaign.
        """
        self._tool_calls += 1
        if self._tool_calls > MAX_TOOL_CALLS:
            raise AgentLimit(f"{MAX_TOOL_CALLS} tool calls")
        if isinstance(arguments, dict):
            result = self._scenario.execute(name, arguments, self._env)
        else:
            result = "Error: tool arguments must be a JSON object"
        self._emit({"type": "tool", "phase": self._phase, "attempt": self._attempt,
                    "name": name, "args": arguments, "result": str(result)[:400]})
        return result


def load_adapter(spec: str):
    """Load /path/to/agent.py:run_agent (rsplit also handles Windows drives)."""
    path_text, sep, function_name = spec.rpartition(":")
    if not sep or not function_name.isidentifier():
        raise ValueError("Use --agent path/to/agent.py:run_agent")
    path = Path(path_text).expanduser().resolve()
    if not path.is_file() or path.suffix != ".py":
        raise ValueError(f"Adapter must be an existing Python file: {path}")
    module_spec = importlib.util.spec_from_file_location(f"sieve_adapter_{uuid.uuid4().hex}", path)
    module = importlib.util.module_from_spec(module_spec)
    # Decorators such as dataclass resolve postponed annotations via sys.modules.
    sys.modules[module_spec.name] = module
    try:
        module_spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop(module_spec.name, None)
        raise
    agent = getattr(module, function_name, None)
    if not callable(agent):
        raise ValueError(f"Adapter has no callable named {function_name}")

    def run(client, cfg, meter, attempt, injection_text, scenario, phase="target", on_event=None):
        env = scenario.new_env(injection_text)
        context = AgentContext(client, cfg, meter, scenario, env, attempt, phase, on_event)
        try:
            final_text = agent(context)
        except AgentLimit:
            final_text = ""  # the sandbox state, not the reply, decides the verdict
        if not isinstance(final_text, str):
            raise TypeError("An agent adapter must return its final answer as a string")
        return TargetRun(env, final_text)

    run.adapter_name = f"{path.name}:{function_name}"
    return run
