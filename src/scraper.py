import requests
from bs4 import BeautifulSoup
import json
import re
import time
import random
import logging
from urllib.parse import quote_plus

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# --- Constantes ---
# Utilisation de headers HTTP pour simuler un navigateur et rendre les requêtes plus crédibles.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}
# URL de base du site à scraper.
BASE_WTTJ_URL = "https://www.welcometothejungle.com"
# Sélecteurs CSS pour identifier les éléments clés dans la page.
SEARCH_RESULTS_SELECTOR = 'ol[data-testid="search-results"]'
JOB_CARD_SELECTOR = 'li[data-testid="search-results-list-item-wrapper"]'
# ID du bouton pour accepter les cookies.
COOKIE_BUTTON_ID = "onetrust-accept-btn-handler"


class WTTJScraper:
    """
    Un scraper pour Welcome to the Jungle utilisant Selenium pour la navigation
    initiale sur les pages de recherche dynamiques.
    """
    def __init__(self, headless: bool = True, wait_time: int = 45):
        """
        Initialise le scraper et le driver Selenium.

        Args:
            headless (bool): Si True, le navigateur Chrome s'exécute en arrière-plan,
                             sans interface graphique. C'est essentiel pour le déploiement.
            wait_time (int): Temps d'attente maximum pour que les éléments apparaissent.
        """
        self.wait_time = wait_time
        # Le driver est configuré via une méthode dédiée pour plus de clarté.
        self.driver = self._setup_driver(headless)
        # On stockera les cookies ici après les avoir acceptés.
        self.cookies = None
        if self.driver:
            self.wait = WebDriverWait(self.driver, self.wait_time)

    def _setup_driver(self, headless: bool) -> webdriver.Chrome | None:
        """
        Configure et initialise l'instance du driver Chrome avec des options optimisées.
        """
        try:
            options = webdriver.ChromeOptions()
            if headless:
                # Le mode headless est crucial pour l'exécution sur un serveur.
                options.add_argument("--headless=new")
# Ces arguments sont des bonnes pratiques pour assurer la stabilité, surtout en environnement conteneurisé.
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-notifications")
            driver = webdriver.Chrome(options=options)
            logging.info("Driver Selenium initialisé avec succès.")
            return driver
        except Exception as e:
# Une erreur critique : si le driver ne démarre pas, on la log pour le débogage.
            logging.critical(f"Erreur critique lors de l'initialisation du driver: {e}", exc_info=True)
            return None

    def _accept_cookies(self):
        """
        Trouve et clique sur le bouton d'acceptation des cookies s'il est présent.
        Cette action est nécessaire pour interagir avec la page et récupérer
        des cookies de session valides.
        """
        try:
            # On attend 3 secondes maximum que le bouton de cookies devienne cliquable.
            cookie_button = WebDriverWait(self.driver, 3).until(
                EC.element_to_be_clickable((By.ID, COOKIE_BUTTON_ID))
            )
            cookie_button.click()
            logging.info("Cookies acceptés.")
            # Petite pause pour simuler un comportement humain et laisser la page réagir.
            time.sleep(random.uniform(0.3, 0.8))
        except Exception:
            # Pas grave si le bouton n'est pas trouvé : soit les cookies sont déjà acceptés, soit la bannière n'est pas apparue.
            logging.info("Bannière de cookies non trouvée ou déjà acceptée.")

    def search_and_scrape_jobs(self, search_term: str, num_pages: int = 2) -> list[dict]:
        """
        Navigue sur les pages de résultats et extrait les métadonnées de chaque offre.
        Cette fonction utilise Selenium car la page de recherche charge son contenu
        dynamiquement avec du JavaScript.

        Args:
            search_term (str): Le métier ou mot-clé à rechercher.
            num_pages (int): Le nombre de pages de résultats à parcourir.

        Returns:
            list[dict]: Une liste de dictionnaires, chaque dictionnaire représentant une offre.
        """
        if not self.driver:
            logging.error("Driver non initialisé. Abandon de la recherche.")
            return []

        # `quote_plus` encode le terme de recherche pour l'inclure sans risque dans une URL (ex: "Data Scientist" devient "Data+Scientist").
        search_term_encoded = quote_plus(search_term)
        
        all_offers = []
        urls_seen = set() # Un `set` est utilisé pour vérifier très rapidement si une URL a déjà été ajoutée, afin d'éviter les doublons.
        
        for page_number in range(1, num_pages + 1):
            search_url = f"{BASE_WTTJ_URL}/fr/jobs?query={search_term_encoded}&page={page_number}"
            logging.info(f"Navigation vers l'URL de recherche : {search_url}")
            self.driver.get(search_url)

            try:
                # C'est l'étape clé de Selenium : on attend que l'élément des résultats soit présent dans le DOM.
                self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, SEARCH_RESULTS_SELECTOR)))
                logging.info(f"Page {page_number} chargée.")

                # On ne gère les cookies qu'une seule fois, sur la première page.
                if page_number == 1:
                    self._accept_cookies()
                    # Après acceptation, les cookies sont sauvegardés pour être réutilisés plus tard avec `requests`.
                    self.cookies = self.driver.get_cookies()
                    logging.info(f"{len(self.cookies)} cookies ont été récupérés.")
                
                # Pause pour s'assurer que tout le JavaScript a eu le temps de s'exécuter.
                time.sleep(random.uniform(1.5, 2.5))

                # On passe le code source de la page (maintenant complet) à BeautifulSoup pour le parser plus facilement.
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                cards = soup.select(JOB_CARD_SELECTOR)
                logging.info(f"{len(cards)} offres trouvées sur la page {page_number}.")

                if not cards:
                    logging.warning("Aucune offre trouvée sur cette page. Arrêt de la pagination.")
                    break

                # On itère sur chaque card d'offre pour extraire les infos de base.
                for card in cards:
                    title_el = card.find('h2')
                    company_img_el = card.find('img', alt=True)
                    link_el = card.find('a', href=True)

                    if title_el and company_img_el and link_el:
                        url = BASE_WTTJ_URL + link_el["href"]
                        if url not in urls_seen:
                            urls_seen.add(url)
                            all_offers.append({
                                "titre": title_el.text.strip(),
                                "entreprise": company_img_el['alt'].strip(),
                                "url": url
                            })
            except Exception as e:
                logging.error(f"Problème lors du parsing de la page {page_number}: {e}", exc_info=True)
                break
        
        logging.info(f"Scraping initial terminé. Total d'offres collectées : {len(all_offers)}.")
        return all_offers

    def close_driver(self):
        """
        Ferme proprement le driver Selenium pour libérer les ressources (mémoire, etc.).
        C'est une étape très importante à ne pas oublier.
        """
        if self.driver:
            logging.info("Fermeture du driver Selenium.")
            self.driver.quit()
            self.driver = None

