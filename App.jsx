import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Html5QrcodeScanner } from 'html5-qrcode';
import { createClient } from '@supabase/supabase-js';
import * as XLSX from 'xlsx';

// Configurazione DIRETTA Supabase
const supabaseUrl = 'https://vnzrewcbnoqbqvzckome.supabase.co';
const supabaseKey = 'sb_publishable_Sq9txbu-PmKdbxETSx2cjw_WqWEFBPO'; // Chiave aggiornata dall'utente
const supabase = createClient(supabaseUrl, supabaseKey);

const API_BASE = "https://tuo-backend-ocr.onrender.com/api"; // Solo per OCR

// Liste predefinite richieste dall'utente
const SPESSORI_LIST = [0.06, 0.08, 0.1, 0.2, 0.3, 0.38, 0.4, 0.45, 0.48, 0.5, 0.55, 0.58, 0.6, 0.65, 0.68, 0.7, 0.75, 0.78, 0.8, 1.0];
const LARGHEZZE_LIST = [1060, 1200, 1225, 1250, 2400];

// Funzione helper per comprimere e ridimensionare le immagini lato client
const compressImage = (file) => {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = (event) => {
      const img = new Image();
      img.src = event.target.result;
      img.onload = () => {
        const canvas = document.createElement('canvas');
        const MAX_SIZE = 1200; // Dimensione ottimale per OCR senza appesantire il caricamento
        let width = img.width;
        let height = img.height;

        if (width > height && width > MAX_SIZE) { height *= MAX_SIZE / width; width = MAX_SIZE; }
        else if (height > MAX_SIZE) { width *= MAX_SIZE / height; height = MAX_SIZE; }

        canvas.width = width;
        canvas.height = height;
        canvas.getContext('2d').drawImage(img, 0, 0, width, height);
        canvas.toBlob((blob) => {
          resolve(new File([blob], file.name, { type: 'image/jpeg' }));
        }, 'image/jpeg', 0.7); // 70% di qualità: riduce il peso del ~90% mantenendo i testi leggibili
      };
    };
  });
};

