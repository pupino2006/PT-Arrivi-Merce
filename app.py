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

# --- 1. CONFIGURAZIONE PAGINA E PWA ---
st.set_page_config(
    page_title="SB App Arrivi", 
    layout="centered", 
    page_icon="ptsimbolo.png"
)

def add_pwa_headers():
    pwa_html = """
        <link rel="manifest" href="manifest.json">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    """
    st.markdown(pwa_html, unsafe_allow_html=True)

add_pwa_headers()

# --- 2. LOGICA DI SICUREZZA ---
def check_password():
    """Gestisce la creazione e la verifica della password."""
    if st.session_state.get("password_correct", False):
        return True

    # Se la password non è mai stata configurata (prima volta assoluta)
    if not os.path.exists(PASSWORD_FILE):
        st.title("🛡️ Configurazione Iniziale")
        st.info("Benvenuto! Crea una password master per proteggere l'accesso all'app.")
        new_pass = st.text_input("Crea Password Master", type="password")
        conf_pass = st.text_input("Conferma Password Master", type="password")
        
        if st.button("Salva e Configura"):
            if new_pass == conf_pass and len(new_pass) > 3:
                with open(PASSWORD_FILE, "w") as f:
                    f.write(new_pass)
                st.success("Password impostata! Ora effettua l'accesso.")
                st.rerun()
            else:
                st.error("Le password non coincidono o sono troppo brevi (min 4 caratteri).")
        return False

    # Login standard
    st.title("🔒 Accesso Riservato")
    st.caption("Contenuto protetto. Inserisci la password per sbloccare le funzioni.")
    
    # Anteprima oscurata
    dummy_df = pd.DataFrame({"ID Collo": ["****", "****"], "Stato": ["PROTETTO", "PROTETTO"]})
    st.table(dummy_df)
    
    input_pass = st.text_input("Password:", type="password")
    if st.button("Sblocca Sistema"):
        with open(PASSWORD_FILE, "r") as f:
            saved_pass = f.read().strip()
        
        if input_pass == saved_pass:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Password errata.")
    return False

