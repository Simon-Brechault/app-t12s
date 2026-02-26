import streamlit as st
from google import genai
import json
from PIL import Image
from streamlit_gsheets import GSheetsConnection
import pandas as pd

# ==========================================
# CONFIGURATION & INITIALISATION
# ==========================================
st.set_page_config(page_title="T12S Meal Planner", layout="wide")

conn = st.connection("gsheets", type=GSheetsConnection)

def charger_bdd():
    try:
        # On lit tout le tableau
        df = conn.read(worksheet="BDD", usecols=[0, 1])
        if df.empty or len(df.columns) < 2:
            return {}
        
        df.columns = ['Utilisateur', 'Data']
        users = {}
        # On transforme chaque ligne en dictionnaire
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
    
    # On recrée le tableau avec tous les utilisateurs mis à jour
    df = pd.DataFrame({
        "Utilisateur": list(users.keys()),
        "Data": [json.dumps(v, ensure_ascii=False) for v in users.values()]
    })
    conn.update(worksheet="BDD", data=df)

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
    st.title("🆕 Créer un profil personnalisé")
    st.write("Répondez à ces quelques questions pour que Gemini adapte parfaitement ses recettes à votre métabolisme et vos goûts.")
    
    with st.form("form_creation"):
        prenom = st.text_input("Prénom")
        nom = st.text_input("Nom")
        objectif = st.selectbox("🎯 Quel est votre objectif principal ?", [
            "Perte de poids (Style T12S - Sain et équilibré)", 
            "Maintien & Santé (Manger mieux au quotidien)", 
            "Prise de masse musculaire (Riche en protéines)", 
            "Végétarien Gourmand"
        ])
        preferences = st.text_area("⚠️ Avez-vous des allergies ou des aversions ? (ex: pas de porc, sans lactose, je déteste les brocolis...)")
        
        submit = st.form_submit_button("Créer mon compte")
        if submit and prenom and nom:
            nom_complet = f"{prenom} {nom}"
            if nom_complet in bdd_users:
                st.error("Ce profil existe déjà !")
            else:
                nouveau_profil = {
                    "profil": {
                        "prenom": prenom,
                        "nom": nom,
                        "objectif": objectif,
                        "preferences": preferences
                    },
                    "menu_semaine": None,
                    "notes_repas": {},
                    "repas_faits": [],
                    "liste_courses": None
                }
                sauvegarder_utilisateur(nom_complet, nouveau_profil)
                st.success("Profil créé avec succès ! Sélectionnez-le maintenant dans le menu de gauche.")
                st.rerun()
    st.stop()

# ==========================================
# VARIABLES DU PROFIL ACTUEL
# ==========================================
current_user_data = bdd_users[choix_user]

# Fonction raccourcie pour sauvegarder la progression de l'utilisateur actuel
def save_current():
    sauvegarder_utilisateur(choix_user, current_user_data)

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

    # Le prompt est maintenant hyper personnalisé selon le profil !
    prompt = f"""
    Tu es un coach en nutrition de classe mondiale. Tu dois créer un menu pour {profil['prenom']}.
    Voici le profil de {profil['prenom']} :
    - Objectif principal : {profil['objectif']}
    - Allergies et aversions (NE JAMAIS UTILISER) : {profil['preferences']}
    
    Génère un menu pour les jours suivants : {jours_a_generer} (Matin, Midi, Soir).
    - Envies du moment : {envies if envies else "Aucune, surprends-moi !"}
    - Repas INTERDITS (déjà mal notés) : {repas_a_eviter}
    """
    
    if photos:
        if mode_strict:
            prompt += "\n\n🚨 CONTRAINTE STRICTE (ANTI-GASPI) : L'utilisateur a fourni des photos de ses placards/frigo. Tu dois EXCLUSIVEMENT utiliser les ingrédients visibles sur ces photos pour créer les recettes. N'ajoute aucun ingrédient qui nécessiterait d'aller faire des courses (sauf sel/poivre/eau)."
        else:
            prompt += "\n\n💡 ASTUCE ANTI-GASPI : Inspire-toi au maximum des ingrédients visibles sur les photos fournies pour vider les restes, mais tu es autorisé à rajouter d'autres ingrédients pour compléter les recettes si besoin."

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

    contenu_a_envoyer = [prompt]
    if photos:
        for p in photos:
            contenu_a_envoyer.append(Image.open(p))

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
    prompt = f"Voici un menu : {json.dumps(menu)}. Fais la liste de courses détaillée. Regroupe par rayon. Format : cases à cocher Markdown `- [ ] Ingrédient`."
    try:
        response = client.models.generate_content(model=st.secrets["GEMINI_MODEL"], contents=prompt)
        return response.text
    except:
        return None

