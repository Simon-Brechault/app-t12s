import streamlit as st
from google import genai
import json
import os
from PIL import Image

# ==========================================
# GESTION DE LA BASE DE DONNÉES (FICHIER JSON)
# ==========================================
FICHIER_SAUVEGARDE = "sauvegarde.json"

def charger_donnees():
    """Charge les données depuis le fichier s'il existe, sinon retourne des valeurs par défaut."""
    if os.path.exists(FICHIER_SAUVEGARDE):
        with open(FICHIER_SAUVEGARDE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "menu_semaine": None,
        "notes_repas": {},
        "repas_faits": [] # Liste des identifiants des repas cochés
    }

def sauvegarder_donnees():
    """Sauvegarde l'état actuel de la session dans le fichier JSON."""
    donnees = {
        "menu_semaine": st.session_state.menu_semaine,
        "notes_repas": st.session_state.notes_repas,
        "repas_faits": st.session_state.repas_faits
    }
    with open(FICHIER_SAUVEGARDE, "w", encoding="utf-8") as f:
        json.dump(donnees, f, indent=4, ensure_ascii=False)

# ==========================================
# INITIALISATION DE L'APPLICATION
# ==========================================
st.set_page_config(page_title="T12S Meal Planner", layout="wide")

# On charge les données au démarrage
donnees_sauvegardees = charger_donnees()

if "menu_semaine" not in st.session_state:
    st.session_state.menu_semaine = donnees_sauvegardees["menu_semaine"]
if "notes_repas" not in st.session_state:
    st.session_state.notes_repas = donnees_sauvegardees["notes_repas"]
if "repas_faits" not in st.session_state:
    st.session_state.repas_faits = donnees_sauvegardees["repas_faits"]

jours_semaine = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# ==========================================
# FONCTION APPEL API GEMINI
# ==========================================
def generer_repas(envies, style, jour_debut_index, photo_frigo=None):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    
    repas_a_eviter = [plat for plat, note in st.session_state.notes_repas.items() if note is not None and note <= 2]
    jours_a_generer = jours_semaine[jour_debut_index:]

    prompt = f"""
    Tu es un coach en nutrition inspiré de la méthode "T12S". Tes repas sont "healthy", gourmands, rapides à faire et équilibrés.
    Génère un menu pour les jours suivants : {jours_a_generer}.
    Pour chaque jour, propose 3 repas (Matin, Midi, Soir).
    
    Contraintes :
    - Envies/Ingrédients : {envies if envies else "Aucune, surprends-moi !"}
    - Style de repas : {style}
    - Repas INTERDITS : {repas_a_eviter}
    """
    
    # Si on a une photo, on ajoute une consigne spéciale
    if photo_frigo:
        prompt += "\n- IMPORTANT : J'ai fourni une photo de l'intérieur de mon frigo/placard. Analyse les ingrédients présents sur la photo et utilise-les EN PRIORITÉ absolue pour créer les premiers repas afin de vider mes restes."

    prompt += """
    RÉPOND UNIQUEMENT AVEC UN OBJET JSON VALIDE (pas de texte avant ou après). 
    Format attendu :
    {
      "Lundi": {
        "Matin": {"titre": "...", "recette": "...", "calories_estimees": "..."},
        "Midi": {"titre": "...", "recette": "...", "calories_estimees": "..."},
        "Soir": {"titre": "...", "recette": "...", "calories_estimees": "..."}
      }
    }
    """

    # Préparation du contenu à envoyer (texte seul, ou texte + image)
    contenu_a_envoyer = [prompt]
    if photo_frigo:
        image_ouverte = Image.open(photo_frigo)
        contenu_a_envoyer.append(image_ouverte)

    try:
        response = client.models.generate_content(
            model=st.secrets["GEMINI_MODEL"],
            contents=contenu_a_envoyer,
        )
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Erreur lors de la génération : {e}")
        return None

def generer_liste_courses(menu):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    
    prompt = f"""
    Voici un menu de la semaine généré au format JSON : {json.dumps(menu)}
    Agis comme un assistant d'organisation. 
    Dresse la liste de courses complète et précise pour réaliser tous ces repas.
    Regroupe les ingrédients par rayon (Fruits/Légumes, Viandes/Poissons, Épicerie, Frais, etc.).
    Ne donne pas de quantités au gramme près (car c'est à adapter selon l'appétit), mais donne des indications (ex: "Poulet pour 3 repas", "Bottes de radis").
    Format de sortie : Uniquement du texte en Markdown avec des cases à cocher de ce type : `- [ ] Ingrédient`.
    """

    try:
        response = client.models.generate_content(
            model=st.secrets["GEMINI_MODEL"],
            contents=prompt,
        )
        return response.text
    except Exception as e:
        st.error(f"Erreur lors de la génération de la liste : {e}")
        return None

# ==========================================
# INTERFACE UTILISATEUR
# ==========================================
st.title("🥗 Mon Planificateur Healthy (Style T12S)")

