# -*- coding: utf-8 -*-
"""
Ce module est l'application principale Streamlit pour SkillScope.
Il définit l'interface utilisateur, gère les entrées de l'utilisateur et
orchestre l'appel au pipeline pour afficher les résultats de l'analyse.
"""

import streamlit as st
import pandas as pd
import numpy as np
import base64
import os

# Import des fonctions du pipeline qui contiennent la logique métier.
from src.pipeline import search_for_offers, analyze_offers_details

# --- Configuration de la Page ---
# st.set_page_config() doit être la première commande Streamlit, elle configure les métadonnées et la mise en page de la page.
st.set_page_config(
    page_title="SkillScope | Analyseur de Compétences",
    page_icon="assets/SkillScope.svg",
    layout="wide" # "wide" utilise toute la largeur de l'écran.
)

# --- CSS Personnalisé ---
# Permet d'injecter du CSS pour peaufiner le style de l'application.
st.markdown("""
<style>
    /* On ajoute un peu d'espace en haut de la page principale. */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
    /* Style pour réduire la taille du texte des messages d'info et d'erreur */
    .small-font {
        font-size:0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# --- Fonctions Utilitaires ---
def load_svg(svg_file: str) -> str | None:
    """
    Charge un fichier SVG et l'encode en Base64 pour l'afficher dans Streamlit.
    C'est une méthode fiable pour intégrer des images vectorielles.
    """
    if not os.path.exists(svg_file):
        return None
    with open(svg_file, "r", encoding="utf-8") as f:
        svg = f.read()
    # L'encodage Base64 permet d'intégrer l'image directement dans le HTML.
    svg_base64 = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{svg_base64}"

# --- Interface Statique (Titre et description) ---
logo_svg_base64 = load_svg("assets/SkillScope.svg")
if logo_svg_base64:
    st.markdown(
        f'<div style="text-align: center;"><img src="{logo_svg_base64}" width="300"></div>',
        unsafe_allow_html=True
    )
else:
    # Si le logo ne peut pas être chargé, on affiche un titre texte simple.
    st.title("SkillScope")

st.markdown("""
<div style='text-align: center;'>
Un outil pour extraire et quantifier les compétences les plus demandées sur le marché.<br>
<em>Basé sur les offres de <strong>Welcome to the Jungle</strong>.</em>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

# --- Conteneur principal pour centrer le contenu ---
# On crée des colonnes pour centrer les éléments et éviter qu'ils prennent toute la largeur.
# La colonne du milieu (content_col) contiendra tous les éléments interactifs.
_left_margin, content_col, _right_margin = st.columns([0.2, 0.6, 0.2])

with content_col:
    # --- Barre de recherche principale ---
    # On utilise les colonnes pour aligner le champ de texte et le bouton.
    col1, col2 = st.columns([3, 1]) # Ratio modifié pour réduire la largeur de la barre de recherche.

    with col1:
        job_to_scrape = st.text_input(
            "Quel métier analyser ?",
            placeholder="Ex: Data Engineer, Product Designer...",
            label_visibility="collapsed" # Cache le label qui est redondant.
        )

    with col2:
        launch_button = st.button(
            "Lancer l'analyse",
            type="primary",
            use_container_width=True,
            disabled=(not job_to_scrape)
        )

    # --- Conteneur pour le Contenu Dynamique ---
    # st.empty() crée un conteneur pour mettre à jour l'interface dynamiquement sans accumuler les éléments.
    placeholder = st.empty()

    # --- Logique de Lancement de l'Analyse ---
    # Ce bloc de code ne s'exécute que lorsque l'utilisateur clique sur le bouton.
    if launch_button:
        # st.session_state est un dictionnaire qui stocke les résultats entre les rechargements.
        st.session_state.pop('df_results', None)
        st.session_state.pop('error_message', None)
        st.session_state['job_title'] = job_to_scrape

        # On utilise le placeholder pour afficher les messages de progression.
        with placeholder.container():
            # `st.spinner` affiche un message de chargement tant que le bloc n'est pas terminé.
            with st.spinner(f"Recherche des offres pour **{job_to_scrape}**..."):
                offers_metadata, cookies = search_for_offers(job_to_scrape)

            # Si aucune offre n'est trouvée, on stocke un message d'erreur.
            if not offers_metadata:
                st.session_state['error_message'] = f"Aucune offre d'emploi n'a été trouvée pour le terme '{job_to_scrape}'."
            else:
                # Si des offres sont trouvées, on passe à l'analyse détaillée.
                progress_text = "Analyse des compétences en cours... Patientez."
                progress_bar = st.progress(0, text=progress_text)
                
                # La fonction de callback permet au pipeline de mettre à jour la barre de progression.
                def progress_callback(progress_percentage):
                    progress_bar.progress(progress_percentage, text=f"{progress_text} ({int(progress_percentage * 100)}%)")

                df_results = analyze_offers_details(
                    offers_metadata=offers_metadata,
                    cookies=cookies,
                    progress_callback=progress_callback
                )
                
                # On stocke le DataFrame de résultats ou un message d'erreur.
                if df_results is not None and not df_results.empty:
                    st.session_state['df_results'] = df_results
                else:
                    st.session_state['error_message'] = "L'analyse a échoué ou aucune compétence n'a pu être extraite."
        
        # st.rerun() force le rechargement du script pour que l'affichage utilise les nouvelles données.
        st.rerun()

    # --- Logique d'Affichage des Résultats ---
    # Ce bloc s'exécute à chaque chargement de page et utilise st.session_state pour décider quoi afficher.
    with placeholder.container():
        # Cas 1 : Une erreur est survenue.
        if 'error_message' in st.session_state:
            st.error(st.session_state['error_message'], icon="🚨")

        # Cas 2 : Les résultats sont disponibles.
        elif 'df_results' in st.session_state:
            df = st.session_state['df_results']
            job_title = st.session_state.get('job_title', 'le métier analysé')
            
            st.subheader(f"📊 Résultats de l'analyse pour : {job_title}", anchor=False)

            # On utilise Pandas pour transformer la liste de tags en un comptage de fréquence.
            tags_exploded = df['tags'].explode().dropna()
            
            if not tags_exploded.empty:
                skill_counts = tags_exploded.value_counts().reset_index()
                skill_counts.columns = ['Compétence', 'Fréquence']
                # On ajoute une colonne de classement pour une meilleure lisibilité.
                skill_counts.index = np.arange(1, len(skill_counts) + 1)
                skill_counts.insert(0, 'Classement', skill_counts.index)
                
                # Affichage des métriques clés.
                col1, col2, col3 = st.columns(3)
                col1.metric("Offres avec Compétences", f"{len(df)}")
                col2.metric("Compétences Uniques", f"{len(skill_counts)}")
                col3.metric("Top Compétence", skill_counts.iloc[0]['Compétence'])

                st.subheader("Classement des compétences", anchor=False)
                # Ajout d'un champ de recherche pour filtrer le tableau de compétences.
                search_skill = st.text_input("Rechercher une compétence :", placeholder="Ex: Power BI, Git...", label_visibility="collapsed")
                if search_skill:
                    skill_counts_display = skill_counts[skill_counts['Compétence'].str.contains(search_skill, case=False, na=False)]
                else:
                    skill_counts_display = skill_counts

                # `st.dataframe` est utilisé pour afficher les DataFrames Pandas de manière interactive.
                st.dataframe(skill_counts_display, use_container_width=True, hide_index=True)
            else:
                st.warning("Aucune compétence n'a pu être extraite des offres analysées.")
                
        # Cas 3 (état initial) : Aucune analyse n'a encore été lancée.
        else:
            # Utilisation de HTML pour un message plus petit et centré
            st.markdown("<p class='small-font' style='text-align: center;'>Lancez une analyse pour afficher les résultats.</p>", unsafe_allow_html=True)


# --- Pied de page (Footer) ---
st.markdown("---")
# Le footer est maintenant directement visible, sans avoir à être déplié.
st.markdown("""
<div style="text-align: center; font-family: 'Source Sans Pro', sans-serif;">
    <p style="font-size: 0.9em; margin-bottom: 10px;">
        SkillScope a été développé par <strong style="color: #2474c5;">Hamza Kachmir</strong>
    </p>
    <p style="font-size: 1.1em;">
        <a href="https://portfolio-hamza-kachmir.vercel.app/" target="_blank" style="text-decoration: none; margin-right: 15px;">
            <strong style="color: #F9B15C;">Portfolio</strong>
        </a>
        <a href="https://www.linkedin.com/in/hamza-kachmir/" target="_blank" style="text-decoration: none;">
            <strong style="color: #F9B15C;">LinkedIn</strong>
        </a>
    </p>
</div>
""", unsafe_allow_html=True)