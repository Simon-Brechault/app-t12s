import streamlit as st
from google import genai
import json
from PIL import Image
import io
import re
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, timedelta

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

def extraire_calories(plat):
    if 'calories' in plat and isinstance(plat['calories'], (int, float)):
        return int(plat['calories'])
    if 'calories_estimees' in plat:
        nums = re.findall(r'\d+', str(plat['calories_estimees']))
        if nums: return int(nums[0])
    return 0

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
        sports = st.text_input("Quels sports pratiquez-vous ? (Séparés par virgules)", value=p.get("sports", ""), placeholder="ex: Musculation, Vélo, Course à pied")

        st.subheader("⌚ Objets Connectés (Balance Calorique)")
        a_montre = st.radio("Portez-vous une montre connectée au quotidien pour suivre votre dépense ?", ["Non", "Oui"], index=0 if p.get("montre", "Non") == "Non" else 1)
        marque_montre = "Aucune"
        if a_montre == "Oui":
            marques_dispos = ["Apple Watch", "Garmin", "Polar", "Wahoo", "Coros", "Suunto", "Samsung Galaxy", "Autre"]
            idx_marque = marques_dispos.index(p.get("marque_montre", "Garmin")) if p.get("marque_montre") in marques_dispos else 0
            marque_montre = st.selectbox("Quelle marque ?", marques_dispos, index=idx_marque)

        st.subheader("🌅 Habitudes du Matin")
        habitudes_matin = st.text_area("Que mangez-vous habituellement le matin ?", value=p.get("habitudes_matin", ""), placeholder="ex: Un grand café et 2 tartines de pain avec de la confiture")
        choix_complexite = ["Simple, rapide et répétitif (Économique & Gain de temps)", "Varié et élaboré"]
        idx_comp = choix_complexite.index(p.get("complexite_matin", choix_complexite[0])) if p.get("complexite_matin") in choix_complexite else 0
        complexite_matin = st.selectbox("Type de petit-déjeuner souhaité pour l'avenir", choix_complexite, index=idx_comp)

        st.subheader("🚫 Contraintes")
        allergies = st.text_input("Allergies (ex: Gluten, Lactose...)", value=p.get("allergies", ""))
        aversions = st.text_input("Ce que vous détestez", value=p.get("aversions", ""))
        
        if st.form_submit_button("Mettre à jour mon profil" if is_edit else "Créer mon profil"):
            if prenom and nom:
                nom_complet = f"{prenom} {nom}"
                nouveau_profil = {
                    "prenom": prenom, "nom": nom, "poids": poids, "objectif": objectif, 
                    "temps_cuisine": temps_cuisine, "sports": sports, 
                    "montre": a_montre, "marque_montre": marque_montre,
                    "habitudes_matin": habitudes_matin, "complexite_matin": complexite_matin,
                    "allergies": allergies, "aversions": aversions
                }
                if not is_edit: data_complete = {"profil": nouveau_profil, "menus_sauvegardes": {}, "notes_repas": {}, "repas_faits": []}
                else:
                    data_complete = bdd_users[nom_complet]
                    data_complete["profil"] = nouveau_profil
                    if "menus_sauvegardes" not in data_complete: data_complete["menus_sauvegardes"] = {}
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
# 🧹 NETTOYAGE AUTOMATIQUE (GARBAGE COLLECTOR)
# ==========================================
current_user_data = bdd_users[choix_user]
if "menus_sauvegardes" not in current_user_data: current_user_data["menus_sauvegardes"] = {}

def save_current(): sauvegarder_utilisateur(choix_user, current_user_data)

