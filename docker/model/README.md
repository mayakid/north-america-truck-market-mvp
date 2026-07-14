# Public Docker model

`ranker.joblib` is a path-sanitized copy of the real BTS model used by the portfolio demo.
It contains no API key or private company data. Regenerate it from the ignored local model with:

```bash
PYTHONPATH=src .venv/bin/python scripts/export_public_artifact.py
```

The exporter rejects synthetic models, failed acceptance gates, local user paths and key-like
metadata before writing the public artifact.
