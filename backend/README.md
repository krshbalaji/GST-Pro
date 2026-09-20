# GST Pro backend

## Local development

From the `backend` directory, install the pinned test/runtime dependencies before running the suite:

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
```

The repository intentionally supports an explicit `GSTPRO_MODE=demo` development mode. Demo data is process-local and is not presented as production persistence. PostgreSQL persistence is a separate implementation milestone.
