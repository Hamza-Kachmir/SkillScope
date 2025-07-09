import redis
import json
import os
import logging

# Durée de vie du cache en secondes (30 jours).
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60

redis_client = None # Variable globale pour stocker l'instance du client Redis.

def initialize_redis():
    """
    Initialise la connexion au client Redis en utilisant l'URL fournie par les variables d'environnement.
    Cette fonction est appelée au démarrage du module pour établir la connexion.
    """
    global redis_client
    if redis_client: # Vérifie si le client Redis est déjà initialisé.
        return

    redis_url = os.getenv('REDIS_URL') # Récupère l'URL de connexion Redis depuis l'environnement.
    if not redis_url:
        logging.critical("La variable d'environnement REDIS_URL n'est pas définie !") # Alerte si l'URL est manquante.
        return

    try:
        redis_client = redis.from_url(redis_url, decode_responses=True) # Crée une instance du client Redis.
        redis_client.ping() # Tente de communiquer avec Redis pour vérifier la connexion.
        logging.info("Connexion à Redis réussie.") # Confirme la connexion réussie.
    except Exception as e:
        logging.error(f"Impossible de se connecter à Redis : {e}") # Gère les erreurs de connexion.
        redis_client = None # Réinitialise le client en cas d'échec de connexion.

def get_cached_results(cache_key: str) -> dict | None:
    """
    Récupère un résultat depuis le cache Redis en utilisant la clé spécifiée.
    Retourne le dictionnaire des résultats si trouvé, sinon None.
    """
    if redis_client is None: return None # Retourne None si le client Redis n'est pas initialisé.
    try:
        cached_json = redis_client.get(cache_key) # Tente de récupérer la valeur associée à la clé.
        if cached_json:
            logging.info(f"Cache HIT for '{cache_key}'.") # Indique que le résultat a été trouvé dans le cache.
            return json.loads(cached_json) # Désérialise la chaîne JSON en dictionnaire.
        logging.info(f"Cache MISS for '{cache_key}'.") # Indique que le résultat n'a pas été trouvé dans le cache.
        return None
    except Exception as e:
        logging.error(f"Erreur lors de la lecture du cache Redis pour la clé '{cache_key}': {e}") # Gère les erreurs de lecture.
        return None

def add_to_cache(cache_key: str, results: dict):
    """
    Ajoute un dictionnaire de résultats au cache Redis avec une durée d'expiration définie.
    Les résultats sont sérialisés en JSON avant d'être stockés.
    """
    if redis_client is None: return # Ne fait rien si le client Redis n'est pas initialisé.
    try:
        value_to_store = json.dumps(results, ensure_ascii=False) # Sérialise le dictionnaire en chaîne JSON.
        redis_client.setex(cache_key, CACHE_TTL_SECONDS, value_to_store) # Stocke la valeur avec une expiration.
        logging.info(f"Cache WRITE for '{cache_key}'.") # Confirme l'écriture dans le cache.
    except Exception as e:
        logging.error(f"Erreur lors de l'écriture du cache Redis pour la clé '{cache_key}': {e}") # Gère les erreurs d'écriture.

def delete_from_cache(cache_key: str):
    """
    Supprime une entrée spécifique du cache Redis en utilisant la clé fournie.
    """
    if redis_client is None: return # Ne fait rien si le client Redis n'est pas initialisé.
    try:
        redis_client.delete(cache_key) # Supprime la clé du cache.
        logging.info(f"CACHE DELETE for entry: '{cache_key}'.") # Confirme la suppression.
    except Exception as e:
        logging.error(f"Erreur lors de la suppression de la clé '{cache_key}' du cache Redis : {e}") # Gère les erreurs de suppression.

def flush_all_cache() -> bool:
    """
    Vide complètement toutes les données de la base de données Redis connectée.
    Cette opération est irréversible et doit être utilisée avec prudence.
    """
    if redis_client is None:
        logging.error("Impossible de vider le cache: client Redis non initialisé.") # Alerte si le client n'est pas prêt.
        return False
    try:
        redis_client.flushall() # Exécute la commande FLUSHALL.
        logging.info("CACHE FLUSH: Toutes les données ont été supprimées.") # Confirme le vidage complet.
        return True
    except Exception as e:
        logging.error(f"Erreur lors du vidage complet du cache Redis : {e}") # Gère les erreurs de vidage.
        return False

# Initialise la connexion Redis au démarrage du module.
initialize_redis()