def get_job_details(url: str, cookies: list[dict]) -> dict:
    """
    Récupère les détails d'une seule offre (description, tags) en utilisant `requests`.
    Cette approche est beaucoup plus rapide et légère que d'utiliser Selenium pour chaque page.

    Args:
        url (str): L'URL de la page de l'offre.
        cookies (list[dict]): Les cookies de session obtenus par Selenium.

    Returns:
        dict: Un dictionnaire contenant la description et les tags de l'offre.
    """
    # Pause aléatoire très courte pour éviter de surcharger le serveur.
    time.sleep(random.uniform(0.1, 0.5))
    details = {'description': None, 'tags': []}
    
    # On crée une session `requests` qui va conserver les cookies pour toutes les requêtes, nous faisant passer pour le même utilisateur qui a navigué sur le site.
    session = requests.Session()
    session.headers.update(HEADERS)
    for cookie in cookies:
        session.cookies.set(cookie['name'], cookie['value'], domain=cookie['domain'])

    try:
        resp = session.get(url, timeout=10)
        resp.raise_for_status() # Lève une exception si la requête a échoué (ex: erreur 404, 500).
        soup = BeautifulSoup(resp.text, "html.parser")
        job_data = None
        
        # Stratégie principale : extraire les données d'un script JSON directement depuis la page pour une meilleure fiabilité.
        script_initial = soup.find("script", string=re.compile("window.__INITIAL_DATA__"))
        if script_initial:
            # Expression régulière pour extraire l'objet JSON de la balise script.
            match = re.search(r'window\.__INITIAL_DATA__\s*=\s*(.*?)\s*window\.__FLAGS_DATA__', script_initial.string, re.DOTALL)
            if match:
                # Le JSON est parfois entouré de guillemets ou se termine par un ';', il faut le nettoyer.
                json_data_raw = match.group(1).strip().rstrip(';')
                if json_data_raw.startswith('"') and json_data_raw.endswith('"'):
                   json_data_raw = json.loads(json_data_raw)
                
                parsed_data = json.loads(json_data_raw) if isinstance(json_data_raw, str) else json_data_raw
                # On navigue dans l'objet JSON pour trouver les données de l'offre.
                job_data = parsed_data.get('queries', [{}])[0].get('state', {}).get('data', {})

        if job_data:
            # Si on a trouvé le JSON, on extrait les données proprement.
            description_html = job_data.get('description', '')
            profile_html = job_data.get('profile', '')
            # On combine les sections et on utilise BeautifulSoup pour nettoyer le HTML et ne garder que le texte.
            details['description'] = BeautifulSoup(f"{description_html}\n\n{profile_html}", 'html.parser').get_text("\n", strip=True)

            # On utilise des compréhensions d'ensemble pour extraire et dédoublonner efficacement les compétences et outils.
            skills_fr = {s['name']['fr'].strip().title() for s in job_data.get('skills', []) if isinstance(s.get('name'), dict) and s.get('name', {}).get('fr')}
            tools = {t['name'].strip().title() for t in job_data.get('tools', []) if t.get('name')}
            
            # L'opérateur `|` fusionne les deux ensembles (sets) pour obtenir une liste unique.
            details['tags'] = sorted(list(skills_fr | tools))
        else:
            # Stratégie de secours : si le JSON est absent, on parse le HTML de la balise <main>. C'est moins fiable, mais ça dépanne.
            main_content = soup.find('main')
            if main_content:
                details['description'] = main_content.get_text("\n", strip=True)

    except requests.exceptions.HTTPError as http_err:
        logging.warning(f"⚠️ Erreur HTTP {http_err.response.status_code} pour {url}. Offre ignorée.")
    except Exception as e:
        logging.error(f"❌ Erreur non gérée pour {url}: {e}", exc_info=True)

    return details