def nettoyer_anciennes_semaines():
    aujourd_hui = datetime.today().date()
    lundi_courant = aujourd_hui - timedelta(days=aujourd_hui.weekday())
    semaines_a_supprimer = []
    for id_semaine, data_semaine in current_user_data.get("menus_sauvegardes", {}).items():
        date_iso = data_semaine.get("date_iso")
        if date_iso:
            if datetime.fromisoformat(date_iso).date() < lundi_courant:
                semaines_a_supprimer.append(id_semaine)
                
    if semaines_a_supprimer:
        for s in semaines_a_supprimer: del current_user_data["menus_sauvegardes"][s]
        jours_gardes = []
        for semaine_data in current_user_data["menus_sauvegardes"].values():
            if isinstance(semaine_data.get("menu"), dict): jours_gardes.extend(semaine_data["menu"].keys())
        current_user_data["repas_faits"] = [rid for rid in current_user_data.get("repas_faits", []) if any(rid.startswith(jour) for jour in jours_gardes)]
        save_current()

nettoyer_anciennes_semaines()

profil = current_user_data.get("profil", {})

if "edit_mode" not in st.session_state: st.session_state["edit_mode"] = False
with st.sidebar:
    if st.button("⚙️ Modifier mon profil"): st.session_state["edit_mode"] = not st.session_state["edit_mode"]

if st.session_state["edit_mode"]:
    st.title("⚙️ Modification du profil")
    afficher_formulaire_profil(donnees_existantes=profil)
    st.stop()

notes_repas = current_user_data.get("notes_repas", {})
repas_faits = current_user_data.get("repas_faits", [])

# ==========================================
# FONCTIONS API GEMINI
# ==========================================
def generer_repas_intelligent(envies, config_semaine, identifiant_semaine, diversite_repas, photos=None, mode_strict=False):
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    repas_a_eviter = [plat for plat, note in notes_repas.items() if note is not None and note <= 2]

    prompt = f"""
    Tu es un coach expert. Crée un menu sur-mesure pour {profil['prenom']}.
    Objectif : {profil['objectif']} | Poids : {profil['poids']}kg.
    Allergies : {profil['allergies']} | Aversions : {profil['aversions']} | Temps max : {profil['temps_cuisine']}.
    
    VOICI LA CONFIGURATION EXACTE DE LA SEMAINE :
    """
    for jour, config in config_semaine.items():
        prompt += f"\n- {jour} :"
        prompt += f"\n  Repas : {', '.join(config['repas']) if config['repas'] else 'AUCUN REPAS CE JOUR LA'}"
        if config['sport'] != "Aucun": prompt += f"\n  Sport : {config['sport']} pendant {config['temps_sport']}. (Ajuste les calories !)"
        if config['partenaire'] != "Personne":
            partenaire_data = bdd_users.get(config['partenaire'], {})
            repas_existant = partenaire_data.get("menus_sauvegardes", {}).get(identifiant_semaine, {}).get("menu", {}).get(jour, {}).get("Soir")
            if repas_existant: prompt += f"\n  🚨 Le repas du Soir est partagé avec {config['partenaire']} qui a DÉJÀ prévu ceci : {repas_existant['titre']}. Tu DOIS l'intégrer."
            else: prompt += f"\n  🤝 Le repas du Soir sera partagé avec {config['partenaire']}. Respecte ses allergies : {partenaire_data.get('profil', {}).get('allergies', 'Aucune')}."

    prompt += f"\n\n🌅 GESTION DU PETIT-DÉJEUNER :"
    prompt += f"\n- Habitudes : {profil.get('habitudes_matin', 'Non renseignées')}."
    prompt += f"\n- Analyse : Rédige une analyse bienveillante des habitudes pour la clé JSON 'analyse_habitudes_matin'."
    prompt += f"\n- Demande : {profil.get('complexite_matin', 'Simple, rapide et répétitif')}."
    prompt += f"\n- Si simple demandé : Répète 2 ou 3 petits-déjeuners max sur toute la semaine."

    prompt += f"\n\n🔄 DIVERSITÉ & DÉTAILS :"
    prompt += f"\n- Diversité : {diversite_repas}. Si Normale, répète les restes (ex: dîner du lundi mangé le mardi midi)."
    prompt += f"\n- NIVEAU DÉBUTANT : Rédige des recettes TRÈS DÉTAILLÉES (étape 1, étape 2, etc.) pour des novices en cuisine."

    if photos: prompt += "\n🚨 MODE STRICT : Utilise UNIQUEMENT les ingrédients des photos." if mode_strict else "\n💡 ANTI-GASPI : Utilise en priorité les ingrédients des photos."

    prompt += """\nRÉPOND UNIQUEMENT EN JSON avec cette structure précise (la clé 'calories' doit OBLIGATOIREMENT être un NOMBRE ENTIER sans texte) :
    {
      "analyse_habitudes_matin": "...",
      "semaine": {
        "Date 1": {"Matin": {"titre": "...", "recette": "Étape 1: ...\nÉtape 2: ...", "calories": 450}, "Midi": {...}, "Soir": {...}}
      }
    }"""

    contenu_a_envoyer = [prompt]
    if photos:
        for p in photos:
            try: contenu_a_envoyer.append(compresser_image(p))
            except: pass

    try:
        response = client.models.generate_content(model=st.secrets["GEMINI_MODEL"], contents=contenu_a_envoyer)
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        parsed = json.loads(clean_json)
        if "semaine" in parsed: return parsed["semaine"], parsed.get("analyse_habitudes_matin", "")
        else: return parsed, ""
    except Exception as e:
        st.error(f"Erreur API : {e}")
        return None, None

