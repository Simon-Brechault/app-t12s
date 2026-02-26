import streamlit as st
from google import genai
import json
from PIL import Image
import io  # Nécessaire pour la gestion de la compression en mémoire
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# ==========================================
# CONFIGURATION & INITIALISATION
# ==========================================
st.set_page_config(page_title="T12S Meal Planner Pro", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

def charger_bdd():
    try:
        # ttl=0 force la relecture du Google Sheet pour voir les nouveaux profils immédiatement
        df = conn.read(worksheet="BDD", usecols=[0, 1], ttl=0)
        if df.empty or len(df.columns) < 2:
            return {}
        
        df.columns = ['Utilisateur', 'Data']
        users = {}
        for _, row in df.iterrows():
            if pd.notna(row['Utilisateur']) and pd.notna(row['Data']):
                try:
                    users[row['Utilisateur']] = json.loads(row['Data'])
                except:
                    pass
        return users
    except Exception as e:
        st.error(f"Erreur de lecture BDD: {e}")
        return {}

def sauvegarder_utilisateur(nom_utilisateur, data_dict):
    users = charger_bdd()
    users[nom_utilisateur] = data_dict
    
    df = pd.DataFrame({
        "Utilisateur": list(users.keys()),
        "Data": [json.dumps(v, ensure_ascii=False) for v in users.values()]
    })
    conn.update(worksheet="BDD", data=df)

# ==========================================
# FONCTION DE COMPRESSION DES IMAGES
# ==========================================
def compresser_image(image_file, max_size=(800, 800)):
    """Redimensionne et compresse l'image pour un envoi ultra-rapide à l'IA."""
    img = Image.open(image_file)
    
    # Correction de l'orientation et conversion RGB pour JPEG
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    
    # Redimensionnement proportionnel (max 800px)
    img.thumbnail(max_size)
    
    # Compression en mémoire
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=75, optimize=True)
    buffer.seek(0)
    
    return Image.open(buffer)

# ==========================================
# GESTION DES PROFILS (MULTI-UTILISATEURS)
# ==========================================
bdd_users = charger_bdd()
liste_utilisateurs = ["-- Choisir un profil --", "➕ Créer un nouveau profil"] + list(bdd_users.keys())

with st.sidebar:
    st.title("👤 Mon Profil")
    choix_user = st.selectbox("Qui êtes-vous ?", liste_utilisateurs)

# --- ECRAN D'ACCUEIL ---
if choix_user == "-- Choisir un profil --":
    st.title("🥗 Bienvenue sur le Planificateur T12S")
    st.info("👈 Veuillez sélectionner votre profil à gauche ou en créer un nouveau pour commencer.")
    st.stop()

# --- ECRAN DE CREATION DE PROFIL ---
elif choix_user == "➕ Créer un nouveau profil":
    st.title("🆕 Bilan Nutritionnel & Profil")
    st.write("Répondez à ce questionnaire pour personnaliser vos futurs menus.")
    
    with st.form("form_creation"):
        st.subheader("👤 Informations de base")
        col1, col2 = st.columns(2)
        prenom = col1.text_input("Prénom")
        nom = col2.text_input("Nom")
        
        st.subheader("🎯 Vos Objectifs")
        objectif = st.selectbox("Quel est votre objectif principal ?", [
            "Perte de poids (Style T12S - Sain, équilibré, sans frustration)", 
            "Maintien & Santé (Manger mieux au quotidien)", 
            "Prise de masse musculaire (Riche en protéines)", 
            "Végétarien Gourmand"
        ])
        
        st.subheader("🔥 Mode de vie")
        col3, col4 = st.columns(2)
        activite = col3.selectbox("Niveau d'activité physique", ["Sédentaire", "Actif", "Sportif régulier"])
        temps_cuisine = col4.selectbox("Temps en cuisine par repas", ["Moins de 15 min", "15 à 30 min", "Plus de 30 min"])

        st.subheader("🚫 Contraintes")
        allergies = st.text_input("Allergies (ex: Gluten, Lactose...)", placeholder="Aucune")
        aversions = st.text_input("Ce que vous détestez", placeholder="Rien")
        
        if st.form_submit_button("Valider mon profil"):
            if prenom and nom:
                nom_complet = f"{prenom} {nom}"
                nouveau_profil = {
                    "profil": {"prenom": prenom, "nom": nom, "objectif": objectif, "activite": activite, "temps_cuisine": temps_cuisine, "allergies": allergies, "aversions": aversions},
                    "menu_semaine": None, "notes_repas": {}, "repas_faits": [], "liste_courses": None
                }
                sauvegarder_utilisateur(nom_complet, nouveau_profil)
                st.success("Profil créé ! La page va s'actualiser...")
                st.rerun()
    st.stop()

