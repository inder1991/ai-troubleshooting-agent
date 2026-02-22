import React, { useState, useEffect } from 'react';
import { previewPostMortem, publishPostMortem } from '../../services/api';

interface PostMortemPreviewModalProps {
  sessionId: string;
  defaultTitle: string;
  onClose: () => void;
  onPublished: () => void;
}

const PostMortemPreviewModal: React.FC<PostMortemPreviewModalProps> = ({
  sessionId,
  defaultTitle,
  onClose,
  onPublished,
}) => {
  const [spaceKey, setSpaceKey] = useState('');
  const [title, setTitle] = useState(defaultTitle);
  const [markdown, setMarkdown] = useState('');
  const [loading, setLoading] = useState(true);
  const [publishing, setPublishing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const data = await previewPostMortem(sessionId);
        setTitle(data.title || defaultTitle);
        setMarkdown(data.body_markdown);
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load preview');
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [sessionId, defaultTitle]);

  const handlePublish = async () => {
    if (!spaceKey.trim()) {
      setError('Space key is required');
      return;
    }
    setPublishing(true);
    setError(null);
    try {
      await publishPostMortem(sessionId, {
        space_key: spaceKey.trim(),
        title,
        body_markdown: markdown,
      });
      onPublished();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Publish failed');
    } finally {
      setPublishing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-8">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-[#0f2023] border border-slate-700/50 rounded-xl shadow-2xl w-full max-w-3xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-violet-400 text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>
              description
            </span>
            <span className="text-sm font-bold text-slate-200">Confluence Post-Mortem Preview</span>
          </div>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-300 transition-colors"
          >
            <span className="material-symbols-outlined text-sm" style={{ fontFamily: 'Material Symbols Outlined' }}>close</span>
          </button>
        </div>

        {/* Form Fields */}
        <div className="px-5 py-3 border-b border-slate-800 space-y-2">
          <div className="flex items-center gap-3">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider w-20 shrink-0">Space Key</label>
            <input
              type="text"
              placeholder="e.g. ENG, OPS"
              value={spaceKey}
              onChange={(e) => setSpaceKey(e.target.value)}
              className="text-[11px] bg-slate-800/60 border border-slate-700/50 rounded px-2 py-1 text-slate-200 placeholder-slate-600 w-40 font-mono focus:outline-none focus:border-violet-500/50"
            />
          </div>
          <div className="flex items-center gap-3">
            <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider w-20 shrink-0">Title</label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="text-[11px] bg-slate-800/60 border border-slate-700/50 rounded px-2 py-1 text-slate-200 flex-1 font-mono focus:outline-none focus:border-violet-500/50"
            />
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden px-5 py-3">
          {loading ? (
            <div className="flex items-center justify-center h-full">
              <div className="w-6 h-6 border-2 border-slate-800 border-t-violet-500 rounded-full animate-spin" />
            </div>
          ) : (
            <textarea
              value={markdown}
              onChange={(e) => setMarkdown(e.target.value)}
              className="w-full h-full min-h-[300px] bg-slate-900/60 border border-slate-700/50 rounded-lg p-3 text-[11px] font-mono text-slate-300 leading-relaxed resize-none focus:outline-none focus:border-violet-500/50 custom-scrollbar"
              spellCheck={false}
            />
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-slate-800 flex items-center justify-between">
          <div>
            {error && (
              <span className="text-[10px] text-red-400">{error}</span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="text-[11px] px-3 py-1.5 rounded text-slate-400 hover:text-slate-200 border border-slate-700/50 hover:border-slate-600"
            >
              Cancel
            </button>
            <button
              onClick={handlePublish}
              disabled={publishing || !spaceKey.trim() || loading}
              className="text-[11px] font-bold px-4 py-1.5 rounded bg-violet-500/20 text-violet-400 border border-violet-500/30 hover:bg-violet-500/30 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {publishing ? 'Publishing...' : 'Publish to Confluence'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PostMortemPreviewModal;