def regenerer_un_repas(jour, moment, repas_actuel_titre):
    """Demande à Gemini de régénérer un seul repas spécifique qui n'a pas plu."""
    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
    repas_a_eviter = [plat for plat, note in notes_repas.items() if note is not None and note <= 2]
    repas_a_eviter.append(repas_actuel_titre) # On ajoute le plat actuel à la liste noire temporaire

    prompt = f"""
    Tu es un coach expert. L'utilisateur n'aime pas le plat proposé ({repas_actuel_titre}).
    Propose une NOUVELLE idée de repas pour le {moment} de {profil['prenom']}.
    Objectif : {profil['objectif']} | Calories souhaitées : Similaires à l'ancien plat.
    Allergies : {profil['allergies']} | Aversions : {profil['aversions']}.
    
    🚨 Plats à NE SURTOUT PAS proposer : {repas_a_eviter}.

    NIVEAU DÉBUTANT : Rédige des recettes TRÈS DÉTAILLÉES.

    RÉPOND UNIQUEMENT EN JSON avec cette structure (calories = entier) :
    {{"titre": "...", "recette": "Étape 1: ...", "calories": 450}}
    """
    
    try:
        response = client.models.generate_content(model=st.secrets["GEMINI_MODEL"], contents=prompt)
        clean_json = response.text.strip().replace('```json', '').replace('```', '')
        return json.loads(clean_json)
    except Exception as e:
        st.error(f"Erreur lors de la régénération : {e}")
        return None


# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
st.title(f"🍽️ Planificateur de {profil.get('prenom', '')}")

liste_semaines = list(current_user_data.get("menus_sauvegardes", {}).keys())
semaine_a_afficher = None
semaine_selectionnee = None

col_aff1, col_aff2 = st.columns([0.7, 0.3])
if liste_semaines:
    semaine_selectionnee = col_aff2.selectbox("📂 Voir une semaine :", ["-- Nouvelle programmation --"] + liste_semaines)
    if semaine_selectionnee != "-- Nouvelle programmation --":
        semaine_a_afficher = current_user_data["menus_sauvegardes"][semaine_selectionnee]

