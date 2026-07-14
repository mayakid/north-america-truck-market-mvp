"""FastAPI application."""

from __future__ import annotations

from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from .exceptions import (
    DataUnavailableError,
    ExternalServiceError,
    IncompleteInputError,
    InvalidInputError,
    ModelUnavailableError,
    RecommenderError,
)
from .rag import lightrag_is_available
from .schemas import (
    HealthResponse,
    ParsedRequest,
    ParseRequest,
    RecommendationResponse,
    RecommendRequest,
)
from .service import RecommendationService
from .settings import get_settings

app = FastAPI(
    title="Canada Cross-Border Truck Market Opportunity API",
    version="0.1.0",
    description="Province-level opportunity ranking from BTS TransBorder Freight Data.",
)


@lru_cache(maxsize=1)
def get_service() -> RecommendationService:
    return RecommendationService(get_settings())


@app.exception_handler(IncompleteInputError)
async def incomplete_input_handler(_, exc: IncompleteInputError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": "incomplete_input",
            "message": str(exc),
            "missing_fields": exc.missing_fields,
        },
    )


@app.exception_handler(InvalidInputError)
async def invalid_input_handler(_, exc: InvalidInputError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"error": "invalid_input", "message": str(exc)})


async def unavailable_handler(_, exc: RecommenderError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"error": "unavailable", "message": str(exc)})


app.add_exception_handler(DataUnavailableError, unavailable_handler)
app.add_exception_handler(ModelUnavailableError, unavailable_handler)


@app.exception_handler(ExternalServiceError)
async def external_handler(_, exc: ExternalServiceError) -> JSONResponse:
    return JSONResponse(
        status_code=502,
        content={"error": "external_service_error", "message": str(exc)},
    )


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    settings = get_settings()
    model_ready = settings.model_artifact_path.exists()
    feature_ready = settings.feature_snapshot_path.exists()
    return HealthResponse(
        status="ok" if model_ready else "degraded",
        model_ready=model_ready,
        feature_snapshot_ready=feature_ready,
        deepseek_configured=settings.deepseek_api_key is not None,
        lightrag_available=lightrag_is_available(),
    )


@app.post("/v1/parse", response_model=ParsedRequest)
def parse_request(body: ParseRequest) -> ParsedRequest:
    return get_service().parse(body.query)


@app.post("/v1/recommend", response_model=RecommendationResponse)
async def recommend(body: RecommendRequest) -> RecommendationResponse:
    try:
        return await get_service().recommend(query=body.query, structured=body.structured)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
