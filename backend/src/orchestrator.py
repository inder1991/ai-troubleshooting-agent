"""
Troubleshooting Workflow Orchestrator

Manages the complete 3-agent troubleshooting workflow with:
- Agent 1: Log Analysis & Exception Extraction
- Agent 2: Code Navigation & Root Cause Analysis (4 responsibilities)
- Agent 3: Fix Generation & PR Creation

Author: Production AI Team
Version: 2.0 (with Production Agent 2)
"""

import os
import asyncio
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from pathlib import Path
from src.agents.agent3.fix_generator import Agent3FixGenerator
from langchain_anthropic import ChatAnthropic


class TroubleshootingOrchestrator:
    """
    Orchestrates the complete troubleshooting workflow
    
    Responsibilities:
    1. Workflow execution (3 agents in sequence)
    2. State management (centralized)
    3. Progress tracking (WebSocket updates)
    4. Resource management (clone/cleanup)
    5. Error handling (graceful degradation)
    """
    
    def __init__(
        self,
        session_id: str,
        github_repo: str,
        elk_index: str,
        timeframe: str,
        error_message: Optional[str] = None,
        websocket_manager: Optional[Any] = None
    ):
        """
        Initialize orchestrator
        
        Args:
            session_id: Unique session identifier
            github_repo: GitHub repository (owner/repo)
            elk_index: ELK index pattern
            timeframe: Time window for log analysis
            error_message: Optional error filter
            websocket_manager: WebSocket manager for real-time updates
        """
        # Configuration
        self.session_id = session_id
        self.github_repo = github_repo
        self.elk_index = elk_index
        self.timeframe = timeframe
        self.error_message = error_message
        self.ws_manager = websocket_manager
        
        # Agent results (workflow state)
        self.agent1_result: Optional[Dict[str, Any]] = None
        self.agent2_result: Optional[Dict[str, Any]] = None
        self.agent3_result: Optional[Dict[str, Any]] = None
        
        # Resources
        self.repo_path: Optional[str] = None
        self.agent3_instance: Optional[Any] = None  

        # Status tracking
        self.current_step = "initialized"
        self.progress = 0.0
        self.errors = []
        self.start_time = datetime.now()
    
    # =========================================================================
    # MAIN WORKFLOW
    # =========================================================================
    
    async def run(self) -> Dict[str, Any]:
        """
        Execute the complete troubleshooting workflow
        
        Returns:
            Complete workflow results including all agent outputs
            
        Raises:
            Exception: If workflow fails critically
        """
        try:
            self._log_workflow_start()
            
            # Phase 1: Agent 1 - Log Analysis
            await self._run_agent1()
            
            # Phase 2: Agent 2 - Code Navigation (Production with 4 responsibilities)
            await self._run_agent2()
            
            # Phase 3: Agent 3 - Fix Generation
            await self._run_agent3()
            
            # Phase 4: Handle PR Creation
            await self._handle_pr_creation()
            
            # Compile final results
            results = self._compile_results()
            
            self._log_workflow_complete()
            
            return results
            
        except Exception as e:
            await self._handle_error(e)
            raise
        
        finally:
            print("done")
            # Always cleanup resources
          #  await self.cleanup()
    
    # =========================================================================
    # AGENT 1: LOG ANALYSIS
    # =========================================================================
    
    async def _run_agent1(self):
        """
        Execute Agent 1: Log Analysis & Exception Extraction
        
        Outputs:
        - exceptionType
        - exceptionMessage
        - stackTrace
        - preliminaryRca
        - correlationId
        - errorPatterns
        """
        try:
            self.current_step = "agent1"
            self.progress = 0.15
            
            await self._send_progress("🔍 Agent 1: Analyzing logs...")
            
            print("\n" + "="*80)
            print("📊 AGENT 1: LOG ANALYSIS & EXCEPTION EXTRACTION")
            print("="*80)
            print(f"  ELK Index: {self.elk_index}")
            print(f"  Timeframe: {self.timeframe}")
            print(f"  Repository: {self.github_repo}")
            
            # Import Agent 1
            from .agents.agent1_node import run_agent1_analysis
            
            # Run Agent 1
            self.agent1_result = await run_agent1_analysis(
                elk_index=self.elk_index,
                timeframe=self.timeframe,
                github_repo=self.github_repo,
                error_filter=self.error_message
            )
            
            # Send results via WebSocket
            if self.ws_manager:
                await self.ws_manager.send_message(self.session_id, {
                    "type": "agent1_streaming_complete",
                    "timestamp": datetime.now().isoformat(),
                    "data": self.agent1_result
                })
            
            # Log summary
            print(f"\n✅ Agent 1 Complete")
            print(f"   Exception Type: {self.agent1_result.get('exceptionType', 'Unknown')}")
            print(f"   Exception Message: {self.agent1_result.get('exceptionMessage', 'N/A')[:60]}...")
            print(f"   Stack Trace Lines: {len(self.agent1_result.get('stackTrace', '').split(chr(10)))}")
            print(f"   Preliminary RCA: {self.agent1_result.get('preliminaryRca', 'N/A')[:60]}...")
            
        except Exception as e:
            print(f"\n❌ Agent 1 Failed: {e}")
            raise
    
    # =========================================================================
    # AGENT 2: CODE NAVIGATION (PRODUCTION - 4 RESPONSIBILITIES)
    # =========================================================================
    
    async def _run_agent2(self):
        """
        Execute Agent 2: Code Navigation & Root Cause Analysis
        
        Production version with 4 key responsibilities:
        1. Codebase Mapping - Map stack trace to repository files
        2. Context Retrieval - Extract functions, imports, code snippets
        3. Call Chain Analysis - Build execution path, identify failure point
        4. Dependency Tracking - Find external/internal dependencies, conflicts
        
        Outputs:
        - mapped_locations (with confidence scores)
        - code_snippets
        - function_definitions
        - call_chain (simple + detailed)
        - data_flow_analysis
        - failure_point
        - external_dependencies
        - internal_dependencies
        - dependency_conflicts
        - root_cause_location
        - root_cause_explanation
        - recommended_fix
        - flowchart_mermaid
        - confidence_score
        """
        try:
            self.current_step = "agent2"
            self.progress = 0.30
            
            await self._send_progress("🔧 Agent 2: Initializing code navigator...")
            
            print("\n" + "="*80)
            print("📦 AGENT 2: CODE NAVIGATION & ANALYSIS (PRODUCTION)")
            print("="*80)
            
            # Step 1: Clone Repository
            await self._clone_repository()
            
            # Step 2: Prepare Agent 2 State
            agent2_state = self._prepare_agent2_state()
            
            # Step 3: Run Production Agent 2
            await self._execute_agent2(agent2_state)
            
            # Step 4: Send All 4 Responsibility Results
            await self._send_agent2_results()
            
            # Log summary
            self._log_agent2_summary()
            
        except Exception as e:
            print(f"\n❌ Agent 2 Failed: {e}")
            raise
    
    async def _clone_repository(self):
        """Clone GitHub repository for code analysis"""
        print("\n📥 Cloning Repository...")
        
        from .utils.repo_manager import RepoManager
        
        self.repo_path = f"/tmp/troubleshoot_{self.session_id}"
        
        clone_result = RepoManager.clone_repo(
            github_repo=self.github_repo,
            target_path=self.repo_path
        )
        
        if not clone_result['success']:
            raise Exception(f"Repository clone failed: {clone_result['error']}")
        
        print(f"✅ Repository cloned successfully")
        print(f"   Path: {self.repo_path}")
        print(f"   Files: {clone_result['file_count']}")
        
        await asyncio.sleep(0.5)
    
    def  _prepare_agent2_state(self) -> Dict[str, Any]:
        """Prepare input state for Agent 2 with all Agent 1 data"""
        return {
            # Core data (already being used)
            "stack_trace": self.agent1_result.get('stackTrace', ''),
            "exception_type": self.agent1_result.get('exceptionType', 'Unknown'),
            "exception_message": self.agent1_result.get('exceptionMessage', ''),
            "preliminary_rca": self.agent1_result.get('preliminaryRca', ''),
            
            # Agent 1 insights (NEW - previously ignored!)
            "agent1_file_path": self.agent1_result.get('filePath', ''),        # ← NEW!
            "agent1_line_number": self.agent1_result.get('lineNumber', 0),     # ← NEW!
            "agent1_function_name": self.agent1_result.get('functionName', ''), # ← NEW!
            "agent1_confidence": self.agent1_result.get('confidence', 0.75),   # ← NEW!
            "correlation_id": self.agent1_result.get('correlationId', ''),     # ← NEW!
            "error_pattern_count": self.agent1_result.get('errorPatterns', 1), # ← NEW!
            "log_count": self.agent1_result.get('logCount', 0),                # ← NEW!
            "bug_id": self.agent1_result.get('bugId', ''),
            # Repository context
            "repo_path": self.repo_path,
            "github_repo": self.github_repo,
            
            # Use Agent 1's confidence as starting point (not hardcoded!)
            "confidence_score": self.agent1_result.get('confidence', 0.75)     # ← FIXED!
        }
        
    async def _execute_agent2(self, agent2_state: Dict[str, Any]):
        """Execute Production Agent 2 with all 4 responsibilities"""
        print("\n⚙️  Running Production Agent 2 (All 4 Responsibilities)...")
        
        from .agents.agent2_code_navigator import agent2_code_navigator_node
        
        self.agent2_result = agent2_code_navigator_node(agent2_state)
        
    
    async def _send_agent2_results(self):
        """Send all 4 Agent 2 responsibility results via WebSocket"""
        if not self.ws_manager:
            return
        
        print("\n📤 Sending Agent 2 results via WebSocket...")
        
        # 1️⃣ Codebase Mapping
        await self._send_codebase_mapping()
        
        # 2️⃣ Context Retrieval
        await self._send_context_retrieval()
        
        # 3️⃣ Call Chain Analysis
        await self._send_call_chain_analysis()
        
        # 4️⃣ Dependency Tracking
        await self._send_dependency_tracking()
        
        # Final Synthesis (backwards compatible)
        await self._send_agent2_synthesis()
    
    async def _send_codebase_mapping(self):
        """Send Responsibility 1: Codebase Mapping results"""
        self.progress = 0.40
        await self._send_progress("1️⃣ Mapping code locations...")
        
        mapped_locations = self.agent2_result.get('mapped_locations', [])
        mapping_rate = self.agent2_result.get('mapping_success_rate', '0/0')
        
        await self.ws_manager.send_message(self.session_id, {
            "type": "agent2_codebase_mapping",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "successRate": mapping_rate,
                "totalLocations": len(mapped_locations),
                "mappedLocations": [
                    {
                        "original": loc.get('original', ''),
                        "normalized": loc.get('file', ''),
                        "repoFile": loc.get('repo_file', ''),
                        "line": loc.get('line', 0),
                        "function": loc.get('function', 'unknown'),
                        "confidence": loc.get('confidence', 'low'),
                        "mapped": loc.get('mapped', False)
                    }
                    for loc in mapped_locations[:10]  # Limit to 10 for performance
                ]
            }
        })
        
        print(f"  ✅ Codebase Mapping: {mapping_rate}")
        await asyncio.sleep(0.3)
    
    async def _send_context_retrieval(self):
        """Send Responsibility 2: Context Retrieval results"""
        self.progress = 0.50
        await self._send_progress("2️⃣ Retrieving code context...")
        
        code_snippets = self.agent2_result.get('code_snippets', {})
        function_defs = self.agent2_result.get('function_definitions', {})
        
        await self.ws_manager.send_message(self.session_id, {
            "type": "agent2_context_retrieval",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "codeSnippetsCount": len(code_snippets),
                "functionDefinitionsCount": len(function_defs),
                "codeSnippets": [
                    {
                        "location": location,
                        "code": code[:500],  # Limit size for WebSocket
                        "preview": code[:200]
                    }
                    for location, code in list(code_snippets.items())[:10]
                ],
                "functionDefinitions": [
                    {
                        "name": name,
                        "signature": defn.get('signature', ''),
                        "startLine": defn.get('start_line', 0),
                        "endLine": defn.get('end_line', 0),
                        "docstring": defn.get('docstring', '')[:200]
                    }
                    for name, defn in list(function_defs.items())[:10]
                ]
            }
        })
        
        print(f"  ✅ Context Retrieval: {len(function_defs)} functions, {len(code_snippets)} snippets")
        await asyncio.sleep(0.3)
    
    async def _send_call_chain_analysis(self):
        """Send Responsibility 3: Call Chain Analysis results"""
        self.progress = 0.60
        await self._send_progress("3️⃣ Analyzing call chain...")
        
        call_chain = self.agent2_result.get('call_chain', [])
        call_chain_detailed = self.agent2_result.get('call_chain_detailed', [])
        data_flow = self.agent2_result.get('data_flow_analysis', {})
        failure_point = self.agent2_result.get('failure_point', {})
        
        await self.ws_manager.send_message(self.session_id, {
            "type": "agent2_call_chain_analysis",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "callChain": call_chain,
                "callChainDetailed": [
                    {
                        "function": step.get('function', 'unknown'),
                        "file": step.get('file', ''),
                        "line": step.get('line', 0),
                        "codePreview": step.get('code', '')[:200],
                        "mapped": step.get('mapped', False)
                    }
                    for step in call_chain_detailed[:10]
                ],
                "dataFlow": {
                    "entryPoint": data_flow.get('entry_point', {}).get('function', 'unknown'),
                    "failurePoint": data_flow.get('failure_point', {}).get('function', 'unknown'),
                    "transformations": len(data_flow.get('transformations', []))
                },
                "failureAnalysis": {
                    "location": failure_point.get('location', 'Unknown'),
                    "function": failure_point.get('function', 'unknown'),
                    "reason": failure_point.get('reason', 'Unknown'),
                    "variable": failure_point.get('variable', ''),
                    "missingCleanup": failure_point.get('missing_cleanup', '')
                }
            }
        })
        
        print(f"  ✅ Call Chain Analysis: {len(call_chain)} steps")
        await asyncio.sleep(0.3)
    
    async def _send_dependency_tracking(self):
        """Send Responsibility 4: Dependency Tracking results"""
        self.progress = 0.65
        await self._send_progress("4️⃣ Tracking dependencies...")
        
        external_deps = self.agent2_result.get('external_dependencies', [])
        internal_deps = self.agent2_result.get('internal_dependencies', [])
        conflicts = self.agent2_result.get('dependency_conflicts', [])
        
        await self.ws_manager.send_message(self.session_id, {
            "type": "agent2_dependency_tracking",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "externalDependencies": external_deps,
                "internalDependencies": internal_deps,
                "totalExternal": len(external_deps),
                "totalInternal": len(internal_deps),
                "conflicts": [
                    {
                        "package": conf.get('package', ''),
                        "versions": conf.get('versions', []),
                        "severity": conf.get('severity', 'unknown')
                    }
                    for conf in conflicts
                ],
                "hasConflicts": len(conflicts) > 0
            }
        })
        
        print(f"  ✅ Dependency Tracking: {len(external_deps)} external, {len(internal_deps)} internal")
        if conflicts:
            print(f"  ⚠️  Found {len(conflicts)} dependency conflicts")
        await asyncio.sleep(0.3)
    
    async def _send_agent2_synthesis(self):
        """Send final Agent 2 synthesis (backwards compatible)"""
        self.progress = 0.66
        await self._send_progress("✅ Agent 2: Analysis complete")
        
        call_chain = self.agent2_result.get('call_chain', [])
        function_defs = self.agent2_result.get('function_definitions', {})
        external_deps = self.agent2_result.get('external_dependencies', [])
        internal_deps = self.agent2_result.get('internal_dependencies', [])
        mapping_rate = self.agent2_result.get('mapping_success_rate', '0/0')
        failure_point = self.agent2_result.get('failure_point', {})
        
        await self.ws_manager.send_message(self.session_id, {
            "type": "agent2_streaming_complete",
            "timestamp": datetime.now().isoformat(),
            "data": {
                "rootCause": self.agent2_result.get('root_cause_location', 'Unknown'),
                "impactAnalysis": self.agent2_result.get("impactAnalysis"),
                "rootCauseExplanation": self.agent2_result.get('root_cause_explanation', ''),
                "relevantFiles": self.agent2_result.get('relevant_files', []),
                "callChain": call_chain,
                "flowchart": self.agent2_result.get('flowchart_mermaid', ''),
                "recommendedFix": self.agent2_result.get('recommended_fix', ''),
                "confidence": self.agent2_result.get('confidence_score', 0.0),
                "summary": {
                    "mappingSuccessRate": mapping_rate,
                    "functionsAnalyzed": len(function_defs),
                    "callChainSteps": len(call_chain),
                    "dependenciesFound": len(external_deps) + len(internal_deps),
                    "hasFailureAnalysis": bool(failure_point)
                }
            }
        })
        
        await asyncio.sleep(0.3)
    
    def _log_agent2_summary(self):
        """Log Agent 2 completion summary"""
        print(f"\n✅ Agent 2 Complete (Production Version)")
        print("   " + "─"*76)
        print(f"   Mapping Success: {self.agent2_result.get('mapping_success_rate', '0/0')}")
        print(f"   Functions Found: {len(self.agent2_result.get('function_definitions', {}))}")
        print(f"   Call Chain Steps: {len(self.agent2_result.get('call_chain', []))}")
        print(f"   Dependencies: {len(self.agent2_result.get('external_dependencies', []))} ext, {len(self.agent2_result.get('internal_dependencies', []))} int")
        print(f"   Root Cause: {self.agent2_result.get('root_cause_location', 'Unknown')}")
        print(f"   Confidence: {self.agent2_result.get('confidence_score', 0):.0%}")
        print("   " + "─"*76)
    
    # =========================================================================
    # AGENT 3: FIX GENERATION
    # =========================================================================
    
    async def _run_agent3(self):
        """
        Execute Agent 3: Fix Generation & PR Orchestration
        
        PRODUCTION VERSION with Two-Phase Workflow:
        - PHASE 1: Verification (automatic)
        - PHASE 2: Action (on-demand after user approval)
        
        Outputs:
        - branch_name
        - commit_sha
        - pr_title
        - pr_body
        - validation (syntax, linting, agent2_review)
        - impact (regression_risk, side_effects)
        - diff
        - status: "awaiting_approval"
        """
        error = None
        try:
            self.current_step = "agent3"
            self.progress = 0.70
            
            await self._send_progress("🔧 Agent 3: Generating fix...")
            
            print("\n" + "="*80)
            print("🔧 AGENT 3: FIX GENERATION & PR ORCHESTRATION")
            print("="*80)
            
            # Import Agent 3 (production version)
            from langchain_openai import ChatOpenAI
            
            # Initialize LLM for Agent 3
                
            llm = ChatAnthropic(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
                temperature=0,
                max_tokens=8192,
                timeout= 120,
                max_retries=3,
                api_key="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"
            )
            
            # Initialize Agent 3
            self.agent3_instance = Agent3FixGenerator(
                repo_path=self.repo_path,
                llm=llm,
                agent2_module=None,  # Will use internal peer review
                websocket_manager=self.ws_manager
            )
            
            # STEP 1: Generate fix using LLM
            await self._send_progress("🤖 Generating fix with LLM...")
            print("\n🤖 Generating fix code with LLM...")
            
            generated_fix = await self._generate_fix_with_llm()
            
            # STEP 2: Run PHASE 1 (Verification)
            # This includes:
            # - Static validation (AST, linting)
            # - Agent 2 peer review
            # - Impact assessment
            # - PR staging (local branch + commit)
            # - WebSocket notification to UI
            
            self.progress = 0.75
            await self._send_progress("🛡️ Validating fix (Phase 1)...")
            
            pr_data = await self.agent3_instance.run_verification_phase(
                session_id=self.session_id,
                agent1_analysis=self.agent1_result,
                agent2_analysis=self.agent2_result,
                generated_fix=generated_fix
            )
            # Store result
            self.agent3_result = {
                "status": "awaiting_approval",
                "branch_name": pr_data['branch_name'],
                "commit_sha": pr_data['commit_sha'],
                "pr_title": pr_data['pr_title'],
                "validation_passed": pr_data['validation']['passed'],
                "confidence": pr_data['validation'].get('agent2_confidence', 0.75),
                "explanation": self.agent2_result.get('root_cause_explanation', ''),
                "proposedFix": pr_data['pr_body']
            }
            
            # Store for later PR creation (Phase 2)
            self._store_pr_data(pr_data)
            
            print(f"\n✅ Agent 3 Phase 1 Complete")
            print(f"   Branch: {pr_data['branch_name']}")
            print(f"   Commit: {pr_data['commit_sha'][:7]}")
            print(f"   Validation: {'✅ Passed' if pr_data['validation']['passed'] else '⚠️ Issues'}")
            print(f"   Confidence: {pr_data['validation'].get('agent2_confidence', 0.75):.0%}")
            print(f"   ⏸️  Awaiting user approval...")
            
        except Exception as e:
            error = e  # Store in outer scope variable
            print(f"Error: {error}")
            
            # if self.verbose:
            #     import traceback
            #     traceback.print_exc()
       
        # Fallback to Agent 2 recommendation
            self.agent3_result = {
                "status": "failed",
                "explanation": f"Agent 3 failed: {str(error)}. Using Agent 2 recommendation.",
                "proposedFix": self.agent2_result.get('recommended_fix', 'Manual fix required'),
                "confidence": self.agent2_result.get('confidence_score', 0.5)
            }
            raise
        finally:
            if error:  # Safe to check now
                print(f"   Cleanup after error: {error}")


    async def _generate_fix_with_llm(self) -> str:
        """
        Generate fix code using LLM based on Agent 2's recommendations
        
        Returns:
            Complete fixed file content
        """
        from langchain_core.prompts import ChatPromptTemplate
        from langchain_openai import ChatOpenAI
        
        # Initialize LLM
        llm = ChatAnthropic(
                model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
                temperature=0,
                max_tokens=8192,
                timeout= 120,
                max_retries=3,
                api_key="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"
            )
        
        # Read original file
        file_path = self.agent1_result.get('filePath', '')
        if not file_path:
            raise Exception("No file path from Agent 1")
        
        # Normalize path (remove /app/ prefix)
        normalized_path = file_path.lstrip('/')
        for prefix in ['/app/', 'app/', '/usr/src/app/', 'usr/src/app/']:
            if normalized_path.startswith(prefix):
                normalized_path = normalized_path[len(prefix):]
        
        full_path = os.path.join(self.repo_path, normalized_path)
        
        if not os.path.exists(full_path):
            raise Exception(f"File not found: {full_path}")
        
        with open(full_path, 'r') as f:
            original_code = f.read()
        
        # Create prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert software engineer generating production-ready code fixes.

        Given a bug analysis and recommendations, generate the complete fixed version of the code.

        CRITICAL REQUIREMENTS:
        1. Follow the recommendations EXACTLY
        2. Maintain existing code structure and style
        3. Add necessary imports at the top
        4. Include proper error handling
        5. Add comments explaining the fix
        6. Generate COMPLETE file content (not just the changed function)
        7. Ensure all syntax is correct

        Output ONLY the fixed Python code, no explanations, no markdown.
        """),
                ("human", """File: {file_path}

        Original Code:
        ```python
        {original_code}
        ```

        Bug Analysis (Agent 1):
        {agent1_rca}

        Recommendations (Agent 2):
        {agent2_fix}

        Root Cause Location: {root_cause_location}
        
        Relevant Files: {relevantFiles}         
        Generate the complete fixed file:
        """)
            ])
            
            # Format inputs
        messages = prompt.format_messages(
            file_path=file_path,
            original_code=original_code,
            agent1_rca=self.agent1_result.get('preliminaryRca', 'N/A'),
            agent2_fix=self.agent2_result.get('recommended_fix', 'N/A'),
            root_cause_location=self.agent2_result.get('root_cause_location', 'N/A'),
            relevantFiles= self.agent2_result.get('relevant_files', []),
               
        )
        
        print(f"   Sending to LLM: {len(original_code)} chars of code...")
        
        # Generate fix
        response = await llm.ainvoke(messages)
        
        # Extract code
        fixed_code = response.content
        
        # Remove markdown code blocks if present
        if '```python' in fixed_code:
            fixed_code = fixed_code.split('```python')[1].split('```')[0]
        elif '```' in fixed_code:
            fixed_code = fixed_code.split('```')[1].split('```')[0]
        
        fixed_code = fixed_code.strip()
        
        print(f"   ✅ Fix generated: {len(fixed_code)} chars")
        
        return fixed_code


    def _store_pr_data(self, pr_data: Dict[str, Any]):
        """
        Store PR data for Phase 2 (PR creation after user approval)
        
        In production, store in Redis or similar
        For now, store in instance variable
        """
        self.pr_data = pr_data
        
        # Also store in global sessions dict (if it exists)
        # This allows API endpoints to access it
        try:
            from src.api.session_manager import store_session_data
            store_session_data(self.session_id, 'pr_data', pr_data)
            store_session_data(self.session_id, 'agent3_instance', self.agent3_instance)
            store_session_data(self.session_id, 'repo_path', self.repo_path)

        except ImportError:
            # Session manager not available, just use instance var
            pass
        
        # =========================================================================
        # PR CREATION
        # =========================================================================
    
    async def _handle_pr_creation(self):
        """
        Handle PR creation with two-phase approach
        
        UPDATED: Agent 3 now uses two phases:
        - Phase 1: Verification (already done in _run_agent3)
        - Phase 2: Action (done here after user approval)
        
        This method now just notifies user that review is needed.
        Actual PR creation happens via API endpoint when user clicks "Create PR"
        """
        status = self.agent3_result.get('status', 'unknown')
    
        if status == "awaiting_approval":
            # Agent 3 Phase 1 complete - waiting for user
            print(f"\n⏸️  Agent 3 Phase 1 complete - Fix ready for review")
            print(f"   User can review and approve in UI")
            
            # WebSocket message already sent by Agent 3
            # User will click "Create PR" button in UI
            # That triggers API endpoint which calls execute_pr_creation()
            
            self.progress = 0.90
            await self._send_progress("⏸️ Waiting for user approval...")
            
        elif status == "failed":
            # Agent 3 failed - request manual intervention
            print(f"\n⚠️  Agent 3 failed - manual fix required")
            await self._request_manual_fix()
        
        else:
            # Unknown status
            print(f"\n⚠️  Unknown Agent 3 status: {status}")
            await self._request_manual_fix()


    async def _request_manual_fix(self):
        """Request manual fix when Agent 3 fails"""
        if self.ws_manager:
            await self.ws_manager.send_message(self.session_id, {
                "type": "manual_fix_required",
                "message": "⚠️ Automated fix generation failed. Manual intervention needed.",
                "data": {
                    "agent2_recommendation": self.agent2_result.get('recommended_fix', ''),
                    "root_cause": self.agent2_result.get('root_cause_location', ''),
                    "confidence": self.agent2_result.get('confidence_score', 0.0)
                }
            })
    
    async def _create_pr(self):
        """Create pull request automatically"""
        self.current_step = "create_pr"
        self.progress = 0.95
        
        await self._send_progress("🚀 Creating pull request...")
        
        print("\n📝 Creating Pull Request...")
        
        # Mock PR creation (replace with actual GitHub API call)
        pr_url = f"https://github.com/{self.github_repo}/pull/{1000 + hash(self.session_id) % 9000}"
        
        print(f"✅ PR Created: {pr_url}")
        
        if self.ws_manager:
            await self.ws_manager.send_message(self.session_id, {
                "type": "completed",
                "pr_url": pr_url,
                "message": "✅ Troubleshooting complete! PR created.",
                "summary": {
                    "correlationId": self.agent1_result.get('correlationId'),
                    "exception": self.agent1_result.get('exceptionType'),
                    "root_cause": self.agent2_result.get('root_cause_location'),
                    "confidence": self.agent3_result.get('confidence'),
                    "pr_url": pr_url
                }
            })
    
    async def _request_approval(self, confidence: float):
        """Request human approval for low-confidence fixes"""
        print(f"\n⏸️  Requesting human approval (confidence: {confidence:.0%})")
        
        if self.ws_manager:
            await self.ws_manager.send_message(self.session_id, {
                "type": "approval_required",
                "message": f"⚠️ Human approval required (confidence: {confidence:.0%})",
                "data": self.agent3_result
            })
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def _send_progress(self, message: str):
        """Send progress update via WebSocket"""
        if self.ws_manager:
            await self.ws_manager.send_message(self.session_id, {
                "type": "progress",
                "step": self.current_step,
                "progress": self.progress,
                "message": message
            })
    
    async def _handle_error(self, error: Exception):
        """Handle workflow errors gracefully"""
        self.errors.append({
            "step": self.current_step,
            "error": str(error),
            "timestamp": datetime.now().isoformat()
        })
        
        print(f"\n" + "="*80)
        print(f"❌ ORCHESTRATOR ERROR")
        print("="*80)
        print(f"Step: {self.current_step}")
        print(f"Error: {error}")
        print("="*80)
        
        if self.ws_manager:
            await self.ws_manager.send_message(self.session_id, {
                "type": "error",
                "message": f"❌ Workflow failed at {self.current_step}: {str(error)}",
                "step": self.current_step
            })
    
    async def cleanup(self):
        """Cleanup resources (always called)"""
        if self.repo_path and Path(self.repo_path).exists():
            print(f"\n🗑️  Cleaning up repository: {self.repo_path}")
            
            from src.utils.repo_manager import RepoManager
            RepoManager.cleanup_repo(self.repo_path)
    
    def _compile_results(self) -> Dict[str, Any]:
        """Compile complete workflow results"""
        duration = (datetime.now() - self.start_time).total_seconds()
        
        return {
            "session_id": self.session_id,
            "status": "completed" if not self.errors else "completed_with_errors",
            "duration_seconds": duration,
            "agent1": self.agent1_result,
            "agent2": self.agent2_result,
            "agent3": self.agent3_result,
            "errors": self.errors,
            "metadata": {
                "github_repo": self.github_repo,
                "elk_index": self.elk_index,
                "timeframe": self.timeframe,
                "start_time": self.start_time.isoformat(),
                "end_time": datetime.now().isoformat()
            }
        }
    
    def _log_workflow_start(self):
        """Log workflow initialization"""
        print("\n" + "="*80)
        print("🚀 TROUBLESHOOTING ORCHESTRATOR - WORKFLOW START")
        print("="*80)
        print(f"Session ID: {self.session_id}")
        print(f"Repository: {self.github_repo}")
        print(f"ELK Index: {self.elk_index}")
        print(f"Timeframe: {self.timeframe}")
        print(f"Start Time: {self.start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80 + "\n")
    
    def _log_workflow_complete(self):
        """Log workflow completion"""
        duration = (datetime.now() - self.start_time).total_seconds()
        
        print("\n" + "="*80)
        print("✅ TROUBLESHOOTING ORCHESTRATOR - WORKFLOW COMPLETE")
        print("="*80)
        print(f"Duration: {duration:.1f} seconds")
        print(f"Agent 1: ✅ {self.agent1_result.get('exceptionType', 'Unknown')}")
        print(f"Agent 2: ✅ {self.agent2_result.get('root_cause_location', 'Unknown')}")
        print(f"Agent 3: ✅ Confidence {self.agent3_result.get('confidence', 0):.0%}")
        print(f"Errors: {len(self.errors)}")
        print("="*80 + "\n")