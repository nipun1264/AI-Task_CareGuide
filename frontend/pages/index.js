import {useEffect, useMemo, useState} from 'react';

const api = 'http://localhost:8000/api/v1';
const terminalStatuses = new Set(['completed', 'failed']);

export default function Home() {
  const [docs, setDocs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [searchMessage, setSearchMessage] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [reports, setReports] = useState([]);

  const refresh = async () => {
    try {
      const response = await fetch(`${api}/documents`);
      if (!response.ok) throw new Error('Could not load documents.');
      setDocs(await response.json());
    } catch {
      setMessage('The API is unavailable. Start the backend, then refresh this page.');
    }
  };
  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 5000);
    return () => clearInterval(id);
  }, []);

  const selected = docs.find(doc => doc.id === selectedId) || docs.find(doc => doc.invoice) || null;
  const totals = useMemo(() => ({
    total: docs.length,
    completed: docs.filter(doc => doc.status === 'completed').length,
    inProgress: docs.filter(doc => !terminalStatuses.has(doc.status)).length,
    attention: docs.filter(doc => doc.status === 'failed' || doc.invoice?.validations?.some(v => v.severity === 'error')).length,
  }), [docs]);

  async function upload(event) {
    const files = event.target.files;
    if (!files?.length) return;
    setBusy(true); setMessage('Uploading documents…');
    try {
      const body = new FormData();
      [...files].forEach(file => body.append('files', file));
      const response = await fetch(`${api}/documents/upload`, {method: 'POST', body});
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      setMessage(`${data.documents.length} document(s) queued for processing.`);
      setSelectedId(data.documents[0]?.id || null);
      await refresh();
    } catch (error) {
      setMessage(`Upload failed: ${error.message}`);
    } finally {
      setBusy(false); event.target.value = '';
    }
  }

  async function search(event) {
    event.preventDefault();
    if (!query.trim()) {
      setResults([]); setSearchMessage('');
      return;
    }
    try {
      setSearchMessage('');
      const response = await fetch(`${api}/search?q=${encodeURIComponent(query)}`);
      if (!response.ok) throw new Error('The search service could not complete your request.');
      setResults(await response.json());
    } catch (error) {
      setResults([]);
      setSearchMessage(`Search failed: ${error.message}`);
    }
  }

  async function callAction(url, success) {
    setMessage('Working…');
    try {
      const response = await fetch(`${api}${url}`, {method: 'POST'});
      if (!response.ok) throw new Error(await response.text());
      const data = await response.json();
      if (Array.isArray(data)) setReports(data);
      setMessage(success);
      await refresh();
    } catch (error) {
      setMessage(`Action failed: ${error.message}`);
    }
  }

  async function deleteDocument(document) {
    if (!window.confirm(`Permanently delete ${document.filename}?`)) return;
    try {
      const response = await fetch(`${api}/documents/${document.id}`, {method: 'DELETE'});
      if (!response.ok) throw new Error(await response.text());
      if (selectedId === document.id) setSelectedId(null);
      setReports([]); setResults(results.filter(result => result.invoice.document_id !== document.id));
      setMessage(`${document.filename} was deleted.`);
      await refresh();
    } catch (error) {
      setMessage(`Delete failed: ${error.message}`);
    }
  }

  return <main>
    <header className="hero">
      <div><p className="eyebrow">CARE GUIDE · DOCUMENT INTELLIGENCE</p><h1>Invoice review, in one place.</h1><p>Upload source documents, follow processing live, inspect extracted values, and resolve validation or reconciliation issues.</p></div>
      <button className="secondary" onClick={() => callAction('/documents/retry-failed', 'Failed documents have been queued again.')}>Retry failed</button>
    </header>
    <section className="metrics" aria-label="Document summary">
      <Metric label="All documents" value={totals.total}/><Metric label="Completed" value={totals.completed}/><Metric label="In progress" value={totals.inProgress}/><Metric label="Needs attention" value={totals.attention}/>
    </section>
    <section className="workspace">
      <div className="panel upload-panel"><h2>Upload documents</h2><p>PDF, PNG, JPG, TIFF, XLSX, XLS, or CSV. You may select multiple files.</p><label className="upload">{busy ? 'Uploading…' : 'Choose files to process'}<span>Drop files here or browse your computer</span><input type="file" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.xlsx,.xls,.csv" multiple onChange={upload}/></label>{message && <p className="notice">{message}</p>}</div>
      <form className="panel search" onSubmit={search}><h2>Find an invoice</h2><p>Search invoice number, supplier, or extracted text.</p><div><input value={query} onChange={event => setQuery(event.target.value)} placeholder="e.g. INV-2026-001"/><button>Search</button></div>{searchMessage && <p className="notice">{searchMessage}</p>}{results.length > 0 && <ul className="search-results">{results.map(result => <li key={result.invoice.id}><button className="link" type="button" onClick={() => setSelectedId(result.invoice.document_id)}>{result.invoice.invoice_number || 'Unnumbered invoice'} <span>{result.filename} · {result.invoice.supplier_name || 'Unknown supplier'} · {result.relevance}% match</span></button></li>)}</ul>}</form>
    </section>
    <section className="layout">
      <section className="panel document-list"><div className="section-title"><div><h2>Processing queue</h2><p>Updates automatically every five seconds.</p></div><button className="text-button" onClick={refresh}>Refresh</button></div>{docs.length ? docs.map(doc => <article key={doc.id} className={`document ${selected?.id === doc.id ? 'active' : ''}`}><button className="document-main" onClick={() => {setSelectedId(doc.id); setReports([]);}}><span className={`status ${doc.status}`}>{doc.status}</span><strong>{doc.filename}</strong><small>{formatDate(doc.created_at)} · {doc.invoice?.supplier_name || 'Waiting for extraction'}</small>{doc.error && <small className="error">{doc.error}</small>}</button><button className="delete-document" aria-label={`Delete ${doc.filename}`} title="Delete document" onClick={() => deleteDocument(doc)}>−</button></article>) : <Empty text="No documents uploaded yet."/>}</section>
      <InvoiceReview doc={selected} reports={reports} callAction={callAction}/>
    </section>
  </main>;
}

