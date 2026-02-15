import React, { useState, useRef, useEffect, useCallback} from 'react';
import { useWebSocket } from '../hooks/useWebSocket';
import { CodebaseMappingCard } from './Agent2/CodebaseMappingCard';
import { ContextRetrievalCard } from './Agent2/ContextRetrievalCard';
import { CallChainAnalysisCard } from './Agent2/CallChainAnalysisCard';
import { Agent2DiagnosticDashboard } from './Agent2/DiagnosticSummary';

import { Agent1Report } from './Agent1/Report';
import { DependencyTrackingCard } from './Agent2/DependencyTrackingCard';
import { ReviewFixScreen, Agent3ProgressCard, PRSuccessScreen, ImpactAssessmentCard } from './Agent3';
import { createPullRequest, rejectFix } from '../services/api';
import { 
  Send, FileText, Clock, AlertCircle, Plus, Code, GitPullRequest, 
  X, Settings, Activity, Terminal, ShieldCheck, Cpu, Trash2, 
  MessageSquare, Server, Box, Loader2, Layers, LucideIcon, Wifi, WifiOff, ChevronDown, ChevronUp
  , AlertTriangle, Fingerprint
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { 
  sendConversationMessage, 
  startTroubleshooting 
} from '../services/api';

// Type definitions
interface MessageAction {
  id: string;
  label: string;
  icon: LucideIcon;
}


interface Message {
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  actions?: MessageAction[];
}

interface AgentResults {
  logs: {
    status?: string;
    summary?: string;
    exception_type?: string;
    exception_message?: string;
    preliminary_rca?: string;
    log_count?: number;
    stacktrace?: string;
    confidence?: number;
    diagnosticSummary?: string;
    functionName?: string;
    traceIDs?: any[];
    errorPatterns: any[];
  } | null;
  trace: {
    root_cause_location?: string;
    relevant_files?: string[];
    call_chain?: any[];
    flowchart?: string;           // ← Add this
    confidence?: number;  
    code_analysis?: boolean;
    diagnosticSummary?: string;
    impactAnalysis?: string;
    recommendedFix?: string;
  } | null;
  fix: {
    pr_title?: string;
    fix_explanation?: string;
    confidence_score?: number;
    changes?: any[];
    branchName: string;
    commitSha: string;
    diff: string;
    prBody: string;
    prTitle: string;
  } | null;
}

interface Session {
  id: string;
  name: string;
  messages: Message[];
  agentResults: AgentResults;
  progress: number;
  targetType: string | null;
  isProcessing: boolean;
  wsConnected: boolean;
  backendSessionId: string | null;
}

interface Sessions {
  [key: string]: Session;
}

interface FormData {
  targetType: 'application' | 'infrastructure';
  repo: string;
  namespace: string;
  errorMessage: string;
  elkIndex: string;
  timeframe: string;
  rawLogs: string;
}

interface DiagnosticFormProps {
  onSubmit: (data: FormData) => void;
  onCancel: () => void;
}

interface InspectorCardProps {
  title: string;
  icon: LucideIcon;
  data: any;
  children?: React.ReactNode;
  isThinking?: boolean;
  activeAgent?: string | null;
}

const TroubleshootingChatbot: React.FC = () => {
  // --- 1. STATE INITIALIZATION ---
  const [sessions, setSessions] = useState<Sessions>({
    'SESS-DEFAULT': {
      id: 'SESS-DEFAULT',
      name: 'System Console',
      messages: [{
        role: 'assistant',
        content: 'Console Ready. Select "New Diagnosis" or click the button below to configure your analysis target.',
        timestamp: new Date().toISOString(),
        actions: [{ id: 'troubleshoot', label: 'Configure Diagnosis', icon: Settings }]
      }],
      agentResults: { logs: null, trace: null, fix: null },
      progress: 0,
      targetType: null,
      isProcessing: false,
      wsConnected: false,
      backendSessionId: null
    }
  });
  const [activeSessionId, setActiveSessionId] = useState<string>('SESS-DEFAULT');
  const [input, setInput] = useState<string>('');
 // const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [activeFormType, setActiveFormType] = useState<string | null>(null);
  // NEW - Agent 2 Production States
  const [agent2Mapping, setAgent2Mapping] = useState<any>(null);
  const [agent2Context, setAgent2Context] = useState<any>(null);
  const [agent2CallChain, setAgent2CallChain] = useState<any>(null);
  const [agent2Dependencies, setAgent2Dependencies] = useState<any>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  // Agent 3 States
  const [agent3Progress, setAgent3Progress] = useState<any[]>([]);
  const [agent3ReviewData, setAgent3ReviewData] = useState<any>(null);
  const [agent3PRResult, setAgent3PRResult] = useState<any>(null);
  const [showReviewScreen, setShowReviewScreen] = useState(false);
  const [showPRSuccess, setShowPRSuccess] = useState(false);
  const [isCreatingPR, setIsCreatingPR] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
// --- ADD THESE LINES ---
  const [isTyping, setIsTyping] = useState(false);
  // TroubleshootingUI.tsx
  const [prDetails, setPrDetails] = useState<{
  pr_url: string;
  pr_number: number;
  branch_name?: string;
  } | null>(null);
  const [isThinking, setIsThinking] = useState(false);
  const [activeAgent, setActiveAgent] = useState<string | null>(null);
  const scrollToBottom = () => messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  useEffect(() => {
  // Safe check prevents the "reading property of undefined" error
   const currentMessages = sessions[activeSessionId]?.messages;
      if (currentMessages) {
        scrollToBottom();
      }
    }, [activeSessionId, sessions, isTyping, isThinking]);

 // --- 2. WEBSOCKET INTEGRATION ---
  
  // WebSocket message handler

  const handleWebSocketMessage = useCallback((data: any) => {
    console.log('📨 WebSocket message:', data);
    const agent1Data =data
    setSessions(prev => {
      const session = prev[activeSessionId];
      if (!session) return prev;
      let updates: Partial<Session> = {};
      let newMessages = [...session.messages];
      if (data.type === 'progress') {
          setIsThinking(true);
          setIsTyping(true);
          
          // Normalize backend step (agent1) to internal ID (1)
          const agentNum = data.step?.replace('agent', '') || "1";
          setActiveAgent(agentNum);
          
          // IMPORTANT: Return here so progress updates don't get added to message history
          return prev; 
        }
      // Agent 1 Updates
      if (data.type === 'agent1_streaming_start') {
        updates.progress = 15;
        updates.wsConnected = true;
        setIsThinking(true);
        const inferredId = data.step ? data.step.replace('agent', '') : "1";
        setActiveAgent(inferredId);
        newMessages.push({
          role: 'assistant',
          content: '🔍 Agent 1: Analyzing logs and refining error context...',
          timestamp: new Date().toISOString()
        });
      }
    
      if (data.type === 'agent1_streaming') {
        updates.progress = 25;
        setIsTyping(true);
      }
      if (data.type === 'agent1_streaming_complete') {
        console.log('✅ Agent 1 streaming complete received');
        console.log('✅ Data:', data);
        const agent1Data = data.data || {};
        updates.progress = 33;
        const narrativeContent = `### 🔍 Log Analysis Complete
          I have analyzed **${agent1Data.logCount || 0} log entries** and identified **${agent1Data.errorPatterns || 0} recurring error patterns**.

          **Root Cause Hypothesis:**
          ${agent1Data.preliminaryRca || 'No RCA available'}

          **Technical Signature:**
          * **Exception:** \`${agent1Data.exceptionType || 'Unknown'}\`
          * **Location:** \`${agent1Data.functionName || 'Unknown'}\` (Line ${agent1Data.lineNumber || '?'})
          * **Correlation ID:** \`${agent1Data.correlationId || 'N/A'}\`

         

          I am now handing this over to **Agent 2** to map the codebase for a potential fix.`.trim();
               
        updates.agentResults = {
          ...session.agentResults,
          logs: {
            status: 'complete',
            exception_type: agent1Data.exceptionType || 'Unknown',
            exception_message: agent1Data.exceptionMessage || '',
            preliminary_rca: narrativeContent || '',
            log_count: agent1Data.logCount || 0,
            summary: `Found ${agent1Data.errorPatterns || 0} error patterns`,
            stacktrace: agent1Data.stackTrace,
            confidence:agent1Data.confidence,
            diagnosticSummary:agent1Data.diagnosticSummary,
            functionName:agent1Data.functionName,
            traceIDs: agent1Data.traceIDs,
            errorPatterns: agent1Data.patterns
          }
        };
        
        newMessages.push({
          role: 'assistant',
          content: `✅ Agent 1 Complete\n\n**Exception Type:** ${agent1Data.exceptionType || 'Unknown'}\n**Message:** ${agent1Data.exceptionMessage || 'N/A'}\n\n**Preliminary RCA:** ${agent1Data.preliminaryRca || 'Analysis complete'}`,
          timestamp: new Date().toISOString()
        });
      }
      
      // Agent 2 Updates
      // ========================================================================
// AGENT 2 UPDATES - PRODUCTION VERSION (4 Responsibilities)
// ========================================================================

// ────────────────────────────────────────────────────────────────────
// 1️⃣ CODEBASE MAPPING
// ────────────────────────────────────────────────────────────────────

      if (data.type === 'agent2_codebase_mapping') {
        console.log('✅ Codebase mapping received:', data.data);
        
        updates.progress = 40;
        setAgent2Mapping(data.data);
        setIsTyping(true);
        const inferredId = data.step ? data.step.replace('agent', '') : "2";
        setActiveAgent("2");
        const mappingData = data.data || {};
        newMessages.push({
          role: 'assistant',
          content: `✅ Codebase Mapping Complete\n\n**Success Rate:** ${mappingData.successRate}\n**Locations Mapped:** ${mappingData.totalLocations}`,
          timestamp: new Date().toISOString()
        });
         updates.agentResults = {
          ...session.agentResults,
          trace: {
            root_cause_location: mappingData.rootCause || 'Unknown',
            relevant_files: mappingData.relevantFiles || [],
            call_chain: mappingData.callChain || [],
            flowchart: mappingData.flowchart || '',
            confidence: mappingData.confidence_score || 1,
            diagnosticSummary: mappingData.root_cause_explanation || '',
            impactAnalysis: mappingData.impactAnalysis || '',
            recommendedFix: mappingData.recommendedFix || '',
          }
        };
        
      }

      // ────────────────────────────────────────────────────────────────────
      // 2️⃣ CONTEXT RETRIEVAL
      // ────────────────────────────────────────────────────────────────────

      if (data.type === 'agent2_context_retrieval') {
        console.log('✅ Context retrieval received:', data.data);
        
        updates.progress = 50;
        setAgent2Context(data.data);
        setIsTyping(true);

        const contextData = data.data || {};
        newMessages.push({
          role: 'assistant',
          content: `✅ Context Retrieval Complete\n\n**Functions Extracted:** ${contextData.functionDefinitionsCount}\n**Code Snippets:** ${contextData.codeSnippetsCount}`,
          timestamp: new Date().toISOString()
        });
        const mappingData = data.data || {};
        updates.agentResults = {
          ...session.agentResults,
          trace: {
            root_cause_location: mappingData.rootCause || 'Unknown',
            relevant_files: mappingData.relevantFiles || [],
            call_chain: mappingData.callChain || [],
            flowchart: mappingData.flowchart || '',
            confidence: mappingData.confidence || 1 ,
            diagnosticSummary: mappingData.rootCauseExplanation || '',
            impactAnalysis: mappingData.impactAnalysis || '',
            recommendedFix: mappingData.recommendedFix || '',
          }
        };
      }

      // ────────────────────────────────────────────────────────────────────
      // 3️⃣ CALL CHAIN ANALYSIS
      // ────────────────────────────────────────────────────────────────────

      if (data.type === 'agent2_call_chain_analysis') {
        console.log('✅ Call chain analysis received:', data.data);
        
        updates.progress = 60;
        setAgent2CallChain(data.data);
        setIsTyping(true);

        const callChainData = data.data || {};
        const failureInfo = callChainData.failureAnalysis || {};
        const mappingData = data.data || {};
        newMessages.push({
          role: 'assistant',
          content: `✅ Call Chain Analysis Complete\n\n**Chain Steps:** ${callChainData.callChain?.length || 0}\n**Failure Point:** ${failureInfo.location || 'Unknown'}\n**Reason:** ${failureInfo.reason || 'N/A'}`,
          timestamp: new Date().toISOString()
        });
        updates.agentResults = {
          ...session.agentResults,
          trace: {
            root_cause_location: mappingData.rootCause || 'Unknown',
            relevant_files: mappingData.relevantFiles || '',
            call_chain: mappingData.callChain || [],
            flowchart: mappingData.flowchart || '',
            confidence: mappingData.confidence  || 1,
            diagnosticSummary: mappingData.rootCauseExplanation,
            impactAnalysis: mappingData.impactAnalysis,
            recommendedFix: mappingData.recommendedFix,
          }
        };
      }

      // ────────────────────────────────────────────────────────────────────
      // 4️⃣ DEPENDENCY TRACKING
      // ────────────────────────────────────────────────────────────────────

      if (data.type === 'agent2_dependency_tracking') {
        console.log('✅ Dependency tracking received:', data.data);
        
        updates.progress = 65;
        setAgent2Dependencies(data.data);
        
        const depsData = data.data || {};
        const conflictWarning = depsData.hasConflicts ? ` ⚠️ ${depsData.conflicts?.length} conflicts detected!` : '';
        const mappingData = data.data || {};
        newMessages.push({
          role: 'assistant',
          content: `✅ Dependency Tracking Complete\n\n**External Dependencies:** ${depsData.totalExternal}\n**Internal Dependencies:** ${depsData.totalInternal}${conflictWarning}`,
          timestamp: new Date().toISOString()
        });
        updates.agentResults = {
          ...session.agentResults,
          trace: {
            root_cause_location: mappingData.rootCause || 'Unknown',
            relevant_files: mappingData.relevantFiles || [],
            call_chain: mappingData.callChain || [],
            flowchart: mappingData.flowchart || '',
            confidence: mappingData.confidence_score  || 1,
            diagnosticSummary: mappingData.rootCauseExplanation || '',
            impactAnalysis: mappingData.impactAnalysis || '',
            recommendedFix: mappingData.recommendedFix || '',
          }
        };
      }

      // ────────────────────────────────────────────────────────────────────
      // BACKWARDS COMPATIBLE: Original agent2_streaming_complete
      // ────────────────────────────────────────────────────────────────────

    if (data.type === 'agent2_streaming_complete') {
      console.log('✅ Agent 2 complete (final synthesis):', data.data);
      const mappingData = data.data || {};
      setActiveAgent("2");
      updates.progress = 66;
      setAgent2CallChain(data.data);
      // Keep existing behavior
      updates.agentResults = {
        ...session.agentResults,
        trace: {
            root_cause_location: mappingData.rootCause || 'Unknown',
            relevant_files: mappingData.relevantFiles || [],
            call_chain: mappingData.callChain || [],
            flowchart: mappingData.flowchart || '',
            confidence: mappingData.confidence_score || 1 ,
            code_analysis: true,
            diagnosticSummary: mappingData.rootCauseExplanation,
            impactAnalysis: mappingData.impactAnalysis,
            recommendedFix: mappingData.recommendedFix,
          }
      };
      
      newMessages.push({
        role: 'assistant',
        content: `✅ Agent 2 Analysis Complete\n\n**Root Cause:** ${data.data?.rootCause || 'Unknown'}\n**Files Analyzed:** ${data.data?.relevantFiles?.length || 0}\n**Confidence:** ${((data.data?.confidence || 0) * 100).toFixed(0)}%\n\n${data.data?.recommendedFix ? '**Recommended Fix:** ' + data.data.recommendedFix : ''}`,
        timestamp: new Date().toISOString()
      });
      console.log('🔥 Created trace:', updates.agentResults.trace);


    }

    // Keep old handlers for backwards compatibility
    if (data.type === 'agent2_start') {
      updates.progress = 35;
      newMessages.push({
        role: 'assistant',
        content: '🔧 Agent 2: Navigating codebase...',
        timestamp: new Date().toISOString()
      });
    }

    if (data.type === 'agent2_streaming') {
      updates.progress = 55;
    }

      // Agent 3 Updates
      if (data.type === 'agent3_start') {
        updates.progress = 75;
        newMessages.push({
          role: 'assistant',
          content: '💡 Agent 3: Generating fix and preparing PR...',
          timestamp: new Date().toISOString()
        });
      }

      if (data.type === 'agent3_streaming') {
        updates.progress = 90;
      }
            // Agent 3 Progress
      if (data.type === 'agent3_progress') {
        setAgent3Progress(prev => [...prev, {
          stage: data.data.stage,
          status: 'in_progress',
          message: data.data.message
        }]);
      }

      // Agent 3 Review Fix
      if (data.type === 'agent3_review_fix') {
        setAgent3ReviewData(data.data);
        setShowReviewScreen(true);
        const mappingData = data.data || {};

        updates.agentResults = {
        ...session.agentResults,
           fix: {
              branchName: mappingData.branch_name|| 'Unknown',
              commitSha: mappingData.commit_sha || '',
              diff: mappingData.diff || '',
              prBody: mappingData.pr_body || 1 ,
              prTitle: mappingData.pr_title || '',

            }
      };
        newMessages.push({
          role: 'assistant',
          content: `✅ Fix Generated & Validated\n\n**Branch:** ${data.data.branch_name}\n**Commit:** ${data.data.commit_sha?.substring(0, 7)}\n**Confidence:** ${Math.round((data.data.validation?.agent2_confidence || 0.75) * 100)}%\n\n⏸️ Review the fix in the Inspector Panel and click "Create PR" when ready.`,
          timestamp: new Date().toISOString()
  });
      }

      // Agent 3 PR Created
      if (data.type === 'agent3_pr_created') {
        setAgent3PRResult(data.data);
        setShowReviewScreen(false);
        setShowPRSuccess(true);
        
        newMessages.push({
          role: 'assistant',
          content: `🎉 Pull Request Created!\n\n**PR #${data.data.number}**\n**URL:** ${data.data.html_url}\n\nYour fix has been submitted for review!`,
          timestamp: new Date().toISOString()
       });
      }
      if (data.type === 'agent3_complete') {
        updates.progress = 100;
        updates.isProcessing = false;
        updates.agentResults = {
          ...session.agentResults,
          fix: data.result
        };
        newMessages.push({
          role: 'assistant',
          content: `🎉 Analysis Complete!\n\n**Fix Generated**\n${data.result.fix_explanation}\n\n**Confidence Score:** ${(data.result.confidence_score * 100).toFixed(0)}%\n**PR Title:** ${data.result.pr_title}`,
          timestamp: new Date().toISOString()
        });
      }
      
      // Error Handling
      if (data.type === 'error') {
        updates.isProcessing = false;
        updates.progress = 0;
        newMessages.push({
          role: 'assistant',
          content: `❌ Error occurred:\n${data.error}`,
          timestamp: new Date().toISOString()
        });
      }

      return {
        ...prev,
        [activeSessionId]: {
          ...session,
          ...updates,
          messages: newMessages
        }
      };
    });
  }, [activeSessionId]);

  // Use the custom WebSocket hook
  const currentBackendSessionId = sessions[activeSessionId]?.backendSessionId;
  useWebSocket(currentBackendSessionId, handleWebSocketMessage);

  // --- 3. SESSION LOGIC ---
  const generatePostmortemMarkdown = (results: any) => {
      const { logs, trace, fix } = results;

          return `
        # Incident Postmortem Report
        **Date:** ${new Date().toLocaleString()}
        **Status:** RESOLVED

        ## 1. Executive Summary (Agent 1)
        - **Incident Type:** ${logs?.exception_type ?? 'Unknown'}
        - **Service:** Checkout Service
        - **Summary:** ${logs?.summary ?? 'No summary provided.'}

        ## 2. Root Cause Analysis (Agent 2)
        - **Location:** \`${trace?.root_cause_location}\`
        - **Technical Breakdown:** ${trace?.diagnosticSummary}
        - **Relevant Files:** ${trace?.relevant_files?.map((f: string) => `  - ${f}`).join('\n')}

        ## 3. Visual Logic Flow
        \`\`\`mermaid
        ${trace?.flowchart}
        \`\`\`

        ## 4. Remediation (Agent 3)
        - **PR Title:** ${fix?.prTitle}
        - **Fix Description:** ${fix?.prBody}

        
        ## 5. Risk & Impact Assessment
        - **Regression Risk:** ${trace?.impactAnalysis}

        ---
        *Generated by AI Troubleshooting System*
          `;
        };
  const handleDownloadReport = () => {
    const markdown = generatePostmortemMarkdown(currentSession.agentResults);
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    
    const link = document.createElement('a');
    link.href = url;
    link.download = `Postmortem_Incident_${Date.now()}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };


  const handleCreateNewSession = (): void => {
    const newId = `SESS-${Math.floor(1000 + Math.random() * 9000)}`;
    const newSession: Session = {
      id: newId,
      name: `Session ${newId}`,
      messages: [{
        role: 'assistant',
        content: `Diagnostic Session ${newId} initialized. Please define the scope (Application or Infrastructure).`,
        timestamp: new Date().toISOString(),
        actions: [{ id: 'troubleshoot', label: 'Setup Parameters', icon: Settings }]
      }],
      agentResults: { logs: null, trace: null, fix: null },
      progress: 0,
      targetType: null,
      isProcessing: false,
      wsConnected: false,
      backendSessionId: null
    };

    setSessions(prev => ({ ...prev, [newId]: newSession }));
    setActiveSessionId(newId);
    setActiveFormType('troubleshoot');
  };

  const handleDeleteSession = (sessionId: string, e: React.MouseEvent): void => {
    e.stopPropagation();
    if (sessionId === 'SESS-DEFAULT') return;

    setSessions(prev => {
      const newSessions = { ...prev };
      delete newSessions[sessionId];
      return newSessions;
    });

    if (sessionId === activeSessionId) {
      setActiveSessionId('SESS-DEFAULT');
    }
  };

  const handleSendMessage = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    if (e) e.preventDefault();
    if (!input.trim() || sessions[activeSessionId]?.isProcessing) return;

    const userMsg = input;
    setInput('');

    // Add user message
    setSessions(prev => ({
      ...prev,
      [activeSessionId]: {
        ...prev[activeSessionId],
        messages: [...prev[activeSessionId].messages, { 
          role: 'user', 
          content: userMsg, 
          timestamp: new Date().toISOString() 
        }]
      }
    }));

    try {
      // Call Agent 0 via API utility
      const result = await sendConversationMessage(
        userMsg, 
        sessions[activeSessionId].messages.slice(-5)
      );

      // Add agent response
      setSessions(prev => ({
        ...prev,
        [activeSessionId]: {
          ...prev[activeSessionId],
          messages: [...prev[activeSessionId].messages, {
            role: 'assistant',
            content: result.response,
            timestamp: result.timestamp || new Date().toISOString(),
            actions: result.show_form ? [
              { id: 'troubleshoot', label: 'Setup Parameters', icon: Settings }
            ] : []
          }]
        }
      }));

      // Show form if needed
      if (result.show_form) {
        setActiveFormType('troubleshoot');
      }

    } catch (error) {
      console.error('Error calling Agent 0:', error);
      setSessions(prev => ({
        ...prev,
        [activeSessionId]: {
          ...prev[activeSessionId],
          messages: [...prev[activeSessionId].messages, {
            role: 'assistant',
            content: '❌ Connection error. Please ensure backend is running at http://localhost:8000',
            timestamp: new Date().toISOString()
          }]
        }
      }));
    }
  };
  // --- 5. TROUBLESHOOTING PIPELINE (using api.ts) ---
  const handleCreatePR = async () => {
    if (!currentSession?.backendSessionId) return;
    try {
      setIsCreatingPR(true);
      setActiveAgent("3");
      setIsThinking(true);
      
      const response=await createPullRequest(currentSession.backendSessionId);
      const successData = {
        pr_url: response.pr_url || "https://github.com/your-org/repo/pull/0",
        pr_number: response.pr_number || 0,
        branch_name: response.branch_name || "fix/incident-bug"
      };
      setPrDetails(successData);
      setAgent3PRResult(successData); 
      setShowPRSuccess(true);
    } catch (error) {
      console.error('Failed to create PR:', error);
    } finally {
      setIsCreatingPR(false);
    }
  };

  const handleRejectFix = async () => {
    if (!currentSession?.backendSessionId) return;
    await rejectFix(currentSession.backendSessionId);
    setShowReviewScreen(false);
    setAgent3ReviewData(null);
  };
  const handleFormSubmit = async (data: FormData): Promise<void> => {
    setActiveFormType(null);
    const sessionKey = activeSessionId;
    setIsTyping(true);
    setIsThinking(true);
    setActiveAgent("1");
    // Add user message
    setSessions(prev => ({
      ...prev,
      [sessionKey]: {
        ...prev[sessionKey],
        name: data.targetType === 'application' ? `App: ${data.repo}` : `Infra: ${data.namespace}`,
        targetType: data.targetType,
        messages: [...prev[sessionKey].messages, {
          role: 'user',
          content: `🚀 Starting ${data.targetType} analysis:\n- Target: ${data.repo || data.namespace}\n- ELK Index: ${data.elkIndex}\n- Timeframe: ${data.timeframe}`,
          timestamp: new Date().toISOString()
        }],
        isProcessing: true,
        progress: 5
      }
    }));

    try {
      // Start troubleshooting via API utility
      const result = await startTroubleshooting({
        elkIndex: data.elkIndex || 'logs-*',
        githubRepo: data.repo || data.namespace,
        timeframe: data.timeframe || '1h',
        errorMessage: data.errorMessage || '',
        rawLogs: data.rawLogs || ''
      });

      console.log('✅ Troubleshooting started:', result.session_id);

      // Save backend session ID (WebSocket will auto-connect via useWebSocket hook)
      setSessions(prev => ({
        ...prev,
        [sessionKey]: {
          ...prev[sessionKey],
          backendSessionId: result.session_id,
          progress: 10
        }
      }));

    } catch (error) {
      console.error('Error starting troubleshooting:', error);
      setSessions(prev => ({
        ...prev,
        [sessionKey]: {
          ...prev[sessionKey],
          isProcessing: false,
          progress: 0,
          messages: [...prev[sessionKey].messages, {
            role: 'assistant',
            content: `❌ Failed to start troubleshooting:\n${error instanceof Error ? error.message : String(error)}\n\nPlease ensure backend is running.`,
            timestamp: new Date().toISOString()
          }]
        }
      }));
    }
  };

  const currentSession = sessions[activeSessionId];
 
  return (
    <div className="flex h-screen bg-[#020617] text-slate-300 font-sans overflow-hidden">
      
      {/* LEFT: SESSION HISTORY */}
      <nav className="w-64 bg-[#0f172a] border-r border-slate-800 flex flex-col">
        <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/40">
          <div className="flex items-center gap-2">
            <Terminal size={16} className="text-blue-500" />
            <span className="font-bold text-[10px] uppercase tracking-widest text-white">SRE_CMD</span>
          </div>
          <button 
            onClick={handleCreateNewSession} 
            className="p-1.5 hover:bg-blue-600/20 text-blue-400 border border-blue-500/30 rounded transition-all"
            type="button"
            title="Session"
          >
            <Plus size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-2 custom-scrollbar">
          {Object.values(sessions).reverse().map((s: Session) => (
            <div 
              key={s.id} 
              onClick={() => setActiveSessionId(s.id)}
              className={`group flex items-center justify-between p-2.5 rounded border cursor-pointer transition-all ${
                activeSessionId === s.id 
                ? 'bg-blue-600/10 border-blue-500/40 text-blue-100' 
                : 'border-transparent text-slate-500 hover:bg-slate-800'
              }`}
            >
              <div className="flex items-center gap-3 overflow-hidden">
                <MessageSquare size={14} />
                <div className="flex flex-col truncate flex-1">
                  <span className="text-[11px] font-mono truncate">{s.name}</span>
                  <span className="text-[9px] opacity-40">{s.id}</span>
                </div>
              </div>
              {s.id !== 'SESS-DEFAULT' && (
                <button
                  onClick={(e) => handleDeleteSession(s.id, e)}
                  className="opacity-0 group-hover:opacity-100 p-1 hover:bg-red-500/20 text-red-400 rounded transition-all"
                  type="button"
                  title="Delete Session"
                >
                  <Trash2 size={12} />
                </button>
                 )}
            </div>
          ))}
        </div>
      </nav>

      {/* CENTER: CHAT */}
      
      <main className="flex-1 flex flex-col relative bg-[#020617]">
        <header className="h-14 border-b border-slate-800 bg-[#0f172a] flex items-center justify-between px-6">
          <div className="flex items-center gap-3">
            <Activity size={14} className="text-blue-500" />
            <span className="text-[10px] font-bold text-white uppercase tracking-widest">
              Live_Session: <span className="text-blue-400 font-mono ml-2">{activeSessionId}</span>
            </span>
          </div>
          <div className="flex items-center gap-4">
            {/* Connection Status */}
            {currentSession?.wsConnected ? (
              <div className="flex items-center gap-1.5">
                <Wifi size={12} className="text-emerald-500" />
                <span className="text-[9px] text-emerald-500 uppercase font-bold">Connected</span>
              </div>
            ) : currentSession?.isProcessing ? (
              <div className="flex items-center gap-1.5">
                <Loader2 size={12} className="animate-spin text-amber-500" />
                <span className="text-[9px] text-amber-500 uppercase font-bold">Processing</span>
              </div>
            ) : (
              <div className="flex items-center gap-1.5">
                <WifiOff size={12} className="text-slate-600" />
                <span className="text-[9px] text-slate-600 uppercase font-bold">Idle</span>
              </div>
            )}
            
            {/* Progress Bar */}
            <div className="h-1 w-24 bg-slate-800 rounded-full overflow-hidden">
              <div 
                className="h-full bg-blue-500 transition-all duration-700" 
                style={{width: `${currentSession?.progress || 0}%`}} 
              />
            </div>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto p-6 space-y-8 custom-scrollbar">
           
           {currentSession?.messages.map((m: Message, i: number) => {
            const isAgent1Summary = m.role === 'assistant' && m.content.includes('Agent 1');
            const hasAgentData = !!currentSession.agentResults.logs;
            const isAgent2Summary = m.role === 'assistant' && m.content.includes('Agent 2 Analysis Complete');
            if (isAgent2Summary) return null;

            // You must return the JSX here because of the curly braces above
            return (
              <div key={i} className={`flex gap-4 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {m.role !== 'user' && (
                  <div className="w-8 h-8 rounded bg-slate-800 border border-slate-700 flex items-center justify-center flex-shrink-0">
                    <Cpu size={16} className="text-blue-500"/>
                  </div>
                )}
                <div className={`p-4 rounded border ${
                  m.role === 'user' 
                    ? 'bg-blue-600/10 border-blue-500/20 max-w-[70%]' 
                    : 'bg-slate-900/50 border-slate-800 max-w-[85%]'
                }`}>
                  {/* Conditional Rendering logic */}
                  {isAgent1Summary && hasAgentData ? (
                    <Agent1Report 
                      content={m.content} 
                      data={currentSession.agentResults.logs} 
                    />
                  ) : (
                    <div className="text-[13px] font-mono leading-relaxed text-slate-300 whitespace-pre-wrap">
                      {m.content}
                    </div>
                  )}

                  {/* Actions logic */}
                  {m.actions && (
                    <div className="flex gap-2 mt-4">
                      {m.actions.map((a: MessageAction) => (
                        <button 
                          key={a.id} 
                          onClick={() => setActiveFormType('troubleshoot')} 
                          className="flex items-center gap-2 px-3 py-1.5 bg-slate-950 border border-slate-800 rounded text-[10px] uppercase font-bold text-slate-400 hover:text-white transition-all"
                          type="button"
                        >
                          <a.icon size={12}/> {a.label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
      
           {currentSession?.agentResults?.trace?.diagnosticSummary &&( 
             <Agent2DiagnosticDashboard 
              data={{
                root_cause_location: currentSession.agentResults.trace?.root_cause_location ?? "Unknown Location",
                relevant_files: currentSession.agentResults.trace?.relevant_files ?? [],
                diagnosticSummary: currentSession.agentResults.trace?.diagnosticSummary ?? "No summary available",
                flowchart: currentSession.agentResults.trace?.flowchart ?? "",
                impactAnalysis: currentSession.agentResults.trace?.impactAnalysis ?? "No analysis available",
                recommendedFix: currentSession.agentResults.trace?.recommendedFix ?? "",
                confidence: currentSession.agentResults.trace?.confidence ?? 0
              }}
              onStagePR={handleCreatePR} 
              />
          )}
        {activeAgent === "3" && (
        <div className="space-y-6 animate-in slide-in-from-right-4 duration-500">
        

       {/* B. Once the fix arrives, show the Review Screen */}
              {currentSession.agentResults.fix?.diff && (
                <div className="space-y-8">
                  
                  {/* The Main Review Screen (Diff + PR Info) */}
                  <ReviewFixScreen 
                    pr_title={currentSession.agentResults.fix?.prTitle}
                    pr_body={currentSession.agentResults.fix?.prBody}
                    diff={currentSession.agentResults.fix?.diff}
                    branch_name={currentSession.agentResults.fix?.branchName}
                    onCreatePR={handleCreatePR} // Your function to finalize the PR
                    onReject={() => setActiveAgent("2")} // Go back to Agent 2 if rejected
                  />

                </div>
              )}
            </div>
          )}
           {/* Inside the main content area of TroubleshootingUI.tsx */}
            {showPRSuccess && prDetails &&(
              <div className="max-w-2xl mx-auto py-8 animate-in zoom-in-95 duration-500">
                <PRSuccessScreen data={prDetails} />
                
                {/* Add your Postmortem Download Button here for a complete experience */}
                <div className="mt-4 flex justify-center">
                  <button 
                    onClick={handleDownloadReport}
                    className="flex items-center gap-2 text-[10px] text-slate-500 hover:text-white transition-colors"
                  >
                    <FileText size={14} /> Generate Incident Postmortem
                  </button>
                </div>
              </div>
            ) }   
         
                  {/* 2. THE THINKING DOTS (Always at the bottom of the list) */}
          {isTyping && (
            <div className="flex justify-start mb-4 animate-in fade-in duration-300">
              <div className="bg-slate-900 border border-slate-800 rounded-lg p-3">
                <div className="flex gap-1">
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce" />
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:0.2s]" />
                  <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-bounce [animation-delay:0.4s]" />
                </div>
              </div>
            </div>
          )} 
          {/* Bottom reference for scrolling */}
          <div ref={messagesEndRef} />
        </div>

        <footer className="p-4 border-t border-slate-800 bg-[#0f172a]">
          <form onSubmit={handleSendMessage} className="relative max-w-4xl mx-auto">
            <Terminal size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-700" />
            <input 
              value={input}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setInput(e.target.value)}
              disabled={currentSession?.isProcessing}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-12 pr-4 py-3 text-sm font-mono text-blue-100 outline-none focus:border-blue-500/30 transition-all placeholder:text-slate-800 disabled:opacity-50"
              placeholder="Enter CLI command..."
              type="text"
            />
          </form>
        </footer>

        {/* --- THE MODAL FORM --- */}
        {activeFormType && (
          <div className="absolute inset-0 z-50 flex items-center justify-center p-6 bg-black/60 backdrop-blur-sm">
            <DiagnosticForm 
              onSubmit={handleFormSubmit} 
              onCancel={() => setActiveFormType(null)} 
            />
          </div>
        )}
      </main>

      {/* RIGHT: INSPECTOR - NOW ALWAYS VISIBLE */}
      <aside className="w-[400px] bg-[#0f172a] border-l border-slate-800 flex flex-col">
        <div className="p-4 border-b border-slate-800 flex justify-between items-center bg-slate-900/50">
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-600">
            Context_Inspector
          </span>
          <ShieldCheck size={14} className="text-emerald-600" />
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-6 custom-scrollbar">
           <InspectorCard 
             title="Agent_01: Logs Analysis" 
             data={currentSession?.agentResults?.logs} 
             icon={FileText}
             isThinking={isThinking}
             activeAgent={activeAgent}
           >
              {currentSession?.agentResults?.logs && (
                <div className="space-y-2">
                  <div className="text-[11px] font-mono text-blue-400">
                    {currentSession.agentResults.logs.exception_type}
                  </div>
                  <div className="text-[9px] text-slate-500">
                    {currentSession.agentResults.logs.exception_message}
                  </div>
                  <div className="text-[9px] text-slate-600 mt-2">
                    Error Logs: {currentSession.agentResults.logs.log_count}
                  </div>
                </div>
              )}
           </InspectorCard>
           <InspectorCard 
             title="Agent_02: Context Graph" 
             data={currentSession?.agentResults?.trace} 
             icon={Layers}
             isThinking={isThinking}      // <-- Pass the state here
             activeAgent={activeAgent}
           >
              {currentSession?.agentResults?.trace && (
                <div className="space-y-2">
                  <div className="text-[11px] font-mono text-emerald-400">
                    {currentSession.agentResults.trace.root_cause_location}
                  </div>
                  <div className="text-[9px] text-slate-500">
                    Files: {currentSession.agentResults.trace.relevant_files?.length || 0}
                  </div>
                  <div className="text-[9px] text-slate-600">
                    Call Chain: {currentSession.agentResults.trace.call_chain?.length || 0}
                  </div>
                </div>
              )}
           </InspectorCard>
           <InspectorCard 
             title="Agent_03: Proposed Fix" 
             data={currentSession?.agentResults?.fix} 
             icon={GitPullRequest}
             isThinking={isThinking}      // <-- Pass the state here
             activeAgent={activeAgent}
           >
              {currentSession?.agentResults?.fix && (
                <div className="space-y-2">
                  <div className="text-[11px] font-mono text-purple-400">
                    {currentSession.agentResults.fix.pr_title}
                  </div>
                  <div className="text-[9px] text-slate-500">
                    Confidence: {(currentSession.agentResults.fix.confidence_score! * 100).toFixed(0)}%
                  </div>
                  <div className="text-[9px] text-slate-600">
                    Changes: {currentSession.agentResults.fix.changes?.length || 0}
                  </div>
                </div>
              )}
           </InspectorCard>           
           {/* NEW - Agent 2 Production Details */}
           {agent2Mapping && <CodebaseMappingCard data={agent2Mapping} />}
           {agent2Context && <ContextRetrievalCard data={agent2Context} />}
           {agent2CallChain && <CallChainAnalysisCard data={agent2CallChain} />}
           {agent2Dependencies && <DependencyTrackingCard data={agent2Dependencies} />}
           {agent3Progress.length > 0 && !showReviewScreen && (
              <Agent3ProgressCard
                currentStage={agent3Progress[agent3Progress.length - 1]?.stage}
                stages={agent3Progress}
              />
            )}

           {showReviewScreen && agent3ReviewData && (
              <ReviewFixScreen
                {...agent3ReviewData}
                sessionId={currentSession?.backendSessionId || ''}
                onCreatePR={handleCreatePR}
                onReject={handleRejectFix}
                isCreatingPR={isCreatingPR}
              />
            )}

           {showPRSuccess && (
              <PRSuccessScreen data={agent3PRResult} />
            )}
         
        </div>
      </aside>
        </div>
  );
};

// --- SUB-COMPONENTS ---

const DiagnosticForm: React.FC<DiagnosticFormProps> = ({ onSubmit, onCancel }) => {
  const [data, setData] = useState<FormData>({ 
    targetType: 'application', 
    repo: '', 
    namespace: '', 
    errorMessage: '',
    elkIndex: 'logs-production-*',
    timeframe: '1h',
    rawLogs: ''
  });
  const handleSubmit = (): void => {
    onSubmit(data);
  };

  return (
    <div className="w-full max-w-md bg-[#0f172a] border border-blue-500/30 rounded-lg shadow-2xl overflow-hidden animate-in zoom-in-95">
      <div className="bg-slate-800/50 p-4 border-b border-slate-800 flex justify-between items-center">
        <span className="text-[10px] font-bold uppercase tracking-widest text-white">
          Setup_Analysis
        </span>
        <button 
          onClick={onCancel} 
          className="text-slate-400 hover:text-white transition-colors"
          type="button"
        >
          <X size={16}/>
        </button>
      </div>
      <div className="p-6 space-y-5">
        {/* Target Type Toggle */}
        <div className="flex p-1 bg-slate-950 border border-slate-800 rounded">
            <button 
              onClick={() => setData({...data, targetType: 'application'})} 
              className={`flex-1 py-2 text-[10px] font-bold rounded ${
                data.targetType === 'application' ? 'bg-blue-600 text-white' : 'text-slate-500'
              }`}
              type="button"
            >
              APPLICATION
            </button>
            <button 
              onClick={() => setData({...data, targetType: 'infrastructure'})} 
              className={`flex-1 py-2 text-[10px] font-bold rounded ${
                data.targetType === 'infrastructure' ? 'bg-blue-600 text-white' : 'text-slate-500'
              }`}
              type="button"
            >
              INFRASTRUCTURE
            </button>
        </div>
        
        {/* Repo/Namespace Field */}
        <div className="space-y-1">
            <label className="text-[9px] uppercase font-bold text-slate-500">
              {data.targetType === 'application' ? 'GitHub Repo *' : 'Namespace/Resource *'}
            </label>
            <input 
              value={data.targetType === 'application' ? data.repo : data.namespace}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setData({
                ...data, 
                repo: data.targetType === 'application' ? e.target.value : data.repo,
                namespace: data.targetType === 'infrastructure' ? e.target.value : data.namespace
              })} 
              className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-mono text-blue-400 outline-none focus:border-blue-500/50" 
              placeholder={data.targetType === 'application' ? "org/repo" : "openshift-project"}
              type="text"
            />
        </div>

        {/* ELK Index */}
        <div className="space-y-1">
          <label className="text-[9px] uppercase font-bold text-slate-500">ELK Index Pattern</label>
          <input 
            value={data.elkIndex}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setData({...data, elkIndex: e.target.value})} 
            className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-mono text-blue-400 outline-none focus:border-blue-500/50" 
            placeholder="logs-production-*"
            type="text"
          />
        </div>

        {/* Timeframe and Error Filter */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-[9px] uppercase font-bold text-slate-500">Timeframe</label>
            <select
              value={data.timeframe}
              onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setData({...data, timeframe: e.target.value})}
              className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-mono text-blue-400 outline-none focus:border-blue-500/50"
            >
              <option value="15m">15 minutes</option>
              <option value="1h">1 hour</option>
              <option value="6h">6 hours</option>
              <option value="24h">24 hours</option>
            </select>
          </div>
          <div className="space-y-1">
            <label className="text-[9px] uppercase font-bold text-slate-500">Error Filter</label>
            <input 
              value={data.errorMessage}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setData({...data, errorMessage: e.target.value})}
              className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-mono text-slate-400 outline-none focus:border-blue-500/50" 
              placeholder="Optional"
              type="text"
            />
          </div>
        </div>

        {/* Raw Logs */}
        <textarea 
          value={data.rawLogs}
          onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setData({...data, rawLogs: e.target.value})} 
          rows={3} 
          className="w-full bg-slate-950 border border-slate-800 rounded p-2 text-xs font-mono text-slate-400 outline-none focus:border-blue-500/50" 
          placeholder="Paste raw logs (optional)..." 
        />
        
        {/* Submit Button */}
        <button 
          onClick={handleSubmit} 
          className="w-full bg-blue-600 hover:bg-blue-700 py-3 rounded text-[10px] font-bold uppercase tracking-widest text-white transition-all shadow-lg hover:shadow-blue-500/50"
          type="button"
        >
          Start Pipeline
        </button>
      </div>
    </div>
  );
};
const InspectorCard: React.FC<InspectorCardProps> = ({ 
      title, icon: Icon, data, children, isThinking, activeAgent 
    }) => {
      // Logic to determine if THIS specific card should show the thinking state
      // We map the card title to the Agent ID (e.g., Log Analysis = Agent 1)
      const isThisAgentThinking = isThinking && (
        (title.includes("Logs") && activeAgent === "1") ||
        (title.includes("Context") && activeAgent === "2") ||
        (title.includes("Fix") && activeAgent === "3")
      );

      return (
        <div className={`transition-all duration-700 ${data || isThisAgentThinking ? 'opacity-100' : 'opacity-20'}`}>
          <div className="flex items-center gap-2 mb-2">
            <Icon size={14} className={isThisAgentThinking ? "text-blue-500" : "text-slate-600"} />
            <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">
              {title}
            </span>
          </div>
          <div className={`min-h-[80px] border border-dashed rounded p-4 transition-colors ${
            isThisAgentThinking ? 'border-blue-500/50 bg-blue-500/5' : 'border-slate-800 bg-slate-950/40'
          }`}>
            {data ? (
              children
            ) : (
              <div className="text-[9px] font-mono flex items-center gap-2">
                <Loader2 size={10} className={`animate-spin ${isThisAgentThinking ? 'text-blue-500' : 'text-slate-800'}`} /> 
                {isThisAgentThinking ? (
                  <span className="text-blue-400 animate-pulse tracking-widest">AGENT {activeAgent} ANALYZING...</span>
                ) : (
                  <span className="text-slate-800 uppercase">Awaiting Signal...</span>
                )}
              </div>
            )}
          </div>
        </div>
      );
    };
// Add custom scrollbar styles
if (typeof document !== 'undefined') {
  const style = document.createElement('style');
  style.textContent = `
    .custom-scrollbar::-webkit-scrollbar {
      width: 6px;
    }
    .custom-scrollbar::-webkit-scrollbar-track {
      background: #0f172a;
    }
    .custom-scrollbar::-webkit-scrollbar-thumb {
      background: #334155;
      border-radius: 3px;
    }
    .custom-scrollbar::-webkit-scrollbar-thumb:hover {
      background: #475569;
    }
  `;
  document.head.appendChild(style);
}

export default TroubleshootingChatbot;
