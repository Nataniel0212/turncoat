"""Bring your orchestration to Turncoat, with an optional confirmation policy.

python run.py --agent examples/custom_agent.py:run_agent --scenario bank
python run.py --agent examples/custom_agent.py:confirmation_agent --scenario bank

Both commands use offline fakes unless --live is supplied. Copy your own
message handling, memory and tool policy into this function. Use context.chat
and context.execute_tool as the transport boundaries during the evaluation.
"""
import json


def _run(context, require_confirmation):
    messages = [{"role": "system", "content": context.system_prompt},
                {"role": "user", "content": context.task}]
    sensitive = {"transfer_funds", "send_email", "get_account_secret", "delete_file"}
    for _ in range(6):
        result = context.chat(messages)
        if not result.tool_calls:
            return result.content
        messages.append({"role": "assistant", "content": result.content or None,
                         "tool_calls": [{"id": t["id"], "type": "function", "function": {
                             "name": t["name"], "arguments": json.dumps(t["args"])}}
                             for t in result.tool_calls]})
        for call in result.tool_calls:
            if require_confirmation and call["name"] in sensitive:
                # No user consent exists in these read-only tasks. This is an
                # application policy, not a model robustness improvement.
                output = json.dumps({"error": "Human confirmation required; no action performed."})
            else:
                output = context.execute_tool(call["name"], call["args"])
            messages.append({"role": "tool", "tool_call_id": call["id"], "content": output})
    return "Stopped after six model turns."


def run_agent(context):
    return _run(context, require_confirmation=False)


def confirmation_agent(context):
    return _run(context, require_confirmation=True)
