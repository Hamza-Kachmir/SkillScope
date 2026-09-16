<p align="center">
  <img src="public/SkillScope.svg" alt="Logo SkillScope" width="280">
</p>

# SkillScope

<p align="center">
  <a href="https://github.com/Hamza-Kachmir/SkillScope/actions/workflows/ci.yml">
    <img src="https://github.com/Hamza-Kachmir/SkillScope/actions/workflows/ci.yml/badge.svg" alt="État des contrôles qualité">
  </a>
</p>

SkillScope est un projet que j’ai développé pour mieux comprendre les compétences demandées pour un métier à partir des offres d’emploi publiées par France Travail.

L’utilisateur recherche un métier et lance l’analyse. L’application récupère alors un échantillon d’offres actives et utilise Gemini pour repérer les compétences et les niveaux d’études les plus souvent mentionnés. Les résultats sont ensuite présentés sous forme de graphiques.

➡️ **[Accéder à l’application SkillScope](https://skillscope.pages.dev/)**

## Fonctionnalités principales

- Recherche de métiers avec autocomplétion ROME 4.0.
- Analyse d'un échantillon allant jusqu'à 100 offres actives.
- Extraction sémantique des compétences avec Gemini.
- Regroupement des variantes et déduplication par offre.
- Classement des compétences par fréquence d'apparition.
- Visualisation des niveaux d'études cités.
- Cache Redis pour accélérer les recherches déjà effectuées.
- Interface responsive et accessible.

## Fonctionnement

1. L'utilisateur recherche un métier.
2. Le backend récupère les offres correspondantes auprès de France Travail.
3. Gemini analyse les descriptions afin d'en extraire les compétences réellement demandées.
4. Les variantes évidentes sont regroupées et une compétence ne compte qu'une fois par offre.
5. L'interface présente les résultats sous forme de graphiques.

## Architecture technique

- **Frontend :** React, TypeScript et Vite
- **Backend :** FastAPI et Python
- **Données :** API France Travail et référentiel ROME 4.0
- **Intelligence artificielle :** Gemini via Vertex AI
- **Cache :** Redis avec Upstash
- **Hébergement :** Cloudflare Pages pour le frontend et Google Cloud Run pour le backend
- **Conteneurisation :** Docker et Docker Compose pour l'environnement local
- **Tests & qualité du code :** Pytest, Ruff et Oxlint
- **Intégration continue :** GitHub Actions

## Méthodologie

Les offres sont analysées par lots, puis les résultats sont consolidés afin de rapprocher uniquement les formulations équivalentes. Les pourcentages sont calculés sur l'ensemble des offres récupérées pour la recherche. La couverture indique la part des offres dans lesquelles au moins une compétence a été identifiée.

## Limites

Les résultats dépendent de l'échantillon d'offres disponible au moment de la recherche et de la qualité de leurs descriptions. L'analyse reposant en partie sur une intelligence artificielle, certaines interprétations peuvent être imprécises. SkillScope fournit donc des tendances indicatives et non une mesure exhaustive du marché de l'emploi.

## Améliorations prévues

- Étendre les tests aux principaux parcours utilisateur.
- Continuer à affiner l'extraction des compétences.
