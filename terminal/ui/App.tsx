import React from 'react';
import Navbar from './components/Navbar';

const App: React.FC = () => {
    return (
        <div className="min-h-screen bg-[#020617] text-[#F8FAFC] font-fira-sans">
            <Navbar />
            <main className="p-4 grid grid-cols-2 gap-4">
                <div className="bg-[#121212] p-4 rounded border border-[#1E1E1E]">
                    <h2 className="text-[#6C6C6C] uppercase text-xs tracking-wider mb-4 border-b border-[#1E1E1E] pb-2">Intelligence</h2>
                </div>
                <div className="bg-[#121212] p-4 rounded border border-[#1E1E1E]">
                    <h2 className="text-[#6C6C6C] uppercase text-xs tracking-wider mb-4 border-b border-[#1E1E1E] pb-2">Watchlist</h2>
                </div>
                <div className="bg-[#121212] p-4 rounded border border-[#1E1E1E]">
                    <h2 className="text-[#6C6C6C] uppercase text-xs tracking-wider mb-4 border-b border-[#1E1E1E] pb-2">Risk & Positions</h2>
                </div>
                <div className="bg-[#121212] p-4 rounded border border-[#1E1E1E]">
                    <h2 className="text-[#6C6C6C] uppercase text-xs tracking-wider mb-4 border-b border-[#1E1E1E] pb-2">Alerts & Logs</h2>
                </div>
            </main>
        </div>
    );
};

export default App;
