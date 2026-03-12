import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="SB App Arrivi", layout="centered", page_icon="🏗️")

PASSWORD_FILE = ".password_hash"

# --- 2. LOGICA DI SICUREZZA ---
def check_password():
    if st.session_state.get("password_correct", False):
        return True

    if not os.path.exists(PASSWORD_FILE):
        st.title("🛡️ Configurazione Iniziale")
        new_pass = st.text_input("Crea Password Master", type="password")
        conf_pass = st.text_input("Conferma Password", type="password")
        if st.button("Salva e Configura"):
            if new_pass == conf_pass and len(new_pass) > 3:
                with open(PASSWORD_FILE, "w") as f: f.write(new_pass)
                st.success("Password impostata!")
                st.rerun()
        return False

    st.title("🔒 Accesso Riservato")
    input_pass = st.text_input("Inserisci Password:", type="password")
    if st.button("Sblocca Sistema"):
        with open(PASSWORD_FILE, "r") as f: saved_pass = f.read().strip()
        if input_pass == saved_pass:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Password errata.")
    return False

# --- 3. FUNZIONI CORE (ESTERNE PER PULIZIA) ---
def analizza_con_google(image_bytes):
    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        if response.text_annotations:
            return response.text_annotations[0].description
        return ""
    except Exception as e:
        st.error(f"Errore Google Vision: {e}")
        return ""

def estrai_dati_chirurgica(testo_intero):
    testo_intero = testo_intero.upper().replace('§', 'S').replace('|', 'I')
    dati = {
        "barcode": "Non trovato", "fornitore": "Sconosciuto", 
        "spessore": 0.0, "peso": 0, "larghezza": 0, "lunghezza": 0.0,
        "data_etichetta": datetime.now().strftime("%d/%m/%Y"),
        "codice_colore": "", "descrizione": ""
    }

    # Fornitori
    fornitori = {
        "MARCEGAGLIA": "MARCEGAGLIA", "LAMPRE": "LAMPRE", "ARCELOR": "ARCELORMITTAL",
        "NOVELIS": "NOVELIS", "VARCOLOR": "VARCOLOR", "METALCOAT": "METALCOAT",
        "SANDRINI": "SANDRINI METALLI", "VETRORESINA": "VETRORESINA SPA",
        "FIBROSAN": "FIBROSAN", "RIVIERASCA": "RIVIERASCA"
    }
    for k, v in fornitori.items():
        if k in testo_intero:
            dati["fornitore"] = v
            break

    # Barcode/ID (Più flessibile per codici con / o -)
    match_bar = re.search(r'\b([A-Z0-9/-]{8,25})\b', testo_intero)
    if match_bar: dati["barcode"] = match_bar.group(1)

    # Spessore (Gestisce 0.45 e anche 1.8 della vetroresina)
    match_sp = re.search(r'([0-2][.,]\d{1,2})', testo_intero)
    if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))

    # Peso
    match_peso = re.search(r'(\d{3,5})\s*(?:KG|NET|NETTO)', testo_intero)
    if match_peso: dati["peso"] = int(match_peso.group(1))

    # Larghezza
    match_largh = re.search(r'\b(1000|1200|1219|1225|1250|1500|600|360)\b', testo_intero)
    if match_largh: dati["larghezza"] = int(match_largh.group(1))

    return dati

# --- 4. AVVIO APPLICAZIONE ---
if check_password():
    
    # Configurazione Google Cloud
    if "google_credentials" in st.secrets:
        creds = dict(st.secrets["google_credentials"])
        if not os.path.exists("temp_key.json"):
            with open("temp_key.json", "w") as f: json.dump(creds, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

    # UI Header
    st.title("🏗️ SB Supporti - Arrivi")
    st.caption(f"Utente Autenticato - {datetime.now().strftime('%d/%m/%Y')}")

    if 'session_data' not in st.session_state:
        st.session_state.session_data = []

    # Sezione Input
    input_mode = st.radio("Sorgente immagine:", ["📷 Scatta Foto", "📁 Galleria"], horizontal=True)
    foto_bytes = None

    if input_mode == "📷 Scatta Foto":
        camera_img = st.camera_input("Inquadra l'etichetta")
        if camera_img: foto_bytes = camera_img.getvalue()
    else:
        uploaded_file = st.file_uploader("Carica immagine", type=['jpg', 'jpeg', 'png'])
        if uploaded_file: foto_bytes = uploaded_file.getvalue()

    # Processamento
    if foto_bytes:
        with st.spinner('L\'AI sta analizzando...'):
            testo_raw = analizza_con_google(foto_bytes)
            if testo_raw:
                info = estrai_dati_chirurgica(testo_raw)
                
                # Form di conferma
                with st.form("validazione"):
                    st.subheader("📝 Verifica Dati Estratti")
                    col1, col2 = st.columns(2)
                    f_bar = col1.text_input("Codice / ID Collo", info["barcode"])
                    f_forn = col2.text_input("Fornitore", info["fornitore"])
                    
                    c1, c2, c3 = st.columns(3)
                    f_spess = c1.number_input("Spessore", value=info["spessore"], format="%.2f")
                    f_peso = c2.number_input("Peso (kg)", value=info["peso"])
                    f_largh = c3.selectbox("Larghezza", [1250, 1220, 1000, 600, 360, 0], index=0)
                    
                    f_colore = st.text_input("Codice Colore", info["codice_colore"])
                    f_linea = st.selectbox("Linea Destinazione", ["1", "2"])

                    if st.form_submit_button("✅ AGGIUNGI AL CARICO"):
                        st.session_state.session_data.append({
                            "Codice": f_bar, "Fornitore": f_forn, "Spessore": f_spess,
                            "Peso": f_peso, "Larghezza": f_largh, "Colore": f_colore,
                            "Linea": f_linea, "Data": datetime.now().strftime("%d/%m/%Y")
                        })
                        st.success("Riga aggiunta correttamente!")
                        st.balloons()

    # Tabella e Download
    if st.session_state.session_data:
        st.divider()
        df = pd.DataFrame(st.session_state.session_data)
        st.subheader("📋 Riepilogo Sessione")
        st.dataframe(df, use_container_width=True)

        col_dl, col_del = st.columns(2)
        
        # Excel Export
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False, sheet_name='Arrivi')
        
        col_dl.download_button(
            label="📥 SCARICA EXCEL",
            data=output.getvalue(),
            file_name=f"Carico_SB_{datetime.now().strftime('%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

        if col_del.button("🗑️ Svuota Tutto"):
            st.session_state.session_data = []
            st.rerun()

    # Sidebar Logout
    st.sidebar.markdown("---")
    if st.sidebar.button("Esci"):
        st.session_state["password_correct"] = False
        st.rerun()
