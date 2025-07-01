import streamlit as st
import pandas as pd
import numpy as np
import base64
import os

# Import des fonctions du pipeline contenant la logique métier.
from src.pipeline import search_for_offers, analyze_offers_details

# --- Configuration de la Page ---
# Configure la page Streamlit. Doit être la première commande Streamlit exécutée.
st.set_page_config(
    page_title="SkillScope | Analyseur de Compétences",
    page_icon="assets/SkillScope.svg",
    layout="wide"
)

# --- CSS Personnalisé ---
# Injecte du CSS pour un style personnalisé.
st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; padding-bottom: 2rem; }
    .small-font { font-size:0.9rem; }
</style>
""", unsafe_allow_html=True)

# --- Fonctions Utilitaires ---
def load_svg(svg_file: str) -> str | None:
    """
    Charge un fichier SVG et l'encode en Base64 pour l'affichage.

    Args:
        svg_file (str): Le chemin vers le fichier SVG.

    Returns:
        str | None: La chaîne de données Base64, ou None si le fichier est introuvable.
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
# Affiche le logo SVG, ou un titre texte simple si le fichier est introuvable.
if logo_svg_base64:
    st.markdown(
        f'<div style="text-align: center;"><img src="{logo_svg_base64}" width="300"></div>',
        unsafe_allow_html=True
    )
else:
    st.title("SkillScope")

# Description de l'outil avec la précision sur les deux premières pages.
st.markdown("""
<div style='text-align: center;'>
Un outil pour extraire et quantifier les compétences les plus demandées sur le marché.<br>
<em>Basé sur les <strong>deux premières pages</strong> des offres de <strong>Welcome to the Jungle</strong>.</em>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

# --- Conteneur principal ---
# Centre le contenu principal à l'aide de colonnes pour une meilleure disposition.
_left_margin, content_col, _right_margin = st.columns([0.2, 0.6, 0.2])

with content_col:
    # --- Barre de recherche ---
    # Aligne le champ de texte et le bouton sur la même ligne.
    col1, col2 = st.columns([3, 1])

    with col1:
        # Champ de saisie pour que l'utilisateur entre le métier à analyser.
        job_to_scrape = st.text_input(
            "Quel métier analyser ?",
            placeholder="Ex: Data Engineer, Product Designer...",
            label_visibility="collapsed" # Cache le label qui est redondant.
        )

    with col2:
        # Bouton pour déclencher l'analyse.
        launch_button = st.button(
            "Lancer l'analyse",
            type="primary",
            use_container_width=True,
            disabled=(not job_to_scrape)
        )

    # --- Conteneur Dynamique ---
    # Crée un conteneur "placeholder" qui sera mis à jour dynamiquement.
    placeholder = st.empty()

    # --- Logique de Lancement ---
    # Ce bloc s'exécute uniquement au clic sur le bouton.
    if launch_button:
        # Nettoie les résultats d'une analyse précédente de la session.
        st.session_state.pop('df_results', None)
        st.session_state.pop('error_message', None)
        st.session_state['job_title'] = job_to_scrape

        # Affiche les messages de progression dans le placeholder.
        with placeholder.container():
            # Affiche une animation de chargement pendant la recherche.
            with st.spinner(f"Recherche des offres pour **{job_to_scrape}**..."):
                offers_metadata, cookies = search_for_offers(job_to_scrape)

            # Gère le cas où aucune offre n'est trouvée.
            if not offers_metadata:
                st.session_state['error_message'] = f"Aucune offre d'emploi n'a été trouvée pour '{job_to_scrape}'."
            else:
                progress_text = "Analyse des compétences en cours... Patientez."
                progress_bar = st.progress(0, text=progress_text)
                
                # Callback pour mettre à jour la barre de progression depuis le pipeline.
                def progress_callback(progress_percentage):
                    progress_bar.progress(progress_percentage, text=f"{progress_text} ({int(progress_percentage * 100)}%)")
                
                # Appelle la deuxième étape du pipeline pour l'analyse détaillée.
                df_results = analyze_offers_details(
                    offers_metadata=offers_metadata,
                    cookies=cookies,
                    progress_callback=progress_callback
                )
                
                # Stocke les résultats ou un message d'erreur dans l'état de la session.
                if df_results is not None and not df_results.empty:
                    st.session_state['df_results'] = df_results
                else:
                    st.session_state['error_message'] = "L'analyse a échoué ou aucune compétence n'a pu être extraite."
        
        # Force le rechargement du script pour afficher les nouvelles données.
        st.rerun()

    # --- Logique d'Affichage ---
    # Ce bloc gère l'affichage des résultats, d'une erreur, ou du message initial.
    with placeholder.container():
        # Cas 1 : Une erreur est survenue, on l'affiche.
        if 'error_message' in st.session_state:
            st.error(st.session_state['error_message'], icon="🚨")

        # Cas 2 : Les résultats sont disponibles, on les affiche.
        elif 'df_results' in st.session_state:
            df = st.session_state['df_results']
            job_title = st.session_state.get('job_title', 'le métier analysé')
            
            st.subheader(f"📊 Résultats de l'analyse pour : {job_title}", anchor=False)

            # Transforme la colonne 'tags' pour avoir une ligne par compétence.
            tags_exploded = df['tags'].explode().dropna()
            
            if not tags_exploded.empty:
                skill_counts = tags_exploded.value_counts().reset_index()
                skill_counts.columns = ['Compétence', 'Fréquence']
                skill_counts.index = np.arange(1, len(skill_counts) + 1)
                skill_counts.insert(0, 'Classement', skill_counts.index)
                
                # Affiche les métriques clés de l'analyse.
                col1, col2, col3 = st.columns(3)
                col1.metric("Offres Analysées", f"{len(df)}")
                col2.metric("Compétences Uniques", f"{len(skill_counts)}")
                col3.metric("Top Compétence", skill_counts.iloc[0]['Compétence'])

                st.subheader("Classement des compétences", anchor=False)
                # Champ de recherche pour filtrer le tableau de compétences.
                search_skill = st.text_input("Rechercher une compétence :", placeholder="Ex: Power BI, Git...", label_visibility="collapsed")
                if search_skill:
                    skill_counts_display = skill_counts[skill_counts['Compétence'].str.contains(search_skill, case=False, na=False)]
                else:
                    skill_counts_display = skill_counts

                # Affiche le tableau des compétences.
                st.dataframe(skill_counts_display, use_container_width=True, hide_index=True)
            else:
                st.warning("Aucune compétence n'a pu être extraite des offres analysées.")
                
        # Cas 3 (état initial) : Affiche une invitation à lancer une analyse.
        else:
            st.info("Lancez une analyse pour afficher les résultats.", icon="💡")


# --- Footer ---
st.markdown("---")
st.markdown("""
<div style="text-align: center; font-family: 'Source Sans Pro', sans-serif;">
    <p style="font-size: 0.9em; margin-bottom: 10px;">
        Développé par <strong style="color: #2474c5;">Hamza Kachmir</strong>
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