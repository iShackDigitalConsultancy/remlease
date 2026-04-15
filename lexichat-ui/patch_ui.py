import re

with open("src/App.jsx", "r") as f:
    content = f.read()

# 1. State for sidebar search
search_state = """
  // Sidebar Search State
  const [sidebarSearch, setSidebarSearch] = useState('');
"""
content = re.sub(r'(const \[editingCaseName, setEditingCaseName\] = useState\(\'\'\);)', r'\1\n' + search_state, content)

# 2. Sidebar Search Bar & Title Update
sidebar_top = """
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
"""
content = re.sub(r'(<div className="flex items-center justify-between mb-3 px-2 text-xs font-bold text-brand-blue uppercase tracking-widest">[\s\S]*?</button>\s*</div>)', sidebar_top, content)

# 3. Filter cases mapping
content = re.sub(r'\{cases\.map\(c => \(', r'{cases.filter(c => c.name.toLowerCase().includes(sidebarSearch.toLowerCase())).map(c => (', content)

# 4. Click routing for doc
new_doc_click = """onClick={() => {
                                                 if (doc.workspace_id) {
                                                     setActiveCaseId(doc.workspace_id);
                                                     setActiveView('workspace');
                                                     setSelectedDocId(doc.doc_id);
                                                 }
                                             }}"""
content = re.sub(r'onClick=\{\(\) => \{\s*if \(doc\.workspace_id\) \{\s*setActiveCaseId\(doc\.workspace_id\);\s*setActiveView\(\'workspace\'\);\s*\}\s*\}\}', new_doc_click, content)

# 5. Fix matter spelling
content = content.replace('Continue to your matters', 'Continue to your leases')

with open("src/App.jsx", "w") as f:
    f.write(content)

with open("src/index.css", "a") as f:
    f.write("\n@media print {\n  @page {\n    size: landscape;\n    margin: 1cm;\n  }\n}\n")
