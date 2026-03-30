import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { Html5QrcodeScanner } from 'html5-qrcode';

const API_BASE = "https://tuo-backend-su-render.com/api"; // Cambia questo dopo il deploy

function App() {
  const [step, setStep] = useState(1);
  const [suppliers, setSuppliers] = useState([]);
  const [commonData, setCommonData] = useState({
    fornitore: '',
    descrizione: 'Acciaio Zincato',
    colore: 'RAL 9002',
    spessore: 0.5,
    larghezza: 1250,
    data_arrivo: new Date().toISOString().split('T')[0]
  });
  const [colli, setColli] = useState([]);
  const [isScanning, setIsScanning] = useState(null); // Indice del collo in scansione

  useEffect(() => {
    axios.get(`${API_BASE}/suppliers`).then(res => setSuppliers(res.data));
  }, []);

  // Step 1: Upload Foto
  const handleUpload = async (e) => {
    const files = Array.from(e.target.files);
    const promises = files.map(file => {
      const formData = new FormData();
      formData.append('file', file);
      return axios.post(`${API_BASE}/analyze`, formData);
    });
    const results = await Promise.all(promises);
    setColli(results.map(r => r.data));
    setStep(2);
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

  const handleAddSupplier = async () => {
    const name = prompt("Inserisci il nome del nuovo fornitore:");
    if (name) {
      const res = await axios.post(`${API_BASE}/suppliers`, { name });
      setSuppliers(res.data);
      setCommonData({...commonData, fornitore: name.toUpperCase()});
    }
  };

  const exportExcel = async () => {
    const payload = { ...commonData, colli };
    const res = await axios.post(`${API_BASE}/export`, payload, { responseType: 'blob' });
    const url = window.URL.createObjectURL(new Blob([res.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `arrivi_${commonData.data_arrivo}.xlsx`);
    document.body.appendChild(link);
    link.click();
  };

  return (
    <div className="p-4 max-w-xl mx-auto font-sans">
      <h1 className="text-2xl font-bold text-blue-800 mb-4">SB App Arrivi</h1>
      
      {/* STEP 1 */}
      {step === 1 && (
        <div className="bg-gray-100 p-6 rounded-lg border-2 border-dashed border-gray-300 text-center">
          <p className="mb-4">Carica le foto delle etichette per iniziare</p>
          <input type="file" multiple onChange={handleUpload} className="block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"/>
        </div>
      )}

      {/* STEP 2 */}
      {step === 2 && (
        <div className="space-y-4">
          <h2 className="text-xl font-semibold">Parametri Comuni</h2>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className="block text-sm font-medium">Fornitore</label>
              <div className="flex gap-2">
                <select className="w-full p-2 border rounded" value={commonData.fornitore} onChange={e => setCommonData({...commonData, fornitore: e.target.value})}>
                  <option value="">Seleziona...</option>
                  {suppliers.map(s => <option key={s} value={s}>{s}</option>)}
                </select>
                <button onClick={handleAddSupplier} className="bg-green-600 text-white px-3 rounded">+</button>
              </div>
            </div>
            <div className="col-span-2">
              <label className="block text-sm font-medium">Descrizione</label>
              <input type="text" className="w-full p-2 border rounded" value={commonData.descrizione} onChange={e => setCommonData({...commonData, descrizione: e.target.value})} />
            </div>
            <div>
              <label className="block text-sm font-medium">Colore/RAL</label>
              <input type="text" className="w-full p-2 border rounded" value={commonData.colore} onChange={e => setCommonData({...commonData, colore: e.target.value})} />
            </div>
            <div>
              <label className="block text-sm font-medium">Spessore (mm)</label>
              <input type="number" step="0.01" className="w-full p-2 border rounded" value={commonData.spessore} onChange={e => setCommonData({...commonData, spessore: e.target.value})} />
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