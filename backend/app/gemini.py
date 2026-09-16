import asyncio
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Any, Literal

from google import genai
from google.auth.exceptions import DefaultCredentialsError
from google.genai import errors, types
from google.oauth2 import service_account
from pydantic import BaseModel, Field

from .config import Settings
from .models import AnalysisRequest, AnalysisResponse, EducationResult, SkillResult
from .normalizer import display_label, search_key

EducationLevel = Literal[
    "CAP / BEP",
    "Bac",
    "Bac+2 / BTS",
    "Bac+3 / Licence",
    "Bac+5 / Master",
    "Doctorat",
    "Formation spécifique",
    "Non spécifié",
]
SkillKind = Literal["technology", "tool", "method", "professional_skill"]
Specificity = Literal["named", "specific", "general"]


class GeminiError(RuntimeError):
    pass


class ExtractedSkill(BaseModel):
    name: str = Field(description="Nom court, précis et normalisé de la compétence")
    kind: SkillKind = "professional_skill"
    specificity: Specificity = "specific"


class OfferExtraction(BaseModel):
    index: int
    skills: list[ExtractedSkill]
    education_level: EducationLevel = "Non spécifié"


class ExtractionBatch(BaseModel):
    offers: list[OfferExtraction]


class ConsolidatedSkill(BaseModel):
    name: str
    variants: list[str]


class ConsolidationResult(BaseModel):
    skills: list[ConsolidatedSkill]


EXTRACTION_INSTRUCTION = """
Tu extrais les compétences réellement demandées dans des offres d'emploi françaises.

Règles impératives :
- Vérifie d'abord que chaque offre correspond réellement au métier recherché. Pour une offre
  hybride, ne conserve que les compétences liées à la partie du poste correspondant au métier.
- Garde toutes les technologies, tous les langages, frameworks, bibliothèques, logiciels,
  bases de données, outils, plateformes, méthodes et savoir-faire professionnels concrets
  explicitement demandés.
- Extrais une compétence atomique par élément. Sépare React, Angular, JavaScript, TypeScript,
  Python, SQL, Docker ou Excel lorsqu'ils sont nommés. Ne les remplace jamais par une catégorie
  parente comme « développement front-end », « programmation », « bureautique », « cloud » ou
  « informatique ».
- Pour une technologie ou un logiciel nommé, utilise son nom officiel seul : « Angular » plutôt
  que « Développement Frontend Angular », « Microsoft Excel » plutôt que « Maîtrise d'Excel ».
  Classe-la comme technology ou tool et avec la specificity named.
- Ne sépare pas les expressions consacrées qui forment une seule pratique, comme CI/CD, ETL/ELT,
  UX/UI ou hygiène et sécurité.
- Une compétence doit être attendue du candidat pour exercer les missions principales du poste.
  Exclue les outils et équipements liés à une tâche marginale ou à un autre métier présent dans
  l'offre.
- Privilégie les compétences spécifiques et utiles à un candidat : Python, SQL, Spark,
  Docker, ETL, modélisation de données, gestion de projet, par exemple.
- Exclue l'intitulé du poste et ses synonymes (Data Engineer, Data Scientist, etc.).
- Exclue les domaines ou mots trop généraux isolés (informatique, architecture, cycle,
  français, système d'information, données, design, équipe, entreprise, projet).
- Exclue les qualités personnelles vagues et les missions qui ne nomment aucun savoir-faire.
- Refuse les libellés ambigus ou trop courts comme « animation », « suivi » ou « gestion ».
  Conserve-les uniquement sous une forme précise explicitement justifiée par le texte, comme
  « animation d'ateliers » ou « gestion des appels entrants ».
- N'invente rien : une compétence doit être présente dans la description ou dans les
  compétences déclarées de l'offre.
- Pour les savoir-faire non technologiques, conserve un libellé autonome avec une action et son
  objet : « gestion du standard téléphonique » plutôt que « gestion ».
- Une catégorie générale n'est acceptable que si l'offre ne fournit aucune compétence plus
  précise pour la même exigence. Elle ne doit jamais remplacer ses compétences enfants.
- Normalise les variantes évidentes vers leur nom usuel, sans fusionner des technologies ou des
  savoir-faire distincts : JavaScript et TypeScript, SQL et PostgreSQL restent séparés.
- Commence chaque libellé par une majuscule et respecte la casse officielle des acronymes,
  technologies, logiciels, langages et marques.
- Pour le niveau d'études, utilise les formations structurées et le texte. Ne déduis jamais
  un diplôme à partir du métier.
- Retourne exactement une entrée pour chaque index reçu, même si ses listes sont vides.
""".strip()

