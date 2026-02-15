import React from 'react';
import type { TokenUsage } from '../../types';

interface TokenSummaryProps {
  tokenUsage: TokenUsage[];
}

const TokenSummary: React.FC<TokenSummaryProps> = ({ tokenUsage }) => {
  if (tokenUsage.length === 0) return null;

  const totalInput = tokenUsage.reduce((sum, t) => sum + t.input_tokens, 0);
  const totalOutput = tokenUsage.reduce((sum, t) => sum + t.output_tokens, 0);
  const grandTotal = tokenUsage.reduce((sum, t) => sum + t.total_tokens, 0);

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4">
      <h4 className="text-xs text-gray-400 mb-2 uppercase tracking-wide">Token Usage</h4>
      <table className="w-full text-xs">
        <thead>
          <tr className="text-gray-400 border-b border-gray-700">
            <th className="text-left py-1.5 pr-2">Agent</th>
            <th className="text-right py-1.5 pr-2">Input</th>
            <th className="text-right py-1.5 pr-2">Output</th>
            <th className="text-right py-1.5">Total</th>
          </tr>
        </thead>
        <tbody>
          {tokenUsage.map((t, i) => (
            <tr key={i} className="border-b border-gray-700/50">
              <td className="py-1.5 pr-2 text-gray-300">{t.agent}</td>
              <td className="py-1.5 pr-2 text-right text-gray-400 font-mono">
                {t.input_tokens.toLocaleString()}
              </td>
              <td className="py-1.5 pr-2 text-right text-gray-400 font-mono">
                {t.output_tokens.toLocaleString()}
              </td>
              <td className="py-1.5 text-right text-gray-300 font-mono">
                {t.total_tokens.toLocaleString()}
              </td>
            </tr>
          ))}
          <tr className="border-t border-gray-600 font-semibold">
            <td className="py-2 pr-2 text-white">Total</td>
            <td className="py-2 pr-2 text-right text-gray-300 font-mono">
              {totalInput.toLocaleString()}
            </td>
            <td className="py-2 pr-2 text-right text-gray-300 font-mono">
              {totalOutput.toLocaleString()}
            </td>
            <td className="py-2 text-right text-white font-mono">
              {grandTotal.toLocaleString()}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};

export default TokenSummary;
