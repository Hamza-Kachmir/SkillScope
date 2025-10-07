import google.generativeai as genai
from google.oauth2 import service_account
import logging
import json
import os
import asyncio
from typing import Dict, Any, List, Optional

# --- Constantes de configuration Gemini ---
MODEL_NAME = 'gemini-2.5-flash-lite' # Définit le nom du modèle Gemini à utiliser.
EXTRACTION_PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'prompt.md')
CONSOLIDATION_PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'consolidation_prompt.md')

# --- État global du module ---
model: Optional[genai.GenerativeModel] = None
prompt_templates: Dict[str, str] = {} # Dictionnaire pour stocker les prompts chargés.
_current_logger: logging.Logger = logging.getLogger(__name__)

def _load_prompts() -> bool:
    """Charge tous les templates de prompt nécessaires depuis les fichiers."""
    global prompt_templates
    try:
        with open(EXTRACTION_PROMPT_PATH, 'r', encoding='utf-8') as f:
            prompt_templates['extraction'] = f.read()
            _current_logger.info(f"Gemini : Prompt d'extraction chargé avec succès.")

        with open(CONSOLIDATION_PROMPT_PATH, 'r', encoding='utf-8') as f:
            prompt_templates['consolidation'] = f.read()
            _current_logger.info(f"Gemini : Prompt de consolidation chargé avec succès.")

        return True
    except FileNotFoundError as e:
        _current_logger.critical(f"Gemini : Fichier de prompt non trouvé : {e}")
        return False
    except Exception as e:
        _current_logger.critical(f"Gemini : Erreur lors de la lecture des fichiers de prompt : {e}")
        return False

def initialize_gemini(logger: logging.Logger) -> bool:
    """Initialise le client Gemini et charge les prompts."""
    global model, _current_logger
    _current_logger = logger

    if model and prompt_templates:
        return True

    if not prompt_templates:
        if not _load_prompts():
            return False

    if not model:
        google_creds_json = os.getenv('GOOGLE_CREDENTIALS')
        if not google_creds_json:
            _current_logger.critical("Gemini : La variable d'environnement GOOGLE_CREDENTIALS n'est pas définie !")
            return False

        try:
            credentials_info = json.loads(google_creds_json)
            credentials = service_account.Credentials.from_service_account_info(credentials_info)
            genai.configure(credentials=credentials)
            generation_config = {"temperature": 0.0, "response_mime_type": "application/json"}
            model = genai.GenerativeModel(MODEL_NAME, generation_config=generation_config)
            _current_logger.info(f"Gemini : Client '{MODEL_NAME}' initialisé avec succès.")
        except Exception as e:
            _current_logger.critical(f"Gemini : Échec de l'initialisation de Gemini : {e}")
            return False
    return True

async def extract_skills_with_gemini(job_title: str, descriptions: List[str], logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """Envoie un lot de descriptions à Gemini pour l'extraction initiale."""
    global _current_logger
    _current_logger = logger

    if not model or 'extraction' not in prompt_templates:
        _current_logger.error("Gemini : Tentative d'appel à Gemini sans initialisation préalable.")
        if not initialize_gemini(logger): return None

    indexed_descriptions = "\n---\n".join([f"{i}: {desc}" for i, desc in enumerate(descriptions)])
    full_prompt = prompt_templates['extraction'].format(indexed_descriptions=indexed_descriptions)
    _current_logger.info(f"Gemini (Extraction) : Envoi de {len(descriptions)} descriptions au modèle.")

    try:
        response = await model.generate_content_async(full_prompt)
        cleaned_text = response.text.replace(r"\'", "'")
        skills_json = json.loads(cleaned_text)
        _current_logger.info(f"Gemini (Extraction) : Réponse JSON reçue et parsée avec succès.")
        return skills_json
    except Exception as e:
        _current_logger.error(f"Gemini (Extraction) : Erreur lors de l'appel à l'API : {e}")
        return None

async def consolidate_skills_with_gemini(skills_to_consolidate: List[str], logger: logging.Logger) -> Optional[List[str]]:
    """Envoie une liste de compétences à Gemini pour consolidation."""
    global _current_logger
    _current_logger = logger

    if not model or 'consolidation' not in prompt_templates:
        _current_logger.error("Gemini : Tentative de consolidation sans initialisation.")
        if not initialize_gemini(logger): return None

    # Formatte la liste des compétences en une chaîne JSON pour l'inclure dans le prompt.
    skills_json_string = json.dumps(skills_to_consolidate, ensure_ascii=False)
    
    full_prompt = prompt_templates['consolidation'].replace('__SKILLS_TO_CONSOLIDATE__', skills_json_string)
    
    _current_logger.info(f"Gemini (Consolidation) : Envoi de {len(skills_to_consolidate)} compétences pour nettoyage.")

    try:
        response = await model.generate_content_async(full_prompt)
        response_json = json.loads(response.text)
        consolidated_list = response_json.get("consolidated_skills")

        if consolidated_list is None:
            _current_logger.error("Gemini (Consolidation) : La clé 'consolidated_skills' est manquante dans la réponse.")
            return None

        _current_logger.info(f"Gemini (Consolidation) : {len(consolidated_list)} compétences reçues après nettoyage.")
        return consolidated_list
    except Exception as e:
        _current_logger.error(f"Gemini (Consolidation) : Erreur lors de l'appel à l'API : {e}")
        # En cas d'erreur de consolidation, on retourne la liste originale pour ne pas bloquer l'utilisateur.
        return skills_to_consolidate