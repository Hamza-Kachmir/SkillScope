import google.generativeai as genai
from google.oauth2 import service_account
import logging
import json
import os
import asyncio
from enum import Enum
from typing import Dict, Any, List, Optional

# Nouveaux imports pour le suivi de santé
from collections import deque
import time

# --- Énumération pour les statuts ---
class GeminiStatus(Enum):
    OPERATIONAL = ("#28a745", "Service Gemini : Opérationnel")
    DEGRADED = ("#ffc107", "Service Gemini : Performances dégradées (temps de réponse lents)")
    OUTAGE = ("#dc3545", "Service Gemini : Panne détectée (indisponible ou erreurs)")

# --- Classe pour le suivi de l'état de l'API ---
class GeminiHealthTracker:
    def __init__(self, window_size=50, time_limit_seconds=300):
        # Garde les N derniers appels
        self.requests = deque(maxlen=window_size)
        # Les appels plus vieux que 5 minutes sont ignorés
        self.time_limit = time_limit_seconds

    def _cleanup_old_requests(self):
        """Nettoie les enregistrements trop anciens."""
        now = time.time()
        while self.requests and now - self.requests[0]['timestamp'] > self.time_limit:
            self.requests.popleft()

    def record_call(self, success: bool):
        """Enregistre le résultat d'un appel API."""
        self.requests.append({'timestamp': time.time(), 'success': success})

    def get_error_rate(self) -> float:
        """Calcule le taux d'erreur sur la fenêtre de temps récente."""
        self._cleanup_old_requests()
        if not self.requests:
            return 0.0
        
        failures = sum(1 for req in self.requests if not req['success'])
        return failures / len(self.requests)

# --- Instance globale du tracker ---
health_tracker = GeminiHealthTracker()

# --- Constantes de configuration Gemini ---
MODEL_NAME = 'gemini-2.5-flash-lite'
EXTRACTION_PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'prompt.md')
CONSOLIDATION_PROMPT_PATH = os.path.join(os.path.dirname(__file__), '..', 'consolidation_prompt.md')

# --- État global du module ---
model: Optional[genai.GenerativeModel] = None
prompt_templates: Dict[str, str] = {}
_current_logger: logging.Logger = logging.getLogger(__name__)


def _load_prompts() -> bool:
    """Charge tous les templates de prompt nécessaires depuis les fichiers."""
    global prompt_templates
    try:
        with open(EXTRACTION_PROMPT_PATH, 'r', encoding='utf-8') as f:
            prompt_templates['extraction'] = f.read()
        with open(CONSOLIDATION_PROMPT_PATH, 'r', encoding='utf-8') as f:
            prompt_templates['consolidation'] = f.read()
        _current_logger.info("Gemini : Prompts chargés avec succès.")
        return True
    except Exception as e:
        _current_logger.critical(f"Gemini : Erreur critique lors du chargement des prompts : {e}")
        return False

def initialize_gemini(logger: logging.Logger) -> bool:
    """Initialise le client Gemini et charge les prompts."""
    global model, _current_logger
    _current_logger = logger

    if model and prompt_templates:
        return True

    if not prompt_templates and not _load_prompts():
        return False

    if not model:
        google_creds_json = os.getenv('GOOGLE_CREDENTIALS')
        if not google_creds_json:
            _current_logger.critical("Gemini : Variable d'environnement GOOGLE_CREDENTIALS non définie.")
            return False
        try:
            credentials = service_account.Credentials.from_service_account_info(json.loads(google_creds_json))
            genai.configure(credentials=credentials)
            generation_config = {"temperature": 0.0, "response_mime_type": "application/json"}
            model = genai.GenerativeModel(MODEL_NAME, generation_config=generation_config)
            _current_logger.info(f"Gemini : Client '{MODEL_NAME}' initialisé avec succès.")
        except Exception as e:
            _current_logger.critical(f"Gemini : Échec de l'initialisation : {e}")
            return False
    return True

