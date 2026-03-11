import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# --- FILE PER LA PERSISTENZA PASSWORD ---
PASSWORD_FILE = ".password_hash"

# --- 1. CONFIGURAZIONE PAGINA E PWA ---
st.set_page_config(
    page_title="SB App Arrivi", 
    layout="centered", 
    page_icon="ptsimbolo.png"
)

def add_pwa_headers():
    pwa_html = """
        <link rel="manifest" href="manifest.json">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    """
    st.markdown(pwa_html, unsafe_allow_html=True)

add_pwa_headers()

# --- 2. LOGICA DI SICUREZZA ---
def check_password():
    """Gestisce la creazione e la verifica della password."""
    if st.session_state.get("password_correct", False):
        return True

    # Se la password non è mai stata configurata (prima volta assoluta)
    if not os.path.exists(PASSWORD_FILE):
        st.title("🛡️ Configurazione Iniziale")
        st.info("Benvenuto! Crea una password master per proteggere l'accesso all'app.")
        new_pass = st.text_input("Crea Password Master", type="password")
        conf_pass = st.text_input("Conferma Password Master", type="password")
        
        if st.button("Salva e Configura"):
            if new_pass == conf_pass and len(new_pass) > 3:
                with open(PASSWORD_FILE, "w") as f:
                    f.write(new_pass)
                st.success("Password impostata! Ora effettua l'accesso.")
                st.rerun()
            else:
                st.error("Le password non coincidono o sono troppo brevi (min 4 caratteri).")
        return False

    # Login standard
    st.title("🔒 Accesso Riservato")
    st.caption("Contenuto protetto. Inserisci la password per sbloccare le funzioni.")
    
    # Anteprima oscurata
    dummy_df = pd.DataFrame({"ID Collo": ["****", "****"], "Stato": ["PROTETTO", "PROTETTO"]})
    st.table(dummy_df)
    
    input_pass = st.text_input("Password:", type="password")
    if st.button("Sblocca Sistema"):
        with open(PASSWORD_FILE, "r") as f:
            saved_pass = f.read().strip()
        
        if input_pass == saved_pass:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Password errata.")
    return False

# --- 3. LOGICA APPLICATIVA (Solo se autenticati) ---
if check_password():
    
    # --- CONFIGURAZIONE GOOGLE VISION (Locale o Cloud) ---
    if os.path.exists("chiave_google.json"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "chiave_google.json"
    elif "google_credentials" in st.secrets:
        # Gestione segreti per il deploy su Streamlit Cloud
        creds_dict = dict(st.secrets["google_credentials"])
        with open("temp_key.json", "w") as f:
            json.dump(creds_dict, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

    def analizza_con_google(image_bytes):
        try:
            client = vision.ImageAnnotatorClient()
            image = vision.Image(content=image_bytes)
            response = client.text_detection(image=image)
            return response.text_annotations[0].description if response.text_annotations else ""
        except Exception as e:
            st.error(f"Errore Google Vision: {e}")
            return ""

    def estrai_dati_chirurgica(testo_ocr):
        righe = [r.strip().upper() for r in testo_ocr.split('\n') if r.strip()]
        t_completo = " ".join(righe)
        dati = {
            "barcode": "Non trovato", "fornitore": "Sconosciuto", "spessore": 0.0,
            "peso": 0, "larghezza": 0, "lunghezza": 0.0,
            "data_etichetta": datetime.now().strftime("%d/%m/%Y"),
            "codice_colore": "", "descrizione": "Verificare materiale"
        }
        
        # Identificazione Fornitore
        for forn in ["LAMPRE", "MARCEGAGLIA", "ARCELOR", "NOVELIS"]:
            if forn in t_completo:
                dati["fornitore"] = "ARCELORMITTAL" if forn == "ARCELOR" else forn

        for i, riga in enumerate(righe):
            # Barcode
            if 'S' in riga:
                bc_match = re.search(r'S\s*(\d\s*){9,10}', riga)
                if bc_match: dati["barcode"] = re.sub(r'\s+', '', bc_match.group(0))
            # Colore
            if any(x in riga for x in ["COLOR", "COLOUR", "MP"]):
                col_match = re.search(r'\b(MP\d{3}|RAL\s*\d{4}|\d{4})\b', riga)
                if col_match: dati["codice_colore"] = col_match.group(0).replace(' ', '')
            # Spessore
            if any(x in riga for x in ["SPESS", "THICK", "THK"]):
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_spess = re.search(r'\b0[.,](\d{2,3})\b|\b0(\d{2})\b', cerca_in)
                if val_spess:
                    res = val_spess.group(0).replace(',', '.')
                    dati["spessore"] = float(res) if '.' in res else float(res)/100
            # Larghezza
            if any(x in riga for x in ["LARGH", "WIDTH", "WID"]):
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_largh = re.search(r'\b(1000|1200|1219|1225|1250|1500)\b', cerca_in)
                if val_largh: dati["larghezza"] = int(val_largh.group(1))
            # Lunghezza
            if any(x in riga for x in ["LUNGH", "LENGTH", "M."]):
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_lungh = re.search(r'(\d+[,.]\d{1,2})', cerca_in)
                if val_lungh: dati["lunghezza"] = float(val_lungh.group(1).replace(',', '.'))
            # Peso
            if "NET" in riga or "KG" in riga:
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_peso = re.findall(r'\b\d{4}\b', cerca_in)
                for p in val_peso:
                    if 500 < int(p) < 8000 and int(p) != dati["larghezza"]: dati["peso"] = int(p)
            # Data
            if any(x in riga for x in ["DATA", "DATE"]):
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_data = re.search(r'(\d{2}/\d{2}/\d{2,4})', cerca_in)
                if val_data: dati["data_etichetta"] = val_data.group(1)
        return dati

    # --- UI ESTETICA ---
    st.markdown("""
        <style>
        .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #004a99; color: white; font-weight: bold; }
        .stDownloadButton>button { background-color: #28a745 !important; border-radius: 12px; }
        .stCameraInput>div>button { background-color: #004a99 !important; color: white !important; }
        </style>
        """, unsafe_allow_html=True)

    try:
        logo = Image.open("ptsimbolo.png")
        st.image(logo, width=100)
    except:
        st.title("🏗️ SB Supporti")
    
    st.subheader("Carico Arrivi Intelligente")

    if 'session_data' not in st.session_state:
        st.session_state.session_data = []

    # Sezione Input
    st.divider()
    input_mode = st.radio("Metodo inserimento:", ["Scatta Foto", "Scegli dalla Galleria"], horizontal=True)

    foto_bytes = None
    if input_mode == "Scatta Foto":
        camera_img = st.camera_input("Inquadra l'etichetta")
        if camera_img: foto_bytes = camera_img.getvalue()
    else:
        uploaded_file = st.file_uploader("Carica immagine", type=['jpg', 'jpeg', 'png'])
        if uploaded_