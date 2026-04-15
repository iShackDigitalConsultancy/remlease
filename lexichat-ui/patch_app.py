import re

with open("src/App.jsx", "r") as f:
    content = f.read()

# 1. State logic
state_logic = """
  // Portfolio Dashboard State
  const [activeView, setActiveView] = useState('workspace'); // 'workspace' or 'portfolio'
  const [portfolioData, setPortfolioData] = useState(null);
  const [isFetchingPortfolio, setIsFetchingPortfolio] = useState(false);

  const fetchPortfolioOverview = useCallback(async (forceRefresh = false) => {
    if (!forceRefresh && portfolioData) return;
    setIsFetchingPortfolio(true);
    try {
      const headers = token ? { Authorization: `Bearer ${token}` } : { 'x-session-id': sessionId };
      const res = await axios.get(`${API_BASE}/portfolio-overview`, { headers });
      const sorted = res.data.data.sort((a,b) => {
          if (!a.expiry_date && !b.expiry_date) return 0;
          if (!a.expiry_date) return 1;
          if (!b.expiry_date) return -1;
          return new Date(a.expiry_date) - new Date(b.expiry_date);
      });
      setPortfolioData(sorted);
    } catch(err) {
      console.error(err);
      alert("Failed to run portfolio overview.");
    } finally {
      setIsFetchingPortfolio(false);
    }
  }, [portfolioData, token, sessionId]);

  useEffect(() => {
     if(activeView === 'portfolio' && !portfolioData) {
         fetchPortfolioOverview();
     }
  }, [activeView, portfolioData, fetchPortfolioOverview]);
"""
# Insert after "const [isExtractingExpiries, setIsExtractingExpiries] = useState(false);"
content = re.sub(r'(const \[isExtractingExpiries, setIsExtractingExpiries\] = useState\(false\);)', r'\1\n' + state_logic, content)

# 2. Sidebar Button
sidebar_button = """
              <button 
                  onClick={() => setActiveView('portfolio')}
                  className={`w-full text-left flex items-center gap-2 px-3 py-2.5 rounded-lg font-bold text-sm transition-colors mb-6 ${activeView === 'portfolio' ? 'bg-brand-blue text-white shadow-md' : 'bg-white border border-slate-200 text-slate-700 hover:bg-slate-100 hover:border-slate-300'}`}
              >
                  <Building2 size={16} /> Global Portfolio Dashboard
              </button>
"""
# Insert before "<span>Property Portfolios</span>"
content = re.sub(r'(<div className="mb-4 shrink-0">\s*<div className="flex items-center justify-between mb-3 px-2 text-xs font-bold text-brand-blue uppercase tracking-widest">)', sidebar_button + r'\1', content)

# 3. Add to Workspace onClick logic to set activeView
content = re.sub(r'if \(editingCaseId !== c\.id\) setActiveCaseId\(c\.id\);', r'if (editingCaseId !== c.id) setActiveCaseId(c.id);\n                              setActiveView(\'workspace\');', content)

# 4. Wrap Chat Interface
portfolio_ui = """
      {/* Portfolio Overview */}
      {activeView === 'portfolio' && (
        <div className="flex-1 overflow-y-auto bg-slate-50 p-8 z-10 flex flex-col h-full relative">
            <div className="max-w-6xl mx-auto w-full">
               <div className="flex justify-between items-center mb-8">
                  <div>
                      <h1 className="text-2xl font-black text-slate-900 tracking-tight flex items-center gap-2"><Building2 className="text-brand-blue" /> Global Portfolio Dashboard</h1>
                      <p className="text-slate-500 mt-1">Unified view of all leases and franchise agreements across the firm.</p>
                  </div>
                  <button 
                     onClick={() => fetchPortfolioOverview(true)}
                     disabled={isFetchingPortfolio}
                     className="bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 px-4 py-2 rounded-xl font-bold text-sm shadow-sm flex items-center gap-2 hover:shadow disabled:opacity-50 transition-all"
                  >
                     {isFetchingPortfolio ? <><Loader2 size={16} className="animate-spin text-brand-blue" /> Syncing...</> : <><Database size={16} className="text-brand-blue" /> Refresh Portfolio Data</>}
                  </button>
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
                                         <p className="font-bold text-sm text-slate-900 leading-tight">{doc.filename}</p>
                                         <span className={`inline-block mt-2 px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wide ${doc.doc_type?.toLowerCase().includes('franchise') ? 'bg-brand-blue/10 text-brand-blue' : 'bg-slate-100 text-slate-600'}`}>
                                            {doc.doc_type || 'Unknown'}
                                         </span>
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
"""

content = content.replace('{/* Chat Interface */}', portfolio_ui)

# Need to close the conditional around line 996 (where the chat div ends, just before `{showLimitModal && (`)
end_div_pattern = r'(</div>\s*)({\s*showLimitModal\s*&&)'
content = re.sub(end_div_pattern, r'\1      )}\n\n\2', content)

with open("src/App.jsx", "w") as f:
    f.write(content)
