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
# --- 2. GESTIONE PASSWORD ---
if "auth" not in st.session_state: st.session_state.auth = False
if not st.session_state.auth:
    st.markdown("<h1 style='text-align: center;'>🔐 ACCESSO</h1>", unsafe_allow_html=True)
    pwd = st.text_input("Inserisci Password", type="password")
    if st.button("ENTRA"):
        if pwd == "PIETRO2024":
            st.session_state.auth = True
            st.rerun()
        else: st.error("Password errata")
    st.stop()

# --- 3. INIZIALIZZAZIONE ---
if 'archivio' not in st.session_state: st.session_state.archivio = []
if 'temp' not in st.session_state: st.session_state.temp = {}
if 'show_scan' not in st.session_state: st.session_state.show_scan = False

# Funzione per estrarre dati da testo (Google Vision)
def estrai_dati_da_testo(testo):
    testo_u = testo.upper()
    dati = {"barcode": "", "fornitore": "", "spessore": 0.0}
    # Esempio semplice di regex per barcode
    m_bar = re.search(r'\b(S\d{7,15}|[0-9]{10,20})\b', testo_u)
    if m_bar: dati["barcode"] = m_bar.group(1)
    return dati

st.markdown("<h2 class='orange-text'>PIETRO ROSETO - CARICO MERCI</h2>", unsafe_allow_html=True)

tab1, tab2 = st.tabs(["📝 NUOVO CARICO", "📦 STORICO"])

with tab1:
    # --- SEZIONE CARICAMENTO FILE / FOTO ---
    with st.expander("📷 ACQUISIZIONE ETICHETTA (FOTO O FILE)"):
        opzione = st.radio("Scegli sorgente:", ["Scatta Foto", "Carica da Dispositivo"])
        
        testo_estratto = ""
        img_source = None
        
        if opzione == "Scatta Foto":
            img_source = st.camera_input("Inquadra etichetta")
        else:
            img_source = st.file_uploader("Seleziona file immagine", type=['png', 'jpg', 'jpeg'])
            
        if img_source:
            # Qui andrebbe la logica Google Vision (analizza_con_google)
            # Per ora simuliamo l'estrazione per non bloccare l'app
            st.info("Immagine acquisita. Analisi in corso...")
            # st.session_state.temp = estrai_dati_da_testo(testo_estratto)

    # --- SCANNER BARCODE LIVE ---
    if st.session_state.show_scan:
        val = qrcode_scanner(key='scanner')
        if val:
            st.session_state.temp["barcode"] = val
            st.session_state.show_scan = False
            st.rerun()
        if st.button("CHIUDI SCANNER"):
            st.session_state.show_scan = False
            st.rerun()

    # --- FORM CON TUTTI I 10 CAMPI ---
    with st.form("main_form", clear_on_submit=True):
        st.markdown("### 📋 Dati Materiale")
        
        # 1. Codice a Barre (con tasto Scan)
        col_bar_1, col_bar_2 = st.columns([3, 1])
        f_barcode = col_bar_1.text_input("📦 CODICE A BARRE", value=st.session_state.temp.get("barcode", ""))
        with col_bar_2:
            st.write("##")
            if st.form_submit_button("📷 SCAN"):
                st.session_state.show_scan = True
                st.rerun()

        # 2. Produttore/Fornitore
        f_fornitore = st.text_input("🏭 PRODUTTORE/FORNITORE", value=st.session_state.temp.get("fornitore", ""))

        c1, c2 = st.columns(2)
        # 3. Spessore dichiarato
        f_spessore = c1.number_input("📏 SPESSORE DICHIARATO", value=0.0, format="%.2f")
        # 4. Arrivo (Data)
        f_arrivo = c2.date_input("📅 DATA ARRIVO", datetime.now())

        # 5. Descrizione
        f_descrizione = st.text_input("📝 DESCRIZIONE")

        c3, c4 = st.columns(2)
        # 6. Codice Colore
        f_colore = c3.text_input("🎨 CODICE COLORE")
        # 7. Peso
        f_peso = c4.number_input("⚖️ PESO (KG)", value=0, step=1)

        c5, c6 = st.columns(2)
        # 8. Metri Quadri
        f_mq = c5.number_input("📐 METRI QUADRI", value=0.0, format="%.2f")
        # 9. Linea
        f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"])

        # 10. Terminato
        f_terminato = st.selectbox("🏁 TERMINATO", ["NO", "SI"])

        if st.form_submit_button("🚀 REGISTRA CARICO"):
            nuovo_dato = {
                "Codice a barre": f_barcode,
                "Produttore/Fornitore": f_fornitore,
                "Spessore dichiarato": f_spessore,
                "Arrivo": f_arrivo.strftime("%d/%m/%Y"),
                "Descrizione": f_descrizione,
                "Codice Colore": f_colore,
                "Peso": f_peso,
                "Metri Quadri": f_mq,
                "Terminato": f_terminato,
                "Linea": f_linea
            }
            st.session_state.archivio.append(nuovo_dato)
            st.session_state.temp = {}
            st.success("✅ Materiale registrato con successo!")

with tab2:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.dataframe(df)
        
        # Download Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 SCARICA EXCEL", output.getvalue(), "archivio_carichi.xlsx")
    else:
        st.info("Nessun carico registrato.")