# ==========================================
# INTERFACE UTILISATEUR PRINCIPALE
# ==========================================
st.title(f"🍽️ Le Planificateur de {profil.get('prenom', '')}")
st.caption(f"Objectif : {profil.get('objectif', '')}")

with st.sidebar:
    st.markdown("---")
    envies = st.text_area("💭 Mes envies de la semaine")
    jour_actuel = st.selectbox("📅 Nous sommes quel jour ?", jours_semaine)
    jour_index = jours_semaine.index(jour_actuel)

    st.markdown("---")
    st.subheader("📸 Anti-Gaspi Pro")
    st.info("Ajoutez autant de photos que vous le souhaitez !")
    
    # On utilise file_uploader avec accept_multiple_files, c'est génial sur iPhone !
    photos_frigo = st.file_uploader("Photos (Frigo, Placards...)", type=["jpg", "jpeg", "png"], accept_multiple_files=True)
    
    mode_strict = False
    if photos_frigo:
        mode_strict = st.checkbox("🚨 Mode Strict : Cuisiner UNIQUEMENT avec ces ingrédients (0 courses !)")

    if st.button("🪄 Générer le menu"):
        with st.spinner("Gemini analyse votre profil et vos photos..."):
            nouveau_menu = generer_repas(envies, jour_index, photos_frigo, mode_strict)
            if nouveau_menu:
                if menu_semaine is None:
                    current_user_data["menu_semaine"] = nouveau_menu
                else:
                    current_user_data["menu_semaine"].update(nouveau_menu)
                save_current()
                st.success("Menu généré avec succès !")
                st.rerun()

# --- AFFICHAGE DU MENU ---
if menu_semaine:
    total_repas = len(menu_semaine) * 3
    repas_coches = len(repas_faits)
    st.progress(repas_coches / total_repas if total_repas > 0 else 0, text=f"Progression : {repas_coches}/{total_repas} repas dégustés !")

    tabs = st.tabs(list(menu_semaine.keys()))
    
    for i, (jour, repas_jour) in enumerate(menu_semaine.items()):
        with tabs[i]:
            for moment in ["Matin", "Midi", "Soir"]:
                if moment in repas_jour:
                    plat = repas_jour[moment]
                    titre_plat = plat['titre']
                    repas_id = f"{jour}_{moment}"
                    
                    col1, col2, col3 = st.columns([0.1, 0.6, 0.3])
                    with col1:
                        est_coche = repas_id in repas_faits
                        if st.checkbox("Fait", value=est_coche, key=f"check_{repas_id}"):
                            if repas_id not in repas_faits:
                                current_user_data["repas_faits"].append(repas_id)
                                save_current()
                                st.rerun()
                        else:
                            if repas_id in repas_faits:
                                current_user_data["repas_faits"].remove(repas_id)
                                save_current()
                                st.rerun()
                    with col2:
                        st.subheader(f"🍽️ {moment} : {titre_plat}")
                        with st.expander("Voir la recette"):
                            st.write(f"**Calories :** {plat['calories_estimees']}")
                            st.write(plat['recette'])
                    with col3:
                        note_actuelle = notes_repas.get(titre_plat, 0) - 1 if notes_repas.get(titre_plat) else None
                        note = st.feedback("stars", key=f"note_{repas_id}")
                        if note is not None:
                            current_user_data["notes_repas"][titre_plat] = note + 1
                            save_current()

    # --- LISTE DE COURSES ---
    st.markdown("---")
    st.header("🛒 Liste de Courses")
    if st.button("📝 Générer la liste"):
        with st.spinner("Rédaction de la liste..."):
            liste = generer_liste_courses(menu_semaine)
            if liste:
                current_user_data["liste_courses"] = liste
                save_current()
                st.rerun()
                
    if liste_courses:
        st.markdown(liste_courses)
else:
    st.info("👈 Remplissez vos critères à gauche et générez le menu !")