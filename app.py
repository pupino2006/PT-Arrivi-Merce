import streamlit as st
import pandas as pd
import re
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from google.oauth2 import service_account
from PIL import Image
from streamlit_qrcode_scanner import qrcode_scanner

# --- 1. CONFIGURAZIONE E DESIGN ---
st.set_page_config(page_title="SB App Arrivi", layout="centered", page_icon="ptsimbolo.png")

st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap');
    .stApp { background-color: #0b0f1a !important; font-family: 'Inter', sans-serif; }
    header { visibility: hidden; }
    h1, h2, h3, label, p, .stMarkdown { color: #f8fafc !important; font-weight: 800 !important; }
    
    /* INPUT FIELDS */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"], .stDateInput input {
        background-color: #1e293b !important; 
        border: 1px solid #334155 !important; 
        color: #f8fafc !important; 
        border-radius: 12px !important;
        height: 50px !important;
    }

    /* BOTTONE ARANCIONE */
    div.stButton > button, div.stFormSubmitButton > button {
        background: #f97316 !important; 
        color: white !important; 
        border-radius: 18px !important; 
        font-weight: 900 !important; 
        text-transform: uppercase; 
        width: 100%; 
        height: 60px !important;
        box-shadow: 0 4px 15px rgba(249, 115, 22, 0.3) !important;
    }
    
    .orange-text { color: #f97316; }
    div[data-testid="stExpander"] {
        background: rgba(30, 41, 59, 0.6) !important;
        border-radius: 20px !important;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. LOGICA DI ANALISI GOOGLE VISION ---
def analizza_etichetta(image_bytes):
    try:
        # Invece di json.loads, usiamo direttamente il dizionario dai Secrets
        creds_info = st.secrets["google_credentials"]
        creds = service_account.Credentials.from_service_account_info(creds_info)
        
        client = vision.ImageAnnotatorClient(credentials=creds)
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        
        return response.text_annotations[0].description if response.text_annotations else ""
    except Exception as e:
        st.error(f"Errore Google Vision: {e}")
        return ""

def estrai_tutti_i_dati(testo):
    testo_u = testo.upper().replace('\n', ' ')
    # Inizializziamo i campi
    dati = {
        "barcode": "", "fornitore": "", "spessore": 0.0, 
        "peso": 0, "mq": 0.0, "colore": "", "desc": ""
    }
    
    # 1. BARCODE: Cerca stringhe che iniziano con S o sequenze lunghe di numeri
    m_bar = re.search(r'\b(S\d{7,15}|[0-9]{10,20})\b', testo_u)
    if m_bar: dati["barcode"] = m_bar.group(1)
    
    # 2. FORNITORE: Ricerca per parole chiave
    for f in ["LAMPRE", "MARCEGAGLIA", "VARCOLOR", "METALCOAT", "ARVEDI"]:
        if f in testo_u:
            dati["fornitore"] = f.capitalize()
            break
            
    # 3. SPESSORE: Cerca formati come 0.50 o 0,60
    m_sp = re.search(r'(0[.,]\d{2})', testo_u)
    if m_sp: dati["spessore"] = float(m_sp.group(1).replace(',', '.'))
    
    # 4. PESO: Cerca numeri seguiti da KG o vicino a "NET"
    m_peso = re.search(r'(\d{3,5})\s*KG', testo_u)
    if m_peso: dati["peso"] = int(m_peso.group(1))
    
    # 5. MQ: Cerca numeri decimali vicino a MQ o M2
    m_mq = re.search(r'(\d{2,4}[.,]\d{2})\s*(MQ|M2)', testo_u)
    if m_mq: dati["mq"] = float(m_mq.group(1).replace(',', '.'))

    # 6. COLORE: Prova a cercare codici RAL (es: RAL 9010)
    m_ral = re.search(r'(RAL\s*\d{4})', testo_u)
    if m_ral: dati["colore"] = m_ral.group(1)

    return dati

# --- 3. PASSWORD ---
if "auth" not in st.session_state: st.session_state.auth = False
if not st.session_state.auth:
    st.markdown("<h1 style='text-align: center;'>🔐 ACCESSO SB</h1>", unsafe_allow_html=True)
    pwd = st.text_input("Inserisci Password", type="password")
    if st.button("ENTRA"):
        if pwd == "Pannelli.2021":
            st.session_state.auth = True
            st.rerun()
        else: st.error("Accesso Negato")
    st.stop()

# --- 4. APP PRINCIPALE ---
if 'archivio' not in st.session_state: st.session_state.archivio = []
if 'temp' not in st.session_state: st.session_state.temp = {}
if 'show_scan' not in st.session_state: st.session_state.show_scan = False

st.markdown("<h2 class='orange-text'>PT Roseto - GESTIONE ARRIVI</h2>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📝 REGISTRA CARICO", "📦 ARCHIVIO"])

with tab1:
    # SEZIONE FOTO/FILE
    with st.expander("📷 ACQUISIZIONE AUTOMATICA (FOTO O GALLERIA)"):
        tipo = st.radio("Sorgente:", ["Fotocamera", "Galleria Dispositivo"], horizontal=True)
        img = st.camera_input("Scatta") if tipo == "Fotocamera" else st.file_uploader("Carica file", type=['jpg','png','jpeg'])
        
        if img:
            if st.button("🔍 ANALIZZA ORA"):
                with st.spinner("Estrazione dati in corso..."):
                    testo_raw = analizza_etichetta(img.getvalue())
                    if testo_raw:
                        st.session_state.temp = estrai_tutti_i_dati(testo_raw)
                        st.success("Dati pronti nel modulo sotto!")
                        st.rerun()

    # SCANNER BARCODE LIVE
    if st.session_state.show_scan:
        val = qrcode_scanner(key='live_scan')
        if val:
            st.session_state.temp["barcode"] = val
            st.session_state.show_scan = False
            st.rerun()
        st.button("CHIUDI SCANNER", on_click=lambda: st.session_state.update({"show_scan": False}))

    # IL FORM CON TUTTI I 10 CAMPI
    with st.form("form_registrazione", clear_on_submit=True):
        st.markdown("### 📋 Modulo di Carico")
        
        # 1. Barcode
        c_b1, c_b2 = st.columns([3,1])
        f_barcode = c_b1.text_input("📦 CODICE A BARRE", value=st.session_state.temp.get("barcode", ""))
        with c_b2:
            st.write("##")
            if st.form_submit_button("📷 SCAN"):
                st.session_state.show_scan = True
                st.rerun()

        # 2. Fornitore
        f_forn = st.text_input("🏭 PRODUTTORE/FORNITORE", value=st.session_state.temp.get("fornitore", ""))

        # 3 e 4. Spessore e Data
        c1, c2 = st.columns(2)
        f_spess = c1.number_input("📏 SPESSORE DICHIARATO", value=float(st.session_state.temp.get("spessore", 0.0)), format="%.2f")
        f_data = c2.date_input("📅 DATA ARRIVO", datetime.now())

        # 5. Descrizione
        f_desc = st.text_input("📝 DESCRIZIONE", value=st.session_state.temp.get("desc", ""))

        # 6 e 7. Colore e Peso
        c3, c4 = st.columns(2)
        f_col = c3.text_input("🎨 CODICE COLORE", value=st.session_state.temp.get("colore", ""))
        f_peso = c4.number_input("⚖️ PESO (KG)", value=int(st.session_state.temp.get("peso", 0)))

        # 8 e 9. MQ e Linea
        c5, c6 = st.columns(2)
        f_mq = c5.number_input("📐 METRI QUADRI", value=float(st.session_state.temp.get("mq", 0.0)), format="%.2f")
        f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"])

        # 10. Terminato
        f_term = st.selectbox("🏁 TERMINATO", ["NO", "SI"])

        if st.form_submit_button("🚀 REGISTRA MATERIALE"):
            st.session_state.archivio.append({
                "Codice a barre": f_barcode, "Produttore/Fornitore": f_forn,
                "Spessore dichiarato": f_spess, "Arrivo": f_data.strftime("%d/%m/%Y"),
                "Descrizione": f_desc, "Codice Colore": f_col,
                "Peso": f_peso, "Metri Quadri": f_mq, "Terminato": f_term, "Linea": f_linea
            })
            st.session_state.temp = {}
            st.success("✅ Salvato con successo!")

with tab2:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.dataframe(df, use_container_width=True)
        
        # EXPORT EXCEL
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
            df.to_excel(wr, index=False)
        st.download_button("📥 SCARICA EXCEL", out.getvalue(), "archivio_carichi.xlsx")
        
        if st.button("🗑️ SVUOTA ARCHIVIO"):
            st.session_state.archivio = []
            st.rerun()



