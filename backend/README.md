# WechatAgent Backend

Local-only FastAPI service for connector probing, idempotent message ingestion, SQLite FTS5 search, contacts, sync state, and source context.

Development defaults to the deterministic synthetic connector. The current verification environment remains at `connector_missing`; Go/No-Go verification has not been authorized. Do not install or execute `wx-cli` as part of local development or automated testing.

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m pytest -q
```

The service never binds a public interface by default. Do not place real chat exports, decrypted databases, connector keys, raw PoC results, or local account paths inside the repository.
