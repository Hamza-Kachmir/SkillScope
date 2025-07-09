import google.generativeai as genai
from google.oauth2 import service_account
import logging
import json
import os
import asyncio
from typing import Dict, Any, List, Optional

# --- Constantes de configuration Gemini ---
MODEL_NAME = 'gemini-1.5-flash-latest' # Définit le nom du modèle Gemini à utiliser.
PROMPT_FILE_PATH = os.path.join(os.path.dirname(__file__), '..', 'prompt.md') # Chemin vers le fichier du prompt.

# --- État global du module ---
model: Optional[genai.GenerativeModel] = None # Variable globale pour stocker l'instance du modèle Gemini.
prompt_template: Optional[str] = None # Variable globale pour stocker le contenu du prompt.
_current_logger: logging.Logger = logging.getLogger(__name__) # Logger spécifique pour ce module.


def _load_prompt_from_file() -> Optional[str]:
    """Charge le template du prompt depuis le fichier prompt.md."""
    try:
        with open(PROMPT_FILE_PATH, 'r', encoding='utf-8') as f:
            _current_logger.info(f"Gemini : Prompt chargé avec succès depuis '{PROMPT_FILE_PATH}'.")
            return f.read() # Retourne le contenu du fichier.
    except FileNotFoundError:
        _current_logger.critical(f"Gemini : Fichier de prompt non trouvé à l'emplacement '{PROMPT_FILE_PATH}' !")
        return None # Retourne None si le fichier n'est pas trouvé.
    except Exception as e:
        _current_logger.critical(f"Gemini : Erreur lors de la lecture du fichier de prompt : {e}")
        return None # Gère les autres erreurs de lecture.

def initialize_gemini(logger: logging.Logger) -> bool:
    """
    Initialise le client Gemini et charge le prompt pour l'extraction de données.
    Cette fonction doit être appelée avant toute utilisation du modèle Gemini.
    """
    global model, prompt_template, _current_logger
    _current_logger = logger # Met à jour le logger avec l'instance fournie.

    # Vérifie si le modèle et le prompt sont déjà initialisés pour éviter de les recharger.
    if model and prompt_template:
        return True

    # Charge le prompt si ce n'est pas déjà fait.
    if not prompt_template:
        prompt_template = _load_prompt_from_file()
        if not prompt_template:
            return False # Échec si le prompt ne peut pas être chargé.

    # Initialise le modèle Gemini si ce n'est pas déjà fait.
    if not model:
        google_creds_json = os.getenv('GOOGLE_CREDENTIALS') # Récupère les identifiants Google Cloud.
        if not google_creds_json:
            _current_logger.critical("Gemini : La variable d'environnement GOOGLE_CREDENTIALS n'est pas définie !")
            return False # Échec si les identifiants sont manquants.

        try:
            credentials_info = json.loads(google_creds_json) # Parse les identifiants JSON.
            credentials = service_account.Credentials.from_service_account_info(credentials_info) # Crée les identifiants de service.
            genai.configure(credentials=credentials) # Configure l'API Gemini avec les identifiants.

            generation_config = {"temperature": 0.0, "response_mime_type": "application/json"} # Configure la génération pour un JSON déterministe.

            model = genai.GenerativeModel(MODEL_NAME, generation_config=generation_config) # Crée l'instance du modèle Gemini.
            _current_logger.info(f"Gemini : Client '{MODEL_NAME}' initialisé avec succès.")
            return True # Succès de l'initialisation.
        except Exception as e:
            _current_logger.critical(f"Gemini : Échec de l'initialisation de Gemini : {e}")
            return False # Gère les erreurs d'initialisation du modèle.

    return True

async def extract_skills_with_gemini(job_title: str, descriptions: List[str], logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """
    Envoie un lot de descriptions de postes à l'API Gemini pour extraire les compétences et le niveau d'éducation.
    """
    global _current_logger
    _current_logger = logger # Met à jour le logger avec l'instance fournie.

    # Vérifie si le modèle et le prompt sont initialisés avant de procéder.
    if not model or not prompt_template:
        _current_logger.error("Gemini : Tentative d'appel à Gemini sans initialisation préalable.")
        if not initialize_gemini(logger):
            return None # Retourne None si l'initialisation échoue.

    # Formate les descriptions pour les inclure dans le prompt.
    indexed_descriptions = "\n---\n".join([f"{i}: {desc}" for i, desc in enumerate(descriptions)])
    full_prompt = prompt_template.format(indexed_descriptions=indexed_descriptions) # Construit le prompt complet.

    _current_logger.info(f"Gemini : Envoi de {len(descriptions)} descriptions au modèle (lot pour '{job_title}').")

    try:
        response = await model.generate_content_async(full_prompt) # Appelle l'API Gemini de manière asynchrone.

        cleaned_text = response.text.replace(r"\'", "'") # Nettoie la réponse pour corriger les échappements.
        skills_json = json.loads(cleaned_text) # Parse la réponse JSON.

        _current_logger.info(f"Gemini : Réponse JSON complète reçue et parsée avec succès pour ce lot ({len(descriptions)} descriptions).")
        return skills_json # Retourne les données extraites.

    except json.JSONDecodeError as e:
        _current_logger.error(f"Gemini : Erreur de décodage JSON de la réponse : {e}. Réponse complète reçue : {response.text[:1000]}...")
        return None # Gère les erreurs de parsing JSON.
    except Exception as e:
        _current_logger.error(f"Gemini : Erreur inattendue lors de l'appel à l'API : {e}")
        return None # Gère les erreurs générales de l'API.