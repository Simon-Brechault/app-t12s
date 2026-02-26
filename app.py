import streamlit as st
from google import genai
import json
from PIL import Image
import io
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta # NOUVEAU : Outils de temps

# ==========================================
# CONFIGURATION & SÉCURITÉ
# ==========================================
st.set_page_config(page_title="T12S Meal Planner Pro", layout="wide")

def check_password():
    if "password_correct" not in st.session_state:
        st.session_state["password_correct"] = False
    if not st.session_state["password_correct"]:
        st.title("🔒 Accès Restreint")
        pwd = st.text_input("Mot de passe", type="password")
        if st.button("Valider"):
            if pwd == st.secrets.get("APP_PASSWORD", "T12S"):
                st.session_state["password_correct"] = True
                st.rerun()
            else:
                st.error("Mot de passe incorrect ❌")
        st.stop()
check_password()

# ==========================================
# OUTILS DE DATES EN FRANÇAIS
# ==========================================
JOURS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MOIS_FR = ["Janvier", "Février", "Mars", "Avril", "Mai", "Juin", "Juillet", "Août", "Septembre", "Octobre", "Novembre", "Décembre"]

def formater_date_fr(date_obj):
    jour = JOURS_FR[date_obj.weekday()]
    mois = MOIS_FR[date_obj.month - 1]
    return f"{jour} {date_obj.day} {mois} {date_obj.year}"

# ==========================================
# BASE DE DONNÉES
# ==========================================
conn = st.connection("gsheets", type=GSheetsConnection)

def charger_bdd():
    try:
        df = conn.read(worksheet="BDD", usecols=[0, 1], ttl=0)
        if df.empty or len(df.columns) < 2: return {}
        df.columns = ['Utilisateur', 'Data']
        users = {}
        for _, row in df.iterrows():
            if pd.notna(row['Utilisateur']) and pd.notna(row['Data']):
                try: users[row['Utilisateur']] = json.loads(row['Data'])
                except: pass
        return users
    except Exception as e:
        return {}

def sauvegarder_utilisateur(nom_utilisateur, data_dict):
    users = charger_bdd()
    users[nom_utilisateur] = data_dict
    df = pd.DataFrame({
        "Utilisateur": list(users.keys()),
        "Data": [json.dumps(v, ensure_ascii=False) for v in users.values()]
    })
    conn.update(worksheet="BDD", data=df)

def compresser_image(image_file, max_size=(800, 800)):
    img = Image.open(image_file)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail(max_size)
    buffer = io.BytesIO()
    img.save(buffer, format="JPEG", quality=75, optimize=True)
    buffer.seek(0)
    return Image.open(buffer)

# ==========================================
# GESTION DES PROFILS
# ==========================================
bdd_users = charger_bdd()
liste_utilisateurs = ["-- Choisir un profil --", "➕ Créer un nouveau profil"] + list(bdd_users.keys())

with st.sidebar:
    st.title("👤 Mon Profil")
    choix_user = st.selectbox("Qui êtes-vous ?", liste_utilisateurs)

def afficher_formulaire_profil(donnees_existantes=None):
    is_edit = donnees_existantes is not None
    p = donnees_existantes if is_edit else {}
    
    with st.form("form_profil"):
        st.subheader("👤 Informations de base")
        col1, col2, col3 = st.columns(3)
        prenom = col1.text_input("Prénom", value=p.get("prenom", ""))
        nom = col2.text_input("Nom", value=p.get("nom", ""))
        poids = col3.number_input("Poids (kg)", min_value=30, max_value=200, value=int(p.get("poids", 70)))
        
        st.subheader("🎯 Objectifs & Mode de vie")
        objectif = st.selectbox("Objectif principal", ["Perte de poids (Style T12S)", "Maintien & Santé", "Prise de masse musculaire", "Végétarien Gourmand"], index=0 if not is_edit else ["Perte de poids (Style T12S)", "Maintien & Santé", "Prise de masse musculaire", "Végétarien Gourmand"].index(p.get("objectif", "Perte de poids (Style T12S)")))
        temps_cuisine = st.selectbox("Temps en cuisine par repas", ["Moins de 15 min", "15 à 30 min", "Plus de 30 min"], index=0 if not is_edit else ["Moins de 15 min", "15 à 30 min", "Plus de 30 min"].index(p.get("temps_cuisine", "15 à 30 min")))

        st.subheader("🏃‍♂️ Activité Sportive")
        sports = st.text_input("Quels sports pratiquez-vous ? (Séparés par des virgules)", value=p.get("sports", ""), placeholder="ex: Musculation, Vélo, Course à pied")

        st.subheader("🚫 Contraintes")
        allergies = st.text_input("Allergies (ex: Gluten, Lactose...)", value=p.get("allergies", ""))
        aversions = st.text_input("Ce que vous détestez", value=p.get("aversions", ""))
        
        if st.form_submit_button("Mettre à jour mon profil" if is_edit else "Créer mon profil"):
            if prenom and nom:
                nom_complet = f"{prenom} {nom}"
                nouveau_profil = {"prenom": prenom, "nom": nom, "poids": poids, "objectif": objectif, "temps_cuisine": temps_cuisine, "sports": sports, "allergies": allergies, "aversions": aversions}
                if not is_edit: data_complete = {"profil": nouveau_profil, "menu_semaine": None, "notes_repas": {}, "repas_faits": [], "liste_courses": None}
                else:
                    data_complete = bdd_users[nom_complet]
                    data_complete["profil"] = nouveau_profil
                sauvegarder_utilisateur(nom_complet, data_complete)
                st.session_state["edit_mode"] = False
                st.success("Profil enregistré ! Actualisation...")
                st.rerun()

