# 024-M4_thin_client_model_errors

## Thin clients never see model errors

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Low: an unreachable gateway looks like a provider with no models. Change risk: none beyond the linked ticket. |
| reach | Thin clients |
| effort | none beyond the linked ticket |
| evidence | reproduced |
| touches | `chronicler/core/services/system_service.py:25`, `chronicler/core/llm/registry.py` |

### description

`ModelRegistry` lives on a `SystemService`, which is rebuilt for every scope. Over HTTP,
`list_models` and `model_error` are separate requests with separate instances. With an
unreachable gateway, a local call reports `Could not reach http://127.0.0.1:9/v1/models`
and the thin client gets `null`.

Sprint 11 wired up `model_error` specifically to explain this situation.

### related tickets

- (CLOSED BY) [023-S7_model_list_single_call](023-S7_model_list_single_call.md): models and error come back in one response
