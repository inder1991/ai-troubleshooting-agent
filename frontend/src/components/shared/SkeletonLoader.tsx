import React from 'react';

interface SkeletonLoaderProps {
  type: 'text' | 'card' | 'avatar' | 'row';
  width?: string;
  height?: string;
  className?: string;
}

export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({ type, width, height, className = '' }) => {
  const base = 'animate-pulse bg-[#1e1b15] border border-[#3d3528]';

  if (type === 'avatar') return <div className={`${base} rounded-full ${width || 'w-8'} ${height || 'h-8'} ${className}`} />;
  if (type === 'text') return <div className={`${base} rounded ${width || 'w-full'} ${height || 'h-4'} ${className}`} />;
  if (type === 'card') return <div className={`${base} rounded-lg ${width || 'w-full'} ${height || 'h-32'} ${className}`} />;
  return <div className={`${base} rounded ${width || 'w-full'} ${height || 'h-12'} ${className}`} />;
};
