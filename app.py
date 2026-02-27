import streamlit as st
from google import genai
import json
from PIL import Image
import io
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

        # --- NOUVEAUTÉ : HABITUDES DU MATIN ---
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
            date_semaine = datetime.fromisoformat(date_iso).date()
            if date_semaine < lundi_courant:
                semaines_a_supprimer.append(id_semaine)
                
    if semaines_a_supprimer:
        for s in semaines_a_supprimer:
            del current_user_data["menus_sauvegardes"][s]
            
        jours_gardes = []
        for semaine_data in current_user_data["menus_sauvegardes"].values():
            if isinstance(semaine_data.get("menu"), dict):
                jours_gardes.extend(semaine_data["menu"].keys())
            
        current_user_data["repas_faits"] = [
            rid for rid in current_user_data.get("repas_faits", [])
            if any(rid.startswith(jour) for jour in jours_gardes)
        ]
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
# FONCTIONS API GEMINI (INTELLIGENCE RENFORCÉE)
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
        prompt += f"\n  Repas à générer : {', '.join(config['repas']) if config['repas'] else 'AUCUN REPAS CE JOUR LA'}"
        if config['sport'] != "Aucun": prompt += f"\n  Sport prévu : {config['sport']} pendant {config['temps_sport']}."
        if config['partenaire'] != "Personne":
            partenaire_data = bdd_users.get(config['partenaire'], {})
            repas_existant = partenaire_data.get("menus_sauvegardes", {}).get(identifiant_semaine, {}).get("menu", {}).get(jour, {}).get("Soir")
            if repas_existant: prompt += f"\n  🚨 Le repas du Soir est partagé avec {config['partenaire']} qui a DÉJÀ prévu ceci : {repas_existant['titre']}. Tu DOIS IMPÉRATIVEMENT intégrer cette recette pour le Soir."
            else: prompt += f"\n  🤝 Le repas du Soir sera partagé avec {config['partenaire']}. Respecte ses allergies : {partenaire_data.get('profil', {}).get('allergies', 'Aucune')}."

    prompt += f"\n\n🌅 GESTION DU PETIT-DÉJEUNER :"
    prompt += f"\n- Habitudes actuelles : {profil.get('habitudes_matin', 'Non renseignées')}."
    prompt += f"\n- Règle 1 : Rédige une brève analyse (1 ou 2 phrases bienveillantes) de ces habitudes pour la clé JSON 'analyse_habitudes_matin' (indique si c'est bien ou pas pour son objectif)."
    prompt += f"\n- Règle 2 : L'utilisateur souhaite des petits-déjeuners : {profil.get('complexite_matin', 'Simple, rapide et répétitif')}."
    prompt += f"\n- Règle 3 : Tu DOIS créer 2 ou 3 petits-déjeuners types MAXIMUM pour toute la semaine, et les répéter. Ne crée surtout pas un petit-déjeuner différent chaque jour !"

    prompt += f"\n\n🔄 DIVERSITÉ MIDI & SOIR :"
    prompt += f"\n- Niveau de diversité demandé : {diversite_repas}."
    prompt += f"\n- Si la diversité est 'Normale', IMITE LA VRAIE VIE : répète des plats (ex: le dîner du lundi est mangé en reste le mardi midi) ou alterne entre 3-4 grosses recettes pour faire des économies et gagner du temps. Ne crée pas 14 plats uniques."

    prompt += f"\n\nEnvies générales : {envies if envies else 'Varié'}."
    prompt += f"\nRepas interdits (déjà mal notés) : {repas_a_eviter}."
    if photos: prompt += "\n🚨 MODE STRICT : Utilise UNIQUEMENT les ingrédients des photos." if mode_strict else "\n💡 ANTI-GASPI : Utilise en priorité les ingrédients des photos."

    prompt += """\nRÉPOND UNIQUEMENT EN JSON avec cette structure (respecte scrupuleusement les clés) :
    {
      "analyse_habitudes_matin": "Ton avis de coach sur les habitudes du matin...",
      "semaine": {
        "Date 1": {"Matin": {"titre": "...", "recette": "...", "calories_estimees": "..."}, "Midi": {...}, "Soir": {...}}
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
        # Gestion intelligente du JSON pour éviter les crashs si l'IA modifie la structure
        if "semaine" in parsed:
            return parsed["semaine"], parsed.get("analyse_habitudes_matin", "")
        else:
            return parsed, ""
    except Exception as e:
        st.error(f"Erreur API : {e}")
        return None, None

# ==========================================
# INTERFACE PRINCIPALE
# ==========================================
st.title(f"🍽️ Planificateur de {profil.get('prenom', '')}")

liste_semaines = list(current_user_data.get("menus_sauvegardes", {}).keys())
semaine_a_afficher = None

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
        # --- NOUVEAUTÉ : DIVERSITÉ ---
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
                        "date_iso": date_debut.isoformat() 
                    }
                    save_current()

                    # Synchronisation avec le partenaire
                    for jour, config in config_semaine.items():
                        partenaire = config['partenaire']
                        if partenaire != "Personne" and partenaire in bdd_users:
                            partenaire_data = bdd_users[partenaire]
                            repas_existant = partenaire_data.get("menus_sauvegardes", {}).get(identifiant_semaine, {}).get("menu", {}).get(jour, {}).get("Soir")
                            
                            if not repas_existant and jour in nouveau_menu and "Soir" in nouveau_menu[jour]:
                                if "menus_sauvegardes" not in partenaire_data: partenaire_data["menus_sauvegardes"] = {}
                                if identifiant_semaine not in partenaire_data["menus_sauvegardes"]: 
                                    partenaire_data["menus_sauvegardes"][identifiant_semaine] = {"menu": {}, "liste_courses": None, "date_iso": date_debut.isoformat()}
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
    
    # --- NOUVEAUTÉ : LE MOT DU COACH ---
    if semaine_a_afficher.get("analyse_matin"):
        st.info(f"💡 **Le mot du Coach sur vos petits-déjeuners :** {semaine_a_afficher['analyse_matin']}")
        
    menu = semaine_a_afficher.get("menu", {})
    
    if st.button("🗑️ Supprimer cette programmation", type="primary"):
        del current_user_data["menus_sauvegardes"][semaine_selectionnee]
        save_current()
        st.success("Semaine supprimée avec succès !")
        st.rerun()

    if not menu:
        st.warning("⚠️ Oups ! Le menu de cette semaine est vide. Utilisez le bouton rouge ci-dessus pour supprimer cette programmation et la refaire.")
    else:
        tabs = st.tabs(list(menu.keys()))
        
        for i, (jour, repas_jour) in enumerate(menu.items()):
            if not isinstance(repas_jour, dict):
                continue
                
            with tabs[i]:
                for moment in ["Matin", "Midi", "Soir"]:
                    if moment in repas_jour and isinstance(repas_jour[moment], dict):
                        plat = repas_jour[moment]
                        rid = f"{jour}_{moment}"
                        col1, col2 = st.columns([0.1, 0.9])
                        with col1:
                            if st.checkbox("Fait", value=(rid in repas_faits), key=f"c_{rid}"):
                                if rid not in repas_faits: current_user_data["repas_faits"].append(rid); save_current(); st.rerun()
                            elif rid in repas_faits: current_user_data["repas_faits"].remove(rid); save_current(); st.rerun()
                        with col2:
                            st.subheader(f"{moment} : {plat.get('titre', 'Repas')}")
                            with st.expander("Voir recette"): st.write(plat.get('recette', 'Aucune recette détaillée.'))

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
                    st.error("Serveurs surchargés. Veuillez réessayer dans quelques secondes ! 🔄")
            
        if semaine_a_afficher.get("liste_courses"): 
            st.markdown(semaine_a_afficher["liste_courses"])
            
            st.markdown("---")
            st.info("💡 **Astuce Mobile :** Exportez cette liste vers votre application Notes pour la cocher au supermarché !")
            
            col_export1, col_export2 = st.columns(2)
            with col_export1:
                st.download_button(label="📤 Exporter le fichier", data