function Metric({label, value}) { return <article><strong>{value}</strong><span>{label}</span></article>; }
function Empty({text}) { return <p className="empty">{text}</p>; }
function formatDate(value) { return value ? new Date(value).toLocaleString() : 'Just now'; }
function money(value, currency) { return value == null ? 'Not found' : `${currency || ''} ${Number(value).toFixed(2)}`; }

function InvoiceReview({doc, reports, callAction}) {
  if (!doc) return <section className="panel review"><h2>Invoice review</h2><Empty text="Select a processed document to inspect its extracted invoice."/></section>;
  const invoice = doc.invoice;
  return <section className="panel review"><div className="section-title"><div><p className="eyebrow">INVOICE REVIEW</p><h2>{invoice?.invoice_number || doc.filename}</h2></div>{invoice && <button className="secondary" onClick={() => callAction(`/reconciliation/${invoice.id}/run`, 'Reconciliation is complete.')}>Run reconciliation</button>}</div>
    {!invoice ? <><p className="empty">This document is <b>{doc.status}</b>. Extracted values will appear here when processing finishes.</p>{['failed', 'queued'].includes(doc.status) && <button onClick={() => callAction(`/documents/${doc.id}/reprocess`, 'Document queued for reprocessing.')}>Reprocess document</button>}</> : <>
      <dl className="details"><div><dt>Supplier</dt><dd>{invoice.supplier_name || 'Not found'}</dd></div><div><dt>Invoice date</dt><dd>{invoice.invoice_date || 'Not found'}</dd></div><div><dt>Customer</dt><dd>{invoice.customer_name || 'Not found'}</dd></div><div><dt>Confidence</dt><dd>{invoice.confidence != null ? `${Math.round(invoice.confidence * 100)}%` : 'Not available'}</dd></div></dl>
      <div className="amounts"><div><span>Subtotal</span><b>{money(invoice.subtotal, invoice.currency)}</b></div><div><span>Tax</span><b>{money(invoice.tax, invoice.currency)}</b></div><div className="total"><span>Total</span><b>{money(invoice.total, invoice.currency)}</b></div></div>
      <ValidationReport validations={invoice.validations || []}/>
      {reports.length > 0 && <section className="reconciliation"><h3>Reconciliation results</h3>{reports.map(report => <div key={report.id}><b>{report.status.replace('_', ' ')}</b> · {Math.round(report.match_score * 100)}% match {report.candidate && `with ${report.candidate.invoice_number || report.candidate.supplier_name}`}</div>)}</section>}
    </>}
  </section>;
}

function ValidationReport({validations}) {
  return <section className="validation"><div className="section-title"><div><h3>Validation report</h3><p>{validations.length ? `${validations.length} finding(s) detected` : 'No validation issues detected.'}</p></div></div>{validations.map((item, index) => <div key={`${item.rule}-${index}`} className={`finding ${item.severity}`}><b>{item.severity}</b><span>{item.rule.replaceAll('_', ' ')} — {item.message}</span></div>)}</section>;
}