if choix_user == "-- Choisir un profil --":
    st.title("🥗 Bienvenue sur le Planificateur T12S")
    st.info("👈 Veuillez sélectionner votre profil à gauche ou en créer un nouveau pour commencer.")
    st.stop()
elif choix_user == "➕ Créer un nouveau profil":
    st.title("🆕 Bilan Nutritionnel & Profil")
    afficher_formulaire_profil()
    st.stop()

# ==========================================
# VARIABLES DU PROFIL ACTUEL
# ==========================================
current_user_data = bdd_users[choix_user]
profil = current_user_data.get("profil", {})

if "edit_mode" not in st.session_state: st.session_state["edit_mode"] = False
with st.sidebar:
    if st.button("⚙️ Modifier mon profil"): st.session_state["edit_mode"] = not st.session_state["edit_mode"]

if st.session_state["edit_mode"]:
    st.title("⚙️ Modification du profil")
    afficher_formulaire_profil(donnees_existantes=profil)
    st.stop()

def save_current(): sauvegarder_utilisateur(choix_user, current_user_data)

menu_semaine = current_user_data.get("menu_semaine")
notes_repas = current_user_data.get("notes_repas", {})
repas_faits = current_user_data.get("repas_faits", [])
liste_courses = current_user_data.get("liste_courses")

# ==========================================
# FONCTIONS API GEMINI (AVEC DATES)
# ==========================================
def generer_repas(envies, jours_a_generer, photos=None, mode_strict=False):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    repas_a_eviter = [plat for plat, note in notes_repas.items() if note is not None and note <= 2]

    prompt = f"""
    Tu es un coach expert. Crée un menu sur-mesure pour {profil['prenom']}.
    Objectif : {profil['objectif']} | Poids : {profil['poids']}kg | Sports pratiqués : {profil['sports']}
    Allergies : {profil['allergies']} | Temps max en cuisine : {profil['temps_cuisine']}.
    
    IMPORTANT : Voici les dates exactes de la semaine à planifier : {jours_a_generer}.
    Adapte tes recettes avec des fruits et légumes de saison correspondants à ces dates !
    Envies de la semaine : {envies if envies else "Varié"}.
    """
    
    if photos:
        if mode_strict: prompt += "\n🚨 MODE STRICT : Utilise UNIQUEMENT les ingrédients des photos (0 courses)."
        else: prompt += "\n💡 ANTI-GASPI : Utilise en priorité les ingrédients des photos."

    # On demande à Gemini de reprendre exactement les dates comme clés du JSON
    prompt += """
    Format JSON attendu (utilise EXACTEMENT les dates fournies comme clés, ex: 'Lundi 14 Mars 2026') :
    {
      "Date 1": {"Matin": {"titre": "...", "recette": "...", "calories_estimees": "..."}, "Midi": {...}, "Soir": {...}},
      "Date 2": {"Matin": {...}, "Midi": {...}, "Soir": {...}}
    }
    """

    contenu_a_envoyer = [prompt]
    if photos:
        for p in photos:
            try: contenu_a_envoyer.append(compresser_image(p))
            except: pass

    try:
        response = client.models.generate_content(model=st.secrets["GEMINI_MODEL"], contents=contenu_a_envoyer)
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Erreur API : {e}")
        return None

# ==========================================
# INTERFACE PRINCIPALE (CALENDRIER)
# ==========================================
st.title(f"🍽️ Planificateur de {profil.get('prenom', '')}")

with st.sidebar:
    st.markdown("---")
    st.subheader("📅 Planification")
    
    # LE FAMEUX CALENDRIER
    date_debut = st.date_input("Date de début de la semaine", datetime.today())
    # On calcule les 7 jours à partir de la date choisie
    jours_generes = [formater_date_fr(date_debut + timedelta(days=i)) for i in range(7)]
    
    st.markdown("---")
    envies = st.text_area("💭 Mes envies")
    st.subheader("📸 Inventaire")
    photos_frigo = st.file_uploader("Prendre en photo le stock", type=["jpg", "png"], accept_multiple_files=True)
    mode_strict = st.checkbox("🚨 Mode Strict (Cuisiner uniquement avec le stock)") if photos_frigo else False

    if st.button("🪄 Générer le menu (7 jours)"):
        with st.spinner(f"Création du menu pour la semaine du {jours_generes[0]}..."):
            # On envoie la liste des 7 jours exacts à Gemini !
            nouveau = generer_repas(envies, jours_generes, photos_frigo, mode_strict)
            if nouveau:
                current_user_data["menu_semaine"] = nouveau # On remplace l'ancien menu
                save_current()
                st.rerun()

if menu_semaine:
    st.info(f"Semaine planifiée : Vous avez sélectionné vos repas en fonction de votre calendrier.")
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
    st.info("👈 Choisissez une date de début et générez votre menu à gauche.")