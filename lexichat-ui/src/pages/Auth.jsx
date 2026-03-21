import React, { useState } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';
import { useNavigate, Link } from 'react-router-dom';
import { Scale, Building2, User, Mail, Lock, AlertCircle } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000/api';

export const AuthScreen = ({ isLogin = false }) => {
    const { login } = useAuth();
    const navigate = useNavigate();
    
    const [isFirmSignup, setIsFirmSignup] = useState(false);
    const [formData, setFormData] = useState({
        email: '',
        password: '',
        full_name: '',
        firm_name: ''
    });
    const [error, setError] = useState(null);
    const [loading, setLoading] = useState(false);

    const handleChange = (e) => setFormData({ ...formData, [e.target.name]: e.target.value });

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError(null);
        setLoading(true);

        try {
            if (isLogin) {
                const formBody = new URLSearchParams();
                formBody.append('username', formData.email);
                formBody.append('password', formData.password);
                
                const res = await axios.post(`${API_BASE}/auth/login`, formBody, {
                    headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
                });
                
                login(res.data.access_token, res.data.user);
                navigate('/app');
            } else {
                // Signup
                const payload = {
                    email: formData.email,
                    password: formData.password,
                    full_name: formData.full_name,
                    firm_name: formData.firm_name || null,
                    is_firm_admin: isFirmSignup
                };
                const sessionId = localStorage.getItem('rem_session_id');
                const headers = sessionId ? { 'X-Session-Id': sessionId } : {};
                await axios.post(`${API_BASE}/auth/signup`, payload, { headers });
                // Auto login after signup
                const formBody = new URLSearchParams();
                formBody.append('username', formData.email);
                formBody.append('password', formData.password);
                const res = await axios.post(`${API_BASE}/auth/login`, formBody);
                login(res.data.access_token, res.data.user);
                navigate('/app');
            }
        } catch (err) {
            setError(err.response?.data?.detail || "An error occurred");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="min-h-screen relative bg-slate-50 flex flex-col justify-center py-12 px-6 lg:px-8 font-sans overflow-hidden text-slate-900">
            {/* Minimalist ambient light background if desired, but pure slate-50 is clinical enough */}
            <div className="absolute inset-0 bg-gradient-to-br from-white to-slate-100 opacity-50 pointer-events-none z-0" />

            <div className="sm:mx-auto sm:w-full sm:max-w-md relative z-10">
                <Link to="/" className="flex items-center justify-center mb-6 cursor-pointer">
                    <img src="/rem-logo.png" alt="REM-Leases" className="h-10" />
                </Link>
                <h2 className="mt-2 text-center text-3xl font-extrabold text-slate-900">
                    {isLogin ? "Sign in to your Property Dashboard" : "Create your Leasing Account"}
                </h2>
                {!isLogin && (
                    <div className="mt-4 flex justify-center">
                        <div className="bg-slate-200/50 backdrop-blur-md border border-slate-200 p-1 rounded-xl flex gap-1 shadow-inner">
                            <button 
                                type="button" 
                                onClick={() => setIsFirmSignup(false)} 
                                className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${!isFirmSignup ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-800'}`}
                            >
                                Independent Landlord / Join Agency
                            </button>
                            <button 
                                type="button" 
                                onClick={() => setIsFirmSignup(true)} 
                                className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${isFirmSignup ? 'bg-white shadow-sm text-slate-900' : 'text-slate-500 hover:text-slate-800'}`}
                            >
                                Register Property Group
                            </button>
                        </div>
                    </div>
                )}
            </div>

            <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md relative z-10">
                <div className="bg-white rounded-2xl shadow-xl border border-slate-200 py-8 px-4 sm:px-10">
                    <form className="space-y-6" onSubmit={handleSubmit}>
                        {!isLogin && (
                            <div>
                                <label className="block text-sm font-medium text-slate-700">Full Name</label>
                                <div className="mt-1 relative">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <User size={18} className="text-slate-400" />
                                    </div>
                                    <input name="full_name" type="text" required className="bg-slate-50 border border-slate-300 text-slate-900 rounded-xl focus:bg-white focus:ring-2 focus:ring-brand-blue/30 focus:border-brand-blue outline-none transition-all pl-10 px-3 py-3 w-full sm:text-sm shadow-sm" placeholder="John Doe" onChange={handleChange} />
                                </div>
                            </div>
                        )}

                        <div>
                            <label className="block text-sm font-medium text-slate-700">Email address</label>
                            <div className="mt-1 relative">
                                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                    <Mail size={18} className="text-slate-400" />
                                </div>
                                <input name="email" type="email" required className="bg-slate-50 border border-slate-300 text-slate-900 rounded-xl focus:bg-white focus:ring-2 focus:ring-brand-blue/30 focus:border-brand-blue outline-none transition-all pl-10 px-3 py-3 w-full sm:text-sm shadow-sm" placeholder="leasing@propertygroup.co.za" onChange={handleChange} />
                            </div>
                        </div>

                        {!isLogin && (
                            <div>
                                <label className="block text-sm font-medium text-slate-700">
                                    {isFirmSignup ? "Property Group / Agency Name" : "Agency Name to Join (Optional)"}
                                </label>
                                <div className="mt-1 relative">
                                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                        <Building2 size={18} className="text-slate-400" />
                                    </div>
                                    <input name="firm_name" type="text" required={isFirmSignup} className="bg-slate-50 border border-slate-300 text-slate-900 rounded-xl focus:bg-white focus:ring-2 focus:ring-brand-blue/30 focus:border-brand-blue outline-none transition-all pl-10 px-3 py-3 w-full sm:text-sm shadow-sm" placeholder={isFirmSignup ? "PropTech Rentals" : "Leave blank for Personal"} onChange={handleChange} />
                                </div>
                                {!isFirmSignup && <p className="mt-2 text-xs text-slate-500 border-l-2 border-slate-300 pl-2">If your agency is registered, type its exact name to request access to shared portfolios.</p>}
                            </div>
                        )}

                        <div>
                            <label className="block text-sm font-medium text-slate-700">Password</label>
                            <div className="mt-1 relative">
                                <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                    <Lock size={18} className="text-slate-400" />
                                </div>
                                <input name="password" type="password" required className="bg-slate-50 border border-slate-300 text-slate-900 rounded-xl focus:bg-white focus:ring-2 focus:ring-brand-blue/30 focus:border-brand-blue outline-none transition-all pl-10 px-3 py-3 w-full sm:text-sm shadow-sm" placeholder="••••••••" onChange={handleChange} />
                            </div>
                        </div>

                        {error && (
                            <div className="rounded-xl bg-red-50 p-4 border border-red-200 flex items-start gap-3 shadow-sm">
                                <AlertCircle size={20} className="text-red-500 mt-0.5" />
                                <h3 className="text-sm font-medium text-red-800">{error}</h3>
                            </div>
                        )}

                        <div>
                            <button type="submit" disabled={loading} className="bg-brand-blue text-white shadow-md hover:shadow-lg hover:-translate-y-0.5 w-full flex justify-center py-3 px-4 rounded-xl text-sm font-bold focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-brand-blue transition-all disabled:opacity-50 disabled:hover:translate-y-0">
                                {loading ? 'Processing...' : (isLogin ? 'Sign in' : 'Create Account')}
                            </button>
                        </div>
                    </form>

                    <div className="mt-6">
                        <div className="relative">
                            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-200" /></div>
                            <div className="relative flex justify-center text-sm">
                                <span className="px-2 bg-white text-slate-500 font-medium">Or</span>
                            </div>
                        </div>
                        <div className="mt-6 text-center">
                            {isLogin ? (
                                <p className="text-sm text-slate-600">Don't have an account? <Link to="/signup" className="font-bold text-brand-blue hover:text-brand-blue-dark transition-colors">Sign up</Link></p>
                            ) : (
                                <p className="text-sm text-slate-600">Already have an account? <Link to="/login" className="font-bold text-brand-blue hover:text-brand-blue-dark transition-colors">Sign in</Link></p>
                            )}
                        </div>
                    </div>
                </div>
                
                <p className="mt-8 text-center text-xs text-slate-500 relative z-10">
                    By continuing, you agree to REM-Leases's <Link to="/terms" className="text-slate-600 hover:text-slate-900 transition-colors underline decoration-slate-300 underline-offset-2">Terms of Service</Link> and <Link to="/privacy" className="text-slate-600 hover:text-slate-900 transition-colors underline decoration-slate-300 underline-offset-2">Privacy Policy</Link>.
                </p>
            </div>
        </div>
    );
};
