import logging
import asyncio
from typing import Dict, Any, List, Optional
from collections import defaultdict
import unicodedata

from src.france_travail_api import FranceTravailClient
from src.cache_manager import get_cached_results, add_to_cache
from src.gemini_extractor import extract_skills_with_gemini, initialize_gemini, consolidate_skills_with_gemini

# --- Configuration du pipeline ---
GEMINI_BATCH_SIZE = 10
TOP_SKILLS_FINAL_LIMIT = 20
CONSOLIDATION_CANDIDATE_LIMIT = 30

def _chunk_list(data: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Divise une liste en sous-listes (chunks) de taille fixe pour le traitement par lots.
    """
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

def _aggregate_results(batch_results: List[Optional[Dict]]) -> Dict[str, Any]:
    """
    Agrège les résultats bruts des lots de Gemini avant la consolidation.
    """
    skill_frequencies = defaultdict(int)
    # Dictionnaire pour garder une version cohérente du nom de la compétence par clé de comptage
    skill_display_names = {}
    education_frequencies = defaultdict(int)

    for result_batch in filter(None, batch_results):
        if 'extracted_data' in result_batch:
            for data_entry in result_batch['extracted_data']:
                processed_skills_for_description = set()
                for skill_raw in data_entry.get('skills', []):
                    skill_stripped = skill_raw.strip()
                    if not skill_stripped:
                        continue
                    
                    # Clé de comptage simple et robuste
                    counting_key = unicodedata.normalize('NFKD', skill_stripped).encode('ascii', 'ignore').decode('utf-8').lower()
                    
                    if counting_key not in skill_display_names:
                        skill_display_names[counting_key] = skill_stripped
                    
                    processed_skills_for_description.add(counting_key)

                for key in processed_skills_for_description:
                    skill_frequencies[key] += 1
                
                education_level = data_entry.get('education_level', 'Non spécifié')
                if education_level and education_level != "Non spécifié":
                    education_frequencies[education_level] += 1

    # Trie les compétences par fréquence pour obtenir le classement initial
    sorted_skills = sorted(skill_frequencies.items(), key=lambda item: item[1], reverse=True)
    
    # Prépare la liste pour la consolidation
    top_skills_unconsolidated = [{"skill": skill_display_names[key], "frequency": freq} for key, freq in sorted_skills]
    
    top_education = max(education_frequencies, key=education_frequencies.get) if education_frequencies else "Non précisé"
    
    return {"skills": top_skills_unconsolidated, "top_diploma": top_education}

async def get_skills_for_job(job_title: str, num_offers: int, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """
    Orchestre le processus complet en deux étapes : extraction puis consolidation.
    """
    logger.info(f"Début du processus pour '{job_title}' ({num_offers} offres).")

    cache_key = f"v2:{job_title}@{num_offers}"
    cached_results = get_cached_results(cache_key)
    if cached_results:
        logger.info(f"Résultats trouvés dans le cache (v2) pour '{cache_key}'.")
        return cached_results

    if not initialize_gemini(logger):
        logger.critical("Échec de l'initialisation de Gemini; abandon du processus.")
        return None

    # ÉTAPE 1: EXTRACTION
    ft_client = FranceTravailClient(logger=logger)
    all_offers = await ft_client.search_offers_async(job_title, max_offers=num_offers)
    if not all_offers:
        logger.warning("Aucune offre France Travail trouvée.")
        return None

    descriptions = [offer['description'] for offer in all_offers if offer.get('description')]
    if not descriptions:
        logger.warning("Aucune description d'offre exploitable trouvée.")
        return None

    description_chunks = _chunk_list(descriptions, GEMINI_BATCH_SIZE)
    tasks = [extract_skills_with_gemini(job_title, chunk, logger) for chunk in description_chunks]
    batch_results = await asyncio.gather(*tasks)
    aggregated_data = _aggregate_results(batch_results)

    if not aggregated_data.get("skills"):
        logger.error("L'extraction initiale n'a produit aucune compétence.")
        return None

    # ÉTAPE 2: CONSOLIDATION
    skills_for_consolidation = [item['skill'] for item in aggregated_data['skills'][:CONSOLIDATION_CANDIDATE_LIMIT]]
    
    if not skills_for_consolidation:
        logger.info("Pas de compétences à consolider, finalisation.")
        final_skills_list = []
    else:
        logger.info(f"Envoi de {len(skills_for_consolidation)} compétences pour la consolidation.")
        final_skills_list = await consolidate_skills_with_gemini(skills_for_consolidation, logger)
        if final_skills_list is None:
             # En cas d'échec de la consolidation, on utilise la liste brute pour ne pas planter
            logger.warning("La consolidation a échoué, utilisation de la liste de compétences brutes.")
            final_skills_list = skills_for_consolidation

    # Construction du résultat final
    final_skills_formatted = [{"skill": skill} for skill in final_skills_list[:TOP_SKILLS_FINAL_LIMIT]]
    
    final_result = {
        "skills": final_skills_formatted,
        "top_diploma": aggregated_data["top_diploma"],
        "actual_offers_count": len(all_offers)
    }

    logger.info(f"Processus terminé. {len(final_result['skills'])} compétences finales agrégées.")
    add_to_cache(cache_key, final_result)
    return final_result