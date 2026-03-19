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
import easyocr

# Inizializza EasyOCR (caricato una sola volta in cache)
@st.cache_resource
def get_easyocr_reader():
    return easyocr.Reader(['it', 'en'], gpu=True)

# Dizionario fornitori per matching fuzzy
FORNITORI_MAP = {
    "LAMPRE": "Lampre",
    "MARCEGAGLIA": "Marcegaglia",
    "VARCOLOR": "Varcolor",
    "METALCOAT": "Metalcoat S.P.A.",
    "ARVEDI": "Arv",
    "ARV": "Arv",
    "ALUSTEEL": "Alusteel",
    "STACBOND": "stacbond",
    "VETRORESINA": "Vetroresina Spa",
    "EFINOX": "Efinox",
    "EDILTEC": "Ediltec",
    "ITALCOAT": "Italcoat",
    "NOVELIS": "Novelis",
    "ORIGONI": "Origoni e Zanoletti",
    "SANDRINI": "Sandrini",
    "BRIANZA": "Brianza",
    "POLSER": "Polser",
    "RIVIERASCA": "Rivierasca",
    "STABILIT": "Stabilit",
    "FIBROSAN": "Fibrosan",
    "ARCELORMITTAL": "Arcelormittal",
}

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

# --- 2. LOGICA DI ANALISI GOOGLE VISION E EASYOCR ---
def analizza_etichetta_google(image_bytes):
    """Analisi con Google Vision API"""
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

def analizza_etichetta_easyocr(image_bytes):
    """Analisi con EasyOCR (offline)"""
    try:
        reader = get_easyocr_reader()
        image = Image.open(BytesIO(image_bytes))
        result = reader.readtext(BytesIO(image_bytes), detail=0)
        return ' '.join(result)
    except Exception as e:
        st.error(f"Errore EasyOCR: {e}")
        return ""

