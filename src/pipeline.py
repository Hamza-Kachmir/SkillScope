import logging
import asyncio
from typing import Dict, Any, List, Optional
from collections import defaultdict
import re
import unicodedata

from src.france_travail_api import FranceTravailClient
from src.cache_manager import get_cached_results, add_to_cache
from src.gemini_extractor import extract_skills_with_gemini, initialize_gemini

# Configuration pour l'analyse des offres et les lots Gemini.
GEMINI_BATCH_SIZE = 5  # Définit la taille des lots de descriptions pour Gemini.
TOP_SKILLS_LIMIT = 20 # Nombre maximum de compétences à afficher dans le classement final.

# Liste de mots (prépositions, articles, etc.) à laisser en minuscule lors de la capitalisation des compétences.
_LOWERCASE_WORDS = {'de', 'des', 'du', 'la', 'le', 'les', 'l\'', 'à', 'aux', 'et', 'ou', 'd\'', 'un', 'une', 'pour', 'avec', 'sans', 'sur', 'dans', 'en', 'par', 'est', 'sont'}

def _standardize_skill_python(skill_name: str) -> str:
    """
    Normalise une compétence en Python pour le comptage et l'affichage des résultats.
    Cette fonction post-traite les inconsistances de Gemini sur la casse et le singulier/pluriel.
    """
    original_stripped = skill_name.strip()

    # Conserve la casse des acronymes ou chaînes tout en majuscules.
    if original_stripped.isupper() and len(original_stripped) > 1 and ' ' not in original_stripped:
        return original_stripped

    # Applique une capitalisation spécifique pour les termes connus.
    if original_stripped.lower() == "power bi": return "Power BI"
    if original_stripped.lower() == "microsoft excel": return "Microsoft Excel"
    if original_stripped.lower() == "big data": return "Big Data"
    if original_stripped.lower() == "machine learning": return "Machine Learning"
    if original_stripped.lower() == "veille technologique": return "Veille Technologique"
    if original_stripped.lower() == "soins aux animaux": return "Soins Aux Animaux"
    if original_stripped.lower() == "soins des animaux": return "Soins Aux Animaux"
    if original_stripped.lower() == "alimentation": return "Alimentation"
    if original_stripped.lower() == "decoupe": return "Découpe"
    if original_stripped.lower() == "preparation": return "Préparation"
    if original_stripped.lower() == "vente": return "Vente"
    if original_stripped.lower() == "mise en valeur des produits": return "Mise En Valeur Des Produits"


    # Convertit la compétence en minuscule pour faciliter le traitement.
    lower_case_skill = original_stripped.lower()

    # Tente une singularisation simple en supprimant le 's' final.
    singularized_skill = lower_case_skill
    if singularized_skill.endswith('s') and len(singularized_skill) > 2 and not singularized_skill.endswith('ss'):
        singularized_skill = singularized_skill[:-1]

    # Capitalise intelligemment les mots pour l'affichage des compétences.
    words = singularized_skill.split()
    capitalized_words = []
    for i, word in enumerate(words):
        if i > 0 and word.lower() in _LOWERCASE_WORDS:
            capitalized_words.append(word.lower())
        else:
            capitalized_words.append(word.capitalize())

    return ' '.join(capitalized_words)


def _chunk_list(data: List[Any], chunk_size: int) -> List[List[Any]]:
    """
    Divise une liste en sous-listes (chunks) de taille fixe pour le traitement par lots.
    """
    return [data[i:i + chunk_size] for i in range(0, len(data), chunk_size)]

