import streamlit as st
import pandas as pd
import re
import os
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image
from streamlit_qrcode_scanner import qrcode_scanner

# --- 1. CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="SB App Arrivi", layout="centered", page_icon="ptsimbolo.png")

# --- 2. CSS PERSONALIZZATO (Il tuo design Dark/Orange) ---
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&display=swap');

    .stApp {
        background-color: #0b0f1a !important;
        font-family: 'Inter', sans-serif;
    }

    header { visibility: hidden; }

    h1, h2, h3, label, p, .stMarkdown {
        color: #f8fafc !important;
        font-weight: 800 !important;
        letter-spacing: -0.5px;
    }

    /* INPUT FIELDS */
    .stTextInput input, .stNumberInput input, .stSelectbox div[data-baseweb="select"] {
        background-color: #1e293b !important;
        border: 1px solid #334155 !important;
        color: #f8fafc !important;
        border-radius: 12px !important;
        height: 50px !important;
    }

    /* BOTTONE PRINCIPALE (Arancione Neon) */
    div.stButton > button, div.stFormSubmitButton > button {
        width: 100% !important;
        background: #f97316 !important; 
        color: white !important;
        border: none !important;
        border-radius: 18px !important;
        height: 60px !important;
        font-size: 1.1rem !important;
        font-weight: 900 !important;
        text-transform: uppercase;
        font-style: italic;
        box-shadow: 0 4px 15px rgba(249, 115, 22, 0.3) !important;
        transition: all 0.2s ease;
    }

    div.stButton > button:active { transform: scale(0.95); }

    /* CARD EFFETTO VETRO */
    div[data-testid="stExpander"] {
        background: rgba(30, 41, 59, 0.6) !important;
        border-radius: 24px !important;
        border: 1px solid rgba(255, 255, 255, 0.05) !important;
    }
    
    .orange-text { color: #f97316; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. FUNZIONI LOGICHE ---
def analizza_con_google(image_bytes):
    try:
        # Assicurati di aver caricato le "Secrets" su Streamlit Cloud
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=image_bytes)
        response = client.text_detection(image=image)
        if response.text_annotations:
            return response.text_annotations[0].description
        return ""
    except Exception as e:
        st.error(f"Errore Google Vision: {e}")
        return ""

def estrai_dati(testo):
    testo_u = testo.upper()
    dati = {"barcode": "", "fornitore": "", "spessore": 0.0}
    match_bar = re.search(r'\b(S\d{7,15}|[0-9]{10,20})\b', testo_u)
    if match_bar: dati["barcode"] = match_bar.group(1)
    mappa = {"LAMPRE": "Lampre", "MARCEGAGLIA": "Marcegaglia", "VARCOLOR": "Varcolor", "METALCOAT": "Metalcoat"}
    for k, v in mappa.items():
        if k in testo_u: dati["fornitore"] = v
    match_sp = re.search(r'(0[.,]\d{2})', testo_u)
    if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))
    return dati

# --- 4. GESTIONE PASSWORD ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.markdown("<h1 style='text-align: center;'>🔐 ACCESSO RISERVATO</h1>", unsafe_allow_html=True)
    password = st.text_input("Inserisci la Password", type="password")
    if st.button("ACCEDI"):
        if password == "pt2026": # Cambia la password qui
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Password errata")
    st.stop()

# --- 5. LOGICA APP (Dopo Login) ---
if 'archivio' not in st.session_state: st.session_state.archivio = []
if 'temp_scan' not in st.session_state: st.session_state.temp_scan = {}
if 'show_quick_scan' not in st.session_state: st.session_state.show_quick_scan = False

st.markdown("<h2 class='orange-text'>PIETRO ROSETO - CARICO MERCI</h2>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📝 NUOVO CARICO", "📦 STORICO"])

with tab1:
    # Google Vision Expander
    with st.expander("📷 SCANSIONE ETICHETTA COMPLETA (FOTO)"):
        foto = st.camera_input("Scatta per auto-compilare")
        if foto:
            testo = analizza_con_google(foto.getvalue())
            if testo:
                st.session_state.temp_scan = estrai_dati(testo)
                st.success("Dati estratti!")
                st.rerun()

    # Scanner Rapido Barcode
    if st.session_state.show_quick_scan:
        barcode = qrcode_scanner(key='scanner')
        if barcode:
            st.session_state.temp_scan["barcode"] = barcode
            st.session_state.show_quick_scan = False
            st.rerun()
        if st.button("CHIUDI SCANNER"):
            st.session_state.show_quick_scan = False
            st.rerun()

    # Form Principale
    with st.form("form_carico"):
        col_a, col_b = st.columns([3, 1])
        f_barcode = col_a.text_input("📦 CODICE A BARRE", value=st.session_state.temp_scan.get("barcode", ""))
        with col_b:
            st.write("##")
            if st.form_submit_button("📷 SCAN"):
                st.session_state.show_quick_scan = True
                st.rerun()

        c1, c2 = st.columns(2)
        f_fornitore = c1.text_input("🏭 FORNITORE", value=st.session_state.temp_scan.get("fornitore", ""))
        f_spessore = c2.number_input("📏 SPESSORE", value=float(st.session_state.temp_scan.get("spessore", 0.0)), step=0.01)

        f_desc = st.text_input("📝 DESCRIZIONE")
        
        if st.form_submit_button("🚀 REGISTRA MATERIALE"):
            st.session_state.archivio.append({
                "Barcode": f_barcode, "Fornitore": f_fornitore, "Spessore": f_spessore, 
                "Descrizione": f_desc, "Data": datetime.now().strftime("%d/%m/%Y")
            })
            st.session_state.temp_scan = {}
            st.success("Registrato!")

with tab2:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.table(df)
        # Bottone Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 SCARICA EXCEL", output.getvalue(), "carico.xlsx")