def estrai_tutti_i_dati(testo, mostra_debug=False):
    """Estrazione avanzata con regex multiple e fuzzy matching"""
    if not testo:
        return {"barcode": "", "fornitore": "", "spessore": 0.0, "peso": 0, "mq": 0.0, "colore": "", "desc": ""}
    
    testo_u = testo.upper()
    testo_norm = re.sub(r'\s+', ' ', testo_u)  # Normalizza spazi
    
    if mostra_debug:
        st.text_area("📄 Testo OCR grezzo (per verifica):", value=testo, height=150)
    
    dati = {
        "barcode": "", 
        "fornitore": "", 
        "spessore": 0.0, 
        "peso": 0, 
        "mq": 0.0, 
        "colore": "", 
        "desc": ""
    }
    
    # === BARCODE: pattern multipli ===
    patterns_barcode = [
        r'\bS\d{8,15}\b',           # S + 8-15 cifre
        r'\b\d{12,20}\b',           # Solo cifre 12-20
        r'\b[A-Z]{2,4}\d{6,12}\b',  # Lettere + cifre
        r'\b\d{8}[A-Z0-9]{2,8}\b',  # Cifre + lettere
    ]
    for pat in patterns_barcode:
        m = re.search(pat, testo_norm)
        if m:
            dati["barcode"] = m.group()
            break
    
    # === FORNITORE: fuzzy matching con dizionario ===
    for chiave, valore in FORNITORI_MAP.items():
        if chiave in testo_norm:
            dati["fornitore"] = valore
            break
    
    # === SPESSORE: pattern multipli per catturare diversi formati ===
    patterns_spessore = [
        r'SPESSORE[:\s]*(\d+[.,]\d{2})',  # SPESSORE: 0.50
        r'(\d[.,]\d{2})\s*MM\b',           # 0.50 MM
        r'\b(0[.,]\d{2})\b',               # 0.50 standalone
        r'\b(\d[.,]\d{2})\s*(MM|MILL)?',   # 2.00MM o 2.00 MILL
    ]
    for pat in patterns_spessore:
        m = re.search(pat, testo_norm)
        if m:
            try:
                dati["spessore"] = float(m.group(1).replace(',', '.'))
                break
            except:
                pass
    
    # === PESO: KG con vari formati ===
    patterns_peso = [
        r'PESO[:\s]*(\d{3,5})\s*KG',       # PESO: 1250 KG
        r'(\d{3,5})\s*KG\b',               # 1250 KG
        r'KG\s*(\d{3,5})\b',               # KG 1250
        r'PESO\s*NETTO[:\s]*(\d{3,5})',    # PESO NETTO: 1250
    ]
    for pat in patterns_peso:
        m = re.search(pat, testo_norm)
        if m:
            try:
                dati["peso"] = int(m.group(1))
                break
            except:
                pass
    
    # === METRI QUADRI ===
    patterns_mq = [
        r'(?:MQ|M2|MQ\.)\s*[:\s]*(\d{2,4}[.,]\d{2})',  # MQ: 125.50
        r'(\d{2,4}[.,]\d{2})\s*(?:MQ|M2)',              # 125.50 MQ
        r'SUPERFICIE[:\s]*(\d{2,4}[.,]\d{2})',         # SUPERFICIE: 125.50
    ]
    for pat in patterns_mq:
        m = re.search(pat, testo_norm)
        if m:
            try:
                dati["mq"] = float(m.group(1).replace(',', '.'))
                break
            except:
                pass
    
    # === COLORE: RAL, NCS, NOMI COMUNI ===
    patterns_colore = [
        r'RAL\s*(\d{4})',                     # RAL 7016
        r'NCS\s*[S]?\s*(\d{4}[-\s]?[A-Z]{2})', # NCS 7016-M
        r'COLORE[:\s]*([A-Z0-9\-]{3,15})',     # COLORE: grigio antracite
    ]
    for pat in patterns_colore:
        m = re.search(pat, testo_norm)
        if m:
            dati["colore"] = m.group()
            break
    
    # === DESCRIZIONE: cerca parole chiave ===
    descrizioni = [
        "PANNELLO", "LAMIERA", "COIL", "LASTRA", "RIBASSO",
        "GOFRATO", "LISCIO", "PREVERNICIATO", "ALLUMINIO", "ACCIAIO",
        "COMPOSITE", "SANDWICH", "PANEL", "ELEMENT"
    ]
    for desc in descrizioni:
        if desc in testo_norm:
            dati["desc"] = desc.lower()
            break

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
    # SEZIONE FOTO/FILE - CARICAMENTO MULTIPLO
    with st.expander("📷 ACQUISIZIONE MULTIPLA ETICHETTE (LOTTO)"):
        st.info("💡 Carica tutte le foto delle etichette del lotto contemporaneamente. Compila i dati comuni una sola volta!")
        
        # Scelta motore OCR
        ocr_engine = st.radio("🧠 Motore OCR:", ["Google Vision API", "EasyOCR (Offline)"], horizontal=True, help="Google Vision è più preciso ma richiede connessione. EasyOCR funziona offline.")
        
        # File uploader per caricamento multiplo
        uploaded_files = st.file_uploader("📂 Carica tutte le foto delle etichette (puoi selezionarne più di una)", 
                                          type=['jpg','png','jpeg'], 
                                          accept_multiple_files=True)
        
        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)} etichette caricate")
            
            # Inizializza la lista delle etichette analizzate se non esiste
            if 'etichette_lotto' not in st.session_state:
                st.session_state.etichette_lotto = []
            
            # Se il numero di file è cambiato, ri-analizza tutto
            if len(st.session_state.etichette_lotto) != len(uploaded_files):
                if st.button("🔍 ANALIZZA TUTTE LE ETICHETTE"):
                    with st.spinner("Analisi in corso..."):
                        st.session_state.etichette_lotto = []
                        for i, file in enumerate(uploaded_files):
                            with st.spinner(f"Analizzando etichetta {i+1}/{len(uploaded_files)}..."):
                                if ocr_engine == "Google Vision API":
                                    testo_raw = analizza_etichetta_google(file.getvalue())
                                else:
                                    testo_raw = analizza_etichetta_easyocr(file.getvalue())
                                
                                dati = estrai_tutti_i_dati(testo_raw)
                                st.session_state.etichette_lotto.append({
                                    "index": i,
                                    "filename": file.name,
                                    "barcode": dati.get("barcode", ""),
                                    "fornitore": dati.get("fornitore", ""),
                                    "spessore": dati.get("spessore", 0.0),
                                    "peso": dati.get("peso", 0),
                                    "mq": dati.get("mq", 0.0),
                                    "colore": dati.get("colore", ""),
                                    "desc": dati.get("desc", ""),
                                    "ocr_raw": testo_raw,
                                    "manuale": False  # Flag per tracciare se il barcode è stato inserito manualmente
                                })
                        st.success(f"✅ Analizzate {len(st.session_state.etichette_lotto)} etichette!")
                        st.rerun()
            
            # Mostra le etichette analizzate
            if st.session_state.etichette_lotto:
                st.markdown("### 📋 Riepilogo Etichette Analizzate")
                
                # Mostra tabella riepilogativa
                for i, et in enumerate(st.session_state.etichette_lotto):
                    status_icon = "✅" if et["barcode"] else "⚠️"
                    st.markdown(f"**{status_icon} Etichetta {i+1}** ({et['filename']}) - Barcode: `{et['barcode'] or 'NON RILEVATO'}`")
                
                # Se ci sono barcode non rilevati, offre la possibilità di scansionarli
                barcode_mancanti = [i for i, et in enumerate(st.session_state.etichette_lotto) if not et["barcode"]]
                
                if barcode_mancanti:
                    st.warning(f"⚠️ {len(barcode_mancanti)} etichette senza barcode rilevato. Serve scansione manuale.")
                    
                    # Scanner per barcode mancanti
                    if 'idx_scan_corrente' not in st.session_state:
                        st.session_state.idx_scan_corrente = 0
                    
                    idx_corrente = barcode_mancanti[st.session_state.get('idx_scan_corrente', 0)]
                    
                    if st.session_state.show_scan:
                        val = qrcode_scanner(key=f'scan_{idx_corrente}')
                        if val:
                            st.session_state.etichette_lotto[idx_corrente]["barcode"] = val
                            st.session_state.etichette_lotto[idx_corrente]["manuale"] = True
                            st.session_state.show_scan = False
                            st.rerun()
                        st.button("CHIUDI SCANNER", on_click=lambda: st.session_state.update({"show_scan": False}))
                    
                    # Mostra quale barcode scansionare
                    st.markdown(f"#### 📷 Scansiona barcode per etichetta {idx_corrente + 1}")
                    col_scan1, col_scan2 = st.columns([3, 1])
                    with col_scan1:
                        if st.button("🔴 ATTIVA SCANNER BARCODE"):
                            st.session_state.show_scan = True
                            st.rerun()
                    with col_scan2:
                        # Passa all'etichetta successiva se ce ne sono altre
                        if len(barcode_mancanti) > 1:
                            next_idx = (st.session_state.get('idx_scan_corrente', 0) + 1) % len(barcode_mancanti)
                            if st.button("⏭️ SUCCESSIVA"):
                                st.session_state.idx_scan_corrente = next_idx
                                st.rerun()
                    
                    # Possibilità di inserire manualmente il barcode
                    col_manual1, col_manual2 = st.columns([3, 1])
                    barcode_manuale = col_manual1.text_input(f"Inserisci manualmente barcode etichetta {idx_corrente + 1}", key=f"manual_barcode_{idx_corrente}")
                    if col_manual2.button("✅ CONFERMA", key=f"confirm_barcode_{idx_corrente}"):
                        if barcode_manuale:
                            st.session_state.etichette_lotto[idx_corrente]["barcode"] = barcode_manuale
                            st.session_state.etichette_lotto[idx_corrente]["manuale"] = True
                            st.rerun()
                
                # Link per pulire e ricominciare
                if st.button("🗑️ NUOVO LOTTO (Pulisci tutto)"):
                    st.session_state.etichette_lotto = []
                    st.session_state.idx_scan_corrente = 0
                    st.rerun()
        
        else:
            # Se non ci sono file, pulisci le etichette caricate precedentemente
            if 'etichette_lotto' in st.session_state:
                st.session_state.etichette_lotto = []

    # SCANNER BARCODE LIVE (per uso singolo se necessario)
    if st.session_state.show_scan:
        val = qrcode_scanner(key='live_scan')
        if val:
            st.session_state.temp["barcode"] = val
            st.session_state.show_scan = False
            st.rerun()
        st.button("CHIUDI SCANNER", on_click=lambda: st.session_state.update({"show_scan": False}))

    # MODULO DATI COMUNI (solo se ci sono etichette caricate)
    if 'etichette_lotto' in st.session_state and st.session_state.etichette_lotto:
        st.markdown("---")
        st.markdown("### 📝 DATI COMUNI DEL LOTTO (saranno applicati a tutte le etichette)")
        st.info("💡 Compila questi dati una sola volta - verranno applicati a tutte le etichette caricate")
        
        # Pre-compila con i dati della prima etichetta (se disponibili)
        prima_etichetta = st.session_state.etichette_lotto[0]
        
        # 1. Fornitore
        ocr_forn = prima_etichetta.get("fornitore", "")
        forn_options = ["Seleziona..."] + sorted(FORNITORI_FISSI) + ["ALTRO (Scrittura Libera)"]
        idx_forn = 0
        if ocr_forn:
            for i, f in enumerate(forn_options):
                if ocr_forn.upper() in f.upper():
                    idx_forn = i
                    break

        scelta_forn = st.selectbox("🏭 PRODUTTORE/FORNITORE", options=forn_options, index=idx_forn, key="lotto_forn")
        
        if scelta_forn == "ALTRO (Scrittura Libera)":
            f_forn = st.text_input("Scrivi Produttore/Fornitore", value=ocr_forn, key="lotto_forn_alt")
        else:
            f_forn = scelta_forn if scelta_forn != "Seleziona..." else ""

        # 2. Descrizione
        desc_options = ["Seleziona..."]
        if f_forn and not df_db.empty:
            filtro_db = df_db[df_db["Produttore/Fornitore"].str.contains(f_forn, case=False, na=False)]
            desc_uniche = filtro_db["Descrizione"].dropna().unique().tolist()
            desc_options.extend(sorted(desc_uniche))
        desc_options.append("ALTRO (Scrittura Libera)")

        ocr_desc = prima_etichetta.get("desc", "")
        scelta_desc = st.selectbox("📝 DESCRIZIONE", options=desc_options, key="lotto_desc")

        if scelta_desc == "ALTRO (Scrittura Libera)":
            f_desc = st.text_input("Scrivi Descrizione", value=ocr_desc, key="lotto_desc_alt")
        else:
            f_desc = scelta_desc if scelta_desc != "Seleziona..." else ""

        # 3. Colore
        color_options = ["Seleziona..."]
        if f_forn and f_desc and not df_db.empty:
            filtro_colore = df_db[(df_db["Produttore/Fornitore"].str.contains(f_forn, case=False, na=False)) & 
                                  (df_db["Descrizione"] == f_desc)]
            col_unici = filtro_colore["Codice Colore"].dropna().unique().tolist()
            color_options.extend(sorted(col_unici))
        color_options.append("ALTRO (Scrittura Libera)")

        ocr_colore = prima_etichetta.get("colore", "")
        
        c1, c2 = st.columns(2)
        scelta_col = c1.selectbox("🎨 CODICE COLORE", options=color_options, key="lotto_col")
        if scelta_col == "ALTRO (Scrittura Libera)":
            f_col = c1.text_input("Scrivi Codice Colore", value=ocr_colore, key="lotto_col_alt")
        else:
            f_col = scelta_col if scelta_col != "Seleziona..." else ""

        # 4. Spessore, Peso, MQ
        f_spess = c2.number_input("📏 SPESSORE DICHIARATO", value=float(prima_etichetta.get("spessore", 0.0)), format="%.2f", key="lotto_spess")
        
        c3, c4 = st.columns(2)
        f_peso = c3.number_input("⚖️ PESO SINGOLO (KG)", value=int(prima_etichetta.get("peso", 0)), help="Peso per singola etichetta", key="lotto_peso")
        f_mq = c4.number_input("📐 MQ SINGOLI", value=float(prima_etichetta.get("mq", 0.0)), help="Metri quadri per singola etichetta", format="%.2f", key="lotto_mq")

        c5, c6 = st.columns(2)
        f_data = c5.date_input("📅 DATA ARRIVO", datetime.now(), key="lotto_data")
        f_linea = c6.selectbox("🏗️ LINEA", ["1", "2"], key="lotto_linea")

        f_term = st.selectbox("🏁 TERMINATO", [" ", "NO", "SI"], key="lotto_term")

        # Verifica che tutti i barcode siano presenti
        barcode_mancanti = [i+1 for i, et in enumerate(st.session_state.etichette_lotto) if not et["barcode"]]
        
        if barcode_mancanti:
            st.error(f"⚠️ Impossibile salvare: barcode mancanti per le etichette {barcode_mancanti}. Scansionare prima.")
        elif st.button(f"🚀 REGISTRA {len(st.session_state.etichette_lotto)} ETICHETTE"):
            # Crea una riga per ogni etichetta
            for et in st.session_state.etichette_lotto:
                st.session_state.archivio.append({
                    "Codice a barre": et["barcode"],
                    "Produttore/Fornitore": f_forn,
                    "Spessore dichiarato": f_spess,
                    "Arrivo": f_data.strftime("%d/%m/%Y"),
                    "Descrizione": f_desc,
                    "Codice Colore": f_col,
                    "Peso": f_peso,
                    "Metri Quadri": f_mq,
                    "Terminato": f_term,
                    "Linea": f_linea
                })
            
            # Pulisci le etichette caricate
            st.session_state.etichette_lotto = []
            st.session_state.idx_scan_corrente = 0
            
            st.success(f"✅ Salvate {len(st.session_state.archivio)} etichette nell'archivio!")
            st.rerun()
    
    elif 'etichette_lotto' not in st.session_state or not st.session_state.etichette_lotto:
        # MODULO DI CARICO SINGOLO (vecchia logica per compatibilità)
        st.markdown("### 📋 Carico Singolo (nessun lotto caricato)")
        
        # 1. Barcode
        c_b1, c_b2 = st.columns([3,1], vertical_alignment="bottom")
        f_barcode = c_b1.text_input("📦 CODICE A BARRE", value=st.session_state.temp.get("barcode", ""))
        with c_b2:
            if st.button("📷 SCAN"):
                st.session_state.show_scan = True
                st.rerun()

        # 2. Fornitore
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

        # 3. Descrizione
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

        # 4. Colore
        color_options = ["Seleziona..."]
        if f_forn and f_desc and not df_db.empty:
            filtro_colore = df_db[(df_db["Produttore/Fornitore"].str.contains(f_forn, case=False, na=False)) & 
                                  (df_db["Descrizione"] == f_desc)]
            col_unici = filtro_colore["Codice Colore"].dropna().unique().tolist()
            color_options.extend(sorted(col_unici))
        color_options.append("ALTRO (Scrittura Libera)")

        ocr_colore = st.session_state.temp.get("colore", "")
        
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
            st.session_state.temp = {}
            st.success("✅ Salvato con successo!")
            st.rerun()