with st.sidebar:
    st.header("⚙️ Paramètres")
    st.success(f"Connecté avec le modèle : {st.secrets["GEMINI_MODEL"]}")
    st.markdown("---")
    
    envies = st.text_area("Mes envies de la semaine")
    style = st.selectbox("Style de repas", ["Équilibré T12S", "Faible en calories", "Riche en protéines", "Végétarien Gourmand"])
    
    jour_actuel = st.selectbox("Nous sommes quel jour ?", jours_semaine)
    jour_index = jours_semaine.index(jour_actuel)

    # ---> NOUVEAUTÉ : ON AJOUTE LA CAMÉRA ICI <---
    st.markdown("---")
    st.subheader("📸 Anti-Gaspi")
    st.info("Prends ton frigo en photo pour que j'utilise tes restes en priorité !")
    photo_frigo = st.camera_input("Appareil photo")

    # Bouton pour générer le menu
    if st.button("🪄 Générer / Actualiser le menu"):
        if not st.secrets["GEMINI_API_KEY"] or st.secrets["GEMINI_API_KEY"].startswith("*"):
            st.warning("Veuillez mettre votre vraie clé API dans config_app.py")
        else:
            with st.spinner("Gemini crée vos recettes..."):
                
                # ---> NOUVEAUTÉ : ON DONNE LA PHOTO À LA FONCTION <---
                nouveau_menu = generer_repas(envies, style, jour_index, photo_frigo)
                
                if nouveau_menu:
                    if st.session_state.menu_semaine is None:
                        st.session_state.menu_semaine = nouveau_menu
                    else:
                        st.session_state.menu_semaine.update(nouveau_menu)
                    
                    # On sauvegarde dès qu'un nouveau menu est créé
                    sauvegarder_donnees()
                    st.success("Menu généré et sauvegardé avec succès !")
                    st.rerun() # Rafraîchit la page pour afficher le nouveau menu

# 3. Affichage du Menu et Barre de progression
if st.session_state.menu_semaine:
    total_repas = len(st.session_state.menu_semaine) * 3
    repas_coches = len(st.session_state.repas_faits)
    
    progress_val = repas_coches / total_repas if total_repas > 0 else 0
    st.progress(progress_val, text=f"Progression : {repas_coches}/{total_repas} repas healthy savourés !")

    tabs = st.tabs(list(st.session_state.menu_semaine.keys()))
    
    for i, (jour, repas_jour) in enumerate(st.session_state.menu_semaine.items()):
        with tabs[i]:
            for moment in ["Matin", "Midi", "Soir"]:
                plat = repas_jour[moment]
                titre_plat = plat['titre']
                repas_id = f"{jour}_{moment}"
                
                col1, col2, col3 = st.columns([0.1, 0.6, 0.3])
                
                with col1:
                    # Gestion de la case à cocher avec sauvegarde automatique
                    est_coche = repas_id in st.session_state.repas_faits
                    if st.checkbox("Fait", value=est_coche, key=f"check_{repas_id}"):
                        if repas_id not in st.session_state.repas_faits:
                            st.session_state.repas_faits.append(repas_id)
                            sauvegarder_donnees()
                            st.rerun()
                    else:
                        if repas_id in st.session_state.repas_faits:
                            st.session_state.repas_faits.remove(repas_id)
                            sauvegarder_donnees()
                            st.rerun()
                            
                with col2:
                    st.subheader(f"🍽️ {moment} : {titre_plat}")
                    with st.expander("Voir la recette"):
                        st.write(f"**Calories estimées :** {plat['calories_estimees']}")
                        st.write(plat['recette'])
                        
                with col3:
                    # Système de notation (sauvegarde automatique)
                    note_actuelle = st.session_state.notes_repas.get(titre_plat, 0) - 1 if st.session_state.notes_repas.get(titre_plat) else None
                    note = st.feedback("stars", key=f"note_{repas_id}")
                    if note is not None:
                        st.session_state.notes_repas[titre_plat] = note + 1
                        sauvegarder_donnees()
# ==========================================
    # LISTE DE COURSES
    # ==========================================
    st.markdown("---")
    st.header("🛒 Ma Liste de Courses")
    
    # On sauvegarde la liste dans la session pour ne pas la regénérer à chaque clic
    if "liste_courses" not in st.session_state:
        st.session_state.liste_courses = None

    if st.button("📝 Générer la liste de courses pour ce menu"):
        with st.spinner("Gemini analyse vos recettes et rédige votre liste..."):
            liste = generer_liste_courses(st.session_state.menu_semaine)
            if liste:
                st.session_state.liste_courses = liste
                # On pourrait aussi sauvegarder ça dans le fichier JSON si tu le souhaites !

    if st.session_state.liste_courses:
        st.info("💡 Astuce : Vous pouvez copier-coller cette liste dans vos notes ou vous l'envoyer par message.")
        st.markdown(st.session_state.liste_courses)
else:
    st.info("👈 Remplissez vos critères dans la barre latérale et générez le menu !")