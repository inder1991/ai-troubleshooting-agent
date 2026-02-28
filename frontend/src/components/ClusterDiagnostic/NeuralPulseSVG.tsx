import React from 'react';

interface NeuralPulseSVGProps {
  hasRootCause: boolean;
}

const NeuralPulseSVG: React.FC<NeuralPulseSVGProps> = ({ hasRootCause }) => {
  return (
    <svg
      className="absolute inset-0 w-full h-full pointer-events-none z-20"
      style={{ mixBlendMode: 'screen' }}
    >
      <path
        className="neural-pulse-path"
        d="M280 420 Q 450 420, 600 350"
        fill="none"
        stroke="#13b6ec"
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.8"
      />
      <path
        className="neural-pulse-path"
        d="M280 200 Q 400 200, 600 300"
        fill="none"
        stroke="#13b6ec"
        strokeWidth="1.5"
        strokeLinecap="round"
        opacity="0.6"
        style={{ animationDelay: '0.5s' }}
      />

      {hasRootCause && (
        <path
          className="neural-pulse-path"
          d="M1050 200 Q 900 200, 750 300"
          fill="none"
          stroke="#ef4444"
          strokeWidth="2"
          strokeLinecap="round"
          opacity="0.9"
          style={{ animationDuration: '1.5s' }}
        />
      )}

      <path
        className="tether-path"
        d="M280 420 Q 450 420, 500 350"
        fill="none"
        stroke="#13b6ec"
        strokeWidth="1"
        opacity="0.1"
      />
      <path
        className="tether-path-flow"
        d="M1050 200 Q 900 200, 700 300"
        fill="none"
        stroke="#13b6ec"
        strokeWidth="1"
        opacity="0.3"
      />
    </svg>
  );
};

export default NeuralPulseSVG;
