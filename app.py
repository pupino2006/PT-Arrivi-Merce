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

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(
    page_title="SB App Arrivi", 
    layout="centered", 
    page_icon="ptsimbolo.png"
)

# --- 2. FUNZIONI DI SUPPORTO ---
def analizza_con_google(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        # Restituiamo il testo completo trovato
        return response.text_annotations[0].description if response.text_annotations else ""
    except Exception as e:
        st.error(f"Errore Google Vision: {e}")
        return ""

def estrai_dati_chirurgica(testo_intero):
    testo_intero = testo_intero.upper()
    testo_intero = testo_intero.replace('§', 'S').replace('|', 'I')
    
    dati = {
        "barcode": "Non trovato", "fornitore": "Sconosciuto", 
        "spessore": 0.0, "peso": 0, "larghezza": 0, "lunghezza": 0.0,
        "data_etichetta": datetime.now().strftime("%d/%m/%Y"),
        "codice_colore": "", "descrizione": ""
    }

    # Mappatura Fornitori
    fornitori_map = {
        "MARCEGAGLIA": "MARCEGAGLIA", "LAMPRE": "LAMPRE", "ARCELOR": "ARCELORMITTAL",
        "NOVELIS": "NOVELIS", "VARCOLOR": "VARCOLOR", "METALCOAT": "METALCOAT",
        "SANDRINI": "SANDRINI METALLI", "VETRORESINA": "VETRORESINA SPA",
        "FIBROSAN": "FIBROSAN", "RIVIERASCA": "RIVIERASCA"
    }
    
    for chiave, nome in fornitori_map.items():
        if chiave in testo_intero:
            dati["fornitore"] = nome
            break

    # Barcode
    if dati["fornitore"] == "LAMPRE":
        match = re.search(r'S\s*(\d{9,10})', testo_intero)
        if match: dati["barcode"] = "S" + match.group(1)
    else:
        match = re.search(r'\b(\d{9,12})\b', testo_intero)
        if match: dati["barcode"] = match.group(1)

    # Spessore
    if any(x in dati["fornitore"] for x in ["VETRORESINA", "FIBROSAN", "RIVIERASCA"]):
        match_sp = re.search(r'(\d[.,]\d)', testo_intero)
        if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))
    else:
        match_sp = re.search(r'(0[.,]\d{2,3})', testo_intero)
        if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))

    # Peso e Larghezza
    match_peso = re.search(r'(\d{3,5})\s*(?:KG|NET|NETTO)', testo_intero)
    if match_peso: dati["peso"] = int(match_peso.group(1))
    
    match_largh = re.search(r'\b(1000|1200|1219|1225|1250|1500|600|360)\b', testo_intero)
    if match_largh: dati["larghezza"] = int(match_largh.group(1))

    # Colore
    if "9010" in testo_intero: dati["codice_colore"] = "RAL 9010"
    
    return dati

def check_password():
    if st.session_state.get("password_correct", False):
        return True

    if not os.path.exists(PASSWORD_FILE):
        st.title("🛡️ Configurazione Iniziale")
        new_pass = st.text_input("Crea Password Master", type="password")
        conf_pass = st.text_input("Conferma Password", type="password")
        if st.button("Salva"):
            if new_pass == conf_pass and len(new_pass) > 3:
                with open(PASSWORD_FILE, "w") as f: f.write(new_pass)
                st.rerun()
        return False

    st.title("🔒 Accesso Riservato")
    input_pass = st.text_input("Password:", type="password")
    if st.button("Sblocca"):
        with open(PASSWORD_FILE, "r") as f: saved_pass = f.read().strip()
        if input_pass == saved_pass:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Password errata.")
    return False

# --- 3. LOGICA PRINCIPALE ---
if check_password():
    # Setup Google Credentials
    if "google_credentials" in st.secrets:
        creds_dict = dict(st.secrets["google_credentials"])
        if not os.path.exists("temp_key.json"):
            with open("temp_key.json", "w") as f:
                json.dump(creds_dict, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

    st.title("🏗️ SB Supporti - Carico")
    
    if 'session_data' not in st.session_state:
        st.session_state.session_data = []

    input_mode = st.radio("Metodo:", ["Scatta Foto", "Galleria"], horizontal=True)

    foto_bytes = None
    if input_mode == "Scatta Foto":
        camera_img = st.camera_input("Inquadra")
        if camera_img: foto_bytes = camera_img.getvalue()
    else:
        uploaded_file = st.file_uploader("Carica", type=['jpg', 'png'])
        if uploaded_file: foto_bytes = uploaded_file.getvalue()

    if foto_bytes:
        with st.spinner('Analisi in corso...'):
            testo_ocr = analizza_con_google(foto_bytes)
            if testo_ocr:
                info = estrai_dati_chirurgica(testo_ocr)
                linea_calc = "1" if info["larghezza"] in [1200, 1225, 1250] else "2"
                
                with st.form("conferma"):
                    f_bar = st.text_input("Codice", info["barcode"])
                    f_forn = st.text_input("Fornitore", info["fornitore"])
                    f_peso = st.number_input("Peso", value=info["peso"])
                    f_spess = st.number_input("Spessore", value=info["spessore"], format="%.2f")
                    f_linea = st.selectbox("Linea", ["1", "2"], index=0 if linea_calc=="1" else 1)
                    
                    if st.form_submit_button("AGGIUNGI"):
                        st.session_state.session_data.append({
                            "Codice": f_bar, "Fornitore": f_forn, "Peso": f_peso, "Spessore": f_spess, "Linea": f_linea
                        })
                        st.success("Aggiunto!")

    if st.session_state.session_data:
        df = pd.DataFrame(st.session_state.session_data)
        st.dataframe(df)
        
        # Download Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 SCARICA EXCEL", output.getvalue(), "carico.xlsx")

    if st.sidebar.button("Logout"):
        st.session_state["password_correct"] = False
        st.rerun()
