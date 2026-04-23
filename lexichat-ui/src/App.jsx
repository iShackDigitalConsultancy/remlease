import React, { useState, useCallback, useRef, useEffect, Component } from 'react';
import { useDropzone } from 'react-dropzone';
import axios from 'axios';
import { Document, Page, pdfjs } from 'react-pdf';
import 'react-pdf/dist/Page/AnnotationLayer.css';
import 'react-pdf/dist/Page/TextLayer.css';

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

import { 
  FileText, UploadCloud, MessageSquare, Send, CheckCircle2, 
  Loader2, Scale, BookOpen, Clock, ChevronRight, ChevronDown, ChevronUp, Lock, Trash2, FolderOpen, X, Download, LogOut, Building2, Edit2, Shield, Zap, ShieldCheck, XCircle, ShieldAlert, Users, GitCompare, Calendar, CalendarPlus, Database, BellRing, Layers, ExternalLink, Printer, RefreshCw, MapPin
} from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { BrowserRouter as Router, Routes, Route, Navigate, Link, useNavigate } from 'react-router-dom';

import { AuthProvider, useAuth } from './context/AuthContext';
import { AuthScreen } from './pages/Auth';
import { PrivacyPolicy, TermsConditions, HowToUse } from './pages/LegalPages';

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }
  static getDerivedStateFromError(error) { return { hasError: true, error }; }
  componentDidCatch(error, errorInfo) { this.setState({ errorInfo }); }
  render() {
    if (this.state.hasError) {
      return (
        <div className="p-8 font-mono text-red-500 bg-red-50 min-h-screen">
          <h2 className="text-2xl font-bold mb-4">React Runtime Error</h2>
          <p className="mb-4">{this.state.error?.toString()}</p>
          <pre className="text-xs bg-white p-4 rounded shadow overflow-auto">{this.state.errorInfo?.componentStack}</pre>
        </div>
      );
    }
    return this.props.children;
  }
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

// Module-level variable to pass a file dropped on the landing page into the app
let pendingDropFile = null;

const ProtectedRoute = ({ children }) => {
    // In Freemium mode, everyone can access the workspace.
    return children;
};

