# SkillScope

Une application web pour analyser et classer en temps réel les compétences les plus demandées pour un métier donné, en utilisant les données de France Travail et l'IA de Google Gemini.

---

### Contexte du Projet

Chaque jour, des milliers d'offres d'emploi sont publiées, chacune avec sa propre liste de compétences. Dans ce volume d'informations, comment identifier le "signal" du "bruit" ? Quelles sont les compétences qui reviennent systématiquement et définissent réellement un poste aujourd'hui, au-delà des fiches de poste génériques ?

**SkillScope** a été créé pour répondre à cette problématique. Cet outil analyse un grand nombre d'offres d'emploi en direct pour extraire, nettoyer et classer les compétences les plus fréquemment mentionnées, offrant ainsi un aperçu précis et basé sur la donnée des attentes du marché.

### Comment ça marche ? Le Pipeline

Lorsqu'un utilisateur lance une analyse, SkillScope exécute un pipeline de traitement de données en plusieurs étapes :

1.  **Mise en Cache (Redis) :** L'application vérifie d'abord si une analyse pour ce métier a déjà été faite récemment. Si c'est le cas, les résultats sont servis instantanément depuis le cache **Redis** pour une performance optimale. Le cache se reset tous les 30 jours.

2.  **Recherche d'Offres (France Travail API) :** Si les données ne sont pas en cache, l'application interroge l'**API de France Travail** pour récupérer les 100 dernières offres d'emploi correspondant au métier recherché.

3.  **Extraction par l'IA (Google Gemini) :** Les descriptions des offres sont envoyées par lots à l'API **Google Gemini**. Un premier prompt spécialisé lui demande d'extraire de manière brute toutes les compétences techniques (Hard Skills) et le niveau d'étude mentionnés.

4.  **Consolidation par l'IA (Google Gemini) :** La liste de compétences brutes est souvent redondante ("Gestion de projet", "gestion de projets", etc.). Elle est donc renvoyée à Gemini avec un second prompt avancé qui lui demande de nettoyer, normaliser (casse, singulier/pluriel) et de fusionner les doublons évidents, tout en conservant la granularité des savoir-faire.

5.  **Affichage et Export :** La liste finale des compétences, propre et classée, est affichée à l'utilisateur dans une interface interactive. Les résultats peuvent également être exportés aux formats **Excel** et **CSV**.

---

### Technologies Utilisées

* **Backend :** Python
* **Interface Web :** NiceGUI
* **IA & Analyse :** Google Gemini API
* **Source de Données :** France Travail API
* **Mise en Cache :** Redis
* **Librairies Clés :** Aiohttp (appels API asynchrones), Pandas (manipulation et export de données)