with tab2:
    st.markdown("### 🔍 RICERCA E FILTRI")
    
    # Filtri di ricerca
    c1, c2, c3 = st.columns(3)
    
    with c1:
        filtro_forn = st.selectbox("🏭 Filtra Fornitore", ["Tutti"] + sorted(FORNITORI_FISSI))
    with c2:
        filtro_colore = st.selectbox("🎨 Filtra Colore", ["Tutti"])
    with c3:
        filtro_linea = st.selectbox("🏗️ Filtra Linea", ["Tutti", "1", "2"])
    
    # Campo ricerca libera
    cerca = st.text_input("🔎 Ricerca libera (barcode, descrizione...)", "")
    
    if st.session_state.archivio:
        df = pd.DataFrame(st.session_state.archivio)
        
        # Applica filtri
        df_filtrato = df.copy()
        
        if filtro_forn != "Tutti":
            df_filtrato = df_filtrato[df_filtrato["Produttore/Fornitore"].str.contains(filtro_forn, case=False, na=False)]
        
        if filtro_linea != "Tutti":
            df_filtrato = df_filtrato[df_filtrato["Linea"] == filtro_linea]
        
        if cerca:
            df_filtrato = df_filtrato[
                df_filtrato.apply(lambda row: row.astype(str).str.contains(cerca, case=False).any(), axis=1)
            ]
        
        # Aggiorna lista colori disponibili
        if "Codice Colore" in df.columns:
            colori_unici = ["Tutti"] + sorted(df["Codice Colore"].dropna().unique().tolist())
            with c2:
                filtro_colore = st.selectbox("🎨 Filtra Colore", colori_unici)
            if filtro_colore != "Tutti":
                df_filtrato = df_filtrato[df_filtrato["Codice Colore"] == filtro_colore]
        
        # Mostra statistiche
        st.markdown("#### 📊 Statistiche")
        c_stat1, c_stat2, c_stat3, c_stat4 = st.columns(4)
        with c_stat1:
            st.metric("📦 Totale Carichi", len(df_filtrato))
        with c_stat2:
            st.metric("⚖️ Peso Totale (KG)", f"{df_filtrato['Peso'].sum():,}" if "Peso" in df_filtrato else "0")
        with c_stat3:
            st.metric("📐 MQ Totali", f"{df_filtrato['Metri Quadri'].sum():.1f}" if "Metri Quadri" in df_filtrato else "0")
        with c_stat4:
            st.metric("🏭 Fornitori", df_filtrato["Produttore/Fornitore"].nunique() if "Produttore/Fornitore" in df_filtrato else 0)
        
        # Tabella dati filtrati
        st.dataframe(df_filtrato, use_container_width=True, hide_index=True)
        
        # Esportazione
        out = BytesIO()
        with pd.ExcelWriter(out, engine='xlsxwriter') as wr:
            df_filtrato.to_excel(wr, index=False)
        st.download_button("📥 SCARICA EXCEL FILTRATO", out.getvalue(), "archivio_carichi_filtrato.xlsx")
        
        # Azioni
        c_az1, c_az2 = st.columns(2)
        with c_az1:
            if st.button("🗑️ SVUOTA ARCHIVIO"):
                st.session_state.archivio = []
                st.rerun()
        with c_az2:
            if st.button("💾 SALVA SU SUPABASE"):
                try:
                    url = st.secrets["supabase"]["url"]
                    key = st.secrets["supabase"]["key"]
                    supabase: Client = create_client(url, key)
                    for item in st.session_state.archivio:
                        supabase.table("arrivi_merce").insert(item).execute()
                    st.success("✅ Salvato su Supabase!")
                except Exception as e:
                    st.error(f"Errore: {e}")
    else:
        st.info("📭 L'archivio è vuoto. Registra i carichi nella sezione 'Registra Carico'.")