# --- 3. LOGICA APPLICATIVA (Solo se autenticati) ---
if check_password():
    
    # --- CONFIGURAZIONE GOOGLE VISION (Locale o Cloud) ---
    if os.path.exists("chiave_google.json"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "chiave_google.json"
    elif "google_credentials" in st.secrets:
        # Gestione segreti per il deploy su Streamlit Cloud
        creds_dict = dict(st.secrets["google_credentials"])
        with open("temp_key.json", "w") as f:
            json.dump(creds_dict, f)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "temp_key.json"

    def analizza_con_google(image_bytes):
        try:
            client = vision.ImageAnnotatorClient()
            image = vision.Image(content=image_bytes)
            response = client.text_detection(image=image)
            return response.text_annotations[0].description if response.text_annotations else ""
        except Exception as e:
            return ""

    def estrai_dati_chirurgica(testo_ocr):
        """Estrae dati dall'OCR delle foto - CODICE, MQ e PESO"""
        if not testo_ocr:
            return {
                "barcode": "", "fornitore": "", "spessore": 0.0,
                "peso": 0, "larghezza": 0, "lunghezza": 0.0,
                "mq": 0.0, "codice": "", "data_etichetta": "",
                "codice_colore": "", "descrizione": ""
            }
        
        righe = [r.strip().upper() for r in testo_ocr.split('\n') if r.strip()]
        t_completo = " ".join(righe)
        dati = {
            "barcode": "", 
            "fornitore": "", 
            "spessore": 0.0,
            "peso": 0, 
            "larghezza": 0, 
            "lunghezza": 0.0,
            "mq": 0.0,
            "codice": "",
            "data_etichetta": "",
            "codice_colore": "", 
            "descrizione": ""
        }
        
        # Identificazione Fornitore
        for forn in ["LAMPRE", "MARCEGAGLIA", "ARCELOR", "NOVELIS"]:
            if forn in t_completo:
                dati["fornitore"] = "ARCELORMITTAL" if forn == "ARCELOR" else forn

        for i, riga in enumerate(righe):
            # Barcode
            if 'S' in riga:
                bc_match = re.search(r'S\s*(\d\s*){9,10}', riga)
                if bc_match: dati["barcode"] = re.sub(r'\s+', '', bc_match.group(0))
            
            # Codice articolo (cerco pattern comuni)
            if any(x in riga for x in ["COD", "CODE", "ART"]):
                cod_match = re.search(r'\b([A-Z]{2,4}\d{4,8}|\d{8})\b', riga)
                if cod_match: dati["codice"] = cod_match.group(0).replace(' ', '')
            
            # Colore
            if any(x in riga for x in ["COLOR", "COLOUR", "MP"]):
                col_match = re.search(r'\b(MP\d{3}|RAL\s*\d{4}|\d{4})\b', riga)
                if col_match: dati["codice_colore"] = col_match.group(0).replace(' ', '')
            
            # Spessore
            if any(x in riga for x in ["SPESS", "THICK", "THK"]):
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_spess = re.search(r'\b0[.,](\d{2,3})\b|\b0(\d{2})\b', cerca_in)
                if val_spess:
                    res = val_spess.group(0).replace(',', '.')
                    dati["spessore"] = float(res) if '.' in res else float(res)/100
            
            # Larghezza
            if any(x in riga for x in ["LARGH", "WIDTH", "WID"]):
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_largh = re.search(r'\b(1000|1200|1219|1225|1250|1500)\b', cerca_in)
                if val_largh: dati["larghezza"] = int(val_largh.group(1))
            
            # Lunghezza
            if any(x in riga for x in ["LUNGH", "LENGTH", "M."]):
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_lungh = re.search(r'(\d+[,.]\d{1,2})', cerca_in)
                if val_lungh: dati["lunghezza"] = float(val_lungh.group(1).replace(',', '.'))
            
            # Peso (KG)
            if "NET" in riga or "KG" in riga:
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_peso = re.findall(r'\b\d{4}\b', cerca_in)
                for p in val_peso:
                    if 500 < int(p) < 8000 and int(p) != dati["larghezza"]: 
                        dati["peso"] = int(p)
            
            # MQ (metri quadrati)
            if "MQ" in riga or "M2" in riga or "M²" in riga:
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_mq = re.search(r'(\d+[.,]\d{1,3})', cerca_in)
                if val_mq: 
                    dati["mq"] = float(val_mq.group(1).replace(',', '.'))
            
            # Data
            if any(x in riga for x in ["DATA", "DATE"]):
                cerca_in = riga + " " + (righe[i+1] if i+1 < len(righe) else "")
                val_data = re.search(r'(\d{2}/\d{2}/\d{2,4})', cerca_in)
                if val_data: dati["data_etichetta"] = val_data.group(1)
        
        # Calcola MQ se non trovato direttamente ma abbiamo larghezza e lunghezza
        if dati["mq"] == 0.0 and dati["larghezza"] > 0 and dati["lunghezza"] > 0:
            dati["mq"] = (dati["larghezza"] / 1000) * dati["lunghezza"]
        
        return dati

    # --- UI ESTETICA ---
    st.markdown("""
        <style>
        .stButton>button { width: 100%; border-radius: 12px; height: 3.5em; background-color: #004a99; color: white; font-weight: bold; }
        .stDownloadButton>button { background-color: #28a745 !important; border-radius: 12px; }
        .success-box { background-color: #d4edda; padding: 15px; border-radius: 8px; border-left: 4px solid #28a745; }
        .warning-box { background-color: #fff3cd; padding: 15px; border-radius: 8px; border-left: 4px solid #ffc107; }
        </style>
        """, unsafe_allow_html=True)

    try:
        logo = Image.open("ptsimbolo.png")
        st.image(logo, width=100)
    except:
        st.title("🏗️ SB Supporti")
    
    st.subheader("Carico Arrivi Intelligente")

    # Inizializza stati sessione
    if 'foto_caricate' not in st.session_state:
        st.session_state.foto_caricate = []
    if 'dati_analizzati' not in st.session_state:
        st.session_state.dati_analizzati = []
    if 'session_data' not in st.session_state:
        st.session_state.session_data = []

    # ===== SEZIONE 1: CARICAMENTO FOTO =====
    st.divider()
    st.markdown("### 📸 Carica le Foto delle Etichette")
    st.caption("Carica una o più foto per analizzarle automaticamente. Puoi anche inserire i dati manualmente.")
    
    # Caricamento file dalla galleria (NO camera per compatibilità cloud)
    uploaded_files = st.file_uploader("📁 Seleziona foto dalla galleria", 
                                       type=['jpg', 'jpeg', 'png'], 
                                       accept_multiple_files=True,
                                       label_visibility="collapsed")

    # Aggiungi foto dalla galleria
    if uploaded_files:
        with st.spinner("🔄 Analisi in corso..."):
            for f in uploaded_files:
                # Evita duplicati
                if not any(pf['nome'] == f.name for pf in st.session_state.foto_caricate):
                    bytes_data = f.getvalue()
                    testo_ocr = analizza_con_google(bytes_data)
                    dati = estrai_dati_chirurgica(testo_ocr)
                    dati['testo_ocr'] = testo_ocr
                    dati['nome_foto'] = f.name
                    
                    st.session_state.foto_caricate.append({
                        'file': f,
                        'bytes': bytes_data,
                        'nome': f.name
                    })
                    st.session_state.dati_analizzati.append(dati)
        
        if uploaded_files:
            st.success(f"✅ {len(uploaded_files)} foto analizzata/e!")
        st.rerun()

    # Mostra foto caricate
    if st.session_state.foto_caricate:
        st.markdown("#### 📷 Foto Caricate:")
        
        # Crea griglia per visualizzare le foto
        cols = st.columns(min(4, len(st.session_state.foto_caricate)))
        for idx, (foto, dati) in enumerate(zip(st.session_state.foto_caricate, st.session_state.dati_analizzati)):
            with cols[idx % 4]:
                st.image(foto['bytes'], caption=foto['nome'], width=150)
                
                # Mostra preview dati trovati
                with st.expander("📋 Dati trovati"):
                    if dati.get('codice'):
                        st.write(f"**Codice:** {dati['codice']}")
                    else:
                        st.write("**Codice:** Non trovato")
                    if dati.get('peso'):
                        st.write(f"**Peso:** {dati['peso']} kg")
                    else:
                        st.write("**Peso:** Non trovato")
                    if dati.get('mq'):
                        st.write(f"**MQ:** {dati['mq']:.2f}")
                    else:
                        st.write("**MQ:** Non trovato")
                    if dati.get('barcode'):
                        st.write(f"**Barcode:** {dati['barcode']}")
        
        # Pulsante per rimuovere tutte
        if st.button("🗑️ Rimuovi Tutte le Foto"):
            st.session_state.foto_caricate = []
            st.session_state.dati_analizzati = []
            st.rerun()

    # ===== SEZIONE 2: DATI COMUNI =====
    st.divider()
    st.markdown("### 📝 Dati Comuni a Tutti i Colli")
    
    col1, col2 = st.columns(2)
    with col1:
        fornitore = st.selectbox("🏭 Fornitore:", 
                                 ["", "LAMPRE", "MARCEGAGLIA", "ARCELORMITTAL", "NOVELIS", "ALTRO", "Sconosciuto"])
    
    with col2:
        data_arrivo = st.text_input("📅 Data Arrivo:", value=datetime.now().strftime("%d/%m/%Y"))
    
    descrizione = st.text_area("📝 Note / Descrizione:", value="")

    # ===== SEZIONE 3: DATI PER OGNI COLLO =====
    st.divider()
    st.markdown("### 📋 Dati per ogni Collo")
    st.caption("Compila i dati per ogni collo. I campi sono precompilati se trovati nelle foto.")
    
    num_colli = st.number_input("Numero di colli:", min_value=1, max_value=100, value=max(1, len(st.session_state.foto_caricate)), step=1)
    
    # Assicura che ci siano abbastanza dati
    while len(st.session_state.dati_analizzati) < num_colli:
        st.session_state.dati_analizzati.append({
            "barcode": "", "fornitore": "", "spessore": 0.0,
            "peso": 0, "larghezza": 0, "lunghezza": 0.0,
            "mq": 0.0, "codice": "", "data_etichetta": "",
            "codice_colore": "", "descrizione": "", "nome_foto": ""
        })
    
    # Mostra i campi per ogni collo
    for idx in range(num_colli):
        dati = st.session_state.dati_analizzati[idx]
        nome_foto = dati.get('nome_foto', '') if idx < len(st.session_state.foto_caricate) else ''
        
        with st.expander(f"📦 Collo {idx + 1}" + (f" - {nome_foto}" if nome_foto else "")):
            col_a, col_b = st.columns(2)
            
            with col_a:
                # Codice - proponi quello trovato dall'OCR se disponibile
                codice = st.text_input(
                    "🏷️ Codice Articolo:", 
                    value=dati.get('codice', ''),
                    key=f"codice_{idx}"
                )
                
                # MQ - proponi quello calcolato/trovato
                mq_default = dati.get('mq', 0.0) if dati.get('mq', 0) > 0 else 0.0
                mq = st.number_input(
                    "📐 Metri Quadrati (MQ):", 
                    min_value=0.0, 
                    value=mq_default if mq_default > 0 else 0.0,
                    step=0.5, format="%.2f",
                    key=f"mq_{idx}"
                )
            
            with col_b:
                # Peso - proponi quello trovato
                peso_default = dati.get('peso', 0) if dati.get('peso', 0) > 0 else 0
                peso = st.number_input(
                    "⚖️ Peso (KG):", 
                    min_value=0, 
                    value=peso_default if peso_default > 0 else 0,
                    step=10,
                    key=f"peso_{idx}"
                )
                
                # Barcode
                barcode = st.text_input(
                    "📊 Barcode:", 
                    value=dati.get('barcode', ''),
                    key=f"barcode_{idx}"
                )
            
            # Dettagli espandibili
            with st.expander("🔍 Dettagli Aggiuntivi"):
                col_c, col_d = st.columns(2)
                with col_c:
                    spessore = st.number_input(
                        "📏 Spessore (mm):", 
                        min_value=0.0, 
                        value=float(dati.get('spessore', 0)) if dati.get('spessore', 0) > 0 else 0.0,
                        step=0.1, format="%.2f",
                        key=f"spessore_{idx}"
                    )
                    larghezza = st.number_input(
                        "↔️ Larghezza (mm):", 
                        min_value=0, 
                        value=dati.get('larghezza', 0) if dati.get('larghezza', 0) > 0 else 1000,
                        step=50,
                        key=f"larghezza_{idx}"
                    )
                
                with col_d:
                    lunghezza = st.number_input(
                        "↕️ Lunghezza (m):", 
                        min_value=0.0, 
                        value=float(dati.get('lunghezza', 0)) if dati.get('lunghezza', 0) > 0 else 0.0,
                        step=0.5, format="%.2f",
                        key=f"lunghezza_{idx}"
                    )
                    colore = st.text_input(
                        "🎨 Codice Colore:", 
                        value=dati.get('codice_colore', ''),
                        key=f"colore_{idx}"
                    )
            
            # Salva i dati nella sessione
            st.session_state.dati_analizzati[idx].update({
                'codice': codice,
                'mq': mq,
                'peso': peso,
                'barcode': barcode,
                'spessore': spessore,
                'larghezza': larghezza,
                'lunghezza': lunghezza,
                'codice_colore': colore
            })

    # ===== SEZIONE 4: SALVA =====
    st.divider()
    
    if st.button("✅ Salva e Esporta in Excel", type="primary", use_container_width=True):
        # Costruisci il DataFrame con tutti i dati
        rows = []
        for idx, dati in enumerate(st.session_state.dati_analizzati[:num_colli]):
            foto_nome = st.session_state.foto_caricate[idx]['nome'] if idx < len(st.session_state.foto_caricate) else ''
            row = {
                'Foto': foto_nome,
                'Codice': dati.get('codice', ''),
                'MQ': dati.get('mq', 0),
                'Peso (KG)': dati.get('peso', 0),
                'Fornitore': fornitore,
                'Data Arrivo': data_arrivo,
                'Barcode': dati.get('barcode', ''),
                'Spessore': dati.get('spessore', 0),
                'Larghezza': dati.get('larghezza', 0),
                'Lunghezza': dati.get('lunghezza', 0),
                'Colore': dati.get('codice_colore', ''),
                'Note': descrizione
            }
            rows.append(row)
        
        df = pd.DataFrame(rows)
        
        # Mostra riepilogo
        st.markdown("### ✅ Riepilogo Dati")
        st.dataframe(df, use_container_width=True)
        
        # Calcola totali
        totale_mq = sum(r.get('MQ', 0) for r in rows)
        totale_peso = sum(r.get('Peso (KG)', 0) for r in rows)
        
        st.markdown(f"""
        <div class="success-box">
        <strong>📊 Totali:</strong><br>
        • Colli: {len(rows)}<br>
        • MQ Totali: {totale_mq:.2f}<br>
        • Peso Totale: {totale_peso} kg
        </div>
        """, unsafe_allow_html=True)
        
        # Esporta in Excel
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Arrivi', index=False)
        
        output.seek(0)
        
        st.download_button(
            "📥 Scarica Excel",
            output.getvalue(),
            file_name=f"arrivi_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
        if st.button("🔄 Nuovo Carico"):
            st.session_state.foto_caricate = []
            st.session_state.dati_analizzati = []
            st.rerun()
