import React from 'react';
import { Shield, Book, Globe } from 'lucide-react';
import { Link } from 'react-router-dom';

const PageLayout = ({ title, icon, children }) => (
    <div className="min-h-screen bg-slate-900/50 flex flex-col font-sans text-slate-300">
        <nav className="w-full h-16 px-8 flex items-center justify-between border-b border-white/10 glass-panel sticky top-0 z-50">
            <Link to="/" className="font-bold text-xl tracking-tight text-white flex flex-row items-center gap-2">
                <GlobIcon /> REM-Leases
            </Link>
            <div className="flex gap-6 items-center">
                <Link to="/how-to" className="text-sm font-medium text-slate-500 hover:text-white">How to Use</Link>
                <Link to="/login" className="text-sm font-bold text-brand-blue">Login</Link>
            </div>
        </nav>
        <main className="flex-1 max-w-4xl mx-auto w-full p-8 md:p-12">
            <div className="flex items-center gap-4 mb-8 pb-4 border-b border-white/10">
                <div className="p-3 bg-brand-blue text-white rounded-xl">{icon}</div>
                <h1 className="text-4xl font-extrabold text-white">{title}</h1>
            </div>
            <div className="prose prose-invert max-w-none prose-headings:text-white prose-a:text-brand-blue">
                {children}
            </div>
        </main>
        <footer className="w-full border-t border-white/10 glass-panel p-6 text-center text-sm text-slate-400">
            &copy; {new Date().getFullYear()} REM-Leases. All rights reserved. Not legal advice.
        </footer>
    </div>
);

const GlobIcon = () => <div className="w-6 h-6 rounded bg-brand-blue text-white flex items-center justify-center text-xs">⚖️</div>;

export const PrivacyPolicy = () => (
    <PageLayout title="Privacy Policy" icon={<Shield size={28} />}>
        <p className="lead italic">Last Updated: {new Date().toLocaleDateString()}</p>
        
        <h2>1. Introduction</h2>
        <p>REM-Leases ("we," "us," or "our") respects your privacy and ensures the protection of Personal Information in compliance with the <strong>Protection of Personal Information Act, No. 4 of 2013 (POPIA)</strong> of South Africa.</p>

        <h2>2. Data Collection and Processing</h2>
        <p>We collect and process personal data, including documents uploaded to Case Workspaces, solely for the purpose of providing legal AI analysis. We act as an 'Operator' under POPIA, while you or your Firm acts as the 'Responsible Party' regarding any client/third-party data uploaded.</p>

        <h2>3. Data Residency and Security</h2>
        <ul>
            <li><strong>AWS Region:</strong> All Pinecone Vector databases are hosted within the prescribed secure cloud regions.</li>
            <li><strong>Encryption:</strong> Data is encrypted at rest and in transit using industry-standard AES-256.</li>
            <li><strong>LLM Processing:</strong> Selected AI models (e.g., Groq/Llama) do not use your inputs or uploaded documents to train their foundational models.</li>
        </ul>

        <h2>4. Data Retention and Deletion</h2>
        <p>You may request deletion of your Case Workspaces at any time. Upon deletion, documents are purged from our servers and the Pinecone vector index immediately.</p>

        <h2>5. Your Rights</h2>
        <p>Under POPIA, you retain the right to access, rectify, or request the deletion of your Personal Information.</p>
    </PageLayout>
);

export const TermsConditions = () => (
    <PageLayout title="Terms & Conditions" icon={<Book size={28} />}>
         <p className="lead italic">Subject to the Electronic Communications and Transactions Act, 25 of 2002 (ECT Act).</p>

        <h2>1. Nature of the Service</h2>
        <p>REM-Leases provides AI-assisted document analysis and retrieval. <strong>REM-Leases IS NOT A LAW FIRM AND DOES NOT PROVIDE LEGAL ADVICE.</strong> The output generated is for informational and research purposes only and must be verified by a qualified legal practitioner.</p>

        <h2>2. Enterprise & Firm Accounts</h2>
        <p>Firms are responsible for managing the access controls of their members. The Firm accepts liability for any documents uploaded and shared within their Workspaces, ensuring they possess the necessary rights and consents to upload such documents.</p>

        <h2>3. South African Jurisdiction</h2>
        <p>These Terms are governed by the laws of the Republic of South Africa. Any disputes shall be subject to the exclusive jurisdiction of the South African courts.</p>

        <h2>4. Limitation of Liability</h2>
        <p>Due to the probabilistic nature of Large Language Models (LLMs), "hallucinations" or inaccuracies may occur. REM-Leases shall not be liable for any direct, indirect, incidental, or consequential damages resulting from reliance on the AI-generated outputs.</p>

        <h2>5. Acceptable Use</h2>
        <p>You agree not to reverse engineer the system, attempt to bypass access controls, or upload malicious files.</p>
    </PageLayout>
);

export const HowToUse = () => (
    <PageLayout title="How to Use REM-Leases" icon={<Globe size={28} />}>
        <div className="grid md:grid-cols-2 gap-8 mb-8">
            <div className="glass-panel p-6 rounded-2xl border border-white/10 shadow-sm">
                <h3 className="text-xl font-bold mb-3 flex items-center gap-2"><div className="w-8 h-8 rounded-full bg-brand-blue/20 text-brand-blue-light flex items-center justify-center font-bold">1</div> Uploading Cases</h3>
                <p className="text-slate-300">Create a new <strong>Workspace</strong> for your matter. Drag and drop any PDFs (Briefs, Pleadings, Affidavits) into the dropzone. REM-Leases will automatically extract and vectorize the text.</p>
            </div>
            <div className="glass-panel p-6 rounded-2xl border border-white/10 shadow-sm">
                <h3 className="text-xl font-bold mb-3 flex items-center gap-2"><div className="w-8 h-8 rounded-full bg-brand-blue/20 text-brand-blue-light flex items-center justify-center font-bold">2</div> Chatting & Analysis</h3>
                <p className="text-slate-300">Ask questions! E.g., "What are the common cause facts?" or "Are there any contradictions in witness A's testimony?".</p>
            </div>
            <div className="glass-panel p-6 rounded-2xl border border-white/10 shadow-sm">
                <h3 className="text-xl font-bold mb-3 flex items-center gap-2"><div className="w-8 h-8 rounded-full bg-brand-blue/20 text-brand-blue-light flex items-center justify-center font-bold">3</div> Citations & Visualizer</h3>
                <p className="text-slate-300">REM-Leases provides exact page citations. Click the blue citation buttons in the chat to instantly open the live PDF viewer directly to the exact page referenced.</p>
            </div>
             <div className="glass-panel p-6 rounded-2xl border border-white/10 shadow-sm">
                <h3 className="text-xl font-bold mb-3 flex items-center gap-2"><div className="w-8 h-8 rounded-full bg-brand-blue/20 text-brand-blue-light flex items-center justify-center font-bold">4</div> Firm Collaboration</h3>
                <p className="text-slate-300">Documents uploaded to a Workspace are instantly available to all other users linked to your Firm's account. No more emailing 50MB PDFs back and forth.</p>
            </div>
        </div>
        
        <div className="bg-brand-blue/10 border border-brand-blue/20 p-6 rounded-2xl">
            <h3 className="text-brand-blue font-bold mb-2">Pro Tip: Master Timelines</h3>
            <p className="text-slate-300">Use the "Generate Master Timeline" button to force the AI to read across all uploaded documents and extract a chronological sequence of all events and deadlines.</p>
        </div>
    </PageLayout>
);
