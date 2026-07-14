# syntax=docker/dockerfile:1.7

FROM python:3.12-slim-bookworm AS runtime

ENV CROSSBORDER_PROJECT_ROOT=/app \
    MODEL_ARTIFACT_PATH=/app/artifacts/ranker.joblib \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    OMP_NUM_THREADS=2 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install .

RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home app \
    && mkdir -p /app/artifacts /app/data/raw /app/data/processed /app/rag_storage \
    && chown -R app:app /app

COPY --chown=app:app data/reference ./data/reference
COPY --chown=app:app knowledge ./knowledge
COPY --chown=app:app docker/model/ranker.joblib ./artifacts/ranker.joblib

USER app

EXPOSE 8000

CMD ["crossborder", "serve", "--host", "0.0.0.0", "--port", "8000"]
