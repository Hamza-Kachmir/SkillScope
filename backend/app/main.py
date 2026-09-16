from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .france_travail import FranceTravailClient, FranceTravailError
from .gemini import GeminiAnalyzer, GeminiError
from .models import AnalysisRequest, AnalysisResponse, JobSuggestion
from .service import cache_key, close_cache, get_cached, initialize_cache, set_cached

settings = get_settings()
ft_client: FranceTravailClient | None = None
gemini_analyzer: GeminiAnalyzer | None = None


@asynccontextmanager
async def lifespan(_: FastAPI):
    global ft_client, gemini_analyzer
    await initialize_cache(settings.redis_url)
    if settings.live_mode:
        ft_client = FranceTravailClient(settings.ft_client_id, settings.ft_client_secret)
    if settings.vertex_ai_configured:
        try:
            gemini_analyzer = GeminiAnalyzer(settings)
        except GeminiError:
            gemini_analyzer = None
    yield
    if ft_client:
        await ft_client.close()
    if gemini_analyzer:
        await gemini_analyzer.close()
    await close_cache()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "mode": "live" if settings.live_mode else "not_configured"}


@app.get("/api/jobs", response_model=list[JobSuggestion])
async def search_jobs(q: str = Query(min_length=2, max_length=80)) -> list[JobSuggestion]:
    if not ft_client:
        raise HTTPException(
            status_code=503,
            detail="France Travail n'est pas configuré. Vérifiez FT_CLIENT_ID et FT_CLIENT_SECRET.",
        )
    try:
        return [JobSuggestion(**job) for job in await ft_client.search_jobs(q)]
    except FranceTravailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze(request: AnalysisRequest) -> AnalysisResponse:
    key = cache_key(request, settings.gemini_model)
    cached = await get_cached(key)
    if cached:
        return cached
    try:
        if not ft_client:
            raise HTTPException(
                status_code=503,
                detail=(
                    "France Travail n'est pas configuré. Vérifiez FT_CLIENT_ID et FT_CLIENT_SECRET."
                ),
            )
        offers = await ft_client.search_offers(request.query)
    except FranceTravailError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not offers:
        raise HTTPException(status_code=404, detail="Aucune offre ne correspond à cette recherche.")
    if not gemini_analyzer:
        raise HTTPException(
            status_code=503,
            detail=(
                "Gemini sur Vertex AI n'est pas configuré. Vérifiez GOOGLE_CLOUD_PROJECT "
                "et GOOGLE_CREDENTIALS dans .env."
            ),
        )
    try:
        result = await gemini_analyzer.analyze(request, offers)
    except GeminiError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    await set_cached(key, result, settings.cache_ttl_seconds)
    return result
