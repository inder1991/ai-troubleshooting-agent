import React, { useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { tabContentVariants } from './howItWorksAnimations';
import ArchitectureTab from './ArchitectureTab';
import ScenarioTab from './ScenarioTab';
import InvestigationFlowTab from './InvestigationFlowTab';

type TabId = 'architecture' | 'scenario' | 'flow';

const tabs: { id: TabId; label: string; icon: string }[] = [
  { id: 'architecture', label: 'Architecture', icon: 'account_tree' },
  { id: 'scenario', label: 'Scenario', icon: 'crisis_alert' },
  { id: 'flow', label: 'Investigation Flow', icon: 'play_circle' },
];

const HowItWorksSection: React.FC = () => {
  const [activeTab, setActiveTab] = useState<TabId>('architecture');

  return (
    <section id="how-it-works" className="mt-12 scroll-mt-8">
      {/* Section Header */}
      <div className="mb-6">
        <h2 className="text-xl font-bold text-white tracking-tight">
          How DebugDuck Works
        </h2>
        <p className="text-sm text-slate-400 mt-1">
          Multi-agent architecture for automated incident investigation, root-cause analysis, and fix generation.
        </p>
      </div>

      {/* Tab Bar */}
      <div className="flex gap-1.5 mb-6 border-b border-[#3d3528]">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-1.5 px-4 py-2.5 text-xs font-bold uppercase tracking-wider transition-colors relative ${
              activeTab === tab.id
                ? 'text-[#e09f3e]'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            <span
              className="material-symbols-outlined text-base"
            >
              {tab.icon}
            </span>
            {tab.label}
            {activeTab === tab.id && (
              <motion.div
                layoutId="activeTabIndicator"
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-[#e09f3e]"
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <AnimatePresence mode="wait">
        <motion.div
          key={activeTab}
          variants={tabContentVariants}
          initial="hidden"
          animate="visible"
          exit="exit"
        >
          {activeTab === 'architecture' && <ArchitectureTab />}
          {activeTab === 'scenario' && (
            <ScenarioTab onSwitchToFlow={() => setActiveTab('flow')} />
          )}
          {activeTab === 'flow' && <InvestigationFlowTab />}
        </motion.div>
      </AnimatePresence>
    </section>
  );
};

export default HowItWorksSection;