if not semaine_a_afficher:
    st.subheader("🗓️ Programmer une nouvelle semaine")
    date_debut = st.date_input("Date de début", datetime.today())
    jours_generes = [formater_date_fr(date_debut + timedelta(days=i)) for i in range(7)]
    identifiant_semaine = f"Semaine du {jours_generes[0]}"
    
    if identifiant_semaine in liste_semaines:
        st.warning("⚠️ Une programmation existe déjà pour cette semaine. Si vous générez, elle sera écrasée.")

    st.markdown("### ⚙️ Configuration jour par jour")
    config_semaine = {}
    sports_dispos = ["Aucun"] + [s.strip() for s in profil.get("sports", "").split(",") if s.strip()]
    autres_profils = ["Personne"] + [u for u in bdd_users.keys() if u not in [choix_user, "-- Choisir un profil --", "➕ Créer un nouveau profil"]]

    for jour in jours_generes:
        with st.expander(f"Paramétrer le {jour}"):
            c1, c2, c3 = st.columns(3)
            repas = c1.multiselect("Repas à prévoir", ["Matin", "Midi", "Soir"], default=["Matin", "Midi", "Soir"], key=f"r_{jour}")
            sport = c2.selectbox("Sport", sports_dispos, key=f"s_{jour}")
            temps = c2.text_input("Durée (ex: 1h30)", key=f"t_{jour}") if sport != "Aucun" else ""
            partenaire = c3.selectbox("Partager le Soir ?", autres_profils, key=f"p_{jour}")
            config_semaine[jour] = {"repas": repas, "sport": sport, "temps_sport": temps, "partenaire": partenaire}

    with st.sidebar:
        st.markdown("---")
        st.subheader("🔄 Diversité")
        diversite_repas = st.selectbox("Organisation des repas", ["Normale (Plats qui reviennent, restes = Économique)", "Élevée (1 plat différent à chaque repas = Plus cher)"])

        st.markdown("---")
        envies = st.text_area("💭 Envies particulières ?")
        photos_frigo = st.file_uploader("Stock en photo", type=["jpg", "png"], accept_multiple_files=True)
        mode_strict = st.checkbox("🚨 Mode Strict (0 courses)") if photos_frigo else False

        if st.button("🪄 Générer ma semaine"):
            with st.spinner(f"Création de la {identifiant_semaine}..."):
                nouveau_menu, analyse_matin = generer_repas_intelligent(envies, config_semaine, identifiant_semaine, diversite_repas, photos_frigo, mode_strict)
                if nouveau_menu:
                    current_user_data["menus_sauvegardes"][identifiant_semaine] = {
                        "menu": nouveau_menu, 
                        "analyse_matin": analyse_matin,
                        "liste_courses": None,
                        "date_iso": date_debut.isoformat(),
                        "depenses": {} 
                    }
                    save_current()

                    for jour, config in config_semaine.items():
                        partenaire = config['partenaire']
                        if partenaire != "Personne" and partenaire in bdd_users:
                            partenaire_data = bdd_users[partenaire]
                            repas_existant = partenaire_data.get("menus_sauvegardes", {}).get(identifiant_semaine, {}).get("menu", {}).get(jour, {}).get("Soir")
                            
                            if not repas_existant and jour in nouveau_menu and "Soir" in nouveau_menu[jour]:
                                if "menus_sauvegardes" not in partenaire_data: partenaire_data["menus_sauvegardes"] = {}
                                if identifiant_semaine not in partenaire_data["menus_sauvegardes"]: 
                                    partenaire_data["menus_sauvegardes"][identifiant_semaine] = {"menu": {}, "liste_courses": None, "date_iso": date_debut.isoformat(), "depenses": {}}
                                if jour not in partenaire_data["menus_sauvegardes"][identifiant_semaine]["menu"]: partenaire_data["menus_sauvegardes"][identifiant_semaine]["menu"][jour] = {}
                                
                                plat_partage = nouveau_menu[jour]["Soir"].copy()
                                plat_partage["titre"] = f"🤝 {plat_partage['titre']} (Prévu par {profil.get('prenom', 'Quelqu\'un')})"
                                
                                partenaire_data["menus_sauvegardes"][identifiant_semaine]["menu"][jour]["Soir"] = plat_partage
                                sauvegarder_utilisateur(partenaire, partenaire_data)
                    
                    st.success("Menu généré !")
                    st.rerun()