function App() {
  const [step, setStep] = useState(1);
  const [suppliers, setSuppliers] = useState([]);
  const [commonData, setCommonData] = useState({
    fornitore: '',
    descrizione: 'Acciaio Zincato',
    colore: 'RAL 9002',
    spessore: '',
    larghezza: '',
    data_arrivo: new Date().toISOString().split('T')[0],
    terminato: 'NO',
    linea: ''
  });
  const [colli, setColli] = useState([]);
  const [newSupplierName, setNewSupplierName] = useState('');
  const [isScanning, setIsScanning] = useState(null); // Indice del collo in scansione
  const [loading, setLoading] = useState(false);

  // Carica i fornitori dal database all'avvio
  const loadSuppliers = async () => {
    if (!supabase) return;
    try {
      // Query diretta a Supabase sulla tabella db_mp_arrivi
      const { data, error } = await supabase
        .from('db_mp_arrivi')
        .select('Produttore/Fornitore');
      
      if (error) throw error;

      const rawNames = data.map(item => item['Produttore/Fornitore']?.toString().trim().toUpperCase()).filter(Boolean);
      const uniqueNames = [...new Set(rawNames.filter(n => n))].sort();
      setSuppliers(uniqueNames);
    } catch (err) {
      console.error("Errore caricamento fornitori", err);
    }
  };

  useEffect(() => {
    loadSuppliers();
  }, []);

  // Step 1: Upload Foto
  const handleUpload = async (e) => {
    const files = Array.from(e.target.files);
    if (files.length === 0) return;
    setLoading(true);
    try {
      const promises = files.map(async (file) => {
        const compressed = await compressImage(file);
        const formData = new FormData();
        formData.append('file', compressed);
        return axios.post(`${API_BASE}/analyze`, formData);
      });
      const results = await Promise.all(promises);
      setColli(results.map(r => r.data));
      setStep(2);
    } catch (err) {
      alert("Errore durante l'elaborazione delle foto");
    } finally {
      setLoading(false);
    }
  };

  // Gestione Scanner Barcode
  useEffect(() => {
    if (isScanning !== null) {
      const scanner = new Html5QrcodeScanner("reader", { fps: 10, qrbox: 250 });
      scanner.render((text) => {
        const newColli = [...colli];
        newColli[isScanning].barcode = text;
        setColli(newColli);
        setIsScanning(null);
        scanner.clear();
      });
      return () => scanner.clear();
    }
  }, [isScanning]);

  // Gestione aggiunta nuovo fornitore
  const handleSaveNewSupplier = async () => {
    const nameToSave = newSupplierName.toUpperCase().trim();
    if (nameToSave) {
      try {
        // Inserimento diretto in Supabase
        const { error } = await supabase
          .from('db_mp_arrivi')
          .insert([{ 'Produttore/Fornitore': nameToSave }]);

        if (error) throw error;

        await loadSuppliers();
        setCommonData(prev => ({...prev, fornitore: nameToSave}));
        setNewSupplierName('');
      } catch (err) {
        console.error("Errore salvataggio:", err);
        alert("Errore nel salvataggio. Verifica i permessi della tabella.");
      }
    }
  };

  // Esporta in Excel direttamente dal Browser (senza backend)
  const exportExcel = () => {
    const rows = colli.map(c => ({
      'Codice a barre': c.barcode,
      'Produttore/Fornitore': commonData.fornitore,
      'Spessore dichiarato': commonData.spessore,
      'Arrivo': commonData.data_arrivo,
      'Descrizione': commonData.descrizione,
      'Codice Colore': commonData.colore,
      'Peso': c.peso,
      'Metri Quadri': c.mq,
      'Terminato': commonData.terminato,
      'Linea': commonData.linea,
      'Larghezza': commonData.larghezza,
      'Foto Originale': c.nome_foto
    }));

    const worksheet = XLSX.utils.json_to_sheet(rows);
    const workbook = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(workbook, worksheet, "Arrivi");
    XLSX.writeFile(workbook, `arrivi_${commonData.data_arrivo}.xlsx`);
  };

  return (
    <div className="p-4 max-w-xl mx-auto font-sans">
      <h1 className="text-2xl font-bold text-blue-800 mb-4">SB App Arrivi</h1>
      
      {/* STEP 1 */}
      {step === 1 && (
        <div className="bg-gray-100 p-6 rounded-lg border-2 border-dashed border-gray-300 text-center">
          {loading ? (
            <div className="py-4 text-blue-700 font-bold animate-pulse">🚀 Compressione ed elaborazione in corso...</div>
          ) : (
            <>
              <p className="mb-4">Carica le foto delle etichette per iniziare</p>
              <input type="file" multiple onChange={handleUpload} className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"/>
            </>
          )}
        </div>
      )}

      {/* STEP 2 */}
      {step === 2 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Parametri Comuni</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium mb-1">Fornitore</label>
              <div className="flex gap-2 mb-2">
                <select className="flex-1 p-2 border rounded" value={commonData.fornitore} onChange={e => setCommonData({...commonData, fornitore: e.target.value})}>
                  <option value="">Seleziona Fornitore...</option>
                  {suppliers.map(s => <option key={s} value={s}>{s}</option>)}
                  <option value="NEW_SUPPLIER">+ Aggiungi Nuovo Fornitore...</option>
                </select>
                <button 
                  type="button"
                  onClick={() => setCommonData({...commonData, fornitore: 'NEW_SUPPLIER'})}
                  className="bg-green-600 text-white px-4 rounded font-bold shadow-sm active:bg-green-700"
                  title="Aggiungi nuovo fornitore"
                >
                  +
                </button>
              </div>
              
              {commonData.fornitore === 'NEW_SUPPLIER' && (
                <div className="flex gap-2 p-3 bg-green-50 rounded border border-green-200 shadow-sm">
                  <input 
                    type="text" 
                    placeholder="Nome nuovo fornitore" 
                    className="flex-1 p-2 border rounded focus:ring-2 focus:ring-green-500 outline-none uppercase"
                    value={newSupplierName}
                    onChange={e => setNewSupplierName(e.target.value)}
                  />
                  <button 
                    onClick={(e) => { e.preventDefault(); handleSaveNewSupplier(); }}
                    className="bg-green-600 text-white px-4 rounded font-bold hover:bg-green-700 transition-colors"
                  >
                    Salva
                  </button>
                </div>
              )}
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium">Descrizione</label>
              <input type="text" className="w-full p-2 border rounded" value={commonData.descrizione} onChange={e => setCommonData({...commonData, descrizione: e.target.value})} />
            </div>
            <div>
              <label className="block text-sm font-medium">Data Arrivo</label>
              <input type="date" className="w-full p-2 border rounded" value={commonData.data_arrivo} onChange={e => setCommonData({...commonData, data_arrivo: e.target.value})} />
            </div>
            <div>
              <label className="block text-sm font-medium">Colore/RAL</label>
              <input type="text" className="w-full p-2 border rounded" value={commonData.colore} onChange={e => setCommonData({...commonData, colore: e.target.value})} />
            </div>
            <div>
              <label className="block text-sm font-medium">Spessore dichiarato (mm)</label>
              <select 
                className="w-full p-2 border rounded" 
                value={commonData.spessore} 
                onChange={e => setCommonData({...commonData, spessore: e.target.value})}
              >
                <option value="">Seleziona spessore...</option>
                {SPESSORI_LIST.map(s => (
                  <option key={s} value={s}>{s} mm</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium">Larghezza dichiarata (mm)</label>
              <select 
                className="w-full p-2 border rounded" 
                value={commonData.larghezza} 
                onChange={e => setCommonData({...commonData, larghezza: e.target.value})}
              >
                <option value="">Seleziona larghezza...</option>
                {LARGHEZZE_LIST.map(l => (
                  <option key={l} value={l}>{l} mm</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium">Terminato</label>
              <input type="text" className="w-full p-2 border rounded" value={commonData.terminato} onChange={e => setCommonData({...commonData, terminato: e.target.value})} />
            </div>
          </div>
          <button onClick={() => setStep(3)} className="w-full bg-blue-700 text-white py-3 rounded-lg font-bold">Avanti ➡️</button>
        </div>
      )}

      {/* STEP 3 */}
      {step === 3 && (
        <div className="space-y-6">
          <h2 className="text-xl font-semibold">Dettaglio Colli</h2>
          {colli.map((collo, index) => (
            <div key={index} className="p-4 border rounded-lg bg-white shadow-sm">
              <p className="text-xs text-gray-400 mb-2">{collo.nome_foto}</p>
              <div className="flex items-end gap-2 mb-3">
                <div className="flex-1">
                  <label className="block text-xs font-bold text-gray-600">CODICE LOTTO</label>
                  <input type="text" className="w-full p-2 border rounded bg-yellow-50" value={collo.barcode} onChange={e => {
                    const nc = [...colli]; nc[index].barcode = e.target.value; setColli(nc);
                  }} />
                </div>
                <button onClick={() => setIsScanning(index)} className="bg-blue-100 p-2 rounded border border-blue-300">📷 Scan</button>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-gray-600">PESO (KG)</label>
                  <input type="number" className="w-full p-2 border rounded" value={collo.peso} onChange={e => {
                    const nc = [...colli]; nc[index].peso = e.target.value; setColli(nc);
                  }} />
                </div>
                <div>
                  <label className="block text-xs font-bold text-gray-600">MQ</label>
                  <input type="number" step="0.01" className="w-full p-2 border rounded" value={collo.mq} onChange={e => {
                    const nc = [...colli]; nc[index].mq = e.target.value; setColli(nc);
                  }} />
                </div>
              </div>
            </div>
          ))}
          
          {isScanning !== null && (
            <div className="fixed inset-0 bg-black z-50 flex flex-col p-4">
              <div id="reader" className="bg-white rounded"></div>
              <button onClick={() => setIsScanning(null)} className="mt-4 text-white underline">Chiudi Scanner</button>
            </div>
          )}
          
          <button onClick={() => setStep(4)} className="w-full bg-blue-700 text-white py-3 rounded-lg font-bold">Riepilogo ➡️</button>
        </div>
      )}

      {/* STEP 4 */}
      {step === 4 && (
        <div className="text-center space-y-4">
          <div className="bg-green-100 p-6 rounded-lg">
            <h2 className="text-xl font-bold text-green-800">Pronto per l'Export!</h2>
            <p>Hai elaborato {colli.length} rotoli.</p>
          </div>
          <button onClick={exportExcel} className="w-full bg-green-600 text-white py-4 rounded-xl text-lg font-bold shadow-lg">📥 Scarica Excel per Database</button>
          <button onClick={() => setStep(3)} className="text-blue-700 underline">Torna indietro</button>
        </div>
      )}
    </div>
  );
}

export default App;