CONSOLIDATION_INSTRUCTION = """
Regroupe uniquement les variantes strictement synonymes qui désignent exactement la même
compétence, au même niveau de précision.
Le nom canonique doit obligatoirement être l'un des libellés fournis. N'invente aucune catégorie
parente et ne combine jamais plusieurs libellés pour en créer un nouveau.
Choisis parmi les variantes un nom professionnel concis, autonome et suffisamment précis.
Ne raccourcis jamais un savoir-faire précis en catégorie vague : conserve par exemple
« animation d'ateliers » plutôt que « animation », « formation des équipes » plutôt que
« formation » et « maîtrise de l'anglais » plutôt que « langues ».
Ne fusionne jamais deux technologies, outils, méthodes ou savoir-faire distincts. JavaScript et
TypeScript, React et Angular, SQL et PostgreSQL, AWS et Azure doivent rester dans des groupes
séparés.
Utilise le métier fourni uniquement pour comprendre les ellipses de contexte. Par exemple, pour
un métier alimentaire, « hygiène et sécurité » et « hygiène et sécurité alimentaires » peuvent
désigner la même compétence si les libellés ne décrivent pas deux exigences différentes. Cette
règle ne permet jamais de fusionner des outils, technologies ou gestes professionnels distincts.
Chaque libellé fourni doit apparaître dans exactement une liste variants.
Commence chaque nom canonique par une majuscule et respecte la casse officielle des acronymes,
technologies, logiciels, langages et marques.
""".strip()


def _clean_text(value: str, limit: int = 8_000) -> str:
    value = re.sub(r"<[^>]+>", " ", value)
    value = " ".join(value.split())
    return value[:limit]


def _offer_id(offer: dict[str, Any], index: int) -> str:
    return str(offer.get("id") or offer.get("reference") or f"offer-{index + 1}")


def _is_job_title_fragment(skill_name: str, job_title: str) -> bool:
    skill_key = search_key(skill_name)
    title_key = search_key(job_title)
    if not skill_key or not title_key:
        return False
    return skill_key == title_key or (len(skill_key) >= 4 and f" {skill_key} " in f" {title_key} ")


