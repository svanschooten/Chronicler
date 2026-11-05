# 023-S7_model_list_single_call

## Replace the model registry cache with one call

### info

| | |
| --- | --- |
| importance | medium |
| danger level | Medium: it fixes a real bug. No harm otherwise. Change risk: low. |
| reach | Summaries in all modes |
| effort | S |
| evidence | reproduced |
| touches | `chronicler/core/llm/registry.py`, `chronicler/core/services/system_service.py`, `chronicler/core/models.py`, `chronicler/desktop/app.py`, `chronicler/desktop/state.py`, `tests/chronicler/core/llm/test_llm.py`, `test_system_service.py`, `tests/chronicler/core/test_rpc.py` |

### description

`ModelRegistry` (75 lines) has a 5-minute TTL cache and lives on `SystemService`, which is
rebuilt for every scope. The cache never hits: 3 calls made 3 gateway requests, both over
RPC and across desktop refreshes. `list_models` and `model_error` are also two calls,
which over HTTP means two separate instances.

### proposed fix

1. Replace `list_models()` and `model_error()` with one `list_models()` that returns the
   model IDs and any error together. Move `ModelCheck` from `desktop/state.py` to
   `core/models.py`.
2. Reduce `registry.py` to a function that discovers models, keeping the fallback to the
   configured model.
3. Remove the cache and the `refresh` argument. The desktop already asks only at startup
   and after the configuration changes.
4. Update the API surface count in `test_rpc.py`.

Done when an unreachable gateway reports the same error locally and through a thin client.

### related tickets

- (BLOCKS) [041-S3_services_bundle](041-S3_services_bundle.md): changes `SystemService`
- (CLOSES) [024-M4_thin_client_model_errors](024-M4_thin_client_model_errors.md): models and error come back in one response
