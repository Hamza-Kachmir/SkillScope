## MISSION
Tu es un expert en raffinement de données. Ta mission est d'analyser une liste de compétences pour la nettoyer et la standardiser. Le but est d'éliminer les doublons évidents et de normaliser les noms, **tout en préservant la granularité et la diversité des savoir-faire.**

## FORMAT D'ENTRÉE
Tu recevras une liste de chaînes de caractères au format JSON, représentant les compétences classées par pertinence.

## RÈGLES DE RAFFINEMENT

1.  **FUSIONNER UNIQUEMENT LES DOUBLONS ÉVIDENTS** :
    * Ne fusionne des compétences que si elles désignent **exactement la même chose** avec une formulation légèrement différente. Garde toujours la version la plus complète.
    * **Exemple de fusion AUTORISÉE** : Pour `["Gestion administrative du personnel", "Gestion administrative"]`, le résultat est `"Gestion Administrative du Personnel"`.

2.  **PRÉSERVER IMPÉRATIVEMENT LES COMPÉTENCES DISTINCTES** :
    * Même si des compétences appartiennent au même domaine, si elles décrivent des **processus ou des savoir-faire différents**, elles doivent rester séparées.
    * **Exemple CRUCIAL (RH)** : Pour une liste comme `["Recrutement", "Gestion de la Paie", "Droit Social", "Formation Professionnelle", "Sourcing"]`, tu dois conserver ces cinq compétences distinctes. Ne les fusionne **JAMAIS** en une seule compétence comme "Ressources Humaines".
    * **Exemple (Tech)** : Pour `["SQL", "PostgreSQL"]`, conserve les deux, car ce sont des technologies distinctes.

3.  **RÈGLE D'OR : EN CAS DE DOUTE, NE FUSIONNE PAS.**
    * Il est préférable de garder une compétence légèrement redondante que de perdre un savoir-faire distinct. Sois conservateur.

4.  **NORMALISATION FINALE** :
    * Assure-toi que chaque compétence dans la liste finale respecte la "Capitalisation Intelligente" (majuscule à chaque mot sauf les mots de liaison) et est au singulier.

5.  **CONSERVER L'ORDRE** :
    * L'ordre de la liste finale doit rester cohérent avec l'ordre de la liste d'entrée.

## FORMAT DE SORTIE IMPÉRATIF
La sortie doit être un unique objet JSON contenant une seule clé `"consolidated_skills"`, dont la valeur est la liste finale des compétences nettoyées et classées.

LISTE DE COMPÉTENCES À CONSOLIDER :
__SKILLS_TO_CONSOLIDATE__