class GeminiAnalyzer:
    def __init__(self, settings: Settings) -> None:
        credentials = None
        if settings.google_credentials:
            try:
                credentials_info = json.loads(settings.google_credentials)
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"],
                )
            except (ValueError, TypeError, KeyError) as exc:
                raise GeminiError(
                    "GOOGLE_CREDENTIALS ne contient pas une clé de compte de service valide."
                ) from exc
        self.model = settings.gemini_model
        self.batch_size = settings.gemini_batch_size
        self._semaphore = asyncio.Semaphore(settings.gemini_concurrency)
        self._extraction_cache: dict[str, OfferExtraction] = {}
        try:
            self._client = genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
                credentials=credentials,
                http_options=types.HttpOptions(api_version="v1"),
            )
        except DefaultCredentialsError as exc:
            raise GeminiError(
                "Authentification Google Cloud absente. Exécutez "
                "'gcloud auth application-default login' puis redémarrez Docker."
            ) from exc

    async def close(self) -> None:
        await self._client.aio.aclose()

    async def _generate(self, contents: str, schema: type[BaseModel], max_tokens: int) -> Any:
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                async with self._semaphore:
                    response = await self._client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            temperature=0,
                            max_output_tokens=max_tokens,
                            response_mime_type="application/json",
                            response_schema=schema,
                        ),
                    )
                payload = response.parsed
                if payload is None:
                    payload = json.loads(response.text or "{}")
                return schema.model_validate(payload)
            except (errors.APIError, ValueError, TypeError, json.JSONDecodeError) as exc:
                last_error = exc
                code = getattr(exc, "code", None)
                if code not in {429, 500, 502, 503, 504} or attempt == 2:
                    break
                await asyncio.sleep(0.8 * (2**attempt))
        raise GeminiError(
            "Gemini n'a pas pu analyser les offres. Vérifiez le projet, le compte de "
            "service, l'API Google Cloud et le quota disponible."
        ) from last_error

    @staticmethod
    def _extraction_cache_key(job_title: str, offer: dict[str, Any], index: int) -> str:
        content = json.dumps(
            {
                "title": offer.get("intitule", ""),
                "description": offer.get("description", ""),
                "skills": offer.get("competences") or [],
                "education": offer.get("formations") or [],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        fingerprint = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        return f"{search_key(job_title)}|{_offer_id(offer, index)}|{fingerprint}"

    async def _extract_batch(
        self, job_title: str, indexed_offers: list[tuple[int, dict[str, Any]]]
    ) -> ExtractionBatch:
        jobs = []
        for index, offer in indexed_offers:
            jobs.append(
                {
                    "index": index,
                    "title": offer.get("intitule", ""),
                    "description": _clean_text(str(offer.get("description", ""))),
                    "declared_skills": [
                        str(skill.get("libelle", ""))
                        for skill in offer.get("competences") or []
                        if skill.get("libelle")
                    ],
                    "education": [
                        str(
                            formation.get("niveauLibelle")
                            or formation.get("niveauCommentaire")
                            or ""
                        )
                        for formation in offer.get("formations") or []
                    ],
                }
            )
        prompt = (
            f"{EXTRACTION_INSTRUCTION}\n\nMétier recherché : {job_title}\n\n"
            f"Offres à analyser :\n{json.dumps(jobs, ensure_ascii=False)}"
        )
        return await self._generate(prompt, ExtractionBatch, 12_000)

    async def _consolidate(self, job_title: str, labels: list[str]) -> dict[str, str]:
        if not labels:
            return {}
        prompt = (
            f"{CONSOLIDATION_INSTRUCTION}\n\nMétier : {job_title}\n\n"
            f"Libellés :\n{json.dumps(labels, ensure_ascii=False)}"
        )
        result: ConsolidationResult = await self._generate(prompt, ConsolidationResult, 6_000)
        mapping: dict[str, str] = {}
        available = {search_key(label): label for label in labels}
        for group in result.skills:
            variant_keys = [
                key
                for variant in [group.name, *group.variants]
                if (key := search_key(variant)) in available
            ]
            if not variant_keys:
                continue
            canonical_key = search_key(group.name)
            if canonical_key not in available:
                canonical_key = variant_keys[0]
            canonical = available[canonical_key]
            for key in variant_keys:
                mapping[key] = canonical
        return mapping

    async def analyze(
        self,
        request: AnalysisRequest,
        offers: list[dict[str, Any]],
    ) -> AnalysisResponse:
        if len(self._extraction_cache) > 5_000:
            self._extraction_cache.clear()

        indexed = list(enumerate(offers))
        extractions: dict[int, OfferExtraction] = {}
        pending: list[tuple[int, dict[str, Any]]] = []
        for index, offer in indexed:
            cached = self._extraction_cache.get(
                self._extraction_cache_key(request.query, offer, index)
            )
            if cached:
                extractions[index] = cached.model_copy(update={"index": index})
            else:
                pending.append((index, offer))

        batches = [
            pending[start : start + self.batch_size]
            for start in range(0, len(pending), self.batch_size)
        ]
        results = await asyncio.gather(
            *(self._extract_batch(request.query, batch) for batch in batches),
            return_exceptions=True,
        )

        def collect(result: ExtractionBatch) -> None:
            for extraction in result.offers:
                if 0 <= extraction.index < len(offers):
                    extractions[extraction.index] = extraction
                    offer = offers[extraction.index]
                    cache_key = self._extraction_cache_key(request.query, offer, extraction.index)
                    self._extraction_cache[cache_key] = extraction.model_copy()

        for result in results:
            if isinstance(result, ExtractionBatch):
                collect(result)

        missing = [item for item in indexed if item[0] not in extractions]
        retry_size = max(1, min(10, self.batch_size // 2))
        for start in range(0, len(missing), retry_size):
            retry_batch = missing[start : start + retry_size]
            try:
                collect(await self._extract_batch(request.query, retry_batch))
            except GeminiError:
                continue

        if not extractions:
            first_error = next(
                (result for result in results if isinstance(result, Exception)), None
            )
            if isinstance(first_error, GeminiError):
                raise first_error
            raise GeminiError("Gemini n'a renvoyé aucune analyse exploitable.")
        if len(extractions) != len(offers):
            raise GeminiError(
                "Gemini n'a pas analysé toutes les offres. Réessayez dans quelques instants."
            )

        raw_counts: Counter[str] = Counter()
        raw_labels: dict[str, str] = {}
        for extraction in extractions.values():
            for skill in extraction.skills:
                key = search_key(skill.name)
                if key and not _is_job_title_fragment(skill.name, request.query):
                    raw_counts[key] += 1
                    raw_labels.setdefault(key, " ".join(skill.name.split()))
        candidates = [raw_labels[key] for key, _ in raw_counts.most_common(80)]
        try:
            canonical_map = await self._consolidate(request.query, candidates)
        except GeminiError:
            canonical_map = {}

        counts: Counter[str] = Counter()
        education_counts: Counter[str] = Counter()
        usable_offers = 0
        for extraction in extractions.values():
            per_offer: set[str] = set()
            for skill in extraction.skills:
                raw_key = search_key(skill.name)
                if not raw_key or _is_job_title_fragment(skill.name, request.query):
                    continue
                name = display_label(canonical_map.get(raw_key, " ".join(skill.name.split())))
                if _is_job_title_fragment(name, request.query):
                    continue
                per_offer.add(name)
            if per_offer:
                usable_offers += 1
            for name in per_offer:
                counts[name] += 1
            if extraction.education_level != "Non spécifié":
                education_counts[extraction.education_level] += 1

        denominator = len(offers) or 1
        minimum_occurrences = 2 if len(offers) >= 20 else 1
        skills = [
            SkillResult(
                name=name,
                offer_count=count,
                percentage=round(count / denominator * 100, 1),
            )
            for name, count in sorted(
                counts.items(), key=lambda item: (-item[1], item[0].casefold())
            )
            if count >= minimum_occurrences
        ][:10]
        education = [
            EducationResult(
                level=level,
                offer_count=count,
                percentage=round(count / denominator * 100, 1),
            )
            for level, count in sorted(
                education_counts.items(), key=lambda item: (-item[1], item[0])
            )
        ]
        return AnalysisResponse(
            query=request.query,
            generated_at=datetime.now(UTC),
            total_offers=len(offers),
            usable_offers=usable_offers,
            coverage_percentage=(round(usable_offers / denominator * 100, 1) if offers else 0),
            skills=skills,
            education_levels=education,
        )
