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
from supabase import create_client, Client

# --- 1. CONFIGURAZIONE E DESIGN ---
st.set_page_config(page_title="Arrivi Merce PT", layout="centered", page_icon="ptsimbolo.png")

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

# --- LISTE FISSE E SUPABASE ---
FORNITORI_FISSI = [
    "Alusteel", "Vetroresina Spa", "stacbond", "Metalcoat S.P.A.", "Sandrini", 
    "Arcelormittal", "Arv", "Efinox", "Ediltec", "Italcoat", "Lampre", 
    "Marcegaglia", "Novelis", "Origoni e Zanoletti", "Sandrini/Sandrini M.", 
    "Varcolor", "Brianza", "Polser", "Rivierasca", "Stabilit", "Fibrosan"
]

@st.cache_data(ttl=600)
def carica_db_supabase():
    try:
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
        supabase: Client = create_client(url, key)
        response = supabase.table("db_mp_arrivi").select("*").execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.warning("⚠️ Impossibile connettersi a Supabase. Controlla i Secrets.")
        return pd.DataFrame(columns=["Produttore/Fornitore", "Descrizione", "Codice Colore"])

df_db = carica_db_supabase()

# --- 2. LOGICA DI ANALISI GOOGLE VISION ---
def analizza_etichetta(image_bytes):
    try:
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
    dati = {
        "barcode": "", "fornitore": "", "spessore": 0.0, 
        "peso": 0, "mq": 0.0, "colore": "", "desc": ""
    }
    
    m_bar = re.search(r'\b(S\d{7,15}|[0-9]{10,20})\b', testo_u)
    if m_bar: dati["barcode"] = m_bar.group(1)
    
    for f in ["LAMPRE", "MARCEGAGLIA", "VARCOLOR", "METALCOAT", "ARVEDI"]:
        if f in testo_u:
            dati["fornitore"] = f.capitalize()
            break
            
    m_sp = re.search(r'(0[.,]\d{2})', testo_u)
    if m_sp: dati["spessore"] = float(m_sp.group(1).replace(',', '.'))
    
    m_peso = re.search(r'(\d{3,5})\s*KG', testo_u)
    if m_peso: dati["peso"] = int(m_peso.group(1))
    
    m_mq = re.search(r'(\d{2,4}[.,]\d{2})\s*(MQ|M2)', testo_u)
    if m_mq: dati["mq"] = float(m_mq.group(1).replace(',', '.'))

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

st.markdown("<h2 class='orange-text'>Arrivi Merce PT</h2>", unsafe_allow_html=True)

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

    # MODULO DI CARICO (Senza st.form per permettere le liste a cascata)
    st.markdown("### 📋 Modulo di Carico")
    
    # 1. Barcode
    c_b1, c_b2 = st.columns([3,1], vertical_alignment="bottom")
    f_barcode = c_b1.text_input("📦 CODICE A BARRE", value=st.session_state.temp.get("barcode", ""))
    with c_b2:
        if st.button("📷 SCAN"):
            st.session_state.show_scan = True
            st.rerun()

    # 2. Fornitore (con logica OCR)
    ocr_forn = st.session_state.temp.get("fornitore", "")
    forn_options = ["Seleziona..."] + sorted(FORNITORI_FISSI) + ["ALTRO (Scrittura Libera)"]
    idx_forn = 0
    if ocr_forn:
        for i, f in enumerate(forn_options):
            if ocr_forn.upper() in f.upper():
                idx_forn = i
                break

    scelta_forn = st.selectbox("🏭 PRODUTTORE/FORNITORE", options=forn_options, index=idx_forn)
    
    if scelta_forn == "ALTRO (Scrittura Libera)":
        f_forn = st.text_input("Scrivi Produttore/Fornitore", value=ocr_forn)
    else:
        f_forn = scelta_forn if scelta_forn != "Seleziona..." else ""

    # 3. Descrizione (Filtrata da Supabase)
    desc_options = ["Seleziona..."]
    if f_forn and not df_db.empty:
        filtro_db = df_db[df_db["Produttore/Fornitore"].str.contains(f_forn, case=False, na=False)]
        desc_uniche = filtro_db["Descrizione"].dropna().unique().tolist()
        desc_options.extend(sorted(desc_uniche))
    desc_options.append("ALTRO (Scrittura Libera)")

    ocr_desc = st.session_state.temp.get("desc", "")
    scelta_desc = st.selectbox("📝 DESCRIZIONE", options=desc_options)

    if scelta_desc == "ALTRO (Scrittura Libera)":
        f_desc = st.text_input("Scrivi Descrizione", value=ocr_desc)
    else:
        f_desc = scelta_desc if scelta_desc != "Seleziona..." else ""

    # 4. Colore (Filtrato da Fornitore + Descrizione)
    color_options = ["Seleziona..."]
    if f_forn and f_desc and not df_db.empty:
        filtro_colore = df_db[(df_db["Produttore/Fornitore"].str.contains(f_forn, case=False, na=False)) & 
                              (df_db["Descrizione"] == f_desc)]
        col_unici = filtro_colore["Codice Colore"].dropna().unique().tolist()
        color_options.extend(sorted(col_unici))
    color_options.append("ALTRO (Scrittura Libera)")

    ocr_colore = st.session_state.temp.get("colore", "")
    
    # Layout a colonne per il resto
    c1, c2 = st.columns(2)
    scelta_col = c1.selectbox("🎨 CODICE COLORE", options=color_options)
    if scelta_col == "ALTRO (Scrittura Libera)":
        f_col = c1.text_input("Scrivi Codice Colore", value=ocr_colore)
    else:
        f_col = scelta_col if scelta_col != "Seleziona..." else ""

    f_spess = c2.number_input("📏 SPESSORE DICHIARATO", value=float(st.session_state.temp.get("spessore", 0.0)), format="%.2f")
    
    c3, c4 = st.columns(2)
    f_peso = c3.number_input("⚖️ PESO (KG)", value=int(st.session_state.temp.get("peso", 0)))
    f_mq = c4.number_input("📐 METRI QUADRI", value=float(st.session_state.temp.get("mq", 0.0)), format="%.2f")

    c5, c6 = st.columns(2)
    f_data = c5.date_input("📅 DATA ARRIVO", datetime.now())
    f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"])

    f_term = st.selectbox("🏁 TERMINATO", [" ", "NO", "SI"])

    if st.button("🚀 REGISTRA MATERIALE"):
        st.session_state.archivio.append({
            "Codice a barre": f_barcode, "Produttore/Fornitore": f_forn,
            "Spessore dichiarato": f_spess, "Arrivo": f_data.strftime("%d/%m/%Y"),
            "Descrizione": f_desc, "Codice Colore": f_col,
            "Peso": f_peso, "Metri Quadri": f_mq, "Terminato": f_term, "Linea": f_linea
        })
        st.session_state.temp = {} # Pulisce i dati OCR temporanei
        st.success("✅ Salvato con successo!")
        st.rerun()

with tab2:
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        st.dataframe(df, use_container_width=True)
        
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
            df.to_excel(wr, index=False)
        st.download_button("📥 SCARICA EXCEL", out.getvalue(), "archivio_carichi.xlsx")
        
        if st.button("🗑️ SVUOTA ARCHIVIO"):
            st.session_state.archivio = []
            st.rerun()
