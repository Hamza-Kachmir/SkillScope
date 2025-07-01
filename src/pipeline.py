import pandas as pd
import logging
import io
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Any

# Import des composants du scraper nécessaires.
from src.scraper import WTTJScraper, get_job_details

# Configure le logging pour enregistrer les étapes clés de l'exécution du script.
log_stream = io.StringIO()
handler = logging.StreamHandler(log_stream)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logging.basicConfig(level=logging.INFO, handlers=[handler])


def search_for_offers(search_term: str) -> tuple[list[dict], list[dict] | None]:
    """
    Étape 1 du pipeline : Lance Selenium pour rechercher les offres et récupérer
    leurs URLs ainsi que les cookies de session.

    Args:
        search_term (str): Le métier à rechercher.

    Returns:
        tuple: Un tuple contenant la liste des métadonnées des offres et les cookies.
               Retourne ([], None) en cas d'erreur.
    """
    scraper = None
# Le bloc try...finally garantit la fermeture du navigateur Selenium, même en cas d'erreur.
    try:
        logging.info(f"Phase 1 : Lancement de la recherche d'offres pour '{search_term}'.")
        # On instancie notre scraper en mode headless (sans interface graphique).
        scraper = WTTJScraper(headless=True)
        offers_metadata = scraper.search_and_scrape_jobs(search_term, num_pages=2)
        cookies = scraper.cookies
        return offers_metadata, cookies
    except Exception as e:
        logging.error(f"Erreur majeure durant la recherche d'offres : {e}", exc_info=True)
        return [], None
    finally:
        if scraper:
            scraper.close_driver()
            logging.info("Driver Selenium fermé.")


def analyze_offers_details(
    offers_metadata: list[dict],
    cookies: list[dict],
    progress_callback: Callable[[float], None],
    max_workers: int = 5
) -> pd.DataFrame | None:
    """
    Étape 2 du pipeline : Analyse les détails de chaque offre en parallèle pour plus
    de performance.

    Args:
        offers_metadata (list[dict]): Liste des offres récupérées à l'étape 1.
        cookies (list[dict]): Cookies de session pour les requêtes HTTP.
        progress_callback (Callable): Une fonction à appeler pour mettre à jour la
                                      barre de progression dans l'interface Streamlit.
        max_workers (int): Nombre de threads à utiliser pour les requêtes simultanées.
                           Permet d'accélérer drastiquement l'analyse.

    Returns:
        pd.DataFrame | None: Un DataFrame avec les résultats, ou None si l'analyse échoue.
    """
    if not offers_metadata or not cookies:
        logging.warning("Aucune offre ou cookie à analyser. Arrêt de la phase 2.")
        return None

    logging.info(f"Phase 2 : Lancement de l'analyse détaillée de {len(offers_metadata)} offres...")
    
    offers_with_tags = []
    offers_to_rescue = [] # Pour les offres où les tags n'ont pas été trouvés dans le JSON.
    total_offers = len(offers_metadata)
    completed_count = 0

# Un ThreadPoolExecutor est utilisé pour lancer des appels get_job_details en parallèle.
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # On soumet toutes les tâches (une par offre) à l'executor.
        future_to_offer = {
            executor.submit(get_job_details, offer['url'], cookies): offer
            for offer in offers_metadata
        }
        
# as_completed permet de traiter les résultats dès qu'ils sont disponibles, sans attendre la fin de toutes les tâches.
        for future in as_completed(future_to_offer):
            original_offer = future_to_offer[future]
            try:
                result_details = future.result()
                if result_details:
                    original_offer.update(result_details)
                    # Si l'offre a des tags structurés (extraits du JSON), c'est idéal.
                    if result_details.get('tags'):
                        offers_with_tags.append(original_offer)
                    # Sinon, si on a au moins la description, on la met de côté pour un "sauvetage".
                    elif result_details.get('description'):
                        offers_to_rescue.append(original_offer)
            except Exception as exc:
                logging.error(f"L'offre {original_offer.get('url')} a généré une erreur: {exc}")
            finally:
                # Quoi qu'il arrive (succès ou échec), on met à jour la progression.
                completed_count += 1
                progress_callback(completed_count / total_offers)

    logging.info(f"{len(offers_with_tags)} offres avec des compétences structurées trouvées.")

    # --- Mécanisme de sauvetage ---
 # Si le JSON n'est pas trouvé, on extrait les compétences de la description textuelle en cherchant des mots-clés.
    if offers_to_rescue and offers_with_tags:
        # On crée un "dictionnaire" de toutes les compétences déjà trouvées.
        master_skill_set = {skill for offer in offers_with_tags for skill in offer['tags']}
        logging.info(f"Tentative de sauvetage de {len(offers_to_rescue)} offres...")
        
        rescued_count = 0
        for offer in offers_to_rescue:
            found_skills = set()
            description_lower = offer['description'].lower() if offer.get('description') else ''
            
            # Pour chaque compétence du dictionnaire, on regarde si elle est présente dans la description.
            for skill in master_skill_set:
                # `re.search` avec `\b` assure qu'on cherche le mot entier (ex: "go" et non "gopher").
                if re.search(r'\b' + re.escape(skill.lower()) + r'\b', description_lower):
                    found_skills.add(skill)
            
            if found_skills:
                offer['tags'] = sorted(list(found_skills))
                offers_with_tags.append(offer)
                rescued_count += 1
        
        logging.info(f"{rescued_count} offres sauvées avec succès !")

    if not offers_with_tags:
        logging.warning("Aucune compétence n'a pu être extraite.")
        return None

    logging.info("Création du DataFrame final...")
    df = pd.DataFrame(offers_with_tags)
    # On sélectionne et réorganise les colonnes pour un résultat propre.
    final_df = df[['titre', 'entreprise', 'url', 'tags']]
    logging.info(f"Pipeline terminé ! {len(final_df)} offres prêtes.")
    
    return final_df