# --- AFFICHAGE ---
else:
    st.markdown("---")
    if semaine_a_afficher.get("analyse_matin"):
        st.info(f"💡 **Le mot du Coach sur vos petits-déjeuners :** {semaine_a_afficher['analyse_matin']}")
        
    menu = semaine_a_afficher.get("menu", {})
    
    total_calories_semaine = 0
    rids_semaine_actuelle = []
    
    if isinstance(menu, dict):
        for jour, repas_jour in menu.items():
            if isinstance(repas_jour, dict):
                for moment, plat in repas_jour.items():
                    if isinstance(plat, dict):
                        total_calories_semaine += extraire_calories(plat)
                        rids_semaine_actuelle.append(f"{jour}_{moment}")
                        
    st.success(f"🔥 **Bilan Calorique de la semaine :** {total_calories_semaine} kcal (Apport théorique total estimé).")
    
    repas_coches = len([rid for rid in rids_semaine_actuelle if rid in repas_faits])
    total_repas = len(rids_semaine_actuelle)
    if total_repas > 0:
        st.progress(repas_coches / total_repas, text=f"Progression : {repas_coches}/{total_repas} repas dégustés !")

    if st.button("🗑️ Supprimer cette programmation", type="primary"):
        del current_user_data["menus_sauvegardes"][semaine_selectionnee]
        save_current()
        st.success("Semaine supprimée avec succès !")
        st.rerun()

    if not menu:
        st.warning("⚠️ Oups ! Le menu de cette semaine est vide.")
    else:
        tabs = st.tabs(list(menu.keys()))
        
        for i, (jour, repas_jour) in enumerate(menu.items()):
            if not isinstance(repas_jour, dict): continue
            with tabs[i]:
                
                cal_jour = sum(extraire_calories(plat) for plat in repas_jour.values() if isinstance(plat, dict))
                st.metric(label="Total Calories Ingestées", value=f"{cal_jour} kcal")
                st.markdown("---")
                
                for moment in ["Matin", "Midi", "Soir"]:
                    if moment in repas_jour and isinstance(repas_jour[moment], dict):
                        plat = repas_jour[moment]
                        rid = f"{jour}_{moment}"
                        calories_plat = extraire_calories(plat)
                        titre_plat = plat.get('titre', 'Repas')
                        
                        # --- NOUVEAUTÉ : LA MISE EN PAGE EN 3 COLONNES ---
                        col1, col2, col3 = st.columns([0.05, 0.65, 0.3])
                        with col1:
                            if st.checkbox("Fait", value=(rid in repas_faits), key=f"c_{rid}"):
                                if rid not in repas_faits: current_user_data["repas_faits"].append(rid); save_current(); st.rerun()
                            elif rid in repas_faits: current_user_data["repas_faits"].remove(rid); save_current(); st.rerun()
                        
                        with col2:
                            st.subheader(f"{moment} : {titre_plat} ({calories_plat} kcal)")
                            with st.expander("Voir la recette détaillée"): 
                                st.write(plat.get('recette', 'Aucune recette détaillée.'))
                                
                        with col3:
                            # 1. Le retour des étoiles !
                            note_actuelle = notes_repas.get(titre_plat, 0) - 1 if notes_repas.get(titre_plat) else None
                            # On ajoute l'ID de la semaine dans la clé pour éviter les bugs d'affichage
                            note = st.feedback("stars", key=f"note_{rid}_{semaine_selectionnee}")
                            if note is not None:
                                current_user_data["notes_repas"][titre_plat] = note + 1
                                save_current()
                                
                            # 2. Le bouton "Régénérer" !
                            if st.button("🔄 Changer ce repas", key=f"regen_{rid}_{semaine_selectionnee}"):
                                with st.spinner("Recherche d'une alternative..."):
                                    nouveau_plat = regenerer_un_repas(jour, moment, titre_plat)
                                    if nouveau_plat:
                                        # On remplace l'ancien plat par le nouveau dans la base de données
                                        semaine_a_afficher["menu"][jour][moment] = nouveau_plat
                                        # Il faut regénérer la liste de courses
                                        semaine_a_afficher["liste_courses"] = None 
                                        save_current()
                                        st.rerun()

                # --- BILAN JOURNALIER (OPTIONNEL) ---
                st.markdown("---")
                st.subheader("⚖️ Ma Balance Énergétique")
                
                if "depenses" not in semaine_a_afficher: semaine_a_afficher["depenses"] = {}
                depense_actuelle = semaine_a_afficher["depenses"].get(jour, 0)
                
                depense_input = st.number_input(f"Calories dépensées (Lues sur votre montre en fin de journée)", min_value=0, max_value=10000, value=depense_actuelle, step=50, key=f"dep_{jour}_{semaine_selectionnee}")
                
                if depense_input != depense_actuelle:
                    semaine_a_afficher["depenses"][jour] = depense_input
                    save_current()
                    st.rerun()
                
                if depense_input > 0:
                    diff = cal_jour - depense_input
                    objectif_user = profil.get("objectif", "")
                    
                    if "Perte" in objectif_user:
                        if diff < 0: st.success(f"✅ **Contrat rempli !** Vous êtes en déficit de {abs(diff)} kcal. C'est parfait pour une perte de poids saine.")
                        else: st.warning(f"⚠️ **Attention :** Vous êtes en excédent de {diff} kcal aujourd'hui. Vous avez mangé plus que ce que vous avez dépensé.")
                    elif "Prise" in objectif_user:
                        if diff > 0: st.success(f"✅ **Contrat rempli !** Vous êtes en excédent de {diff} kcal. C'est parfait pour nourrir vos muscles.")
                        else: st.warning(f"⚠️ **Attention :** Vous êtes en déficit de {abs(diff)} kcal. Il faut manger plus pour développer votre masse musculaire !")
                    else: 
                        if abs(diff) <= 300: st.success(f"✅ **Équilibre respecté !** Une différence minime de {diff} kcal, c'est idéal pour le maintien.")
                        else: st.info(f"💡 **Bilan du jour :** Il y a un écart de {abs(diff)} kcal entre vos dépenses et vos repas.")
                else:
                    st.caption("*(Optionnel) Saisissez vos calories dépensées le soir pour débloquer l'analyse du coach.*")


        st.markdown("---")
        st.subheader("🛒 Liste de Courses")
        
        if st.button("📝 Générer / Actualiser la liste de courses"):
            with st.spinner("Rédaction de la liste en cours..."):
                try:
                    client = genai.Client(api_key=st.secrets["GEMINI_API_KEY"])
                    res = client.models.generate_content(
                        model=st.secrets["GEMINI_MODEL"], 
                        contents=f"Fais la liste de courses détaillée et triée par rayon pour ce menu : {json.dumps(menu)}. Utilise le format Markdown avec des cases à cocher (ex: - [ ] Tomates)."
                    )
                    semaine_a_afficher["liste_courses"] = res.text
                    save_current()
                    st.rerun()
                except Exception as e:
                    st.error("Serveurs surchargés. Veuillez réessayer ! 🔄")
            
        if semaine_a_afficher.get("liste_courses"): 
            st.markdown(semaine_a_afficher["liste_courses"])
            st.markdown("---")
            col_export1, col_export2 = st.columns(2)
            with col_export1:
                st.download_button(label="📤 Exporter le fichier", data=semaine_a_afficher["liste_courses"], file_name=f"Liste_Courses.txt", mime="text/plain", use_container_width=True)
            with col_export2:
                st.code(semaine_a_afficher["liste_courses"], language="markdown")