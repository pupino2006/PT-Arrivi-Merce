import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# 1. Configurazione della pagina (sempre come prima istruzione)
st.set_page_config(page_title="SB App Arrivi", layout="centered", page_icon="ptsimbolo.png")

# 2. Funzione per caricare il CSS
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"File {file_name} non trovato!") 

# 3. Caricamento file locale e icone FontAwesome
local_css("style.css")
st.markdown('<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">', unsafe_allow_html=True)

# Carica il file
local_css("style.css")

# --- FUNZIONI DI SUPPORTO ---
def analizza_con_google(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        return response.text_annotations[0].description if response.text_annotations else ""
    except Exception as e:
        st.error(f"Errore Vision: {e}")
        return ""

def estrai_dati_completi(testo):
    testo_u = testo.upper()
    dati = {
        "barcode": "", "fornitore": "", "spessore": 0.0, "peso": 0, "mq": 0.0,
        "colore": "", "descrizione": "", "linea": "1"
    }
    
    # Logic Barcode/QR
    match_bar = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo_u)
    if match_bar: dati["barcode"] = match_bar.group(1)
    
    # Logic Fornitore
    mappa = {"LAMPRE": "Lampre", "MARCEGAGLIA": "Marcegaglia", "VARCOLOR": "Varcolor", "METALCOAT": "Metalcoat"}
    for k, v in mappa.items():
        if k in testo_u: dati["fornitore"] = v
        
    # Logic Spessore (es: 0.50 o 0,50)
    match_sp = re.search(r'(0[.,]\d{2})', testo_u)
    if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))

    return dati

# --- LOGICA DI ACCESSO ---
PASSWORD_FILE = ".password_hash"
def check_password():
    if st.session_state.get("password_correct", False): return True
    if not os.path.exists(PASSWORD_FILE):
        st.title("🛡️ Crea Password Master")
        new_p = st.text_input("Password", type="password")
        if st.button("Salva"):
            with open(PASSWORD_FILE, "w") as f: f.write(new_p)
            st.rerun()
        return False
    st.title("🔒 Accesso Riservato")
    input_p = st.text_input("Password", type="password")
    if st.button("Sblocca"):
        with open(PASSWORD_FILE, "r") as f: 
            if input_p == f.read().strip():
                st.session_state["password_correct"] = True
                st.rerun()
    return False

# --- APP PRINCIPALE ---
if check_password():
    if "google_credentials" in st.secrets:
        creds = dict(st.secrets["google_credentials"])
        with open("temp_key.json", "w") as f: json.dump(creds, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

    # Logo
    try: st.image("ptsimbolo.png", width=80)
    except: st.title("SB CARICO")

    if 'archivio' not in st.session_state: st.session_state.archivio = []
    if 'temp_scan' not in st.session_state: st.session_state.temp_scan = {}

    tab1, tab2 = st.tabs(["📝 NUOVO CARICO", "📦 STORICO"])

    with tab1:
        # Zona Scanner
        with st.expander("📷 SCANSIONA ETICHETTA / QR"):
            foto = st.camera_input("Inquadra l'etichetta o il QR")
            if foto:
                testo = analizza_con_google(foto.getvalue())
                st.session_state.temp_scan = estrai_dati_completi(testo)
                st.success("Dati rilevati!")

        # FORM CON I 10 CAMPI
        with st.form("form_carico", clear_on_submit=True):
            st.markdown("### 📝 Dati Materiale")
            
            # 1. Codice a barre + Bottone Scan (trigger visivo)
            col_a, col_b = st.columns([3, 1])
            f_barcode = col_a.text_input("📦 CODICE A BARRE", value=st.session_state.temp_scan.get("barcode", ""))
            with col_b:
                st.write("##")
                st.form_submit_button("📷 SCAN")

            # 2. Fornitore e 3. Spessore
            c1, c2 = st.columns(2)
            f_fornitore = c1.text_input("🏭 PRODUTTORE/FORNITORE", value=st.session_state.temp_scan.get("fornitore", ""))
            f_spessore = c2.number_input("📏 SPESSORE DICHIARATO", value=st.session_state.temp_scan.get("spessore", 0.0), format="%.2f", step=0.01)

            # 4. Arrivo e 5. Descrizione
            f_arrivo = st.date_input("📅 DATA ARRIVO", datetime.now())
            f_descrizione = st.text_input("📝 DESCRIZIONE", value=st.session_state.temp_scan.get("descrizione", ""))

            # 6. Colore e 7. Peso
            c3, c4 = st.columns(2)
            f_colore = c3.text_input("🎨 CODICE COLORE", value=st.session_state.temp_scan.get("colore", ""))
            f_peso = c4.number_input("⚖️ PESO (KG)", value=st.session_state.temp_scan.get("peso", 0), step=1)

            # 8. Mq e 9. Linea
            c5, c6 = st.columns(2)
            f_mq = c5.number_input("📐 METRI QUADRI", value=st.session_state.temp_scan.get("mq", 0.0), step=0.01)
            f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"], index=0 if st.session_state.temp_scan.get("linea")=="1" else 1)

            # 10. Terminato (sempre vuoto all'inizio)
            f_terminato = st.selectbox("🏁 TERMINATO", ["", "SI", "NO"], index=0)

            if st.form_submit_button("🚀 REGISTRA CARICO"):
                st.session_state.archivio.append({
                    "Codice a barre": f_barcode,
                    "Produttore/Fornitore": f_fornitore,
                    "Spessore dichiarato": f_spessore,
                    "Arrivo": f_arrivo.strftime("%Y-%m-%d"),
                    "Descrizione": f_descrizione,
                    "Codice Colore": f_colore,
                    "Peso": f_peso,
                    "Metri Quadri": f_mq,
                    "Terminato": f_terminato,
                    "Linea": f_linea
                })
                st.session_state.temp_scan = {} # Reset
                st.success("Carico registrato!")

    with tab2:
        if st.session_state.archivio:
            df = pd.DataFrame(st.session_state.archivio)
            st.dataframe(df, use_container_width=True)
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 SCARICA EXCEL", output.getvalue(), "carico_merci.xlsx")
            
            if st.button("🗑️ CANCELLA TUTTO"):
                st.session_state.archivio = []
                st.rerun()



