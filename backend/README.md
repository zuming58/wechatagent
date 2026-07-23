# WechatAgent Backend

Local-only FastAPI service for connector probing, idempotent message ingestion, SQLite FTS5 search, contacts, sync state, and source context.

Development defaults to the deterministic synthetic connector. Real-data mode is opt-in:

```powershell
$env:WECHATAGENT_CONNECTOR='wxcli'
python -m app.cli probe
uvicorn app.main:app --host 127.0.0.1 --port 8765
```

The service never binds a public interface by default. Do not place real chat exports, decrypted databases, connector keys, or raw PoC results inside the repository.
