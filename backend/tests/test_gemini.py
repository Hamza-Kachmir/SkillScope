import asyncio

from app.gemini import (
    ExtractedSkill,
    ExtractionBatch,
    GeminiAnalyzer,
    OfferExtraction,
    _is_job_title_fragment,
)
from app.models import AnalysisRequest


def test_job_title_fragments_are_not_skills() -> None:
    assert _is_job_title_fragment("Accueil", "Chargé / Chargée d'accueil")
    assert _is_job_title_fragment("Data engineer", "Data engineer")
    assert not _is_job_title_fragment("Gestion du standard", "Chargé d'accueil")


def test_gemini_analysis_counts_once_per_offer_and_excludes_job_title() -> None:
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.batch_size = 10
    analyzer._extraction_cache = {}

    async def fake_extract_batch(job_title, indexed_offers):
        assert job_title == "Data engineer"
        assert len(indexed_offers) == 2
        return ExtractionBatch(
            offers=[
                OfferExtraction(
                    index=0,
                    skills=[
                        ExtractedSkill(name="Python"),
                        ExtractedSkill(name="Python"),
                        ExtractedSkill(name="Data engineer"),
                    ],
                    education_level="Bac+5 / Master",
                ),
                OfferExtraction(
                    index=1,
                    skills=[
                        ExtractedSkill(name="Python"),
                        ExtractedSkill(name="SQL"),
                    ],
                ),
            ]
        )

    async def fake_consolidate(job_title, labels):
        assert job_title == "Data engineer"
        return {label.casefold(): label for label in labels}

    analyzer._extract_batch = fake_extract_batch
    analyzer._consolidate = fake_consolidate
    offers = [{"id": "a"}, {"id": "b"}]
    result = asyncio.run(analyzer.analyze(AnalysisRequest(query="Data engineer"), offers))

    assert [skill.name for skill in result.skills] == ["Python", "SQL"]
    assert result.skills[0].offer_count == 2
    assert result.education_levels[0].level == "Bac+5 / Master"


def test_gemini_reuses_offer_extractions_when_the_sample_grows() -> None:
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.batch_size = 20
    analyzer._extraction_cache = {}
    batch_sizes: list[int] = []

    async def fake_extract_batch(job_title, indexed_offers):
        batch_sizes.append(len(indexed_offers))
        return ExtractionBatch(
            offers=[
                OfferExtraction(
                    index=index,
                    skills=[ExtractedSkill(name="Python")],
                )
                for index, _ in indexed_offers
            ]
        )

    async def fake_consolidate(job_title, labels):
        return {label.casefold(): label for label in labels}

    analyzer._extract_batch = fake_extract_batch
    analyzer._consolidate = fake_consolidate
    request = AnalysisRequest(query="Data scientist")

    asyncio.run(analyzer.analyze(request, [{"id": "a"}, {"id": "b"}]))
    asyncio.run(
        analyzer.analyze(
            request,
            [{"id": "a"}, {"id": "b"}, {"id": "c"}],
        )
    )

    assert batch_sizes == [2, 1]


def test_gemini_retries_missing_offers_in_smaller_batches() -> None:
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.batch_size = 4
    analyzer._extraction_cache = {}
    batch_sizes: list[int] = []

    async def fake_extract_batch(job_title, indexed_offers):
        batch_sizes.append(len(indexed_offers))
        selected = indexed_offers if len(batch_sizes) > 1 else indexed_offers[:-1]
        return ExtractionBatch(
            offers=[
                OfferExtraction(index=index, skills=[ExtractedSkill(name="Python")])
                for index, _ in selected
            ]
        )

    async def fake_consolidate(job_title, labels):
        return {label.casefold(): label for label in labels}

    analyzer._extract_batch = fake_extract_batch
    analyzer._consolidate = fake_consolidate
    offers = [{"id": str(index)} for index in range(4)]

    result = asyncio.run(
        analyzer.analyze(
            AnalysisRequest(query="Data engineer"),
            offers,
        )
    )

    assert batch_sizes == [4, 1]
    assert result.usable_offers == 4


def test_gemini_excludes_isolated_skills_from_large_samples() -> None:
    analyzer = GeminiAnalyzer.__new__(GeminiAnalyzer)
    analyzer.batch_size = 20
    analyzer._extraction_cache = {}

    async def fake_extract_batch(job_title, indexed_offers):
        extractions = []
        for index, _ in indexed_offers:
            skills = []
            if index < 2:
                skills.append(ExtractedSkill(name="Relation client"))
            if index == 0:
                skills.append(ExtractedSkill(name="Transpalette électrique"))
            extractions.append(OfferExtraction(index=index, skills=skills))
        return ExtractionBatch(offers=extractions)

    async def fake_consolidate(job_title, labels):
        return {label.casefold(): label for label in labels}

    analyzer._extract_batch = fake_extract_batch
    analyzer._consolidate = fake_consolidate
    offers = [{"id": str(index)} for index in range(20)]

    result = asyncio.run(
        analyzer.analyze(
            AnalysisRequest(query="Chargé d'accueil"),
            offers,
        )
    )

    assert [skill.name for skill in result.skills] == ["Relation client"]
