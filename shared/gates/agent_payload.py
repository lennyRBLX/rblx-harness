"""Normalize documented multi-agent hook fields without reading transcripts."""


def normalize(payload, event):
    normalized = dict(payload)
    if not normalized.get("agent_type") and normalized.get("agent_name"):
        normalized["agent_type"] = normalized["agent_name"]
    if event == "stop" and "last_assistant_message" not in normalized:
        normalized["last_assistant_message"] = None
    return normalized