function InnerApp() {
  const { token, user, logout, sessionId } = useAuth();
  const navigate = useNavigate();

  const handleDownloadOriginal = async (docId, filename) => {
    try {
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else headers['x-session-id'] = sessionId;
      
      const baseURL = `${API_BASE.replace('/api', '')}/api/document/${docId}`;
      const res = await fetch(baseURL, { headers });
      if (!res.ok) throw new Error(`Failed to download: ${res.status}`);
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename || "document.pdf";
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err) {
      console.error(err);
      alert("Failed to download document.");
    }
  };

  const handleExportPDF = (reportType) => {
    window.print();
  };

  const [isUploading, setIsUploading] = useState(false);
  const [selectedDocId, setSelectedDocId] = useState(null);
  const [selectedPage, setSelectedPage] = useState(1);
  const [activeJurisdictions, setActiveJurisdictions] = useState([]);
  const [isFirmSearchActive, setIsFirmSearchActive] = useState(false);
  const [editingCaseId, setEditingCaseId] = useState(null);
  const [editingCaseName, setEditingCaseName] = useState("");
  const [editingDocId, setEditingDocId] = useState(null);
  const [editingDocName, setEditingDocName] = useState("");
  const [sidebarSearch, setSidebarSearch] = useState('');
  // Audit Feature State
  const [showAuditModal, setShowAuditModal] = useState(false);
  const [auditDocId, setAuditDocId] = useState(null);
  const [auditPolicy, setAuditPolicy] = useState("1. The lease must stipulate a clear expiration date.\n2. The security deposit amount must be clearly stated.\n3. Tenant maintenance obligations must be defined.");
  const [pipelineProgress, setPipelineProgress] = useState("");
  const [auditResult, setAuditResult] = useState(null);
  const [isAuditing, setIsAuditing] = useState(false);
  
  // Expiry Feature State
  const [showExpiryModal, setShowExpiryModal] = useState(false);
  const [expiryData, setExpiryData] = useState(null);
  const [isExtractingExpiries, setIsExtractingExpiries] = useState(false);

  // Portfolio Dashboard State
  const [activeView, setActiveView] = useState('workspace'); // 'workspace' or 'portfolio'
  const [portfolioData, setPortfolioData] = useState(null);
  const [isFetchingPortfolio, setIsFetchingPortfolio] = useState(false);

  const fetchPortfolioOverview = useCallback(async (forceRefresh = false) => {
    if (!forceRefresh && portfolioData) return;
    setIsFetchingPortfolio(true);
    setPipelineProgress("");
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else headers['x-session-id'] = sessionId;
      
      const res = await fetch(`${API_BASE}/portfolio-overview`, { headers });
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
             try {
               const data = JSON.parse(line.slice(6));
               if (data.status === 'processing') {
                   setPipelineProgress(data.message);
               } else if (data.status === 'complete') {
                   const sorted = data.data.sort((a,b) => {
                       if (!a.expiry_date && !b.expiry_date) return 0;
                       if (!a.expiry_date) return 1;
                       if (!b.expiry_date) return -1;
                       return new Date(a.expiry_date) - new Date(b.expiry_date);
                   });
                   setPortfolioData(sorted);
               } else if (data.status === 'error') {
                   throw new Error(data.message);
               }
             } catch(e) {}
          }
        }
      }
    } catch(err) {
      console.error(err);
      alert("Failed to run portfolio overview.");
    } finally {
      setIsFetchingPortfolio(false);
      setPipelineProgress("");
    }
  }, [portfolioData, token, sessionId]);

  useEffect(() => {
     if(activeView === 'portfolio' && !portfolioData) {
         fetchPortfolioOverview();
     }
  }, [activeView, portfolioData, fetchPortfolioOverview]);


  // Gap Analysis Feature State
  const [showGapModal, setShowGapModal] = useState(false);
  const [gapReportData, setGapReportData] = useState(null);
  const [isRunningGapAnalysis, setIsRunningGapAnalysis] = useState(false);

  // Timeline Feature State
  const [showTimelineModal, setShowTimelineModal] = useState(false);
  const [timelineData, setTimelineData] = useState(null);
  const [isGeneratingTimeline, setIsGeneratingTimeline] = useState(false);

  // Compare Feature State
  const [showCompareModal, setShowCompareModal] = useState(false);
  const [compareResult, setCompareResult] = useState(null);
  const [isComparing, setIsComparing] = useState(false);
  const [compareTargetDocId, setCompareTargetDocId] = useState(null);
  const [isAdvancedSearchExpanded, setIsAdvancedSearchExpanded] = useState(false);

  const [cases, setCases] = useState([]);
  const [activeCaseId, setActiveCaseId] = useState(localStorage.getItem('rem-leases_active_case') || null);
  const activeCaseIdRef = useRef(activeCaseId);
  const [chatMessages, setChatMessages] = useState({}); // mapped by activeCaseId
  const [showLimitModal, setShowLimitModal] = useState(false);
  const [docBriefs, setDocBriefs] = useState({}); // doc_id → brief object

  useEffect(() => { activeCaseIdRef.current = activeCaseId; }, [activeCaseId]);

  const [notificationConfig, setNotificationConfig] = useState({
    is_enabled: false,
    thresholds_days: "180,90,30",
    landlord_email: "",
    franchisee_email: "",
    franchisor_email: ""
  });
  const [isSavingNotifications, setIsSavingNotifications] = useState(false);

  const fetchNotificationConfig = useCallback(async () => {
    if (!activeCaseId) return;
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : { 'x-session-id': sessionId };
      const res = await axios.get(`${API_BASE}/workspaces/${activeCaseId}/notifications`, { headers });
      setNotificationConfig({
        is_enabled: res.data.is_enabled || false,
        thresholds_days: res.data.thresholds_days || "180,90,30",
        landlord_email: res.data.landlord_email || "",
        franchisee_email: res.data.franchisee_email || "",
        franchisor_email: res.data.franchisor_email || ""
      });
    } catch (err) {
      console.error("Failed to fetch notification config:", err);
    }
  }, [activeCaseId, token, sessionId]);

  useEffect(() => {
    fetchNotificationConfig();
  }, [fetchNotificationConfig]);

  const saveNotificationConfig = async (newConfig) => {
    if (!activeCaseId) return;
    setIsSavingNotifications(true);
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : { 'x-session-id': sessionId };
      const res = await axios.put(`${API_BASE}/workspaces/${activeCaseId}/notifications`, newConfig, { headers });
      setNotificationConfig({
        is_enabled: res.data.is_enabled || false,
        thresholds_days: res.data.thresholds_days || "180,90,30",
        landlord_email: res.data.landlord_email || "",
        franchisee_email: res.data.franchisee_email || "",
        franchisor_email: res.data.franchisor_email || ""
      });
    } catch (err) {
      console.error("Failed to save notification config:", err);
      alert("Failed to save notification settings.");
    } finally {
      setIsSavingNotifications(false);
    }
  };

  // Fetch document brief when selected
  useEffect(() => {
    if (selectedDocId && !docBriefs[selectedDocId]) {
      const headers = token ? { Authorization: `Bearer ${token}` } : { 'x-session-id': sessionId };
      axios.get(`${API_BASE}/documents/${selectedDocId}/brief`, { headers })
        .then(res => {
          if (res.data && res.data.brief) {
            setDocBriefs(prev => ({ ...prev, [selectedDocId]: res.data.brief }));
          }
        })
        .catch(err => console.error("Failed to fetch brief:", err));
    }
  }, [selectedDocId]);
  useEffect(() => {
    if (activeCaseId) localStorage.setItem('rem-leases_active_case', activeCaseId);
    else localStorage.removeItem('rem-leases_active_case');
  }, [activeCaseId]);

  const fetchWorkspaces = async () => {
      try {
          const headers = token ? { Authorization: `Bearer ${token}` } : { 'X-Session-Id': sessionId };
          const res = await axios.get(`${API_BASE}/workspaces`, {
              headers
          });
          setCases(res.data);
          
          // Initialize chat messages for new cases if they don't exist
          setChatMessages(prev => {
              const newMsgs = { ...prev };
              res.data.forEach(c => {
                  if (!newMsgs[c.id]) {
                      newMsgs[c.id] = [{
                          role: 'assistant',
                          content: "Hi. I'm REM Assistant, your AI assistant. I have loaded this Leasing Workspace for your portfolio. What would you like to know?"
                      }];
                  }
              });
              return newMsgs;
          });

          if (res.data.length > 0 && !res.data.find(c => c.id === activeCaseId)) {
              setActiveCaseId(res.data[0].id);
          }
      } catch (e) {
          console.error("Error fetching workspaces", e);
          if (e.response?.status === 401) logout();
      }
  };

  useEffect(() => {
      fetchWorkspaces();
  }, [token, sessionId]);

  // Auto-upload a file dropped on the landing page
  useEffect(() => {
    if (!pendingDropFile || !sessionId) return;
    const fileToUpload = pendingDropFile;
    pendingDropFile = null; // clear immediately to avoid double-upload

    const autoUpload = async () => {
      try {
        // First create a workspace for this file
        const formData = new FormData();
        formData.append('name', fileToUpload.name.replace(/\.pdf$/i, ''));
        const headers = token ? { Authorization: `Bearer ${token}` } : { 'X-Session-Id': sessionId };
        const wsRes = await axios.post(`${API_BASE}/workspaces`, formData, { headers });
        const newWs = wsRes.data;

        setCases(prev => [...prev, newWs]);
        setActiveCaseId(newWs.id);
        setChatMessages(prev => ({
          ...prev,
          [newWs.id]: [{ role: 'assistant', content: "Hi! I'm REM Assistant. I'm reading your document now — ask me anything once it's loaded." }]
        }));

        // Then upload the file into it
        setIsUploading(true);
        const uploadForm = new FormData();
        uploadForm.append('file', fileToUpload);
        const uploadHeaders = {};
        if (token) uploadHeaders['Authorization'] = `Bearer ${token}`;
        else uploadHeaders['X-Session-Id'] = sessionId;
        await axios.post(`${API_BASE}/upload/${newWs.id}`, uploadForm, { headers: uploadHeaders });
        await fetchWorkspaces();
      } catch (e) {
        console.error('Auto-upload from landing failed', e);
      } finally {
        setIsUploading(false);
      }
    };
    autoUpload();
  }, [sessionId]);

  const activeCase = cases.find(c => c.id === activeCaseId) || null;
  const messages = chatMessages[activeCaseId] || [];
  const library = activeCase ? activeCase.documents : [];

  const setMessagesForActive = (updater) => {
      setChatMessages(prev => ({
          ...prev,
          [activeCaseIdRef.current]: typeof updater === 'function' ? updater(prev[activeCaseIdRef.current]) : updater
      }));
  };

  const createNewCase = async () => {
    try {
        const formData = new FormData();
        formData.append('name', `New Lease ${cases.length + 1}`);
        const headers = token ? { Authorization: `Bearer ${token}` } : { 'X-Session-Id': sessionId };
        const res = await axios.post(`${API_BASE}/workspaces`, formData, {
            headers
        });
        setCases(prev => [...prev, res.data]);
        setActiveCaseId(res.data.id);
        setChatMessages(prev => ({
            ...prev,
            [res.data.id]: [{
                role: 'assistant',
                content: "Hi. Upload a lease agreement, tenant application, or property document into this new Portfolio workspace, and let's get started."
            }]
        }));
    } catch (e) {
        console.error("Failed to create workspace", e);
        alert(`Could not create workspace: ${e.message || "Unknown error"}. Make sure API is online.`);
    }
  };

  const deleteCase = async (id) => {
    const confirmation = window.prompt("WARNING: This will permanently delete the property portfolio and all its documents for everyone in the firm.\n\nType 'DELETE' to confirm your action:");
    if (confirmation === 'DELETE') {
        try {
            const headers = token ? { Authorization: `Bearer ${token}` } : { 'X-Session-Id': sessionId };
            await axios.delete(`${API_BASE}/workspaces/${id}`, {
                headers
            });
            setCases(prev => prev.filter(c => c.id !== id));
            if (activeCaseId === id) setActiveCaseId(null);
        } catch (e) {
            console.error(e);
            alert("Failed to delete property portfolio.");
        }
    } else if (confirmation !== null) {
        alert("Deletion cancelled. You must type 'DELETE' exactly.");
    }
  };

  const deleteDocument = async (docId) => {
    if (!window.confirm("Remove this document from the workspace? This cannot be undone.")) return;
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : { 'X-Session-Id': sessionId };
      await axios.delete(`${API_BASE}/documents/${docId}`, { headers });
      if (selectedDocId === docId) setSelectedDocId(null);
      setDocBriefs(prev => { const next = { ...prev }; delete next[docId]; return next; });
      await fetchWorkspaces();
    } catch (e) {
      console.error(e);
      alert("Failed to delete document.");
    }
  };

  const renameCase = async (id, newName) => {
      if (!newName.trim()) {
          setEditingCaseId(null);
          return;
      }
      try {
          const headers = token ? { Authorization: `Bearer ${token}` } : { 'X-Session-Id': sessionId };
          await axios.put(`${API_BASE}/workspaces/${id}`, { name: newName }, { headers });
          setCases(prev => prev.map(c => c.id === id ? { ...c, name: newName } : c));
          setEditingCaseId(null);
      } catch (e) {
          console.error("Failed to rename workspace", e);
          alert("Failed to rename workspace.");
      }
  };

  const renameDocument = async (docId, newName) => {
      if (!newName.trim()) {
          setEditingDocId(null);
          return;
      }
      try {
          const headers = token ? { Authorization: `Bearer ${token}` } : { 'X-Session-Id': sessionId };
          await axios.put(`${API_BASE}/documents/${docId}`, { name: newName }, { headers });
          setCases(prev => prev.map(c => {
              if (c.id === activeCaseId) {
                  return {
                      ...c,
                      documents: c.documents.map(d => d.id === docId ? { ...d, name: newName } : d)
                  };
              }
              return c;
          }));
          setEditingDocId(null);
      } catch (e) {
          console.error("Failed to rename document", e);
          alert("Failed to rename document.");
      }
  };

  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const [isReceiving, setIsReceiving] = useState(false);
  const QUOTA_LIMIT = 500;
  
  const loadingMessages = [
    "Reading case file...",
    "Extracting critical clauses...",
    "Vectorizing legal context...",
    "Aligning precedents...",
    "Generating embeddings...",
    "Writing to high-speed memory...",
    "Finalizing document parameters...",
    "Optimizing search indexes...",
    "Just a moment more..."
  ];
  const [loadingIndex, setLoadingIndex] = useState(0);

  useEffect(() => {
    let interval;
    if (isUploading) {
      setLoadingIndex(0);
      interval = setInterval(() => {
        setLoadingIndex(prev => (prev < loadingMessages.length - 1 ? prev + 1 : prev));
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [isUploading]);
  
  const chatEndRef = useRef(null);
  
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleCitationClick = useCallback((filename, pageNum) => {
    const doc = library.find(d => d.name.toLowerCase().includes(filename.toLowerCase()) || filename.toLowerCase().includes(d.name.toLowerCase()));
    if (doc) {
       setSelectedDocId(doc.id);
       setSelectedPage(pageNum);
    }
  }, [library]);

  const renderMessageContent = useCallback((content) => {
    const regex = /\[([^\]]+?),\s*Page\s*(\d+)\]/g;
    const parts = [];
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(content)) !== null) {
      if (match.index > lastIndex) {
        parts.push(content.substring(lastIndex, match.index));
      }
      const filename = match[1].trim();
      const page = parseInt(match[2], 10);
      const doc = library.find(d => d.name.toLowerCase().includes(filename.toLowerCase()) || filename.toLowerCase().includes(d.name.toLowerCase()));
      const docId = doc ? doc.id : null;
      
      parts.push(
        <button 
          key={match.index}
          onClick={() => docId && handleCitationClick(filename, page)}
          className={`inline-flex items-center gap-1 px-1.5 py-0.5 mx-1 text-[11px] font-bold rounded transition-colors border ${docId ? 'bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 border-blue-500/30 cursor-pointer shadow-sm translate-y-[-1px]' : 'bg-white/5 text-slate-400 border-white/10 cursor-not-allowed'}`}
          title={docId ? 'View Source Document in Live Viewer' : 'Document not found in library'}
        >
          <BookOpen size={10} /> {filename}, p.{page}
        </button>
      );
      lastIndex = match.index + match[0].length;
    }
    
    if (lastIndex < content.length) {
      parts.push(content.substring(lastIndex));
    }
    
    return parts;
  }, [library, handleCitationClick]);

  const onDrop = useCallback(async (acceptedFiles) => {
    const selected = acceptedFiles[0];
    if (!selected) return;
    
    let targetId = activeCaseIdRef.current;
    if (!targetId) {
        alert("Please create or select a workspace first.");
        return;
    }

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', selected);
    
    try {
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else headers['X-Session-Id'] = sessionId;
      
      const res = await axios.post(`${API_BASE}/upload/${targetId}`, formData, {
        headers
      });
      // Store the document brief returned by the API
      if (res.data?.brief && res.data?.doc_id) {
        setDocBriefs(prev => ({ ...prev, [res.data.doc_id]: res.data.brief }));
      }
      await fetchWorkspaces(); // Refresh the full list securely from db
    } catch (err) {
      console.error(err);
      alert(err.response?.data?.detail || "Error uploading document.");
    } finally {
      setIsUploading(false);
    }
  }, [token, sessionId]);
  
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1
  });

  const handleDownloadDocx = async (content) => {
    try {
      const res = await fetch(`${API_BASE}/export_docx`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: content })
      });
      if (!res.ok) throw new Error("Failed to generate document");
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `REM-Leases_Draft_${new Date().getTime()}.docx`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error(err);
      alert("Failed to export Word Document.");
    }
  };

  const executeAudit = async (forceRefresh = false) => {
    if (!auditPolicy.trim()) return alert("Please enter a policy to check against.");
    setIsAuditing(true);
    setAuditResult(null);
    setPipelineProgress("");
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else if (sessionId) headers['X-Session-Id'] = sessionId;
      
      const res = await fetch(`${API_BASE}/audit`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          doc_id: auditDocId,
          policy: auditPolicy,
          force_refresh: forceRefresh
        })
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
             try {
               const data = JSON.parse(line.slice(6));
               if (data.status === 'processing') {
                   setPipelineProgress(data.message);
               } else if (data.status === 'complete') {
                   setAuditResult(data.data?.audit || data.data);
               } else if (data.status === 'error') {
                   throw new Error(data.message);
               }
             } catch(e) {}
          }
        }
      }
    } catch (err) {
      console.error(err);
      alert("Failed to run document audit. The document might be too long or an error occurred.");
    } finally {
      setIsAuditing(false);
      setPipelineProgress("");
    }
  };

  const executeGapAnalysis = async (forceRefresh = false) => {
    const activeDocIds = library.map(d => d.id);
    if (activeDocIds.length < 2) return alert("Please upload at least TWO documents (a Lease and a Franchise Agreement) to run Gap Analysis.");
    
    setIsRunningGapAnalysis(true);
    setShowGapModal(true);
    setGapReportData(null);
    setPipelineProgress("");
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else if (sessionId) headers['x-session-id'] = sessionId;
      const res = await fetch(`${API_BASE}/gap-analysis`, { 
        method: 'POST',
        headers,
        body: JSON.stringify({ 
          doc_ids: activeDocIds,
          force_refresh: forceRefresh
        })
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
             try {
               const data = JSON.parse(line.slice(6));
               if (data.status === 'processing') {
                   setPipelineProgress(data.message);
               } else if (data.status === 'complete') {
                   setGapReportData(data.data);
               } else if (data.status === 'error') {
                   throw new Error(data.message);
               }
             } catch(e) {}
          }
        }
      }
    } catch (err) {
      alert("Failed to run gap analysis.");
      setShowGapModal(false);
    } finally {
      setIsRunningGapAnalysis(false);
      setPipelineProgress("");
    }
  };

  const executeExpiryExtraction = async (forceRefresh = false) => {
    const activeDocIds = library.map(d => d.id);
    if (activeDocIds.length === 0) return alert("Please upload documents to scan expiries.");
    
    setIsExtractingExpiries(true);
    setShowExpiryModal(true);
    setExpiryData(null);
    setPipelineProgress("");
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else if (sessionId) headers['x-session-id'] = sessionId;
      const res = await fetch(`${API_BASE}/extract-expiries`, { 
        method: 'POST',
        headers,
        body: JSON.stringify({ 
          doc_ids: activeDocIds,
          force_refresh: forceRefresh
        })
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
             try {
               const data = JSON.parse(line.slice(6));
               if (data.status === 'processing') {
                   setPipelineProgress(data.message);
               } else if (data.status === 'complete') {
                   setExpiryData(data.data);
               } else if (data.status === 'error') {
                   alert("Extraction Error: " + data.message);
                   setShowExpiryModal(false);
                   setIsExtractingExpiries(false);
                   return; // Break out of function entirely
               }
             } catch(e) {
                 // only ignore json parse errors
             }
          }
        }
      }
    } catch (err) {
      alert("Failed to extract expiry dates. Connection issue.");
      setShowExpiryModal(false);
    } finally {
      setIsExtractingExpiries(false);
      setPipelineProgress("");
    }
  };

  const generateICS = (expiry) => {
    if (!expiry.expiry_date) return alert("No valid date extracted for ICS generation.");
    const dateStr = expiry.expiry_date.replace(/-/g, '');
    const icsContent = `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//RealEstateMeta//Lease Expiry Calendar//EN
BEGIN:VEVENT
DTSTART:${dateStr}T090000Z
DTEND:${dateStr}T100000Z
SUMMARY:Lease Expiry / Renewal Notice: ${expiry.document}
DESCRIPTION:${expiry.action_required}.\\n\\nClause: ${expiry.clause}
END:VEVENT
END:VCALENDAR`;
    const blob = new Blob([icsContent], { type: 'text/calendar;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `lease-expiry-${expiry.document}.ics`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const executeTimelineGeneration = async (forceRefresh = false) => {
    const activeDocIds = library.map(d => d.id);
    if (activeDocIds.length === 0) return alert("Please upload documents to generate a timeline.");
    
    setIsGeneratingTimeline(true);
    setShowTimelineModal(true);
    setTimelineData(null);
    setPipelineProgress("");
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else if (sessionId) headers['X-Session-Id'] = sessionId;
      
      const res = await fetch(`${API_BASE}/extract-timeline`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ 
          doc_ids: activeDocIds,
          force_refresh: forceRefresh 
        })
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
             try {
               const data = JSON.parse(line.slice(6));
               if (data.status === 'processing') {
                   setPipelineProgress(data.message);
               } else if (data.status === 'complete') {
                   setTimelineData(data.data);
               } else if (data.status === 'error') {
                   throw new Error(data.message);
               }
             } catch(e) {}
          }
        }
      }
    } catch (err) {
      console.error(err);
      alert("Failed to extract master timeline. The documents might be too complex or an error occurred.");
      setShowTimelineModal(false);
    } finally {
      setIsGeneratingTimeline(false);
      setPipelineProgress("");
    }
  };

  const executeComparison = async (targetDocId, forceRefresh = false) => {
    if (!selectedDocId) {
      return alert("Please click on a 'Base / Original' document in your library to open it first, then click the compare icon on a second document.");
    }
    const compareTgt = targetDocId || compareTargetDocId;
    if (selectedDocId === compareTgt) {
      return alert("Please select a different document to compare against.");
    }
    
    setShowCompareModal(true);
    setIsComparing(true);
    setCompareTargetDocId(compareTgt);
    setCompareResult(null);
    setPipelineProgress("");
    
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else if (sessionId) headers['X-Session-Id'] = sessionId;
      
      const res = await fetch(`${API_BASE}/compare`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          doc_id_a: selectedDocId,
          doc_id_b: compareTgt,
          force_refresh: forceRefresh
        })
      });
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();
        for (const line of lines) {
          if (line.startsWith('data: ')) {
             try {
               const data = JSON.parse(line.slice(6));
               if (data.status === 'processing') {
                   setPipelineProgress(data.message);
               } else if (data.status === 'complete') {
                   setCompareResult(data.data);
               } else if (data.status === 'error') {
                   throw new Error(data.message);
               }
             } catch(e) {}
          }
        }
      }
    } catch (err) {
      console.error(err);
      alert("Failed to compare documents: " + err.message);
      setShowCompareModal(false);
    } finally {
      setIsComparing(false);
      setPipelineProgress("");
    }
  };

  const handleSend = async (e, forceQuery = null, isTimeline = false) => {
    if (e && e.preventDefault) e.preventDefault();
    const activeDocIds = library.map(d => d.id);
    const queryToSend = forceQuery || input.trim();
    
    if (!queryToSend || (activeDocIds.length === 0 && activeJurisdictions.length === 0 && !isFirmSearchActive) || isTyping || isReceiving) return;
    
    if (!forceQuery) setInput('');
    setMessagesForActive(prev => [...(prev||[]), { role: 'user', content: queryToSend }]);
    setIsTyping(true);

    
    try {
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      else headers['X-Session-Id'] = sessionId;

      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          doc_ids: activeDocIds,
          query: queryToSend,
          is_timeline: isTimeline,
          jurisdictions: activeJurisdictions,
          is_firm_search: isFirmSearchActive
        })
      });
      
      if (!res.ok) {
        if (res.status === 402) {
          setShowLimitModal(true);
          setMessagesForActive(prev => {
              const cleaned = [...prev];
              cleaned.pop(); // remove user message attempt
              return cleaned;
          });
          setIsTyping(false);
          return;
        }
        throw new Error(res.statusText);
      }

      setIsTyping(false);
      setIsReceiving(true);
      setMessagesForActive(prev => [...prev, { role: 'assistant', content: '' }]);
      
      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let assistantMessage = '';
      let buffer = '';
      
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop(); // Keep incomplete line in buffer
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              if (data.content) {
                assistantMessage += data.content;
                setMessagesForActive(prev => {
                  const newMessages = [...prev];
                  newMessages[newMessages.length - 1] = {
                    ...newMessages[newMessages.length - 1],
                    content: assistantMessage
                  };
                  return newMessages;
                });
              }
            } catch (e) {
              console.error("Error parsing SSE", e);
            }
          }
        }
      }
    } catch (err) {
      console.error(err);
      setMessagesForActive(prev => [...prev, {
        role: 'assistant',
        content: "Error: I could not contact the local execution engine."
      }]);
      setIsTyping(false);
    } finally {
      setIsReceiving(false);
    }
  };

  return (
    <div className="flex h-screen bg-slate-50 font-sans text-slate-900 overflow-hidden relative">
      
      {/* Sidebar / File View */}
      <div className="w-1/3 min-w-[320px] max-w-[400px] glass-panel border-r border-slate-200 flex flex-col z-10 relative print:hidden">
        <div className="p-6 border-b border-slate-200 flex items-center justify-between bg-white">
          <div className="flex items-center gap-3">
             <img src="/rem-logo.png" alt="REM-Leases" className="h-7 cursor-pointer" onClick={() => navigate('/')} />
          </div>
          <div className="flex items-center gap-3">
              {user ? (
                <>
                  <div className="text-right">
                      <div className="text-[11px] font-bold text-slate-800">{user.full_name}</div>
                      {user.role && <div className="text-[9px] text-brand-blue bg-brand-blue/10 px-1.5 py-0.5 rounded font-bold uppercase tracking-widest mt-0.5 inline-block">{user.role}</div>}
                  </div>
                  <button onClick={() => { logout(); navigate('/login'); }} title="Sign Out" className="p-1.5 rounded bg-transparent hover:bg-slate-100 hover:text-red-500 text-slate-400 transition-colors">
                      <LogOut size={16} />
                  </button>
                </>
              ) : (
                  <button onClick={() => navigate('/login')} className="bg-brand-blue text-white px-4 py-2 rounded-lg text-xs font-bold shadow-sm hover:bg-brand-blue-dark transition-all">
                      Log In To Dashboard
                  </button>
              )}
          </div>
        </div>
        
        <div className="p-4 flex-grow flex flex-col min-h-0 overflow-y-auto bg-slate-50">
          
              <button 
                  onClick={() => setActiveView('portfolio')}
                  className={`w-full text-left flex items-center gap-2 px-3 py-2.5 rounded-lg font-bold text-sm transition-colors mb-6 ${activeView === 'portfolio' ? 'bg-brand-blue text-white shadow-md' : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 hover:border-slate-300'}`}
              >
                  <Building2 size={16} /> Global Portfolio Dashboard
              </button>
<div className="mb-4 shrink-0">
              
              <div className="flex items-center justify-between mb-3 px-2 text-xs font-bold text-brand-blue uppercase tracking-widest">
                  <span>Property Portfolios ({cases.length} Leases)</span>
                  <button onClick={createNewCase} className="hover:text-brand-blue p-1 rounded-lg transition-colors text-slate-500 font-bold" title="New Property Portfolio">+</button>
              </div>
              <div className="px-2 mb-3">
                  <input 
                      type="text" 
                      value={sidebarSearch}
                      onChange={e => setSidebarSearch(e.target.value)}
                      placeholder="Search Leases..." 
                      className="w-full bg-white border border-slate-200 text-xs py-2 px-3 rounded-md outline-none focus:border-brand-blue focus:ring-1 focus:ring-brand-blue placeholder-slate-400"
                  />
              </div>

              <div className="space-y-1">
                  {cases.length === 0 && <p className="text-xs text-slate-500 italic px-2">No firm workspaces yet.</p>}
                  {cases.filter(c => c.name.toLowerCase().includes(sidebarSearch.toLowerCase())).map(c => (
                      <div 
                          key={c.id} 
                          onClick={() => {
                              if (editingCaseId !== c.id) setActiveCaseId(c.id);
                              setActiveView('workspace');
                          }}
                          className={`group flex items-center justify-between p-2 rounded-lg cursor-pointer transition-colors ${activeCaseId === c.id ? 'bg-white border border-slate-300 shadow-sm text-brand-blue' : 'hover:bg-slate-100 text-slate-600 border border-transparent'}`}
                      >
                          <div className="flex items-center gap-2 truncate w-full">
                              <FolderOpen size={14} className={activeCaseId === c.id ? 'text-brand-blue shrink-0' : 'text-slate-400 shrink-0'} />
                              {editingCaseId === c.id ? (
                                  <input 
                                      type="text" 
                                      autoFocus
                                      value={editingCaseName}
                                      onChange={e => setEditingCaseName(e.target.value)}
                                      onBlur={() => renameCase(c.id, editingCaseName)}
                                      onKeyDown={e => {
                                          if (e.key === 'Enter') renameCase(c.id, editingCaseName);
                                          if (e.key === 'Escape') setEditingCaseId(null);
                                      }}
                                      className="text-sm font-semibold w-full bg-white border border-brand-blue rounded px-2 py-0.5 outline-none text-slate-900 shadow-sm"
                                      onClick={e => e.stopPropagation()}
                                  />
                              ) : (
                                  <span className="text-sm font-semibold truncate">{c.name}</span>
                              )}
                          </div>
                          <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity shrink-0 ml-2">
                              {editingCaseId !== c.id && (
                                  <button onClick={(e) => { 
                                      e.stopPropagation(); 
                                      setEditingCaseId(c.id); 
                                      setEditingCaseName(c.name); 
                                  }} className="text-slate-400 hover:text-brand-blue rounded p-1 transition-colors">
                                      <Edit2 size={12} />
                                  </button>
                              )}
                              <button onClick={(e) => { e.stopPropagation(); deleteCase(c.id); }} className="text-slate-400 hover:text-red-500 rounded p-1 transition-colors">
                                  <Trash2 size={12} />
                              </button>
                          </div>
                      </div>
                  ))}
              </div>
          </div>

          {activeCase && (
            <div className="pt-4 border-t border-slate-200 flex flex-col">
              <h3 className="text-[10px] font-bold text-brand-blue uppercase tracking-widest mb-3 px-2 truncate" title={activeCase.name}>Lease Files in: {activeCase.name}</h3>
              
              <div className="flex flex-col space-y-3 mb-6">
                {library.map(doc => (
                  <div key={doc.id} className="glass-card p-3.5 flex items-center justify-between group">
                    <div className="flex items-center gap-3 overflow-hidden cursor-pointer flex-1" onClick={() => { setSelectedDocId(doc.id); setSelectedPage(1); }}>
                      <FileText size={16} className={`flex-shrink-0 transition-transform duration-300 ${selectedDocId === doc.id ? 'text-brand-accent scale-110' : 'text-slate-400 group-hover:text-brand-blue'}`} />
                      {editingDocId === doc.id ? (
                          <input
                              type="text"
                              value={editingDocName}
                              onChange={(e) => setEditingDocName(e.target.value)}
                              onBlur={() => renameDocument(doc.id, editingDocName)}
                              onKeyDown={(e) => {
                                  if (e.key === 'Enter') renameDocument(doc.id, editingDocName);
                                  if (e.key === 'Escape') setEditingDocId(null);
                              }}
                              onClick={(e) => e.stopPropagation()}
                              className="text-[13px] font-semibold text-slate-900 bg-white border border-brand-blue rounded px-1.5 py-0.5 w-full focus:outline-none focus:ring-2 focus:ring-brand-blue/30"
                              autoFocus
                          />
                      ) : (
                          <span className={`text-[13px] font-semibold truncate transition-colors ${selectedDocId === doc.id ? 'text-slate-900' : 'text-slate-600 group-hover:text-slate-900'}`} title={doc.name}>{doc.name}</span>
                      )}
                    </div>
                    <div className="flex items-center">
                      <button
                        onClick={(e) => { e.stopPropagation(); setEditingDocId(doc.id); setEditingDocName(doc.name); }}
                        className="ml-0.5 shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-brand-blue transition-all rounded p-0.5"
                        title="Rename Document"
                      >
                        <Edit2 size={12} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); executeComparison(doc.id); }}
                        className="ml-0.5 shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-brand-blue transition-all rounded p-0.5"
                        title="Compare against currently active document"
                      >
                        <GitCompare size={14} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); setAuditDocId(doc.id); setShowAuditModal(true); setAuditResult(null); }}
                        className="ml-0.5 shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-brand-accent transition-all rounded p-0.5"
                        title="Audit Document"
                      >
                        <ShieldCheck size={14} />
                      </button>
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteDocument(doc.id); }}
                        className="ml-0.5 shrink-0 opacity-0 group-hover:opacity-100 text-slate-400 hover:text-red-500 transition-all rounded p-0.5"
                        title="Remove document"
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>

              <div {...getRootProps()} className={`shrink-0 border-2 border-dashed rounded-xl p-3 text-center cursor-pointer transition-all ${isDragActive ? 'border-brand-accent bg-brand-accent/5' : 'border-slate-300 hover:border-brand-blue hover:bg-slate-100'}`}>
                <input {...getInputProps()} />
                {isUploading ? (
                  <div className="flex flex-col items-center justify-center text-brand-accent">
                    <Loader2 size={16} className="animate-spin mb-1" />
                    <p className="font-semibold text-[10px] text-center transition-all duration-300">{loadingMessages[loadingIndex]}</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center text-slate-500">
                    <UploadCloud size={18} className="text-brand-blue mb-1" />
                    <p className="font-bold text-[11px]">+ Add Document</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {!token && (
            <div className="mt-4 shrink-0 bg-brand-accent/20 border border-brand-accent/50 rounded-xl p-4 text-center shadow-[0_0_15px_rgba(217,119,6,0.2)]">
                <p className="text-xs text-brand-accent-light font-bold mb-2">⚠️ Temporary Session</p>
                <p className="text-[10px] text-slate-300 mb-3">Your workspace will be lost if you clear your browser cache.</p>
                <button onClick={() => window.location.href = '/signup'} className="bg-brand-accent text-white text-[11px] font-bold px-4 py-2 rounded-lg shadow-md hover:bg-brand-accent-dark w-full transition-colors">
                    Save My Documents (Free)
                </button>
            </div>
          )}

          <div className="mt-4 mb-2 shrink-0 border-t border-slate-200 pt-4">
             <button 
                onClick={() => setIsAdvancedSearchExpanded(!isAdvancedSearchExpanded)}
                className="w-full flex items-center justify-between text-[10px] font-bold text-slate-500 uppercase tracking-widest px-2 hover:text-brand-blue transition-colors group"
             >
                 <span className="flex items-center gap-2"><Layers size={12} /> Advanced Settings</span>
                 {isAdvancedSearchExpanded ? <ChevronUp size={14} className="group-hover:text-brand-blue" /> : <ChevronDown size={14} className="group-hover:text-brand-blue" />}
             </button>
             
             {isAdvancedSearchExpanded && (
               <div className="mt-4 space-y-4">
                 <div>
                     <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 px-2 flex items-center gap-2">
                         <BookOpen size={12} /> Property Law & Leasing Regulations
                     </h3>
                     <div className="space-y-2 px-2">
                         <label className="flex items-start gap-2 text-sm text-slate-600 cursor-pointer hover:bg-slate-100 p-2 rounded-lg transition-colors border border-transparent">
                             <input 
                                 type="checkbox" 
                                 checked={activeJurisdictions.includes('za')}
                                 onChange={(e) => {
                                     if (e.target.checked) setActiveJurisdictions(prev => [...prev, 'za']);
                                     else setActiveJurisdictions(prev => prev.filter(j => j !== 'za'));
                                 }}
                                 className="mt-1 rounded border-slate-300 text-brand-blue focus:ring-brand-blue"
                             />
                             <div className="flex flex-col">
                                 <div className="flex items-center gap-2">
                                     <span className="font-semibold text-xs text-slate-900">South Africa</span>
                                     <span className="text-[9px] bg-brand-accent/10 px-1.5 py-0.5 rounded text-brand-accent uppercase tracking-wider font-bold">Premium</span>
                                 </div>
                                 <div className="text-[10px] text-slate-500 leading-tight mt-1 space-y-0.5">
                                     <p>✓ Rental Housing Act (50 of 1999)</p>
                                     <p>✓ Consumer Protection Act (CPA)</p>
                                     <p>✓ Prevention of Illegal Eviction Act (PIE)</p>
                                     <p>✓ National Credit Act (34 of 2005)</p>
                                     <p>✓ Property Practitioners Act</p>
                                 </div>
                             </div>
                         </label>
                     </div>
                 </div>
                 <div className="border-t border-slate-200 pt-4">
                     <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 px-2 flex items-center gap-2">
                         <BellRing size={12} /> Automated Expiry Alerts
                     </h3>
                     <div className="space-y-3 px-2">
                         <label className="flex items-center justify-between cursor-pointer group hover:bg-slate-50 p-2 rounded-lg transition-colors border border-transparent">
                             <div className="flex flex-col">
                                 <span className="font-semibold text-xs text-slate-900 group-hover:text-brand-blue transition-colors">Enable Alerts</span>
                                 <span className="text-[10px] text-slate-500">Auto-email parties before expiry</span>
                             </div>
                             <div className="relative inline-flex items-center cursor-pointer">
                                 <input 
                                     type="checkbox" 
                                     className="sr-only peer"
                                     checked={notificationConfig.is_enabled}
                                     onChange={(e) => {
                                         const newConfig = { ...notificationConfig, is_enabled: e.target.checked };
                                         setNotificationConfig(newConfig);
                                         saveNotificationConfig(newConfig);
                                     }}
                                 />
                                 <div className="w-9 h-5 bg-slate-200 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-slate-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-brand-blue"></div>
                             </div>
                         </label>
                         
                         {notificationConfig.is_enabled && (
                             <div className="space-y-3 bg-slate-50 p-3 rounded-lg border border-slate-200 mt-2">
                                 <div>
                                     <label className="block text-[10px] font-bold text-slate-500 mb-1">Alert me (days before expiry):</label>
                                     <div className="flex flex-wrap gap-1 mb-2">
                                         {notificationConfig.thresholds_days.split(',').filter(Boolean).map(t => (
                                             <span key={t} className="inline-flex items-center gap-1 bg-white border border-slate-300 text-slate-700 text-[10px] px-2 py-0.5 rounded-full font-semibold">
                                                 {t} days
                                                 <button onClick={() => {
                                                     const newT = notificationConfig.thresholds_days.split(',').filter(x => x !== t).join(',');
                                                     setNotificationConfig({...notificationConfig, thresholds_days: newT});
                                                 }} className="text-slate-400 hover:text-red-500 transition-colors"><X size={10} /></button>
                                             </span>
                                         ))}
                                     </div>
                                     <input 
                                         type="number" 
                                         placeholder="Add days & press Enter..." 
                                         className="w-full text-xs p-1.5 border border-slate-300 rounded focus:outline-none focus:border-brand-blue"
                                         onKeyDown={(e) => {
                                             if (e.key === 'Enter' && e.target.value) {
                                                 const val = e.target.value.trim();
                                                 const current = notificationConfig.thresholds_days ? notificationConfig.thresholds_days.split(',') : [];
                                                 if (!current.includes(val)) {
                                                     setNotificationConfig({...notificationConfig, thresholds_days: [...current, val].join(',')});
                                                 }
                                                 e.target.value = '';
                                             }
                                         }}
                                     />
                                 </div>
                                 
                                 <div className="space-y-2 mt-3 pt-3 border-t border-slate-200">
                                     <div>
                                         <label className="block text-[10px] font-bold text-slate-500 mb-1">Landlord Email</label>
                                         <input type="email" placeholder="Optional" value={notificationConfig.landlord_email || ''} onChange={e => setNotificationConfig({...notificationConfig, landlord_email: e.target.value})} className="w-full text-xs p-1.5 border border-slate-300 rounded focus:outline-none focus:border-brand-blue" />
                                     </div>
                                     <div>
                                         <label className="block text-[10px] font-bold text-slate-500 mb-1">Franchisee Email</label>
                                         <input type="email" placeholder="Optional" value={notificationConfig.franchisee_email || ''} onChange={e => setNotificationConfig({...notificationConfig, franchisee_email: e.target.value})} className="w-full text-xs p-1.5 border border-slate-300 rounded focus:outline-none focus:border-brand-blue" />
                                     </div>
                                     <div>
                                         <label className="block text-[10px] font-bold text-slate-500 mb-1">Franchisor Email</label>
                                         <input type="email" placeholder="Optional" value={notificationConfig.franchisor_email || ''} onChange={e => setNotificationConfig({...notificationConfig, franchisor_email: e.target.value})} className="w-full text-xs p-1.5 border border-slate-300 rounded focus:outline-none focus:border-brand-blue" />
                                     </div>
                                 </div>
                                 
                                 <button 
                                     onClick={() => saveNotificationConfig(notificationConfig)}
                                     disabled={isSavingNotifications}
                                     className="w-full flex items-center justify-center gap-2 bg-brand-blue text-white text-xs font-bold py-2 rounded shadow-sm hover:bg-blue-700 transition-colors disabled:opacity-50 mt-3"
                                 >
                                     {isSavingNotifications ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle2 size={12} />}
                                     Save Settings
                                 </button>
                             </div>
                         )}
                     </div>
                 </div>
                 <div className="border-t border-slate-200 pt-4">
                     <h3 className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2 px-2 flex items-center gap-2">
                         <Building2 size={12} /> Agency & Portfolio History
                     </h3>
                     <div className="space-y-2 px-2">
                         <label className="flex items-start gap-2 text-sm text-slate-600 cursor-pointer hover:bg-slate-100 p-2 rounded-lg transition-colors border border-transparent">
                             <input 
                                 type="checkbox" 
                                 checked={isFirmSearchActive}
                                 onChange={(e) => setIsFirmSearchActive(e.target.checked)}
                                 className="mt-1 rounded border-slate-300 text-brand-accent focus:ring-brand-accent"
                                 disabled={!user?.firm_id}
                             />
                             <div className="flex flex-col">
                                 <div className="flex items-center gap-2">
                                     <span className="font-semibold text-xs text-slate-900">Search Portfolio History</span>
                                     <span className="text-[9px] bg-brand-accent/10 px-1.5 py-0.5 rounded text-brand-accent uppercase tracking-wider font-bold">Enterprise</span>
                                 </div>
                                 <div className="text-[10px] text-slate-500 leading-tight mt-1">
                                     <p>Search across all lease agreements and documents uploaded by your agency. Bypasses current workspace limit.</p>
                                 </div>
                             </div>
                         </label>
                     </div>
                 </div>
               </div>
             )}
          </div>
          
          <div className="mt-8 shrink-0 pb-4">
             <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4">Support & Legal</h3>
             <div className="flex flex-col gap-2 mt-4 px-1">
                 <Link to="/how-to" className="text-[11px] text-left text-slate-500 hover:text-brand-blue font-bold transition-colors flex items-center gap-2"><BookOpen size={12}/> How to Use REM-Leases</Link>
                 <Link to="/terms" className="text-[11px] text-left text-slate-500 hover:text-brand-blue font-bold transition-colors flex items-center gap-2 ">⚖️ Terms of Service</Link>
                 <Link to="/privacy" className="text-[11px] text-left text-slate-500 hover:text-brand-blue font-bold transition-colors flex items-center gap-2 ">🛡️ Privacy Policy</Link>
             </div>
          </div>
        </div>
      </div>
      
      
      {/* Portfolio Overview */}
      {activeView === 'portfolio' && (
        <div className="flex-1 overflow-y-auto bg-slate-50 p-8 z-10 flex flex-col h-full relative print:p-0 print:overflow-visible">
            <div className="max-w-6xl mx-auto w-full print:max-w-full">
               <div className="flex justify-between items-center mb-8">
                  <div>
                      <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2"><Building2 className="text-brand-blue" /> Global Portfolio Dashboard</h1>
                      <p className="text-slate-500 mt-1">Unified view of all leases and franchise agreements across the firm.</p>
                  </div>
                  <div className="flex items-center gap-3 print:hidden">
                      <button 
                         onClick={() => window.print()}
                         className="bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 px-4 py-2 rounded-xl font-bold text-sm shadow-sm flex items-center gap-2 hover:shadow transition-all"
                      >
                         <Printer size={16} className="text-slate-500" /> Export PDF
                      </button>
                      <button 
                         onClick={() => fetchPortfolioOverview(true)}
                         disabled={isFetchingPortfolio}
                         className="bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 px-4 py-2 rounded-xl font-bold text-sm shadow-sm flex items-center gap-2 hover:shadow disabled:opacity-50 transition-all"
                      >
                         {isFetchingPortfolio ? <><Loader2 size={16} className="animate-spin text-brand-blue" /> Syncing...</> : <><Database size={16} className="text-brand-blue" /> Refresh Portfolio Data</>}
                      </button>
                  </div>
               </div>

               {isFetchingPortfolio && !portfolioData ? (
                  <div className="flex flex-col items-center justify-center p-20 text-slate-400">
                      <div className="relative w-16 h-16 mb-6">
                          <Loader2 size={64} className="animate-spin text-brand-blue absolute inset-0 opacity-20" />
                          <Loader2 size={64} className="animate-spin text-brand-blue absolute inset-0 [animation-duration:2s]" style={{ animationDirection: "reverse" }} />
                      </div>
                      <p className="text-lg font-bold text-slate-700">Analyzing all firm folders...</p>
                      <p className="text-sm mt-2 text-slate-500 max-w-sm text-center">Llama 3 is reading through all agreements across your platform to map expiry dates and critical terms collectively.</p>
                  </div>
               ) : portfolioData && portfolioData.length > 0 ? (
                  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                     <div className="overflow-x-auto">
                        <table className="w-full text-left border-collapse min-w-[800px]">
                           <thead>
                              <tr className="bg-slate-100 border-b border-slate-200 uppercase text-[10px] font-black text-slate-500 tracking-wider">
                                  <th className="p-4">Document</th>
                                  <th className="p-4">Key Dates</th>
                                  <th className="p-4 min-w-[250px]">Primary Terms Overview</th>
                                  <th className="p-4 min-w-[200px]">Management Flags</th>
                              </tr>
                           </thead>
                           <tbody className="divide-y divide-slate-100">
                              {portfolioData.map((doc, idx) => (
                                 <tr key={idx} className="hover:bg-slate-50/50 transition-colors group">
                                     <td className="p-4 align-top w-64 max-w-[250px] break-words">
                                         <button 
                                             onClick={() => {
                                                 if (doc.workspace_id) {
                                                     setActiveCaseId(doc.workspace_id);
                                                     setActiveView('workspace');
                                                     setSelectedDocId(doc.doc_id);
                                                 }
                                             }}
                                             className="font-bold text-sm text-brand-blue hover:text-brand-blue-dark hover:underline leading-tight text-left flex items-start gap-1 group w-full"
                                             title="View Source Document"
                                         >
                                            <span className="line-clamp-2">{doc.filename}</span>
                                            <ExternalLink size={12} className="shrink-0 mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                                         </button>
                                         <span className={`inline-block mt-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${doc.doc_type?.toLowerCase().includes('franchise') ? 'bg-brand-blue/10 text-brand-blue' : 'bg-slate-100 text-slate-600'}`}>
                                            {doc.doc_type || 'Unknown'}
                                         </span>
                                         <button 
                                            onClick={() => handleDownloadOriginal(doc.doc_id, doc.filename)} 
                                            className="mt-2 text-[10px] flex w-max items-center gap-1 bg-brand-blue/5 hover:bg-brand-blue/15 text-brand-blue py-1 px-2 rounded transition-colors"
                                            title="Download Original PDF"
                                         >
                                            <Download size={10} /> Download PDF
                                         </button>
                                     </td>
                                     <td className="p-4 align-top space-y-3 whitespace-nowrap">
                                         <div className="bg-white border border-slate-200 rounded-lg p-2 shadow-sm">
                                            <span className="block text-[9px] uppercase font-bold text-slate-400 mb-0.5">Expiry Date</span>
                                            <span className="font-bold text-sm text-slate-800">{doc.expiry_date || "N/A"}</span>
                                         </div>
                                         <div className="bg-white border border-slate-200 rounded-lg p-2 shadow-sm">
                                            <span className="block text-[9px] uppercase font-bold text-slate-400 mb-0.5">Renewal Deadline</span>
                                            <span className="font-semibold text-xs text-brand-accent">{doc.renewal_deadline || "N/A"}</span>
                                         </div>
                                     </td>
                                     <td className="p-4 align-top">
                                         <p className="text-sm text-slate-700 leading-relaxed font-medium line-clamp-4 hover:line-clamp-none transition-all">{doc.key_terms}</p>
                                     </td>
                                     <td className="p-4 align-top">
                                         {doc.flags && doc.flags.toLowerCase() !== 'none' && doc.flags.toLowerCase() !== 'not applicable' && doc.flags.toLowerCase() !== 'n/a' ? (
                                            <div className="bg-amber-50/50 border border-amber-200 p-3 rounded-xl flex gap-2">
                                                <ShieldAlert size={14} className="text-amber-500 shrink-0 mt-0.5" />
                                                <p className="text-xs font-semibold text-amber-900/80 leading-relaxed">{doc.flags}</p>
                                            </div>
                                         ) : (
                                            <p className="text-xs text-slate-400 font-medium italic bg-slate-50 border border-slate-100 p-2 rounded-lg text-center">No flags detected</p>
                                         )}
                                     </td>
                                 </tr>
                              ))}
                           </tbody>
                        </table>
                     </div>
                  </div>
               ) : (
                  <div className="text-center p-12 bg-white border border-slate-200 rounded-2xl shadow-sm">
                      <p className="text-slate-500 font-bold mb-4">No documents found across your portfolios.</p>
                      <button onClick={() => setActiveView('workspace')} className="text-brand-blue font-bold text-sm hover:underline">Go back to Workspace</button>
                  </div>
               )}
            </div>
        </div>
      )}

      {/* Chat Interface */}
      {activeView === 'workspace' && (

      <div className="flex-1 flex flex-col relative h-full bg-white z-10">
        <div className="absolute top-0 left-0 w-full h-8 flex z-10 pointer-events-none shrink-0 bg-gradient-to-b from-white to-transparent"></div>
        
        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 md:p-8 space-y-8 scroll-smooth">
          {!activeCase ? (
            <div className="flex flex-col items-center justify-center h-full text-slate-400 mt-20">
              <FolderOpen size={48} className="mb-4 text-slate-300" />
              <p className="text-xl font-bold text-slate-900">Select a Property Portfolio</p>
              <p className="text-sm mt-2 text-center max-w-sm text-slate-500">Choose an existing portfolio from the sidebar or click <span className="font-bold text-brand-blue">+</span> to start a new workspace securely for your team.</p>
            </div>
          ) : (
            <>
              {messages.map((m, idx) => (
                <motion.div 
                  key={idx}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex gap-4 ${m.role === 'user' ? 'justify-end' : 'justify-start max-w-3xl'}`}
                >
                  {m.role === 'assistant' && (
                    <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-blue to-brand-blue-dark flex items-center justify-center text-white flex-shrink-0 mt-1 shadow-[0_0_15px_rgba(8,145,178,0.5)] border border-brand-blue-light/50">
                      <Scale size={14} />
                    </div>
                  )}
                  <div className="flex flex-col gap-1 max-w-2xl">
                    <div className={`p-4 rounded-2xl leading-relaxed text-[15px] whitespace-pre-wrap ${
                      m.role === 'user' 
                        ? 'bg-brand-blue text-white rounded-br-none shadow-md border border-brand-blue-light/30' 
                        : 'bg-white border text-slate-800 border-slate-200 shadow-sm rounded-bl-none'
                    }`}>
                      {m.role === 'assistant' ? renderMessageContent(m.content) : m.content}
                    </div>
                    
                    {m.role === 'assistant' && !isReceiving && m.content.length > 50 && (
                      <button 
                         onClick={() => handleDownloadDocx(m.content)}
                         className="self-start mt-1 flex items-center gap-1.5 text-[11px] font-bold text-slate-500 hover:text-brand-blue py-1 px-2 rounded hover:bg-slate-100 transition-colors"
                         title="Export to Microsoft Word"
                      >
                        <Download size={12} /> Export to Word
                      </button>
                    )}
                  </div>
                </motion.div>
              ))}
            </>
          )}
          
          {isTyping && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-4 max-w-3xl">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-blue to-brand-blue-dark flex items-center justify-center text-white flex-shrink-0 mt-1 shadow-md border border-brand-blue/20">
                <Scale size={14} />
              </div>
              <div className="p-4 bg-white border border-slate-200 shadow-sm rounded-bl-none rounded-2xl flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-brand-blue animate-bounce"></span>
                <span className="w-2 h-2 rounded-full bg-brand-blue animate-bounce delay-75"></span>
                <span className="w-2 h-2 rounded-full bg-brand-blue animate-bounce delay-150"></span>
              </div>
            </motion.div>
          )}
          
          {/* Quick Prompts */}
          {messages.length === 1 && !isTyping && !isReceiving && library.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.5 }} className="flex gap-2 flex-wrap mt-2 max-w-3xl ml-12">
              {["Summarize the main argument", "List all dates and deadlines mentioned", "Find any contradictions"].map((prompt, i) => (
                <button 
                  key={i} 
                  onClick={(e) => { setInput(prompt); setTimeout(() => handleSend(e), 50); }} 
                  className="text-xs font-semibold bg-white text-brand-blue px-4 py-2 rounded-full border border-slate-200 shadow-sm hover:border-brand-blue hover:shadow-md transition-all"
                >
                  {prompt}
                </button>
              ))}
            </motion.div>
          )}
          
          <div ref={chatEndRef} className="h-4 shrink-0" />
        </div>
        
        {/* Input Form */}
        <div className="shrink-0 bg-slate-50 p-4 md:p-6 border-t border-slate-200/60 z-20 relative">

          <div className="max-w-3xl mx-auto relative group">
            <div className="flex justify-between items-center mb-2 px-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-widest">
                Enterprise Active
              </span>
            </div>

            <form onSubmit={handleSend} className="relative flex items-center transition-shadow bg-white rounded-2xl shadow-sm border border-slate-300 focus-within:border-brand-blue focus-within:ring-4 focus-within:ring-brand-blue/20">
              <input 
                type="text" 
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder={isFirmSearchActive ? "Search firm precedents globally..." : !activeCase ? "Select a Workspace first..." : library.length > 0 ? "Ask a question about the firm documents..." : activeJurisdictions.length > 0 ? "Ask a question about the SA Knowledge Base..." : "Awaiting document upload..."}
                disabled={!activeCase || (library.length === 0 && activeJurisdictions.length === 0 && !isFirmSearchActive) || isTyping || isReceiving}
                className="w-full py-4 pl-6 pr-16 bg-transparent outline-none disabled:opacity-50 text-slate-900 placeholder-slate-400 font-medium disabled:bg-slate-50 disabled:cursor-not-allowed rounded-2xl"
              />
              <button 
                type="submit"
                disabled={!activeCase || (library.length === 0 && activeJurisdictions.length === 0 && !isFirmSearchActive) || isTyping || isReceiving || !input.trim()}
                className="absolute right-2 p-2.5 bg-brand-blue text-white rounded-xl disabled:bg-slate-100 disabled:text-slate-400 transition-colors shadow-sm disabled:shadow-none border border-transparent disabled:border-slate-200"
              >
                <Send size={20} className={!activeCase || (library.length === 0 && activeJurisdictions.length === 0 && !isFirmSearchActive) || isTyping || isReceiving || !input.trim() ? "" : "translate-x-[1px] -translate-y-[1px]"} />
              </button>
            </form>
            
            <div className="flex justify-between items-center mt-3 px-1">
              <p className="text-[10px] text-slate-400 font-medium uppercase tracking-wide">REM-Leases AI can hallucinate. Verify claims against primary sources.</p>
              
              <div className="flex items-center gap-2">
                <button 
                  type="button"
                  onClick={() => executeExpiryExtraction(false)}
                  disabled={!activeCase || library.length === 0 || isExtractingExpiries || isRunningGapAnalysis}
                  className="flex items-center gap-1.5 text-xs font-bold text-slate-700 bg-white border border-slate-300 hover:bg-slate-50 px-3 py-1.5 rounded-lg transition-colors shadow-sm disabled:bg-slate-100 disabled:text-slate-400 disabled:cursor-not-allowed"
                >
                  {isExtractingExpiries ? <><Loader2 size={12} className="animate-spin" /> Scanning...</> : <><Clock size={12} /> Scan Expiries/Renewals</>}
                </button>
                <button 
                  type="button"
                  onClick={() => executeGapAnalysis(false)}
                  disabled={!activeCase || library.length < 2 || isRunningGapAnalysis}
                  className="flex items-center gap-1.5 text-xs font-bold text-slate-700 bg-amber-50 border border-amber-300 hover:bg-amber-100 px-3 py-1.5 rounded-lg transition-colors shadow-sm disabled:bg-slate-100 disabled:border-slate-200 disabled:text-slate-400 disabled:cursor-not-allowed"
                >
                  {isRunningGapAnalysis ? <><Loader2 size={12} className="animate-spin text-amber-700" /> Mapping...</> : <><Layers size={12} className="text-amber-700" /> Franchise vs Lease Gap Analysis</>}
                </button>
                <button 
                  type="button"
                  onClick={() => executeTimelineGeneration(false)}
                  disabled={!activeCase || library.length === 0 || isGeneratingTimeline}
                  className="flex items-center gap-1.5 text-xs font-bold text-white bg-brand-accent hover:bg-brand-accent-dark px-3 py-1.5 rounded-lg transition-colors shadow-sm disabled:bg-slate-300 disabled:cursor-not-allowed"
                >
                  {isGeneratingTimeline ? <><Loader2 size={12} className="animate-spin" /> Extracting...</> : <><FileText size={12} /> Extract Fundamental Terms</>}
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

            )}

{showLimitModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-sm p-4">
          <div className="bg-white border border-slate-200 rounded-3xl p-8 max-w-md w-full shadow-2xl transition-all transform scale-100">
            <div className="flex justify-center mb-6">
              <Lock size={48} className="text-brand-blue" />
            </div>
            <h2 className="text-2xl font-bold text-center text-slate-900 mb-4">Registration Required</h2>
            <p className="text-slate-600 text-center mb-8 leading-relaxed">
              Create an account or sign in to save your workspaces, track history, and securely upload unlimited documents.
            </p>
            <div className="space-y-4">
              <button 
                onClick={() => navigate('/auth')} 
                className="w-full bg-brand-blue text-white font-bold py-3 px-4 rounded-xl shadow-lg hover:bg-brand-blue-dark transition-all"
              >
                Sign Up / Login
              </button>
              <button 
                onClick={() => setShowLimitModal(false)}
                className="w-full bg-slate-100 text-slate-600 font-bold py-3 px-4 rounded-xl hover:bg-slate-200 transition-colors"
              >
                Dismiss
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Compare Modal */}
      {showCompareModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl w-full max-w-5xl h-[85vh] flex flex-col border border-slate-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50 shrink-0">
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <GitCompare className="text-brand-accent" size={18} /> Document Redline Comparison
              </h2>
              <div className="flex items-center gap-3">
                <button onClick={() => executeComparison(compareTargetDocId, true)} disabled={isComparing} className="text-xs flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 py-1.5 px-3 rounded-md transition-colors disabled:opacity-50"><RefreshCw size={14}/> {isComparing ? "Refreshing..." : "Refresh"}</button>
                <button onClick={() => handleDownloadOriginal(selectedDocId, "Base_Document.pdf")} className="text-xs flex items-center gap-1.5 bg-brand-blue/10 hover:bg-brand-blue/20 text-brand-blue py-1.5 px-3 rounded-md transition-colors" title="Download Base Document"><Download size={14}/> PDF 1</button>
                <button onClick={() => handleDownloadOriginal(compareTargetDocId, "Target_Document.pdf")} className="text-xs flex items-center gap-1.5 bg-brand-blue/10 hover:bg-brand-blue/20 text-brand-blue py-1.5 px-3 rounded-md transition-colors" title="Download Comparison Document"><Download size={14}/> PDF 2</button>
                <button onClick={() => handleExportPDF("compare-modal-content", "compare")} className="text-xs flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 py-1.5 px-3 rounded-md transition-colors"><FileText size={14}/> Export</button>
                <button 
                  onClick={() => {
                     if(isComparing && !window.confirm("Comparison is still running. Are you sure you want to close?")) return;
                     setShowCompareModal(false);
                  }} 
                  className="p-1 text-slate-400 hover:text-slate-900 rounded-lg hover:bg-slate-200 transition-colors ml-2"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            
            <div id="compare-modal-content" className="print-target flex-1 overflow-y-auto flex flex-col bg-white p-6 md:p-8">
              {isComparing ? (
                 <div className="flex-1 flex flex-col items-center justify-center text-slate-400 gap-4">
                    <Loader2 size={40} className="animate-spin text-brand-accent" />
                    <p className="font-bold text-sm text-slate-500 animate-pulse tracking-wide">{pipelineProgress || "Forensically comparing documents line-by-line..."}</p>
                 </div>
              ) : compareResult ? (
                <div className="max-w-4xl mx-auto w-full space-y-8">
                   {compareResult.document_context?.location && (
                     <div className="bg-slate-50 border border-slate-200 rounded-lg px-6 py-3 flex items-center gap-2">
                       <MapPin size={16} className="text-slate-400" />
                       <span className="text-sm font-medium text-slate-700"><strong>Property Location:</strong> {compareResult.document_context.location}</span>
                     </div>
                   )}
                  {/* Executive Risk Summary */}
                  <div className="bg-slate-50 border border-brand-blue/30 rounded-xl p-6 relative overflow-hidden shadow-sm">
                     <div className="absolute top-0 left-0 w-1 h-full bg-brand-blue"></div>
                     <h3 className="text-xs font-black text-brand-blue uppercase tracking-widest mb-3 flex items-center gap-2">
                        <Zap size={14} className="text-brand-accent" /> Executive Risk Summary
                     </h3>
                     <p className="text-sm text-slate-700 font-medium leading-relaxed">
                        {compareResult.risk_summary}
                     </p>
                  </div>
                  
                  {/* Changes List */}
                  <div className="space-y-6">
                     <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest border-b border-slate-200 pb-2">
                        Identified Clause Modifications
                     </h3>
                     
                     {compareResult.changes?.length === 0 ? (
                        <div className="text-center p-12 text-slate-500 text-sm border-2 border-dashed border-slate-300 rounded-2xl bg-slate-50">No substantive legal changes found between these documents.</div>
                     ) : (
                        compareResult.changes?.map((change, idx) => (
                           <div key={idx} className="bg-white border border-slate-200 shadow-sm rounded-xl text-sm overflow-hidden">
                              <div className={`px-4 py-2 flex justify-between items-center border-b border-slate-200 ${change.type === 'ADDED' ? 'bg-green-50 text-green-700' : change.type === 'DELETED' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>
                                 <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-md ${change.type === 'ADDED' ? 'bg-green-100' : change.type === 'DELETED' ? 'bg-red-100' : 'bg-amber-100'}`}>
                                    {change.type}
                                 </span>
                              </div>
                              
                              <div className="p-0 flex flex-col md:flex-row divide-y md:divide-y-0 md:divide-x divide-slate-200">
                                 {change.type !== 'ADDED' && (
                                    <div className="p-5 flex-1 bg-red-50/30">
                                       <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Original Document</span>
                                       <p className={`text-slate-600 leading-relaxed ${change.type === 'DELETED' ? 'line-through text-red-500/80' : ''}`}>
                                          {change.original_text || "N/A"}
                                       </p>
                                    </div>
                                 )}
                                 {change.type !== 'DELETED' && (
                                    <div className="p-5 flex-1 bg-green-50/30">
                                       <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-wider mb-2">Modified Draft</span>
                                       <p className={`text-slate-800 leading-relaxed ${change.type === 'ADDED' ? 'text-green-700 bg-green-100/50 p-1 -m-1 rounded' : ''}`}>
                                          {change.new_text || "N/A"}
                                       </p>
                                    </div>
                                 )}
                              </div>
                              
                              <div className="bg-slate-50 px-5 py-3 border-t border-slate-200 text-xs flex items-start gap-2">
                                 <ShieldAlert size={14} className="text-brand-blue mt-0.5 shrink-0" />
                                 <span className="text-slate-600 font-medium leading-relaxed"><strong className="text-slate-900">Risk Impact:</strong> {change.impact}</span>
                              </div>
                           </div>
                        ))
                     )}
                  </div>
                </div>
              ) : (
                 <div className="flex-1 flex flex-col items-center justify-center text-red-500 gap-4">
                    <XCircle size={40} />
                    <p className="font-bold text-sm">Failed to extract comparison data.</p>
                 </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Audit Modal */}
      {showAuditModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-2xl flex flex-col max-h-[85vh]">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50 rounded-t-2xl">
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <ShieldCheck className="text-brand-accent" size={18} /> Document Compliance Audit
              </h2>
              <div className="flex items-center gap-3">
                <button onClick={() => executeAudit(true)} disabled={isAuditing} className="text-xs flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 py-1.5 px-3 rounded-md transition-colors disabled:opacity-50"><RefreshCw size={14}/> {isAuditing ? "Refreshing..." : "Refresh"}</button>
                <button onClick={() => handleDownloadOriginal(auditDocId, selectedDocId === auditDocId ? cases.find(c => c.id === activeCaseId)?.documents?.find(d => d.id === auditDocId)?.name : "Audit_Document.pdf")} className="text-xs flex items-center gap-1.5 bg-brand-blue/10 hover:bg-brand-blue/20 text-brand-blue py-1.5 px-3 rounded-md transition-colors"><Download size={14}/> PDF</button>
                <button onClick={() => handleExportPDF("audit-modal-content", "audit")} className="text-xs flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 py-1.5 px-3 rounded-md transition-colors"><FileText size={14}/> Export</button>
                <button onClick={() => setShowAuditModal(false)} className="p-1 text-slate-400 hover:text-slate-900 rounded-lg hover:bg-slate-200 transition-colors ml-2"><X size={16} /></button>
              </div>
            </div>
            
            <div id="audit-modal-content" className="print-target p-6 overflow-y-auto flex-1 flex flex-col gap-4">
               {auditResult?.document_context?.location && (
                 <div className="bg-slate-50 border border-slate-200 rounded-lg px-6 py-3 flex items-center gap-2">
                   <MapPin size={16} className="text-slate-400" />
                   <span className="text-sm font-medium text-slate-700"><strong>Property Location:</strong> {auditResult.document_context.location}</span>
                 </div>
               )}
               <div>
                   <label className="block text-xs font-bold text-slate-500 mb-2 uppercase tracking-wide">Audit Policy Checklist</label>
                   <textarea
                     value={auditPolicy}
                     onChange={e => setAuditPolicy(e.target.value)}
                     disabled={isAuditing}
                     placeholder="- Term must be less than 5 years&#10;- Governing law is South Africa"
                     className="w-full h-32 p-3 text-sm bg-white border border-slate-300 rounded-xl focus:ring-2 focus:ring-brand-accent/40 focus:border-brand-accent outline-none shadow-sm transition-all resize-none text-slate-900 placeholder-slate-400"
                   />
               </div>
               
               <div className="flex justify-end relative">
                  <button 
                    onClick={() => executeAudit(false)}
                    disabled={isAuditing || !auditPolicy.trim()}
                    className="bg-brand-accent text-white hover:bg-brand-accent-dark px-5 py-2.5 rounded-xl font-bold text-sm shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:hover:translate-y-0 flex items-center gap-2"
                  >
                    {isAuditing ? <><Loader2 size={16} className="animate-spin" /> {pipelineProgress || "Running Audit..."}</> : "Run Policy Audit"}
                  </button>
               </div>

               {auditResult && (
                 <div className="mt-4 border-t border-slate-200 pt-6">
                    <h3 className="text-xs font-bold text-slate-500 mb-4 uppercase tracking-wide flex justify-between items-center">
                        Audit Report Card
                        <span className="text-[10px] font-bold px-2 py-0.5 bg-green-100 border border-green-200 text-green-700 rounded-full">{Array.isArray(auditResult) ? auditResult.filter(r => r.status === 'PASS').length : 0} Passed</span>
                    </h3>
                    <div className="space-y-3">
                       {Array.isArray(auditResult) ? auditResult.map((item, idx) => (
                          <div key={idx} className={`p-4 rounded-xl shadow-sm border flex flex-col gap-2 bg-white text-slate-800 ${item.status === 'PASS' ? 'border-l-4 border-l-green-500 border-slate-200' : item.status === 'FAIL' ? 'border-l-4 border-l-red-500 border-slate-200 bg-red-50/30' : 'border-l-4 border-l-amber-500 border-slate-200 bg-amber-50/30'}`}>
                             <div className="flex items-center gap-2 font-bold text-sm text-slate-900">
                                {item.status === 'PASS' ? <CheckCircle2 size={16} className="text-green-500 shrink-0" /> : item.status === 'FAIL' ? <XCircle size={16} className="text-red-500 shrink-0" /> : <ShieldAlert size={16} className="text-amber-500 shrink-0" />}
                                {item.check}
                             </div>
                             <div className="text-xs text-slate-600 leading-relaxed ml-6 rounded bg-slate-50 p-2 border border-slate-100">
                                {item.explanation}
                             </div>
                          </div>
                       )) : (
                         <div className="p-4 bg-red-50 text-red-600 border border-red-200 text-sm rounded-xl">Invalid audit response structure from AI. Please try again.</div>
                       )}
                    </div>
                 </div>
               )}
            </div>
          </div>
        </div>
      )}

      {/* Expiry Modal */}
      {showExpiryModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50 shrink-0">
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Calendar className="text-brand-accent" size={18} /> Global Expiry & Renewal Intelligence
              </h2>
              <div className="flex items-center gap-3">
                <button onClick={() => executeExpiryExtraction(true)} disabled={isExtractingExpiries} className="text-xs flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 py-1.5 px-3 rounded-md transition-colors disabled:opacity-50"><RefreshCw size={14}/> {isExtractingExpiries ? "Scanning..." : "Refresh"}</button>
                <button onClick={() => handleExportPDF("expiry-modal-content", "expiry_intelligence")} className="text-xs flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 py-1.5 px-3 rounded-md transition-colors"><FileText size={14}/> Export</button>
                <button 
                  onClick={() => {
                     if(isExtractingExpiries) {
                        if(!window.confirm("Expiry extraction is still running in the background. Are you sure you want to close?")) return;
                     }
                     setShowExpiryModal(false);
                  }} 
                  className="p-1 text-slate-400 hover:text-slate-900 rounded-lg hover:bg-slate-200 transition-colors ml-2"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            
            <div id="expiry-modal-content" className="print-target flex-1 overflow-y-auto bg-white p-6 md:p-8">
              {isExtractingExpiries ? (
                 <div className="flex-1 h-full flex flex-col items-center justify-center text-slate-400 gap-4">
                    <Loader2 size={40} className="animate-spin text-brand-accent" />
                    <p className="font-bold text-sm text-slate-500 animate-pulse tracking-wide">{pipelineProgress || "Scanning portfolio for critical dates, termination rights and renewals..."}</p>
                 </div>
              ) : expiryData ? (
                <div className="max-w-4xl mx-auto space-y-6">
                   {expiryData.document_context?.location && (
                     <div className="bg-slate-50 border border-slate-200 rounded-lg px-6 py-3 flex items-center gap-2">
                       <MapPin size={16} className="text-slate-400" />
                       <span className="text-sm font-medium text-slate-700"><strong>Property Location:</strong> {expiryData.document_context.location}</span>
                     </div>
                   )}
                  {(!expiryData.expiries || expiryData.expiries.length === 0) ? (
                     <div className="text-center p-12 text-slate-500 text-sm border-2 border-dashed border-slate-300 rounded-2xl bg-slate-50">No expiry dates could be identified in the active documents.</div>
                  ) : (
                    expiryData.expiries.map((exp, idx) => (
                      <div key={idx} className="bg-white border border-slate-200 shadow-md rounded-2xl overflow-hidden hover:border-brand-blue/30 transition-all">
                        <div className="bg-slate-50 border-b border-slate-200 px-6 py-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                           <div className="flex flex-col gap-1 w-full max-w-sm">
                             <div className="flex items-center gap-3">
                               <FileText className="text-brand-blue shrink-0" size={18} />
                               <span className="font-bold text-slate-900 truncate" title={exp.document}>{exp.document}</span>
                             </div>
                             <button 
                               onClick={() => {
                                 const doc = library.find(d => d.name === exp.document || d.filename === exp.document);
                                 if(doc) handleDownloadOriginal(doc.id, doc.filename);
                               }}
                               className="text-[10px] mt-1 ml-7 flex w-max items-center gap-1 bg-brand-blue/5 hover:bg-brand-blue/15 text-brand-blue py-1 px-2 rounded transition-colors"
                             >
                                <Download size={10} /> Download Source PDF
                             </button>
                           </div>
                        </div>
                        
                        <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
                           <div className="lg:col-span-1 space-y-4">
                             <div>
                                <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Commencement Date</span>
                                <div className="text-md font-bold text-slate-700 flex items-center gap-2">
                                  <Clock size={16} className="opacity-70"/> {exp.commencement_date || "Not Specified"}
                                </div>
                             </div>
                             <div className="pt-2 border-t border-slate-100">
                                <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Expiration Date</span>
                                <div className="text-xl font-black text-brand-accent flex items-center gap-2">
                                  <Clock size={18} className="opacity-80"/> {exp.expiry_date || "Not Specified"}
                                </div>
                             </div>
                             <div>
                                <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Renewal Deadline</span>
                                <div className="text-md font-bold text-slate-700">
                                  {exp.renewal_deadline || "Not Specified"}
                                </div>
                             </div>
                           </div>
                           <div className="lg:col-span-2 space-y-4">
                              <div className="bg-amber-50/50 p-4 rounded-xl border border-amber-200/60">
                                <span className="block text-[10px] font-bold text-amber-700 uppercase tracking-widest mb-2 flex items-center gap-1"><BellRing size={12} /> Action Required</span>
                                <p className="text-slate-800 text-sm font-medium">{exp.action_required || "No specific action flagged."}</p>
                              </div>
                              <div>
                                <span className="block text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Governing Clause Extraction</span>
                                <p className="text-slate-600 text-sm italic border-l-2 border-slate-300 pl-3 leading-relaxed">{exp.clause || "Clause text not extracted."}</p>
                              </div>
                           </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              ) : (
                 <div className="flex-1 h-full flex flex-col items-center justify-center text-red-500 gap-4">
                    <ShieldAlert size={40} />
                    <p className="font-bold text-sm">Failed to extract expiry data.</p>
                 </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Gap Analysis Modal */}
      {showGapModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50 shrink-0">
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Layers className="text-amber-600" size={18} /> Franchise vs Lease Gap Analysis
              </h2>
              <div className="flex items-center gap-3">
                <button onClick={() => executeGapAnalysis(true)} disabled={isRunningGapAnalysis} className="text-xs flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 py-1.5 px-3 rounded-md transition-colors disabled:opacity-50"><RefreshCw size={14}/> {isRunningGapAnalysis ? "Mapping..." : "Refresh"}</button>
                <button onClick={() => handleExportPDF("gap-modal-content", "gap_analysis")} className="text-xs flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 py-1.5 px-3 rounded-md transition-colors"><FileText size={14}/> Export</button>
                <button 
                  onClick={() => {
                     if(isRunningGapAnalysis) {
                        if(!window.confirm("Gap analysis is still running in the background. Are you sure you want to close?")) return;
                     }
                     setShowGapModal(false);
                  }} 
                  className="p-1 text-slate-400 hover:text-slate-900 rounded-lg hover:bg-slate-200 transition-colors ml-2"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            
            <div id="gap-modal-content" className="print-target flex-1 overflow-y-auto bg-slate-50/50 p-6 md:p-8">
              {isRunningGapAnalysis ? (
                 <div className="flex-1 h-full flex flex-col items-center justify-center text-slate-400 gap-4">
                    <Loader2 size={40} className="animate-spin text-amber-500" />
                    <p className="font-bold text-sm text-slate-500 animate-pulse tracking-wide">{pipelineProgress || "Cross-referencing Franchise and Lease obligations..."}</p>
                 </div>
              ) : gapReportData ? (
                <div className="max-w-5xl mx-auto flex flex-col gap-8">
                   {gapReportData.document_context?.location && (
                     <div className="bg-slate-50 border border-slate-200 rounded-lg px-6 py-3 flex items-center gap-2">
                       <MapPin size={16} className="text-slate-400" />
                       <span className="text-sm font-medium text-slate-700"><strong>Property Location:</strong> {gapReportData.document_context.location}</span>
                     </div>
                   )}
                  {/* Executive Overview */}
                  <div className="bg-white border border-slate-200 p-6 rounded-2xl shadow-sm">
                    <h3 className="text-xs font-black text-slate-500 uppercase tracking-widest mb-4">Detected Documents</h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                       <div className="p-4 bg-brand-blue/5 border border-brand-blue/20 rounded-xl relative">
                          <span className="text-[10px] uppercase font-bold text-brand-blue mb-1 block">Franchise Agreement</span>
                          <span className="font-semibold text-sm text-slate-800 pr-24 block truncate" title={gapReportData.detected_franchise}>{gapReportData.detected_franchise || "Not Found"}</span>
                          {gapReportData.detected_franchise && gapReportData.detected_franchise !== "Not Found" && (
                            <button 
                               onClick={() => {
                                 const doc = library.find(d => d.name === gapReportData.detected_franchise || d.filename === gapReportData.detected_franchise);
                                 if(doc) handleDownloadOriginal(doc.id, doc.filename);
                               }}
                               className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] flex items-center gap-1 bg-brand-blue/10 hover:bg-brand-blue/20 text-brand-blue py-1.5 px-2 rounded transition-colors"
                            >
                               <Download size={12} /> PDF
                            </button>
                          )}
                       </div>
                       <div className="p-4 bg-slate-100 border border-slate-200 rounded-xl relative">
                          <span className="text-[10px] uppercase font-bold text-slate-500 mb-1 block">Lease Agreement</span>
                          <span className="font-semibold text-sm text-slate-800 pr-24 block truncate" title={gapReportData.detected_lease}>{gapReportData.detected_lease || "Not Found"}</span>
                          {gapReportData.detected_lease && gapReportData.detected_lease !== "Not Found" && (
                            <button 
                               onClick={() => {
                                 const doc = library.find(d => d.name === gapReportData.detected_lease || d.filename === gapReportData.detected_lease);
                                 if(doc) handleDownloadOriginal(doc.id, doc.filename);
                               }}
                               className="absolute right-4 top-1/2 -translate-y-1/2 text-[10px] flex items-center gap-1 bg-white border border-slate-300 hover:bg-slate-200 text-slate-700 py-1.5 px-2 rounded transition-colors shadow-sm"
                            >
                               <Download size={12} /> PDF
                            </button>
                          )}
                       </div>
                    </div>
                  </div>

                  {/* Key Terms Mapped Side by Side */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {/* Franchise Terms */}
                    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                       <div className="bg-brand-blue/10 px-5 py-3 border-b border-brand-blue/20">
                          <h4 className="text-xs font-bold text-brand-blue uppercase">Franchise Baseline</h4>
                       </div>
                       <div className="p-5 space-y-4">
                          <div>
                             <span className="block text-[10px] font-bold text-slate-400 uppercase">Term</span>
                             <p className="text-sm font-medium text-slate-800">{gapReportData.franchise_key_terms?.term || "N/A"}</p>
                          </div>
                          <div>
                             <span className="block text-[10px] font-bold text-slate-400 uppercase">Permitted Use</span>
                             <p className="text-sm font-medium text-slate-800">{gapReportData.franchise_key_terms?.permitted_use || "N/A"}</p>
                          </div>
                       </div>
                    </div>
                    {/* Lease Terms */}
                    <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                       <div className="bg-slate-100 px-5 py-3 border-b border-slate-200">
                          <h4 className="text-xs font-bold text-slate-600 uppercase">Lease Execution</h4>
                       </div>
                       <div className="p-5 space-y-4">
                          <div>
                             <span className="block text-[10px] font-bold text-slate-400 uppercase">Term</span>
                             <p className="text-sm font-medium text-slate-800">{gapReportData.lease_key_terms?.term || "N/A"}</p>
                          </div>
                          <div>
                             <span className="block text-[10px] font-bold text-slate-400 uppercase">Permitted Use</span>
                             <p className="text-sm font-medium text-slate-800">{gapReportData.lease_key_terms?.permitted_use || "N/A"}</p>
                          </div>
                       </div>
                    </div>
                  </div>

                  {/* Gap Conflicts Table */}
                  <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
                     <div className="bg-slate-50 px-6 py-4 border-b border-slate-200">
                        <h3 className="text-xs font-black text-slate-500 uppercase tracking-widest">Compliance Mismatches</h3>
                     </div>
                     <div className="divide-y divide-slate-100">
                       {!gapReportData.gaps || gapReportData.gaps.length === 0 ? (
                          <div className="p-8 text-center text-sm text-slate-500">No notable gaps detected.</div>
                       ) : (
                         gapReportData.gaps.map((gap, i) => (
                           <div key={i} className="p-6 flex flex-col md:flex-row gap-6 hover:bg-slate-50/50 transition-colors">
                              <div className="w-40 shrink-0">
                                 <span className={`inline-flex items-center justify-center px-2.5 py-1 text-[10px] font-bold uppercase rounded-md mb-2 ${gap.status === 'MATCH' ? 'bg-green-100 text-green-700' : gap.status === 'WARNING' ? 'bg-amber-100 text-amber-700' : 'bg-red-100 text-red-700'}`}>
                                    {gap.status}
                                 </span>
                                 <h5 className="font-bold text-sm text-slate-800 leading-tight">{gap.category}</h5>
                              </div>
                              <div className="flex-1 grid grid-cols-1 md:grid-cols-2 gap-4">
                                 <div className="bg-amber-50/30 p-3 rounded-lg border border-amber-100 group hover:border-amber-300">
                                    <span className="block text-[10px] font-bold text-amber-800/60 uppercase mb-1">Franchise Demands</span>
                                    <p className="text-sm text-slate-700 leading-relaxed font-medium">{gap.franchise_requirement}</p>
                                 </div>
                                 <div className="bg-slate-50/50 p-3 rounded-lg border border-slate-200 group hover:border-slate-300">
                                    <span className="block text-[10px] font-bold text-slate-500 uppercase mb-1">Lease Provides</span>
                                    <p className="text-sm text-slate-700 leading-relaxed font-medium">{gap.lease_provision}</p>
                                 </div>
                              </div>
                           </div>
                         ))
                       )}
                     </div>
                  </div>

                </div>
              ) : (
                 <div className="flex-1 h-full flex flex-col items-center justify-center text-red-500 gap-4">
                    <ShieldAlert size={40} />
                    <p className="font-bold text-sm">Failed to extract gap analysis.</p>
                 </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Timeline Modal */}
      {showTimelineModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-5xl h-[85vh] flex flex-col overflow-hidden">
            <div className="px-6 py-4 border-b border-slate-200 flex justify-between items-center bg-slate-50 shrink-0">
              <h2 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <Clock className="text-brand-accent" size={18} /> Fundamental Terms
              </h2>
              <div className="flex items-center gap-3">
                <button onClick={() => executeTimelineGeneration(true)} disabled={isGeneratingTimeline} className="text-xs flex items-center gap-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 py-1.5 px-3 rounded-md transition-colors disabled:opacity-50"><RefreshCw size={14}/> {isGeneratingTimeline ? "Extracting..." : "Refresh"}</button>
                {library.map((doc, i) => (
                    <button key={i} onClick={() => handleDownloadOriginal(doc.id, doc.filename)} className="text-xs flex items-center gap-1.5 bg-brand-blue/10 hover:bg-brand-blue/20 text-brand-blue py-1.5 px-3 rounded-md transition-colors" title={`Download ${doc.filename}`}><Download size={14}/> PDF {i+1}</button>
                ))}
                <button onClick={() => handleExportPDF("timeline-modal-content", "timeline_characters")} className="text-xs flex items-center gap-1.5 bg-emerald-50 hover:bg-emerald-100 text-emerald-700 py-1.5 px-3 rounded-md transition-colors"><FileText size={14}/> Export</button>
                <button 
                  onClick={() => {
                     if(isGeneratingTimeline) {
                        if(!window.confirm("Timeline generation is still running explicitly in the background. Are you sure you want to close?")) return;
                     }
                     setShowTimelineModal(false);
                  }} 
                  className="p-1 text-slate-400 hover:text-slate-900 rounded-lg hover:bg-slate-200 transition-colors ml-2"
                >
                  <X size={16} />
                </button>
              </div>
            </div>
            
            <div id="timeline-modal-content" className="print-target flex-1 overflow-hidden flex flex-col bg-white">
              {isGeneratingTimeline ? (
                 <div className="flex-1 flex flex-col items-center justify-center text-slate-400 gap-4">
                    <Loader2 size={40} className="animate-spin text-brand-accent" />
                    <p className="font-bold text-sm text-slate-500 animate-pulse tracking-wide">{pipelineProgress || "Synthesizing multiple documents into a chronological history..."}</p>
                 </div>
              ) : timelineData ? (
                 <div className="w-full flex flex-col h-full overflow-hidden">
                   {timelineData.document_context?.location && (
                     <div className="bg-slate-50 border-b border-slate-200 px-6 py-3 shrink-0 flex items-center gap-2">
                       <MapPin size={16} className="text-slate-400" />
                       <span className="text-sm font-medium text-slate-700"><strong>Property Location:</strong> {timelineData.document_context.location}</span>
                     </div>
                   )}
                   <div className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-8 bg-slate-50/50">
                     
                     {/* Parties Section */}
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                        {/* Lessor Card */}
                        <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6">
                          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <Building2 size={16} className="text-brand-blue" /> Lessor
                          </h3>
                          <div className="space-y-3">
                            <div><span className="text-[10px] uppercase text-slate-400 font-bold">Name</span><p className="text-sm font-medium text-slate-900">{timelineData.fundamental_terms?.lessor?.name || "N/A"}</p></div>
                            <div><span className="text-[10px] uppercase text-slate-400 font-bold">Registration</span><p className="text-sm text-slate-700">{timelineData.fundamental_terms?.lessor?.registration || "N/A"}</p></div>
                            <div><span className="text-[10px] uppercase text-slate-400 font-bold">Representative</span><p className="text-sm text-slate-700">{timelineData.fundamental_terms?.lessor?.representative || "N/A"}</p></div>
                            <div><span className="text-[10px] uppercase text-slate-400 font-bold">Domicilium</span><p className="text-sm text-slate-700 text-balance">{timelineData.fundamental_terms?.lessor?.domicilium || "N/A"}</p></div>
                          </div>
                        </div>

                        {/* Lessee Card */}
                        <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6">
                          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <Users size={16} className="text-brand-accent" /> Lessee
                          </h3>
                          <div className="space-y-3">
                            <div><span className="text-[10px] uppercase text-slate-400 font-bold">Name</span><p className="text-sm font-medium text-slate-900">{timelineData.fundamental_terms?.lessee?.name || "N/A"}</p></div>
                            <div><span className="text-[10px] uppercase text-slate-400 font-bold">Registration</span><p className="text-sm text-slate-700">{timelineData.fundamental_terms?.lessee?.registration || "N/A"}</p></div>
                            <div><span className="text-[10px] uppercase text-slate-400 font-bold">Representative</span><p className="text-sm text-slate-700">{timelineData.fundamental_terms?.lessee?.representative || "N/A"}</p></div>
                            <div><span className="text-[10px] uppercase text-slate-400 font-bold">Domicilium</span><p className="text-sm text-slate-700 text-balance">{timelineData.fundamental_terms?.lessee?.domicilium || "N/A"}</p></div>
                          </div>
                        </div>
                     </div>

                     {/* Premises & Operating Metrics */}
                     <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 mb-6">
                        <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4 border-b border-slate-100 pb-3">Premises & Key Metrics</h3>
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                           <div><span className="text-[10px] uppercase text-slate-400 font-bold">Description</span><p className="text-sm font-medium text-slate-800">{timelineData.fundamental_terms?.premises?.description || "N/A"}</p></div>
                           <div><span className="text-[10px] uppercase text-slate-400 font-bold">Address</span><p className="text-sm text-slate-700">{timelineData.fundamental_terms?.premises?.address || "N/A"}</p></div>
                           <div><span className="text-[10px] uppercase text-slate-400 font-bold">ERF</span><p className="text-sm text-slate-700">{timelineData.fundamental_terms?.premises?.erf || "N/A"}</p></div>
                           
                           <div className="lg:col-span-3 pt-4 border-t border-slate-100 grid grid-cols-1 md:grid-cols-3 gap-6">
                             <div><span className="text-[10px] uppercase text-slate-400 font-bold">Permitted Use</span><p className="text-sm text-slate-800 border-l-2 border-brand-accent pl-3 mt-1 py-1">{timelineData.fundamental_terms?.permitted_use || "N/A"}</p></div>
                             <div><span className="text-[10px] uppercase text-slate-400 font-bold">Trading Hours</span>
                                 <ul className="text-xs text-slate-700 mt-1 space-y-1">
                                    <li><span className="font-medium">Mon-Thu:</span> {timelineData.fundamental_terms?.trading_hours?.monday_thursday || "N/A"}</li>
                                    <li><span className="font-medium">Friday:</span> {timelineData.fundamental_terms?.trading_hours?.friday || "N/A"}</li>
                                    <li><span className="font-medium">Saturday:</span> {timelineData.fundamental_terms?.trading_hours?.saturday || "N/A"}</li>
                                    <li><span className="font-medium">Sun/PH:</span> {timelineData.fundamental_terms?.trading_hours?.sunday_public_holidays || "N/A"}</li>
                                 </ul>
                             </div>
                             <div><span className="text-[10px] uppercase text-slate-400 font-bold">Security Deposit</span><p className="text-sm font-bold text-amber-600 bg-amber-50 px-3 py-2 rounded-lg mt-1 border border-amber-200">{timelineData.fundamental_terms?.security_deposit || "N/A"}</p></div>
                           </div>
                        </div>
                     </div>

                     {/* Financial & Timeframe Grid */}
                     <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
                        {/* Critical Dates */}
                        <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6">
                          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <Clock size={16} className="text-emerald-500" /> Critical Dates
                          </h3>
                          <div className="space-y-4">
                            <div className="flex justify-between items-center border-b border-slate-50 pb-2"><span className="text-[11px] font-bold text-slate-500 uppercase">Lease Period</span><span className="text-sm font-bold text-slate-800">{timelineData.fundamental_terms?.lease_period || "N/A"}</span></div>
                            <div className="flex justify-between items-center border-b border-slate-50 pb-2"><span className="text-[11px] font-bold text-slate-500 uppercase">Commencement</span><span className="text-sm font-medium text-slate-800">{timelineData.fundamental_terms?.commencement_date || "N/A"}</span></div>
                            <div className="flex justify-between items-center border-b border-slate-50 pb-2"><span className="text-[11px] font-bold text-slate-500 uppercase">Expiry Date</span><span className="text-sm font-bold text-rose-600">{timelineData.fundamental_terms?.expiry_date || "N/A"}</span></div>
                            <div className="flex justify-between items-center border-b border-slate-50 pb-2"><span className="text-[11px] font-bold text-slate-500 uppercase">Beneficial Occupation</span><span className="text-sm font-medium text-slate-800">{timelineData.fundamental_terms?.beneficial_occupation_date || "N/A"}</span></div>
                            <div className="flex justify-between items-center"><span className="text-[11px] font-bold text-slate-500 uppercase">Renewal Option</span><span className="text-sm font-medium text-brand-blue bg-brand-blue/10 px-2 py-0.5 rounded">{timelineData.fundamental_terms?.renewal_option || "None"}</span></div>
                          </div>
                        </div>

                        {/* Payment & Escalation */}
                        <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6">
                          <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest mb-4 flex items-center gap-2">
                            <Database size={16} className="text-indigo-500" /> Financial Details
                          </h3>
                          <div className="space-y-4 mb-6">
                            <div className="flex justify-between items-center pb-2 border-b border-slate-50"><span className="text-[11px] font-bold text-slate-500 uppercase">Escalation Rate</span><span className="text-sm font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-100">{timelineData.fundamental_terms?.escalation_rate || "N/A"}</span></div>
                            <div className="flex justify-between items-center pb-2 border-b border-slate-50"><span className="text-[11px] font-bold text-slate-500 uppercase">Suretyship</span><span className="text-sm font-medium text-slate-700">{timelineData.fundamental_terms?.suretyship || "None specified"}</span></div>
                          </div>
                          
                          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200">
                             <span className="block text-[10px] uppercase font-bold text-slate-400 mb-2">Banking Details</span>
                             <div className="grid grid-cols-2 gap-2 text-xs">
                                <div><span className="text-slate-500">Bank:</span> <span className="font-medium">{timelineData.fundamental_terms?.payment_details?.bank || "N/A"}</span></div>
                                <div><span className="text-slate-500">Branch:</span> <span className="font-medium">{timelineData.fundamental_terms?.payment_details?.branch || "N/A"}</span></div>
                                <div><span className="text-slate-500">Account:</span> <span className="font-medium">{timelineData.fundamental_terms?.payment_details?.account_number || "N/A"}</span></div>
                                <div><span className="text-slate-500">Type:</span> <span className="font-medium">{timelineData.fundamental_terms?.payment_details?.account_type || "N/A"}</span></div>
                             </div>
                          </div>
                        </div>
                     </div>

                     {/* Rental Schedule Table */}
                     {timelineData.fundamental_terms?.rental_schedule && timelineData.fundamental_terms.rental_schedule.length > 0 && (
                       <div className="bg-white border border-slate-200 shadow-sm rounded-2xl overflow-hidden mb-6">
                          <div className="bg-slate-50 px-6 py-4 border-b border-slate-200">
                             <h3 className="text-xs font-bold text-slate-600 uppercase tracking-widest">Rental Schedule</h3>
                          </div>
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm text-left">
                               <thead className="bg-slate-50/50 text-xs uppercase text-slate-500 font-bold border-b border-slate-100">
                                  <tr>
                                     <th className="px-6 py-3 whitespace-nowrap">Period</th>
                                     <th className="px-6 py-3 whitespace-nowrap">Monthly Amount</th>
                                     <th className="px-6 py-3 w-full">Notes</th>
                                  </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-100">
                                   {timelineData.fundamental_terms.rental_schedule.map((rent, i) => (
                                      <tr key={i} className="hover:bg-slate-50 transition-colors">
                                         <td className="px-6 py-3 font-medium text-slate-700 whitespace-nowrap">{rent.period || "N/A"}</td>
                                         <td className="px-6 py-3 font-bold text-emerald-700 whitespace-nowrap">{rent.amount || "N/A"}</td>
                                         <td className="px-6 py-3 text-slate-500 text-xs">{rent.note || "-"}</td>
                                      </tr>
                                   ))}
                                </tbody>
                            </table>
                          </div>
                       </div>
                     )}

                     {/* Special Conditions */}
                     {timelineData.fundamental_terms?.special_conditions && timelineData.fundamental_terms.special_conditions.length > 0 && (
                       <div className="bg-rose-50/50 border border-rose-100 shadow-sm rounded-2xl p-6 mb-6">
                          <h3 className="text-xs font-bold text-rose-800 uppercase tracking-widest mb-4 flex items-center gap-2">
                             <ShieldAlert size={16} /> Special Conditions
                          </h3>
                          <ul className="list-disc pl-5 space-y-2 text-sm text-slate-800">
                             {timelineData.fundamental_terms.special_conditions.map((cond, i) => (
                               <li key={i} className="leading-relaxed">{cond}</li>
                             ))}
                          </ul>
                       </div>
                     )}
                     
                   </div>
                 </div>
              ) : (
                 <div className="flex-1 flex flex-col items-center justify-center text-red-500 gap-4">
                    <ShieldAlert size={40} />
                    <p className="font-bold text-sm">Failed to extract timeline data.</p>
                 </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* PDF Viewer Pane */}
      {selectedDocId && (
        <div className="w-1/3 min-w-[320px] max-w-[450px] glass-panel border-l border-white/10 flex flex-col z-20">
          <div className="p-4 border-b border-white/5 flex items-center justify-between bg-transparent shrink-0">
             <div className="flex items-center gap-2 text-slate-200 font-semibold text-sm truncate pr-4">
                <FileText size={16} className="text-brand-blue shrink-0" />
                <span className="truncate">{library.find(d => d.id === selectedDocId)?.name}</span>
             </div>
             <button onClick={() => setSelectedDocId(null)} className="text-slate-400 hover:text-red-500 transition-colors p-1 rounded-full hover:bg-slate-100 shrink-0">
                <X size={18} />
             </button>
          </div>

           {/* ── Document Brief ── */}
           {docBriefs[selectedDocId] && (() => {
             const brief = docBriefs[selectedDocId];
             return (
               <details className="shrink-0 border-b border-slate-200 bg-amber-50/40 group">
                 <summary className="flex items-center justify-between px-4 py-2.5 cursor-pointer list-none select-none hover:bg-amber-50 transition-colors">
                   <span className="flex items-center gap-2 text-xs font-bold text-amber-700 uppercase tracking-widest">
                     <Zap size={12} className="text-amber-500" />
                     Document Details
                     {brief.doc_type && <span className="font-normal text-amber-600 normal-case tracking-normal ml-1">— {brief.doc_type}</span>}
                   </span>
                   <ChevronRight size={14} className="text-amber-500 group-open:rotate-90 transition-transform" />
                 </summary>
                 <div className="px-4 pb-4 pt-1 space-y-3 text-xs">
                   {/* Summary */}
                   {brief.summary && (
                     <p className="text-slate-600 leading-relaxed font-medium bg-white p-2 border border-amber-200 shadow-sm rounded-md">{brief.summary}</p>
                   )}
                   {/* Parties */}
                   {brief.parties?.length > 0 && (
                     <div>
                       <p className="font-bold text-slate-500 uppercase tracking-widest text-[10px] mb-1">Parties</p>
                       <div className="flex flex-wrap gap-1.5">
                         {brief.parties.map((p, i) => (
                           <span key={i} className="bg-white border border-slate-200 shadow-sm text-slate-700 px-2 py-0.5 rounded-full font-medium">{p}</span>
                         ))}
                       </div>
                     </div>
                   )}
                   {/* Key Dates */}
                   {brief.key_dates?.length > 0 && (
                     <div>
                       <p className="font-bold text-slate-500 uppercase tracking-widest text-[10px] mb-1">Key Dates</p>
                       <div className="space-y-1 bg-white p-2 rounded-md shadow-sm border border-slate-200">
                         {brief.key_dates.map((d, i) => (
                           <div key={i} className="flex justify-between text-slate-700">
                             <span className="text-slate-500">{d.label}</span>
                             <span className="font-bold text-slate-800">{d.value}</span>
                           </div>
                         ))}
                       </div>
                     </div>
                   )}
                   {/* Financial Terms */}
                   {brief.financial_terms?.length > 0 && (
                     <div>
                       <p className="font-bold text-slate-500 uppercase tracking-widest text-[10px] mb-1">Financial Terms</p>
                       <ul className="space-y-1 list-disc pl-4 text-slate-700 text-[11px] leading-relaxed">
                         {brief.financial_terms.map((r, i) => (
                           <li key={i}>{r}</li>
                         ))}
                       </ul>
                     </div>
                   )}
                   {/* Obligations */}
                   {brief.obligations?.length > 0 && (
                     <div>
                       <p className="font-bold text-slate-500 uppercase tracking-widest text-[10px] mb-1">Core Obligations</p>
                       <ul className="space-y-1 list-disc pl-4 text-slate-700 text-[11px] leading-relaxed">
                         {brief.obligations.map((r, i) => (
                           <li key={i}>{r}</li>
                         ))}
                       </ul>
                     </div>
                   )}
                   {/* Execution Status */}
                   {brief.execution_status && (
                     <div>
                       <p className="font-bold text-slate-500 uppercase tracking-widest text-[10px] mb-1">Execution Status</p>
                       <p className="text-amber-800 font-medium bg-amber-100/50 p-2 rounded-md border border-amber-200 text-[11px]">{brief.execution_status}</p>
                     </div>
                   )}
                 </div>
               </details>
             );
           })()}

          <div className="flex-1 bg-slate-900/50 overflow-y-auto flex justify-center py-6">
             <Document
                file={{
                  url: `${API_BASE}/document/${selectedDocId}`,
                  httpHeaders: {
                      Authorization: localStorage.getItem("rem_auth_token") ? `Bearer ${localStorage.getItem("rem_auth_token")}` : undefined,
                      "x-session-id": !localStorage.getItem("rem_auth_token") ? localStorage.getItem("session_id") : undefined
                  }
                }}
                loading={
                   <div className="flex flex-col items-center justify-center text-slate-400 h-full mt-32">
                      <Loader2 size={32} className="animate-spin mb-4 text-brand-blue" />
                      <span className="text-xs font-semibold">Loading PDF visuals...</span>
                   </div>
                }
                error={
                   <div className="text-sm text-red-500 text-center mt-32 px-4 font-semibold">Cannot render document visual. Verify the local server is serving the file bytes.</div>
                }
             >
                <Page 
                  pageNumber={selectedPage} 
                  renderTextLayer={true} 
                  renderAnnotationLayer={false} 
                  className="shadow-2xl border border-white/10"
                  width={400} 
                />
             </Document>
          </div>
          
          <div className="p-4 border-t border-white/10 glass-panel flex justify-between items-center shrink-0 rounded-b-2xl">
             <button disabled={selectedPage <= 1} onClick={() => setSelectedPage(p => Math.max(1, p - 1))} className="px-4 py-2 rounded-lg bg-white/5 text-slate-300 text-xs font-bold hover:bg-white/10 disabled:opacity-50 disabled:cursor-not-allowed transition-colors uppercase tracking-widest shadow-sm">Prev</button>
             <span className="text-xs font-bold text-slate-300 uppercase tracking-widest bg-white/5 px-3 py-1.5 rounded border border-white/10">Page {selectedPage}</span>
             <button onClick={() => setSelectedPage(p => p + 1)} className="px-4 py-2 rounded-lg bg-white/5 text-slate-300 text-xs font-bold hover:bg-white/10 transition-colors uppercase tracking-widest shadow-sm">Next</button>
          </div>
        </div>
      )}
    </div>
  );
}

// Dropzone for unauthenticated users on the landing page.
// Stores the dropped file in the module-level pendingDropFile, then navigates to /app
// where InnerApp's useEffect picks it up and auto-uploads.
function LandingDropzone({ navigate }) {
  const onDrop = useCallback((acceptedFiles) => {
    const file = acceptedFiles[0];
    if (!file) return;
    pendingDropFile = file;
    navigate('/app');
  }, [navigate]);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'application/pdf': ['.pdf'] },
    maxFiles: 1,
  });

  return (
    <div
      {...getRootProps()}
      className={`bg-white border-2 border-dashed rounded-3xl p-12 text-center cursor-pointer transition-all shadow-md ${
        isDragActive
          ? 'border-brand-accent bg-brand-blue/5 shadow-lg scale-[1.02]'
          : 'border-slate-300 hover:border-brand-accent hover:shadow-lg hover:scale-[1.01]'
      }`}
    >
      <input {...getInputProps()} />
      <div className="w-20 h-20 bg-slate-50 rounded-full mx-auto flex items-center justify-center mb-6 text-brand-blue shadow-sm border border-slate-200">
        <UploadCloud size={36} />
      </div>
      {isDragActive ? (
        <>
          <h3 className="text-2xl font-bold text-brand-accent mb-2">Drop it — we've got it.</h3>
          <p className="text-slate-500 font-medium">Release to analyse your document instantly</p>
        </>
      ) : (
        <>
          <h3 className="text-2xl font-bold text-slate-900 mb-2">Drop a PDF to try for free</h3>
          <p className="text-slate-600 mb-6 font-medium">
            Upload any residential or commercial lease for a Free Audit. Start extracting dates and risks immediately.
          </p>
          <div className="inline-flex items-center gap-2 bg-brand-blue hover:bg-brand-blue-dark text-white font-bold px-8 py-3 rounded-full shadow-md hover:shadow-lg transition-all text-sm border border-transparent">
            <UploadCloud size={16} /> Select a PDF
          </div>
          <p className="text-xs text-slate-500 mt-4">PDF files only · Analysed securely in your session</p>
        </>
      )}
    </div>
  );
}

// Separate Landing Page Component
function LandingPage() {
  const { token } = useAuth();
  const navigate = useNavigate();
  const [openFaq, setOpenFaq] = useState(null);

  const features = [
    {
      number: "01",
      title: "Instant Lease Analysis",
      hook: "Drop a 200-page lease. Get answers in 30 seconds.",
      body: "Upload any residential lease, commercial lease, or addendum. RealEstateMeta extracts every clause, obligation, escalation formula, critical date and red flag — then lets you interrogate the document like you wrote it yourself.",
      details: ["Clause extraction and categorisation","Escalation and renewal date mapping","Obligation and liability flagging","Natural language Q&A across the full document"],
    },
    {
      number: "02",
      title: "Portfolio Intelligence",
      hook: "See your entire lease book at a glance. Not one lease at a time.",
      body: "Surface patterns, risks and opportunities across your entire portfolio. Which tenants have below-market escalations? Which leases expire in Q1? Where are your maintenance obligations heaviest? What used to take a week of spreadsheet work now takes three clicks.",
      details: ["Cross-reference clauses across your full portfolio","Surface expiring leases and upcoming renewal windows","Compare escalation terms across tenants","Flag inconsistencies and non-standard clauses"],
    },
    {
      number: "03",
      title: "Firm Tier & Agency White-Labeling",
      hook: "Your tenant data stays yours. Full stop.",
      body: "Generate branded PDF risk-reports to send to your landlord clients. Pass the software cost onto landlords as an administration fee while keeping data strictly POPIA-compliant with enterprise encryption.",
      details: ["Client-branded PDF Risk Reports","Pass-through software billing","POPIA-compliant and Encrypted","Portfolio-wide firm administration"],
    },
  ];

  const steps = [
    { step: "1", title: "Upload", desc: "Drag in any lease — residential, commercial, sectional title, or addendum. PDF, Word, scanned — RealEstateMeta handles it." },
    { step: "2", title: "Ask", desc: 'Ask any question in plain English. "What are the escalation terms?" "When does this lease renew?" "What are my maintenance obligations?" "Flag every clause that favours the tenant."' },
    { step: "3", title: "Act", desc: "Get precise, sourced answers with clause references. Export, share with your team, or keep interrogating. Your lease portfolio is yours to command." },
  ];

  const faqs = [
    { q: "Is my lease data safe?", a: "Yes. RealEstateMeta uses enterprise-grade encryption, and we never retain your data on third-party model infrastructure. Your documents are processed and purged. Our architecture is POPIA-compliant because we believe property AI without bulletproof security isn't property AI — it's a liability." },
    { q: "Does it actually understand leases, or is this just ChatGPT with a skin?", a: "RealEstateMeta is purpose-built for lease document analysis. It understands clause structures, escalation formulas, renewal mechanisms, and South African property terminology. It doesn't hallucinate — every answer is grounded in the document you uploaded, with clause references you can verify." },
    { q: "Will this replace my property manager?", a: "No. It'll make them ten times more useful. RealEstateMeta handles the reading and extraction so your team can focus on negotiation, tenant relations, and the strategic decisions that actually grow your portfolio." },
    { q: "What lease types does it support?", a: "Commercial leases, residential leases, sectional title leases, industrial leases, ground leases, addendums, side letters, lease amendments — if it's a lease document, RealEstateMeta can read it. PDF, Word and scanned documents are all supported." },
    { q: "How long does analysis actually take?", a: "A typical 50-page lease is fully analysed in under 30 seconds. Longer or more complex documents take proportionally longer, but we're talking minutes, not the hours or days you're used to." },
    { q: "Can I analyse my whole portfolio at once?", a: "Yes. Upload your entire lease book and interrogate it as a single dataset. Ask portfolio-wide questions like \"Which leases expire in the next 12 months?\" or \"Show me all tenants with escalation rates below 7%.\"" },
    { q: "Is it compliant with South African legislation?", a: "Our platform is built with POPIA compliance at its core. We process data within secure, encrypted environments and retain nothing after your session. We can also help you identify clauses in your leases that may need updating for Rental Housing Act or Consumer Protection Act compliance." },
  ];

  return (
    <div className="min-h-screen relative bg-white flex flex-col font-sans text-slate-900 overflow-hidden">
      {/* ── NAV ── */}
      <nav className="sticky top-0 z-50 w-full h-18 px-8 flex items-center justify-between border-b border-slate-200 bg-white/80 backdrop-blur-xl">
        <div className="flex items-center">
          <img src="/rem-logo.png" alt="REM-Leases" className="h-8" />
        </div>
        <div className="flex items-center gap-6">
          <a href="#features" className="text-sm font-medium text-slate-600 hover:text-brand-blue hidden md:block transition-colors">Features</a>
          <a href="#security" className="text-sm font-medium text-slate-600 hover:text-brand-blue hidden md:block transition-colors">Security</a>
          <a href="#faq" className="text-sm font-medium text-slate-600 hover:text-brand-blue hidden md:block transition-colors">FAQ</a>
          {!token ? (
            <>
              <Link to="/login" className="text-sm font-medium text-slate-600 hover:text-brand-blue transition-colors">Login</Link>
              <Link to="/app" className="bg-brand-blue text-white text-sm font-bold px-5 py-2.5 rounded-full shadow-md hover:shadow-lg transition-all">Try it free</Link>
              <Link to="/signup" className="bg-brand-accent text-white text-sm font-bold px-5 py-2.5 rounded-full shadow-md hover:shadow-lg transition-all hidden md:inline-flex">Register Firm</Link>
            </>
          ) : (
            <Link to="/app" className="bg-brand-blue text-white text-sm font-bold px-5 py-2.5 rounded-full hover:bg-brand-blue-dark transition-colors shadow-md hover:shadow-lg">Go to Workspace</Link>
          )}
        </div>
      </nav>

      {/* ── HERO ── */}
      <section className="flex flex-col items-center justify-center text-center px-6 pt-24 pb-20 bg-slate-50 relative z-10 border-b border-slate-200">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full border border-brand-accent/30 bg-white text-brand-accent text-[11px] font-bold uppercase tracking-widest mb-8 shadow-sm">
            LEKKER FAST. DEAD ACCURATE. PORTFOLIO READY.
          </div>
          <h1 className="text-4xl md:text-6xl font-extrabold text-slate-900 leading-tight tracking-tight mb-6">
            Your leases have answers.<br />Stop digging through filing cabinets. Start asking.
          </h1>
          <p className="text-lg md:text-xl text-slate-600 max-w-2xl mx-auto leading-relaxed mb-10">
            lease.realestatemeta.ai reads your entire lease portfolio the way you wish your property manager could — in seconds, not days. Upload any lease. Ask any question. Get answers with clause references you can verify.
          </p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
            <Link to="/app" className="bg-brand-blue text-white font-bold px-8 py-4 rounded-xl shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all text-sm border border-transparent">
              Get your Free AI Lease Audit
            </Link>
            <span className="text-xs text-slate-500">No credit card. Free risk audit. Instant answers.</span>
          </div>
        </motion.div>
        {/* Hero dropzone for guests */}
        {!token && (
          <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.15 }} className="w-full max-w-xl mt-14">
            <LandingDropzone navigate={navigate} />
          </motion.div>
        )}
        {token && (
          <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: 0.15 }} className="mt-14">
            <div onClick={() => navigate('/app')} className="glass-panel rounded-2xl p-10 text-center cursor-pointer hover:border-brand-blue/50 hover:shadow-lg transition-all bg-white">
              <FolderOpen size={48} className="mx-auto mb-4 text-brand-blue" />
              <h3 className="font-bold text-slate-900 text-lg mb-1">Open Property Portfolios</h3>
              <p className="text-slate-500 text-sm">Continue to your leases →</p>
            </div>
          </motion.div>
        )}
      </section>

      {/* ── SOCIAL PROOF ── */}
      <section className="bg-slate-50 border-y border-slate-200 px-6 py-10 text-center relative z-10">
        <p className="text-slate-600 text-sm max-w-2xl mx-auto leading-relaxed">
          Trusted by landlords, asset managers and property professionals who manage portfolios — not paperwork.
        </p>
        <div className="flex items-center justify-center gap-2 mt-4 text-xs text-brand-blue font-bold uppercase tracking-widest">
          <Lock size={12} /> POPIA Compliant &nbsp;·&nbsp; <Shield size={12} className="text-brand-accent" /> End-to-end encrypted &nbsp;·&nbsp; <Zap size={12} /> Results in 30 seconds
        </div>
      </section>

      {/* ── PROBLEM ── */}
      <section className="px-6 py-24 max-w-4xl mx-auto w-full relative z-10">
        <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 mb-14 text-center">The property management problem.</h2>
        <div className="grid md:grid-cols-3 gap-8">
          {[
            { pain: "Manual lease extraction is slow and error-prone.", detail: "Reading through every lease to find termination rights, maintenance obligations, or escalation formulas takes hours per document. Multiply that across a portfolio and it becomes impossible." },
            { pain: "You have no portfolio-wide visibility.", detail: "Which leases have favourable escalation clauses? Which tenants have first right of refusal? Nobody knows without manual digging through hundreds of pages." },
            { pain: "Compliance risk and costly legal reviews.", detail: "Non-compliance with POPIA and the Rental Housing Act carries heavy fines. Sending every lease to an attorney at R2,500/hour for routine clauses is wasteful." },
          ].map((p, i) => (
            <div key={i} className="border-l-4 border-brand-accent/30 pl-5 bg-white p-6 shadow-sm rounded-xl border-y border-r border-slate-100">
              <p className="font-bold text-slate-900 text-sm mb-2">{p.pain}</p>
              <p className="text-slate-600 text-sm leading-relaxed">{p.detail}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── FEATURES ── */}
      <section id="features" className="bg-white px-6 py-24 relative z-10 grid-bg">
        <div className="max-w-4xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 mb-4 text-center">
            Three things that change how you manage your leases.
          </h2>
          <p className="text-slate-500 text-center mb-16 text-sm">Purpose-built for property. Not repurposed from a legal tool.</p>
          <div className="grid md:grid-cols-3 gap-6">
            {features.map((f) => (
              <div key={f.number} className="p-6 group relative overflow-hidden bg-white border border-slate-200 shadow-sm rounded-2xl cursor-default hover:shadow-md transition-shadow">
                <div className="absolute top-0 right-0 w-32 h-32 bg-brand-blue/5 group-hover:bg-brand-blue/10 transition-all rounded-full pointer-events-none -mr-10 -mt-10" />
                <div className="flex items-center gap-2 mb-4 relative z-10">
                  <span className="text-brand-accent font-mono font-bold text-xs">{f.number}</span>
                  <span className="text-slate-500 text-xs uppercase tracking-widest font-medium group-hover:text-brand-blue transition-colors">{f.title}</span>
                </div>
                <h3 className="text-slate-900 font-bold text-base mb-3 leading-snug relative z-10">{f.hook}</h3>
                <p className="text-slate-600 text-sm leading-relaxed mb-6 relative z-10">{f.body}</p>
                <div className="flex flex-wrap gap-2 relative z-10 mt-auto pt-4 border-t border-slate-100">
                  {f.details.map((d, i) => (
                    <span key={i} className="text-[10px] text-brand-blue font-semibold bg-brand-blue/5 px-2.5 py-1 rounded-full border border-brand-blue/20">{d}</span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className="px-6 py-24 max-w-4xl mx-auto w-full relative z-10">
        <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 text-center mb-16">Three steps. That's it.</h2>
        <div className="grid md:grid-cols-3 gap-6">
          {steps.map((s) => (
            <div key={s.step} className="p-8 relative overflow-hidden group bg-slate-50 border border-slate-200 shadow-sm rounded-2xl cursor-default hover:border-brand-accent/30 hover:shadow-md transition-all">
              <div className="absolute -right-6 -top-6 text-9xl font-black text-slate-200 group-hover:text-brand-accent/10 transition-colors duration-500 pointer-events-none">{s.step}</div>
              <div className="text-3xl font-extrabold text-brand-accent mb-4 relative z-10">{s.title}</div>
              <h3 className="font-bold text-lg mb-2 relative z-10 text-brand-blue hidden">{s.title}</h3>
              <p className="text-slate-600 text-sm leading-relaxed relative z-10">{s.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── FAQ ── */}
      <section id="faq" className="bg-slate-50 border-y border-slate-200 px-6 py-24 relative z-10">
        <div className="max-w-2xl mx-auto">
          <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 text-center mb-14">Questions you should be asking.</h2>
          <div className="divide-y divide-slate-200">
            {faqs.map((item, i) => (
              <div key={i} className="py-5 cursor-pointer group" onClick={() => setOpenFaq(openFaq === i ? null : i)}>
                <div className="flex justify-between items-center gap-4">
                  <span className="font-semibold text-slate-900 text-sm group-hover:text-brand-blue transition-colors">{item.q}</span>
                  <span className={`text-slate-400 text-xl transition-transform duration-200 group-hover:text-brand-accent ${openFaq === i ? 'rotate-45 text-brand-accent' : ''}`}>+</span>
                </div>
                {openFaq === i && (
                  <p className="mt-4 text-slate-600 text-sm leading-relaxed pr-6 bg-white p-4 rounded-xl border border-slate-200 shadow-sm">{item.a}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section id="security" className="px-6 py-24 relative z-10">
        <div className="max-w-2xl mx-auto bg-white border border-slate-200 rounded-3xl p-12 text-center relative overflow-hidden shadow-xl">
          <div className="absolute inset-0 bg-gradient-to-br from-brand-blue/5 to-transparent opacity-50 pointer-events-none"></div>
          <h2 className="text-3xl md:text-4xl font-extrabold text-slate-900 mb-4 leading-tight relative z-10">
            Your next lease review is waiting.<br />Stop reading. Start asking.
          </h2>
          <p className="text-slate-600 text-sm mb-8 relative z-10">Drop your first lease below to get your Free Audit. Discover risks and missing clauses in 30 seconds.</p>
          <Link to="/app" className="inline-block bg-brand-blue text-white font-bold px-8 py-4 rounded-xl shadow-md hover:shadow-lg hover:-translate-y-0.5 transition-all text-sm relative z-10">
            Try it free
          </Link>
          <p className="text-slate-500 text-xs mt-6 relative z-10">No credit card required.</p>
          <p className="text-slate-500 text-xs mt-2 relative z-10">Prefer a walkthrough? <Link to="/how-to" className="text-brand-blue hover:underline font-semibold">Book a 15-minute demo</Link> with our team.</p>
        </div>
      </section>

      {/* ── FOOTER ── */}
      <footer className="border-t border-slate-200 bg-white px-8 py-10 flex flex-col md:flex-row items-center justify-between gap-6 text-sm relative z-10">
        <img src="/rem-logo.png" alt="REM-Leases" className="h-7" />
        <div className="flex flex-wrap items-center justify-center gap-6 text-slate-500 text-xs font-medium">
          <Link to="/how-to" className="hover:text-slate-900 transition-colors">How to Use</Link>
          <Link to="/privacy" className="hover:text-slate-900 transition-colors">Privacy Policy</Link>
          <Link to="/terms" className="hover:text-slate-900 transition-colors">Terms &amp; Conditions</Link>
          <Link to="/pricing" className="hover:text-brand-blue transition-colors">Enterprise Pricing</Link>
        </div>
        <p className="text-xs text-slate-400">© {new Date().getFullYear()} RealEstateMeta — Lekker fast. Dead accurate. Portfolio ready.</p>
      </footer>

    </div>
  );
}




export default function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
          <Router>
              <Routes>
                  <Route path="/" element={<LandingPage />} />
                  <Route path="/login" element={<AuthScreen isLogin={true} />} />
                  <Route path="/signup" element={<AuthScreen isLogin={false} />} />
                  
                  <Route path="/terms" element={<TermsConditions />} />
                  <Route path="/privacy" element={<PrivacyPolicy />} />
                  <Route path="/how-to" element={<HowToUse />} />

                  <Route path="/app" element={
                      <ProtectedRoute>
                          <InnerApp />
                      </ProtectedRoute>
                  } />
                  
                  <Route path="*" element={<Navigate to="/" />} />
              </Routes>
          </Router>
      </AuthProvider>
    </ErrorBoundary>
  );
}
