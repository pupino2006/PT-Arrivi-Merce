import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Html5QrcodeScanner } from 'html5-qrcode';
import { createClient } from '@supabase/supabase-js';
import * as XLSX from 'xlsx';
import { QRCodeSVG } from 'qrcode.react';

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
  const [thicknesses, setThicknesses] = useState([...SPESSORI_LIST]);
  const [widths, setWidths] = useState([...LARGHEZZE_LIST]);
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
  const [showLabel, setShowLabel] = useState(null); // Indice del collo per etichetta
  const [showMiniLabel, setShowMiniLabel] = useState({}); // Stato per miniatura etichette
  const [applyCommonLabelToAll, setApplyCommonLabelToAll] = useState(true);
  const [activeCollo, setActiveCollo] = useState(0);

  // Carica i fornitori dal database all'avvio
  const loadSuppliers = async () => {
    if (!supabase) return;
    console.log("Inizio caricamento dati da Supabase...");
    try {
      let allData = [];
      let page = 0;
      const pageSize = 1000;
      let hasMore = true;

      // Ciclo per recuperare TUTTE le righe (oltre il limite di 1000)
      while (hasMore) {
        const { data, error } = await supabase
          .from('db_mp_arrivi')
          .select('Produttore/Fornitore, "Spessore dichiarato", Larghezza')
          .range(page * pageSize, (page + 1) * pageSize - 1);

        if (error) throw error;
        if (!data || data.length === 0) {
          hasMore = false;
        } else {
          allData = [...allData, ...data];
          hasMore = data.length === pageSize;
          page++;
        }
      }

      console.log(`Dati caricati: ${allData.length} righe.`);

      // Funzione di pulizia stringhe migliorata
      const cleanStr = (s) => s?.toString()
        .trim()
        .replace(/\s\s+/g, ' ') // Sostituisce spazi multipli con uno solo
        .toUpperCase();

      // 1. Scrematura Fornitori (Senza duplicati "sporchi")
      const rawSuppliers = allData
        .map(item => cleanStr(item['Produttore/Fornitore']))
        .filter(s => s && s.length > 1 && !/^[\d.,]+$/.test(s)); // Filtra nomi troppo corti o solo numerici
      
      const finalSuppliers = [...new Set(rawSuppliers)].sort();
      setSuppliers(finalSuppliers);

      // 2. Scrematura Spessori (Numerici e Univoci)
      const fromDbSpessori = allData
        .map(item => parseFloat(item['Spessore dichiarato']?.toString().replace(',', '.')))
        .filter(n => !isNaN(n) && n > 0);
      
      const combinedSpessori = [...new Set([...SPESSORI_LIST, ...fromDbSpessori])].sort((a, b) => a - b);
      setThicknesses(combinedSpessori);

      // 3. Scrematura Larghezze (Numerici e Univoci)
      const fromDbLarghezze = allData
        .map(item => parseInt(item['Larghezza']))
        .filter(n => !isNaN(n) && n > 0);

      const combinedLarghezze = [...new Set([...LARGHEZZE_LIST, ...fromDbLarghezze])].sort((a, b) => a - b);
      setWidths(combinedLarghezze);

      console.log("Liste aggiornate correttamente.");

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
      setColli(results.map(r => ({
        ...r.data,
        lunghezza: r.data.lunghezza ?? '',
        completed: false,
        descrizione: r.data.descrizione ?? commonData.descrizione,
        colore: r.data.colore ?? commonData.colore,
      })));
      setStep(2);
    } catch (err) {
      alert("Errore durante l'elaborazione delle foto");
    } finally {
      setLoading(false);
    }
  };

  const markColloCompleted = (index) => {
    setColli(prev => {
      const next = prev.map((collo, i) => i === index ? { ...collo, completed: true } : collo);
      const nextIndex = next.findIndex((collo, i) => i > index && !collo.completed);
      const remaining = next.findIndex(collo => !collo.completed);
      if (nextIndex !== -1) setActiveCollo(nextIndex);
      else if (remaining !== -1) setActiveCollo(remaining);
      return next;
    });
  };

  useEffect(() => {
    if (step === 3 && colli.length > 0) {
      const nextActive = colli.findIndex(c => !c.completed);
      setActiveCollo(nextActive !== -1 ? nextActive : 0);
    }
  }, [step, colli]);

  useEffect(() => {
    if (step === 3 && colli.length > 0) {
      const element = document.getElementById(`collo-card-${activeCollo}`);
      element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [activeCollo, step, colli.length]);

  const getLabelDescription = (collo) => applyCommonLabelToAll ? commonData.descrizione : (collo?.descrizione || commonData.descrizione);
  const getLabelColor = (collo) => applyCommonLabelToAll ? commonData.colore : (collo?.colore || commonData.colore);
  const applyAllLabels = () => {
    setColli(prev => prev.map(collo => ({
      ...collo,
      descrizione: commonData.descrizione,
      colore: commonData.colore,
    })));
    setApplyCommonLabelToAll(true);
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
      'Descrizione': getLabelDescription(c),
      'Codice Colore': getLabelColor(c),
      'Peso': c.peso,
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

  // Stampa etichette con Zebra
  const printZebra = async () => {
    const zebraIp = '192.168.68.162';
    
    try {
      // Genera comandi ZPL per ogni collo
      for (const collo of colli) {
        const labelDescrizione = getLabelDescription(collo);
        const labelColore = getLabelColor(collo);
        const zplCommand = `
^XA
^FO50,50^A0N,50,50^FD${labelDescrizione || 'ACCIAIO ZINCATO'}^FS
^FO50,100^A0N,30,30^FD${labelColore || 'RAL 9002'}^FS
^FO50,150^A0N,80,80^FD${collo.barcode || 'N/A'}^FS
^FO50,250^A0N,40,40^FD${commonData.spessore ? parseFloat(commonData.spessore).toFixed(2) : '0.00'} x ${commonData.larghezza || '0'}^FS
^FO50,300^A0N,40,40^FDKG ${collo.peso || '0'}^FS
^FO50,350^BQN,2,8^FDQA,${JSON.stringify({lotto: collo.barcode, fornitore: commonData.fornitore, descrizione: labelDescrizione, colore: labelColore, spessore: commonData.spessore, larghezza: commonData.larghezza, peso: collo.peso, data: commonData.data_arrivo})}^FS
^XZ
        `;
        
        // Invia comando Zebra tramite fetch
        await fetch(`http://${zebraIp}/pstprnt`, {
          method: 'POST',
          headers: {
            'Content-Type': 'text/plain',
          },
          body: zplCommand
        });
      }
      
      alert('Etichette inviate alla stampante Zebra!');
    } catch (error) {
      console.error('Errore stampa Zebra:', error);
      alert('Errore durante la stampa. Verifica che la stampante Zebra sia accessibile all\'indirizzo ' + zebraIp);
    }
  };

  const printZebraActive = async () => {
    const zebraIp = '192.168.68.162';
    const collo = colli[activeCollo];
    if (!collo) {
      alert('Nessun rotolo attivo selezionato per la stampa Zebra.');
      return;
    }

    try {
      const labelDescrizione = getLabelDescription(collo);
      const labelColore = getLabelColor(collo);
      const zplCommand = `
^XA
^FO50,50^A0N,50,50^FD${labelDescrizione || 'ACCIAIO ZINCATO'}^FS
^FO50,100^A0N,30,30^FD${labelColore || 'RAL 9002'}^FS
^FO50,150^A0N,80,80^FD${collo.barcode || 'N/A'}^FS
^FO50,250^A0N,40,40^FD${commonData.spessore ? parseFloat(commonData.spessore).toFixed(2) : '0.00'} x ${commonData.larghezza || '0'}^FS
^FO50,300^A0N,40,40^FDKG ${collo.peso || '0'}^FS
^FO50,350^BQN,2,8^FDQA,${JSON.stringify({lotto: collo.barcode, fornitore: commonData.fornitore, descrizione: labelDescrizione, colore: labelColore, spessore: commonData.spessore, larghezza: commonData.larghezza, peso: collo.peso, data: commonData.data_arrivo})}^FS
^XZ
        `;

      await fetch(`http://${zebraIp}/pstprnt`, {
        method: 'POST',
        headers: {
          'Content-Type': 'text/plain',
        },
        body: zplCommand
      });

      alert('Etichetta del rotolo attivo inviata alla stampante Zebra!');
    } catch (error) {
      console.error('Errore stampa Zebra attiva:', error);
      alert('Errore durante la stampa del rotolo attivo. Verifica la stampante Zebra.');
    }
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
              <div className="mt-4">
                <button 
                  onClick={() => {
                    setColli([{ barcode: '', peso: '', mq: '', lunghezza: '', completed: false, descrizione: commonData.descrizione, colore: commonData.colore, nome_foto: 'Inserimento manuale' }]);
                    setStep(2);
                  }}
                  className="w-full bg-green-600 text-white py-2 rounded-lg font-bold hover:bg-green-700"
                >
                  ➕ Inserisci Manualmente
                </button>
              </div>
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
                {thicknesses.map(s => (
                  <option key={s} value={s}>{typeof s === 'number' ? s.toFixed(2) : s} mm</option>
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
                {widths.map(l => (
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
          <div className="flex flex-col gap-2 bg-blue-50 p-3 rounded border border-blue-200">
            <label className="inline-flex items-center gap-2 text-sm font-medium">
              <input
                type="checkbox"
                checked={applyCommonLabelToAll}
                onChange={e => setApplyCommonLabelToAll(e.target.checked)}
                className="h-4 w-4 text-blue-600 border-gray-300 rounded"
              />
              Applica descrizione e codice colore a tutte le etichette
            </label>
            <div className="text-xs text-gray-600">Rotolo attivo: {activeCollo + 1}/{colli.length}</div>
          </div>
          {colli.map((collo, index) => (
            <div
              key={index}
              id={`collo-card-${index}`}
              className={`p-4 border rounded-lg bg-white shadow-sm ${activeCollo === index ? 'border-blue-500 ring-1 ring-blue-200' : ''} ${collo.completed ? 'bg-green-50 opacity-90' : ''}`}
            >
              <p className="text-xs text-gray-400 mb-2">{collo.nome_foto}</p>
              {collo.completed && (
                <div className="mb-3 rounded-md bg-green-100 border border-green-200 p-2 text-sm text-green-800">✅ Rotolo completato</div>
              )}
              <div className="flex items-end gap-2 mb-3">
                <div className="flex-1">
                  <label className="block text-xs font-bold text-gray-600">CODICE LOTTO</label>
                  <input type="text" className="w-full p-2 border rounded bg-yellow-50" value={collo.barcode} onChange={e => {
                    const nc = [...colli]; nc[index].barcode = e.target.value; setColli(nc);
                  }} />
                </div>
                <button onClick={() => setIsScanning(index)} className="bg-blue-100 p-2 rounded border border-blue-300">📷 Scan</button>
              </div>
              {!applyCommonLabelToAll && (
                <div className="grid grid-cols-2 gap-4 mb-3">
                  <div>
                    <label className="block text-xs font-bold text-gray-600">Descrizione etichetta</label>
                    <input type="text" className="w-full p-2 border rounded" value={collo.descrizione} onChange={e => {
                      const nc = [...colli]; nc[index].descrizione = e.target.value; setColli(nc);
                    }} />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-gray-600">Codice colore etichetta</label>
                    <input type="text" className="w-full p-2 border rounded" value={collo.colore} onChange={e => {
                      const nc = [...colli]; nc[index].colore = e.target.value; setColli(nc);
                    }} />
                  </div>
                </div>
              )}
              <div className="grid grid-cols-1 gap-4">
                <div>
                  <label className="block text-xs font-bold text-gray-600">PESO (KG)</label>
                  <input type="number" className="w-full p-2 border rounded" value={collo.peso} onChange={e => {
                    const nc = [...colli]; nc[index].peso = e.target.value; setColli(nc);
                  }} />
                </div>
              </div>
              <div className="flex gap-2 mt-3">
                <button onClick={() => setShowLabel(index)} className="flex-1 bg-green-600 text-white py-2 rounded font-bold hover:bg-green-700">🏷️ Genera Etichetta</button>
                <button 
                  onClick={() => setShowMiniLabel(prev => ({...prev, [index]: !prev[index]}))}
                  className="flex-1 bg-purple-600 text-white py-2 rounded font-bold hover:bg-purple-700"
                >
                  {showMiniLabel[index] ? '✖️ Chiudi Miniatura' : '👁️ Mostra Miniatura'}
                </button>
                <button
                  onClick={() => markColloCompleted(index)}
                  className="flex-1 bg-emerald-600 text-white py-2 rounded font-bold hover:bg-emerald-700"
                >
                  ✅ Completa rotolo
                </button>
              </div>
              
              {showMiniLabel[index] && (
                <div className="mt-3 p-3 bg-gray-50 rounded border border-gray-200">
                  <div 
                    style={{
                      width: '100%',
                      height: '120px',
                      padding: '8px',
                      backgroundColor: 'white',
                      border: '1px solid #ddd',
                      fontFamily: 'Arial, sans-serif',
                      fontSize: '8pt',
                      position: 'relative',
                      overflow: 'hidden'
                    }}
                  >
                    {/* Logo e descrizione in alto */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <div>
                        <img src="ptsimbolo.png" alt="Logo" style={{ height: '12px' }} />
                      </div>
                      <div style={{ textAlign: 'right', fontSize: '7pt' }}>
                        <div style={{ fontWeight: 'bold' }}>{getLabelDescription(collo) || 'ACCIAIO ZINCATO'}</div>
                        <div>{getLabelColor(collo) || 'RAL 9002'}</div>
                      </div>
                    </div>
                    
                    {/* Codice lotto al centro */}
                    <div style={{ textAlign: 'center', marginBottom: '3px' }}>
                      <div style={{ fontSize: '10pt', fontWeight: 'bold', letterSpacing: '1px' }}>
                        {collo.barcode || 'N/A'}
                      </div>
                    </div>
                    
                    {/* Spessore x Larghezza */}
                    <div style={{ textAlign: 'center', marginBottom: '3px' }}>
                      <div style={{ fontSize: '8pt' }}>
                        {commonData.spessore ? parseFloat(commonData.spessore).toFixed(2) : '0.00'} x {commonData.larghezza || '0'}
                      </div>
                    </div>
                    
                    {/* Peso */}
                    <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '4px' }}>
                      <div style={{ fontSize: '8pt', fontWeight: 'bold' }}>
                        KG {collo.peso || '0'}
                      </div>
                    </div>
                    
                    {/* QR Code miniatura */}
                    <div style={{ position: 'absolute', bottom: '4px', right: '4px' }}>
                      <QRCodeSVG 
                        value={JSON.stringify({
                          lotto: collo.barcode || '',
                          fornitore: commonData.fornitore || '',
                          descrizione: getLabelDescription(collo) || '',
                          colore: getLabelColor(collo) || '',
                          spessore: commonData.spessore || '',
                          larghezza: commonData.larghezza || '',
                          peso: collo.peso || '',
                          data: commonData.data_arrivo || ''
                        })}
                        size={30}
                        level="H"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))}
          
          <div className="flex gap-2">
            <button 
              onClick={() => {
                setColli([...colli, { barcode: '', peso: '', mq: '', lunghezza: '', completed: false, descrizione: commonData.descrizione, colore: commonData.colore, nome_foto: 'Inserimento manuale' }]);
              }}
              className="flex-1 bg-green-600 text-white py-3 rounded-lg font-bold hover:bg-green-700"
            >
              ➕ Aggiungi Nuovo Rotolo
            </button>
          </div>
          
          {isScanning !== null && (
            <div className="fixed inset-0 bg-black z-50 flex flex-col p-4">
              <div id="reader" className="bg-white rounded"></div>
              <button onClick={() => setIsScanning(null)} className="mt-4 text-white underline">Chiudi Scanner</button>
            </div>
          )}
          
          {showLabel !== null && (
            <div className="fixed inset-0 bg-black z-50 flex flex-col items-center justify-center p-4">
              <div className="bg-white p-4 rounded-lg shadow-xl max-w-full overflow-auto">
                <div 
                  id="label-print"
                  style={{
                    width: '230mm',
                    height: '160mm',
                    padding: '10mm',
                    backgroundColor: 'white',
                    border: '1px solid #ccc',
                    fontFamily: 'Arial, sans-serif',
                    position: 'relative'
                  }}
                >
                  {/* Logo e descrizione in alto */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10mm' }}>
                    <div>
                      <img src="ptsimbolo.png" alt="Logo" style={{ height: '15mm' }} />
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontSize: '14pt', fontWeight: 'bold' }}>{getLabelDescription(colli[showLabel]) || 'ACCIAIO ZINCATO'}</div>
                      <div style={{ fontSize: '12pt' }}>{getLabelColor(colli[showLabel]) || 'RAL 9002'}</div>
                    </div>
                  </div>
                  
                  {/* Codice lotto al centro */}
                  <div style={{ textAlign: 'center', marginBottom: '8mm' }}>
                    <div style={{ fontSize: '24pt', fontWeight: 'bold', letterSpacing: '2px' }}>
                      {colli[showLabel]?.barcode || 'N/A'}
                    </div>
                  </div>
                  
                  {/* Spessore x Larghezza */}
                  <div style={{ textAlign: 'center', marginBottom: '8mm' }}>
                    <div style={{ fontSize: '18pt' }}>
                      {commonData.spessore ? parseFloat(commonData.spessore).toFixed(2) : '0.00'} x {commonData.larghezza || '0'}
                    </div>
                  </div>
                  
                  {/* Peso */}
                  <div style={{ display: 'flex', justifyContent: 'center', marginBottom: '10mm' }}>
                    <div style={{ fontSize: '16pt', fontWeight: 'bold' }}>
                      KG {colli[showLabel]?.peso || '0'}
                    </div>
                  </div>
                  
                  {/* QR Code */}
                  <div style={{ position: 'absolute', bottom: '10mm', right: '10mm' }}>
                    <QRCodeSVG 
                      value={JSON.stringify({
                        lotto: colli[showLabel]?.barcode || '',
                        fornitore: commonData.fornitore || '',
                        descrizione: getLabelDescription(colli[showLabel]) || '',
                        colore: getLabelColor(colli[showLabel]) || '',
                        spessore: commonData.spessore || '',
                        larghezza: commonData.larghezza || '',
                        peso: colli[showLabel]?.peso || '',
                        data: commonData.data_arrivo || ''
                      })}
                      size={80}
                      level="H"
                    />
                  </div>
                </div>
                
                <div className="flex gap-2 mt-4">
                  <button 
                    onClick={() => {
                      const printContent = document.getElementById('label-print');
                      const WinPrint = window.open('', '', 'width=900,height=650');
                      WinPrint.document.write('<html><head><title>Etichetta</title></head><body>');
                      WinPrint.document.write(printContent.outerHTML);
                      WinPrint.document.write('</body></html>');
                      WinPrint.document.close();
                      WinPrint.focus();
                      WinPrint.print();
                      WinPrint.close();
                    }}
                    className="flex-1 bg-blue-600 text-white py-2 rounded font-bold hover:bg-blue-700"
                  >
                    🖨️ Stampa
                  </button>
                  <button 
                    onClick={() => setShowLabel(null)}
                    className="flex-1 bg-gray-500 text-white py-2 rounded font-bold hover:bg-gray-600"
                  >
                    ✖️ Chiudi
                  </button>
                </div>
              </div>
            </div>
          )}
          
          <div className="flex flex-col gap-3">
            <button onClick={applyAllLabels} className="w-full bg-slate-700 text-white py-3 rounded-lg font-bold">📋 Applica descrizione e codice colore a tutti i rotoli</button>
            <button onClick={printZebra} className="w-full bg-orange-600 text-white py-3 rounded-lg font-bold">🖨️ Stampa direttamente su Zebra ZT230</button>
            <button onClick={printZebraActive} className="w-full bg-amber-600 text-white py-3 rounded-lg font-bold">🖨️ Stampa solo il rotolo attivo su Zebra ZT230</button>
          </div>
          <button onClick={() => setStep(4)} className="w-full bg-blue-700 text-white py-3 rounded-lg font-bold">Riepilogo ➡️</button>
          <p className="text-xs text-gray-500 text-center">Puoi procedere anche senza compilare tutti i campi</p>
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
          <button onClick={printZebra} className="w-full bg-orange-600 text-white py-4 rounded-xl text-lg font-bold shadow-lg">🖨️ Stampa Etichette Zebra</button>
          <button onClick={() => setStep(3)} className="text-blue-700 underline">Torna indietro</button>
        </div>
      )}
    </div>
  );
}

export default App;