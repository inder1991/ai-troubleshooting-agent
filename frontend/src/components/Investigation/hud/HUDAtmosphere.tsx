import React from 'react';

const HUDAtmosphere: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  return (
    <div className="relative h-full w-full overflow-hidden">
      {/* Layer 1: 30x30 Engineering Grid */}
      <div
        className="absolute inset-0 opacity-20 pointer-events-none mix-blend-overlay"
        style={{
          backgroundImage: `
            linear-gradient(rgba(7,182,213,0.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(7,182,213,0.1) 1px, transparent 1px)
          `,
          backgroundSize: '30px 30px',
        }}
      />

      {/* Layer 2: CRT Scanlines */}
      <div
        className="absolute inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage: 'repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,1) 2px, rgba(0,0,0,1) 4px)',
        }}
      />

      {/* Layer 3: Radial Vignette */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background: 'radial-gradient(circle at center, transparent 0%, rgba(2,6,23,0.6) 100%)',
        }}
      />

      {/* Layer 4: Content */}
      <div className="relative z-10 h-full w-full overflow-hidden flex flex-col">
        {children}
      </div>
    </div>
  );
};

export default HUDAtmosphere;
