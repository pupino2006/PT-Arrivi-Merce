import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from streamlit_barcode_scanner import st_barcode_scanner

# 1. Configurazione della pagina
st.set_page_config(page_title="SB App Arrivi", layout="centered", page_icon="ptsimbolo.png")

# 2. CSS Locale (incluso direttamente per sicurezza)
st.markdown("""
    <style>
    .stApp { background: white; }
    label, p, h3 { color: black !important; font-weight: bold; }
    .stButton>button {
        background-color: #004a99 !important;
        color: white !important;
        font-weight: bold !important;
        border-radius: 8px;
    }
    iframe { border-radius: 10px; border: 2px solid #004a99; }
    </style>
    """, unsafe_allow_html=True)

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
    dati = {"barcode": "", "fornitore": "", "spessore": 0.0, "peso": 0, "mq": 0.0, "colore": "", "descrizione": "", "linea": "1"}
    match_bar = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo_u)
    if match_bar: dati["barcode"] = match_bar.group(1)
    mappa = {"LAMPRE": "Lampre", "MARCEGAGLIA": "Marcegaglia", "VARCOLOR": "Varcolor", "METALCOAT": "Metalcoat"}
    for k, v in mappa.items():
        if k in testo_u: dati["fornitore"] = v
    match_sp = re.search(r'(0[.,]\d{2})', testo_u)
    if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))
    return dati

# --- INIZIALIZZAZIONE STATI ---
if 'archivio' not in st.session_state: st.session_state.archivio = []
if 'temp_scan' not in st.session_state: st.session_state.temp_scan = {}
if 'show_quick_scan' not in st.session_state: st.session_state.show_quick_scan = False

# --- UI ---
try: st.image("ptsimbolo.png", width=80)
except: st.title("SB CARICO")

tab1, tab2 = st.tabs(["📝 NUOVO CARICO", "📦 STORICO"])

with tab1:
    # 1. SCANNER GOOGLE VISION (OPZIONALE)
    with st.expander("📷 ANALISI ETICHETTA COMPLETA (FOTO)"):
        foto = st.camera_input("Scatta foto per estrarre tutti i dati")
        if foto:
            testo = analizza_con_google(foto.getvalue())
            st.session_state.temp_scan = estrai_dati_completi(testo)
            st.success("Dati estratti!")

    # 2. SCANNER RAPIDO BARCODE (Logica JS - fuori dal form)
    if st.session_state.show_quick_scan:
        st.markdown("### 📷 Inquadra il Codice")
        barcode_letto = st_barcode_scanner()
        if barcode_letto:
            st.session_state.temp_scan["barcode"] = barcode_letto
            st.session_state.show_quick_scan = False
            st.rerun()
        if st.button("❌ CHIUDI SCANNER"):
            st.session_state.show_quick_scan = False
            st.rerun()

    # 3. FORM UNICO DI CARICO
    with st.form("form_carico_unico", clear_on_submit=True):
        st.markdown("### 📝 Dati Materiale")
        
        # Codice a barre con tasto SCAN
        col_a, col_b = st.columns([3, 1])
        f_barcode = col_a.text_input("📦 CODICE A BARRE", value=st.session_state.temp_scan.get("barcode", ""))
        
        with col_b:
            st.write("##")
            if st.form_submit_button("📷 SCAN"):
                st.session_state.show_quick_scan = True
                st.rerun()

        # Altri campi
        c1, c2 = st.columns(2)
        f_fornitore = c1.text_input("🏭 FORNITORE", value=st.session_state.temp_scan.get("fornitore", ""))
        f_spessore = c2.number_input("📏 SPESSORE DICHIARATO", value=st.session_state.temp_scan.get("spessore", 0.0), format="%.2f", step=0.01)

        f_descrizione = st.text_input("📝 DESCRIZIONE", value=st.session_state.temp_scan.get("descrizione", ""))
        f_arrivo = st.date_input("📅 DATA ARRIVO", datetime.now())

        c3, c4 = st.columns(2)
        f_colore = c3.text_input("🎨 CODICE COLORE", value=st.session_state.temp_scan.get("colore", ""))
        f_peso = c4.number_input("⚖️ PESO (KG)", value=int(st.session_state.temp_scan.get("peso", 0)), step=1)

        c5, c6 = st.columns(2)
        f_mq = c5.number_input("📐 METRI QUADRI", value=float(st.session_state.temp_scan.get("mq", 0.0)), step=0.01)
        f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"], index=0 if st.session_state.temp_scan.get("linea")=="1" else 1)

        f_terminato = st.selectbox("🏁 TERMINATO", ["", "SI", "NO"], index=0)

        # Pulsante di salvataggio
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
            st.session_state.temp_scan = {} # Reset dati temporanei
            st.success("Carico registrato!")

with tab2:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.dataframe(df, use_container_width=True)
        
        # Download Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df.to_excel(writer, index=False)
        st.download_button("📥 SCARICA EXCEL", output.getvalue(), "carico_merci.xlsx")
        
        if st.button("🗑️ CANCELLA TUTTO"):
            st.session_state.archivio = []
            st.rerun()
