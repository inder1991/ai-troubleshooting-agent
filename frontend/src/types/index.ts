export interface Message {
  role: 'user' | 'assistant';
  content: string;
  type: string;
  timestamp: string;
  actions?: Action[];
  data?: any;
}

export interface SessionData {
  sessionId: string | null;
  config: any;
  agent1Result: any;
  agent2Result: any;
  agent3Result: any;
  wsConnected: boolean;
  agent1Streaming: string;
  agent2Streaming: string;
  agent3Streaming: string;
  isAgent1Streaming: boolean;
  isAgent2Streaming: boolean;
  isAgent3Streaming: boolean;
}

export interface Action {
  id: string;
  label: string;
  icon: any;
  url?: string;
}

export interface Agent1Result {
  correlationId: string;
  exceptionType: string;
  exceptionMessage: string;
  stackTrace: string;
  preliminaryRca: string;
  affectedComponents: string[];
  logCount: number;
}

export interface Agent2Result {
  rootCause: string;
  callChain: string[];
  relevantFiles: string[];
  flowchart: string;
  dependencies: string[];
}

export interface Agent3Result {
  proposedFix: string;
  explanation: string;
  testSuggestions: string[];
  prTitle: string;
  prDescription: string;
  confidence: number;
}