# --- FONCTION DE VÉRIFICATION DE STATUT MISE À JOUR ---
async def check_gemini_status(logger: logging.Logger) -> GeminiStatus:
    """
    Sonde l'API Gemini et vérifie le taux d'erreur interne pour évaluer sa santé.
    Retourne un statut (OPERATIONAL, DEGRADED, OUTAGE).
    """
    if not initialize_gemini(logger):
        return GeminiStatus.OUTAGE

    # Vérification du taux d'erreur interne
    error_rate = health_tracker.get_error_rate()
    ERROR_RATE_THRESHOLD = 0.30

    if error_rate > ERROR_RATE_THRESHOLD:
        logger.error(f"Gemini Status : OUTAGE (Taux d'erreur interne de {error_rate:.0%})")
        return GeminiStatus.OUTAGE

    # Sonde de latence
    probe_timeout = 10.0
    degraded_threshold = 3.0

    try:
        start_time = time.time()
        await asyncio.wait_for(model.count_tokens_async("ping"), timeout=probe_timeout)
        duration = time.time() - start_time
        
        if duration > degraded_threshold:
            logger.warning(f"Gemini Status : DEGRADED (latence de {duration:.2f}s)")
            return GeminiStatus.DEGRADED
        else:
            logger.info(f"Gemini Status : OPERATIONAL (latence de {duration:.2f}s, taux d'erreur de {error_rate:.0%})")
            return GeminiStatus.OPERATIONAL
            
    except Exception as e:
        logger.error(f"Gemini Status : OUTAGE (Erreur sur la sonde: {e})")
        health_tracker.record_call(success=False)
        return GeminiStatus.OUTAGE

async def extract_skills_with_gemini(job_title: str, descriptions: List[str], logger: logging.Logger) -> Optional[Dict[str, Any]]:
    """Envoie un lot de descriptions à Gemini pour l'extraction initiale."""
    global _current_logger
    _current_logger = logger

    if not model or 'extraction' not in prompt_templates:
        if not initialize_gemini(logger): return None

    indexed_descriptions = "\n---\n".join([f"{i}: {desc}" for i, desc in enumerate(descriptions)])
    full_prompt = prompt_templates['extraction'].format(indexed_descriptions=indexed_descriptions)
    _current_logger.info(f"Gemini (Extraction) : Envoi de {len(descriptions)} descriptions.")

    try:
        response = await model.generate_content_async(full_prompt)
        cleaned_text = response.text.replace(r"\'", "'")
        skills_json = json.loads(cleaned_text)
        _current_logger.info("Gemini (Extraction) : Réponse JSON reçue et parsée avec succès.")
        health_tracker.record_call(success=True)
        return skills_json
    except Exception as e:
        _current_logger.error(f"Gemini (Extraction) : Erreur lors de l'appel à l'API : {e}")
        health_tracker.record_call(success=False)
        return None

async def consolidate_skills_with_gemini(skills_to_consolidate: List[str], logger: logging.Logger) -> Optional[List[str]]:
    """Envoie une liste de compétences à Gemini pour consolidation."""
    global _current_logger
    _current_logger = logger

    if not model or 'consolidation' not in prompt_templates:
        if not initialize_gemini(logger): return None

    skills_json_string = json.dumps(skills_to_consolidate, ensure_ascii=False)
    full_prompt = prompt_templates['consolidation'].replace('__SKILLS_TO_CONSOLIDATE__', skills_json_string)
    _current_logger.info(f"Gemini (Consolidation) : Envoi de {len(skills_to_consolidate)} compétences.")

    try:
        response = await model.generate_content_async(full_prompt)
        response_json = json.loads(response.text)
        consolidated_list = response_json.get("consolidated_skills")

        if consolidated_list is None:
            _current_logger.error("Gemini (Consolidation) : Clé 'consolidated_skills' manquante.")
            health_tracker.record_call(success=False)
            return skills_to_consolidate

        _current_logger.info(f"Gemini (Consolidation) : {len(consolidated_list)} compétences reçues après nettoyage.")
        health_tracker.record_call(success=True)
        return consolidated_list
    except Exception as e:
        _current_logger.error(f"Gemini (Consolidation) : Erreur lors de l'appel à l'API : {e}")
        health_tracker.record_call(success=False)
        return skills_to_consolidate