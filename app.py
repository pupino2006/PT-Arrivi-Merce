import streamlit as st
import pandas as pd
import re
import os
import json
from datetime import datetime
from io import BytesIO
from google.cloud import vision
from PIL import Image

# 1. Configurazione della pagina
st.set_page_config(page_title="SB App Arrivi", layout="centered", page_icon="ptsimbolo.png")

# 2. CSS Locale
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError: pass

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
    dati = {"barcode": "", "fornitore": "", "spessore": 0.0, "peso": 0, "mq": 0.0, "colore": "", "descrizione": "", "linea": "1"}
    
    match_bar = re.search(r'\b(S\d{7,15}|[0-9]{10,20}|[A-Z0-9]{15,})\b', testo_u)
    if match_bar: dati["barcode"] = match_bar.group(1)
    
    mappa = {"LAMPRE": "Lampre", "MARCEGAGLIA": "Marcegaglia", "VARCOLOR": "Varcolor", "METALCOAT": "Metalcoat"}
    for k, v in mappa.items():
        if k in testo_u: dati["fornitore"] = v
        
    match_sp = re.search(r'(0[.,]\d{2})', testo_u)
    if match_sp: dati["spessore"] = float(match_sp.group(1).replace(',', '.'))
    return dati

# --- LOGICA DI ACCESSO ---
if "password_correct" not in st.session_state:
    st.session_state.password_correct = False

# (Omettiamo per brevità la funzione check_password ma assumiamo che sia presente)

# --- APP PRINCIPALE ---
if True: # Sostituire con if check_password():
    
    # Inizializzazione stati
    if 'archivio' not in st.session_state: st.session_state.archivio = []
    if 'temp_scan' not in st.session_state: st.session_state.temp_scan = {}
    if 'show_scanner' not in st.session_state: st.session_state.show_scanner = False

    try: st.image("ptsimbolo.png", width=80)
    except: st.title("SB CARICO")

    tab1, tab2 = st.tabs(["📝 NUOVO CARICO", "📦 STORICO"])

    with tab1:
# --- PARTE 2: FORM CON SCANNER RAPIDO PER IL CODICE ---
    with st.form("form_carico"):
        st.markdown("### Dati Materiale")
        
        # Logica Scanner Rapido (stile la tua app JS)
        col_code, col_btn = st.columns([3, 1])
        
        with col_btn:
            st.write("##")
            if st.form_submit_button("📷 SCAN"):
                st.session_state.show_quick_scan = True

        # Se premuto SCAN, appare il lettore stile JS sopra il campo
        barcode_scansionato = ""
        if st.session_state.show_quick_scan:
            barcode_scansionato = st_barcode_scanner()
            if barcode_scansionato:
                st.session_state.temp_data["barcode"] = barcode_scansionato
                st.session_state.show_quick_scan = False
                st.rerun()

        f_barcode = col_code.text_input("📦 CODICE A BARRE / QR", 
                                       value=st.session_state.temp_data.get("barcode", ""))

        # FORM DI CARICO
        with st.form("form_carico", clear_on_submit=True):
            st.markdown("### 📝 Dati Materiale")
            
            col_a, col_b = st.columns([3, 1])
            f_barcode = col_a.text_input("📦 CODICE A BARRE", value=st.session_state.temp_scan.get("barcode", ""))
            
            with col_b:
                st.write("##")
                # IL PULSANTE SCAN ORA ATTIVA LA FOTOCAMERA SOPRA
                if st.form_submit_button("📷 SCAN"):
                    st.session_state.show_scanner = True
                    st.rerun()

            c1, c2 = st.columns(2)
            f_fornitore = c1.text_input("🏭 FORNITORE", value=st.session_state.temp_scan.get("fornitore", ""))
            f_spessore = c2.number_input("📏 SPESSORE DICHIARATO", value=st.session_state.temp_scan.get("spessore", 0.0), format="%.2f", step=0.01)

            f_descrizione = st.text_input("📝 DESCRIZIONE", value=st.session_state.temp_scan.get("descrizione", ""))
            f_arrivo = st.date_input("📅 DATA ARRIVO", datetime.now())

            c3, c4 = st.columns(2)
            f_colore = c3.text_input("🎨 CODICE COLORE", value=st.session_state.temp_scan.get("colore", ""))
            f_peso = c4.number_input("⚖️ PESO (KG)", value=st.session_state.temp_scan.get("peso", 0), step=1)

            c5, c6 = st.columns(2)
            f_mq = c5.number_input("📐 METRI QUADRI", value=st.session_state.temp_scan.get("mq", 0.0), step=0.01)
            f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"], index=0 if st.session_state.temp_scan.get("linea")=="1" else 1)

            f_terminato = st.selectbox("🏁 TERMINATO", ["", "SI", "NO"], index=0)

            if st.form_submit_button("🚀 REGISTRA CARICO"):
                st.session_state.archivio.append({
                    "Codice a barre": f_barcode, "Produttore/Fornitore": f_fornitore,
                    "Spessore dichiarato": f_spessore, "Arrivo": f_arrivo.strftime("%Y-%m-%d"),
                    "Descrizione": f_descrizione, "Codice Colore": f_colore,
                    "Peso": f_peso, "Metri Quadri": f_mq, "Terminato": f_terminato, "Linea": f_linea
                })
                st.session_state.temp_scan = {} 
                st.success("Carico registrato!")

    with tab2:
        if st.session_state.archivio:
            df = pd.DataFrame(st.session_state.archivio)
            st.dataframe(df, use_container_width=True)
            # ... resto del codice per export excel
            
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                df.to_excel(writer, index=False)
            st.download_button("📥 SCARICA EXCEL", output.getvalue(), "carico_merci.xlsx")
            
            if st.button("🗑️ CANCELLA TUTTO"):
                st.session_state.archivio = []
                st.rerun()





