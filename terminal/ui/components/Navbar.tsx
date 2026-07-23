import React from 'react';

const Navbar: React.FC = () => {
    return (
        <nav className="flex items-center justify-between p-4 bg-[#121212] text-[#F8FAFC] border-b border-[#1E1E1E]">
            <div className="text-[#4AF626] font-bold tracking-wider">⟐ SHETTYXTREME</div>
            <div className="flex items-center gap-4 text-xs">
                <span className="px-2 py-1 rounded bg-[#1A1A1A] text-[#4AF626] border border-[#4AF62633]">LIVE</span>
                <span className="w-2 h-2 rounded-full bg-[#4AF626]"></span>
            </div>
        </nav>
    );
};

export default Navbar;