# ==========================================
# VARIABLES DU PROFIL ACTUEL
# ==========================================
current_user_data = bdd_users[choix_user]
def save_current(): sauvegarder_utilisateur(choix_user, current_user_data)

profil = current_user_data.get("profil", {})
menu_semaine = current_user_data.get("menu_semaine")
notes_repas = current_user_data.get("notes_repas", {})
repas_faits = current_user_data.get("repas_faits", [])
liste_courses = current_user_data.get("liste_courses")
jours_semaine = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]

# ==========================================
# FONCTIONS API GEMINI
# ==========================================
def generer_repas(envies, jour_debut_index, photos=None, mode_strict=False):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    repas_a_eviter = [plat for plat, note in notes_repas.items() if note is not None and note <= 2]
    jours_a_generer = jours_semaine[jour_debut_index:]

    prompt = f"""
    Tu es un coach expert. Crée un menu sur-mesure pour {profil['prenom']}.
    Objectif : {profil['objectif']} | Allergies : {profil['allergies']} | Temps : {profil['temps_cuisine']}.
    Menu pour : {jours_a_generer}. Envies : {envies if envies else "Varié"}.
    """
    
    if photos:
        if mode_strict:
            prompt += "\n🚨 MODE STRICT : Utilise UNIQUEMENT les ingrédients des photos (0 courses)."
        else:
            prompt += "\n💡 ANTI-GASPI : Utilise en priorité les ingrédients des photos."

    prompt += "\nFormat JSON attendu : {'Jour': {'Matin': {'titre': '...', 'recette': '...', 'calories_estimees': '...'}}}"

    contenu_a_envoyer = [prompt]
    
    # Compression et ajout des photos
    if photos:
        for p in photos:
            try:
                contenu_a_envoyer.append(compresser_image(p))
            except:
                pass

    try:
        response = client.models.generate_content(model=st.secrets["GEMINI_MODEL"], contents=contenu_a_envoyer)
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Erreur API : {e}")
        return None

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
st.title(f"🍽️ Planificateur de {profil.get('prenom', '')}")

with st.sidebar:
    st.markdown("---")
    envies = st.text_area("💭 Mes envies")
    jour_actuel = st.selectbox("📅 Quel jour ?", jours_semaine)
    st.markdown("---")
    st.subheader("📸 Inventaire")
    photos_frigo = st.file_uploader("Prendre en photo le stock", type=["jpg", "png"], accept_multiple_files=True)
    mode_strict = st.checkbox("🚨 Mode Strict (Cuisiner uniquement avec le stock)") if photos_frigo else False

    if st.button("🪄 Générer le menu"):
        with st.spinner("Analyse du profil et des photos..."):
            nouveau = generer_repas(envies, jours_semaine.index(jour_actuel), photos_frigo, mode_strict)
            if nouveau:
                if menu_semaine is None: current_user_data["menu_semaine"] = nouveau
                else: current_user_data["menu_semaine"].update(nouveau)
                save_current()
                st.rerun()

if menu_semaine:
    tabs = st.tabs(list(menu_semaine.keys()))
    for i, (jour, repas_jour) in enumerate(menu_semaine.items()):
        with tabs[i]:
            for moment in ["Matin", "Midi", "Soir"]:
                if moment in repas_jour:
                    plat = repas_jour[moment]
                    rid = f"{jour}_{moment}"
                    col1, col2 = st.columns([0.1, 0.9])
                    with col1:
                        if st.checkbox("Fait", value=(rid in repas_faits), key=f"c_{rid}"):
                            if rid not in repas_faits: current_user_data["repas_faits"].append(rid); save_current(); st.rerun()
                        elif rid in repas_faits: current_user_data["repas_faits"].remove(rid); save_current(); st.rerun()
                    with col2:
                        st.subheader(f"{moment} : {plat['titre']}")
                        with st.expander("Voir recette"): st.write(plat['recette'])

    st.markdown("---")
    if st.button("📝 Faire la liste de courses"):
        client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
        res = client.models.generate_content(model=st.secrets["GEMINI_MODEL"], contents=f"Fais la liste de courses pour ce menu : {json.dumps(menu_semaine)}. Format Markdown cases à cocher.")
        current_user_data["liste_courses"] = res.text
        save_current(); st.rerun()
    if liste_courses: st.markdown(liste_courses)
else:
    st.info("👈 Prêt ! Générez votre menu à gauche.")