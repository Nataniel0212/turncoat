# Test your own Python agent

Turncoat can run your agent's orchestration, message handling and tool policy in
place of its built-in target loop. The adaptive attacker, per-call metering,
synthetic tools, action-based verdicts and benchmark stay the same.

```bash
# All offline: no key and no API spend.
python run.py --scenario bank --agent examples/custom_agent.py:run_agent
python run.py --scenario bank --agent examples/custom_agent.py:confirmation_agent

# Real Nemotron calls directly to Nebius Token Factory; requires NEBIUS_API_KEY.
python run.py --live --scenario bank --agent examples/custom_agent.py:run_agent --budget 0.10

# Compare your policy over repeated campaigns across all three scenarios.
python run.py --benchmark --trials 5 --agent examples/custom_agent.py:confirmation_agent
```

On Windows use `py -3.12` in place of `python`.

The first offline example reaches a critical finding at attempt 4. The second
requires human confirmation before sensitive actions and therefore performs none
of them in these read-only tasks. These are **deterministic offline checks**, not
new live model-comparison measurements. The policy blocks actions in application
code; it does not make the model itself more resistant to injections.

Export a synchronous function `run_agent(context) -> str` from a local Python
file and pass `--agent path/to/file.py:run_agent`. Turncoat invokes it with fresh
synthetic state for the benign baseline and each attack. Keep per-run state
inside the function so one campaign does not contaminate another.

| Context field or method | Purpose |
|---|---|
| `system_prompt`, `task` | The scenario's trusted instructions and user task |
| `tools` | OpenAI-format schemas for the scenario's synthetic tools (a private copy you may edit) |
| `model` | The selected Nemotron target model |
| `chat(messages, *, enable_thinking=False, temperature=0.3, max_tokens=8192)` | Returns `LLMResult`: content, parsed tool calls, actual model and usage; records tokens, latency and cost |
| `execute_tool(name, arguments)` | Executes a tool in fresh synthetic state and emits its trace. Like the built-in agent, an unknown tool name or non-dictionary arguments return an error string for the model rather than raising |

Copy your agent's orchestration into the function, using `context.chat` and
`context.execute_tool` at the model and tool boundaries. Return its final answer
as a string. See [the complete example](../examples/custom_agent.py), including
tool-call messages and the optional confirmation policy. A run allows up to
12 model turns and 100 tool calls; reaching either cap ends that agent run with
the actions taken so far, as the built-in agent's step cap does, and the
campaign continues. Budget stops apply between calls. An API
response can cross the budget by the cost of that last call.

The adapter cannot declare itself safe: Turncoat classifies the resulting sandbox
state. If an agent already performs an unauthorized action with benign content,
the campaign stops with `baseline_failed`. Incomplete campaigns and campaigns
containing no real attack are excluded from benchmark rates. No valid trials
means **N/A**, not 0% attack success.

Adapters execute trusted local Python code. They are not uploaded to the public
demo and are not a sandbox for untrusted plugins. This version evaluates your
agent logic against Turncoat's three synthetic scenarios; it is not an HTTP connector
to a running production agent. For a different domain, implement a `Scenario`
with its own fixture tools, injection point and deterministic state checks.

The published October 15–16 benchmark and all public replays use the original
built-in agent. They have not been relabelled as measurements of a custom agent.