def _aggregate_results(batch_results: List[Optional[Dict]]) -> Dict[str, Any]:
    """
    Agrège et compte les compétences et niveaux d'études extraits des différents lots Gemini.
    Cette fonction applique une normalisation Python finale pour la déduplication et la standardisation.
    """
    skill_frequencies_normalized_key = defaultdict(int)
    skill_display_names = {}

    education_frequencies = defaultdict(int)

    for result_batch in filter(None, batch_results):
        if 'extracted_data' in result_batch:
            for data_entry in result_batch['extracted_data']:
                # Utilise un ensemble pour dédupliquer les compétences au sein d'une même description après normalisation.
                processed_skills_for_this_description = set()

                for skill_raw in data_entry.get('skills', []):
                    skill_stripped = skill_raw.strip()
                    if not skill_stripped:
                        continue

                    standardized_skill = _standardize_skill_python(skill_stripped)

                    # La clé de comptage est une version en minuscule et sans accent pour une déduplication parfaite.
                    counting_key = unicodedata.normalize('NFKD', standardized_skill).encode('ascii', 'ignore').decode('utf-8').lower()

                    if counting_key not in skill_display_names:
                        skill_display_names[counting_key] = standardized_skill

                    processed_skills_for_this_description.add(counting_key)

                for skill_key_for_counting in processed_skills_for_this_description:
                    skill_frequencies_normalized_key[skill_key_for_counting] += 1

                education_level = data_entry.get('education_level', 'Non spécifié')
                if education_level and education_level != "Non spécifié":
                    education_frequencies[education_level] += 1

    # Trie les compétences par fréquence d'apparition.
    sorted_skills = sorted(skill_frequencies_normalized_key.items(), key=lambda item: item[1], reverse=True)
    top_skills = [{"skill": skill_display_names[skill_key], "frequency": freq} for skill_key, freq in sorted_skills[:TOP_SKILLS_LIMIT]]

    # Détermine le niveau d'études le plus fréquemment demandé.
    top_education = max(education_frequencies, key=education_frequencies.get) if education_frequencies else "Non précisé"

    return {"skills": top_skills, "top_diploma": top_education}

async def get_skills_for_job(job_title: str, num_offers: int, logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """
    Orchestre le processus complet d'extraction de compétences : vérification du cache,
    recherche d'offres d'emploi, extraction via Gemini et agrégation des résultats.
    """
    logger.info(f"Début du processus pour '{job_title}' ({num_offers} offres).")

    cache_key = f"{job_title}@{num_offers}"
    cached_results = get_cached_results(cache_key)
    if cached_results:
        logger.info(f"Résultats trouvés dans le cache pour '{cache_key}'. Fin du processus.")
        return cached_results
    logger.info(f"Aucun résultat en cache pour '{cache_key}', poursuite de l'analyse.")

    if not initialize_gemini(logger):
        logger.critical("Échec de l'initialisation de Gemini; abandon du processus.")
        return None

    logger.info(f"Appel à l'API France Travail pour '{job_title}'.")
    ft_client = FranceTravailClient(logger=logger)
    all_offers = await ft_client.search_offers_async(job_title, max_offers=num_offers)

    if not all_offers:
        logger.warning("Aucune offre France Travail trouvée; fin du processus.")
        return None

    descriptions = [offer['description'] for offer in all_offers if offer.get('description')]
    if not descriptions:
        logger.warning("Aucune description d'offre exploitable trouvée; fin du processus.")
        return None
    logger.info(f"{len(all_offers)} offres trouvées, dont {len(descriptions)} avec une description valide.")

    # Division des descriptions en lots pour un traitement parallèle par Gemini.
    description_chunks = _chunk_list(descriptions, GEMINI_BATCH_SIZE)
    logger.info(f"Division des descriptions en {len(description_chunks)} lots pour analyse parallèle.")

    # Exécute les appels à Gemini en parallèle.
    tasks = [extract_skills_with_gemini(job_title, chunk, logger) for chunk in description_chunks]
    batch_results = await asyncio.gather(*tasks)

    logger.info("Fusion et comptage des résultats de tous les lots Gemini...")
    aggregated_data = _aggregate_results(batch_results)

    if not aggregated_data.get("skills"):
        logger.error("L'analyse n'a produit aucune compétence; fin du processus.")
        return None

    final_result = {
        "skills": aggregated_data["skills"],
        "top_diploma": aggregated_data["top_diploma"],
        "actual_offers_count": len(all_offers)
    }

    logger.info(f"Un total de {len(final_result['skills'])} compétences uniques et le diplôme le plus demandé ('{final_result['top_diploma']}') ont été agrégés.")

    logger.info(f"Mise en cache du résultat final avec la clé '{cache_key}'.")
    add_to_cache(cache_key, final_result)

    logger.info(f"Fin du processus pour '{job_title}'.")
    return final_result