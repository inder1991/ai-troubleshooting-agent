"""
Agent 1 Node - Integrates EnterpriseAgent1_LogParser with your system
"""

from typing import Dict, Any
from elasticsearch import Elasticsearch
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
import os

# Import your existing Agent 1
from .agent1_log_analyzer import EnterpriseAgent1_LogParser


async def run_agent1_analysis(
    elk_index: str,
    timeframe: str,
    github_repo: str,
    error_filter: str = None
) -> Dict[str, Any]:
    """
    Run Agent 1 log analysis
    
    Returns structured data for UI display and Agent 2
    """
    
    print("\n" + "="*80)
    print("🤖 AGENT 1: LOG ANALYSIS")
    print("="*80)
    print(f"ELK Index: {elk_index}")
    print(f"Timeframe: {timeframe}")
    print(f"Repo: {github_repo}")
    print("="*80 + "\n")
    
    try:
        # Initialize Elasticsearch
        elk = Elasticsearch(
            "https://localhost:9200",
            basic_auth=("elastic", "Z020j96A9TQ5k3j0NTuQVHB6"),
            verify_certs=False
        )
        
        # Initialize LLM
       # llm = ChatOpenAI(
           # temperature=5,
           #  base_url="http://localhost:11434/v1",
         #   api_key="ollama"
        #)
        llm = ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        temperature=0,
        max_tokens=8192,
        timeout= 120,
        max_retries=3,
        api_key=os.getenv("ANTHROPIC_API_KEY", "")
        )
        # Initialize Agent 1
        agent = EnterpriseAgent1_LogParser(
            elk_client=elk,
            llm_client=llm,
            timezone="Asia/Dubai"
        )
        
        # Extract service name from repo
        service_name = extract_service_name(github_repo)
        
        print(f"🎯 Analyzing service: {service_name}")
        
        # Run Agent 1
        result = await agent.run(
            elk_index=elk_index,
            timeframe=timeframe,
            user_reported_issue=error_filter or "",
            service_name=service_name,
            namespace="",
            environment="",
            error_message_filter=error_filter or ""
        )
        print("✅ Agent 1 analysis complete")
        llm_analysis = result.get('llm_analysis', {})
        # Extract the nested data
        if 'structured_input' in result:
            print("📦 Extracting data from 'structured_input' (nested format)")
            structured_data = result['structured_input']
        else:
            print("📦 Using direct format (no nesting)")
            structured_data = result
        
        # Extract results from the correct location
        patterns = structured_data.get('error_pattern_summary', [])
        log_summary = structured_data.get('log_volume_summary', {})        
        # Validation
        if not patterns:
            print("⚠️  Warning: No error patterns found in Agent 1 response")
        
        primary_error = patterns[0] if patterns else {}
        
        print(f"✅ Found {len(patterns)} error patterns")
        print(f"✅ Total errors: {log_summary.get('error_events_matched', 0)}")
        
        # Debug output
        if primary_error:
            print(f"\n📍 Primary Error Details:")
            print(f"   Type: {primary_error.get('exception_type', 'Unknown')}")
            print(f"   Message: {primary_error.get('message_fingerprint', 'N/A')}")
            print(f"   File: {primary_error.get('file_path', 'Unknown')}")
            print(f"   Line: {primary_error.get('line_number', 0)}")
            print(f"   Function: {primary_error.get('function_name', 'Unknown')}")
        
        # Format for your UI and Agent 2
        formatted_result = {
            "correlationId": primary_error.get('correlation_ids_sample', [''])[0],
            "exceptionType": primary_error.get('exception_type', 'Unknown'),
            "exceptionMessage": primary_error.get('message_fingerprint', ''),
            "stackTrace": primary_error.get('stack_trace_sample', ''),
            "preliminaryRca": llm_analysis.get('root_cause', 'Analysis complete'),
            "logCount": log_summary.get('error_events_matched', 0),
            "errorPatterns": len(patterns),
            "confidence": calculate_confidence(structured_data, llm_analysis),
            "filePath": primary_error.get('file_path', ''),
            "lineNumber": primary_error.get('line_number', 0),
            "functionName": primary_error.get('function_name', ''),
            "bugId": primary_error.get('bug_id', ''),
            "preliminaryRca": llm_analysis.get('root_cause', 'Analysis complete'),
            "diagnosticSummary": llm_analysis.get('diagnostic_summary', ''),
            "developerRecommendation": llm_analysis.get('developer_recommendations', ''),
            "agent2Directive": llm_analysis.get('agent_2_directive', ''),
            "severity": llm_analysis.get('severity', 'MEDIUM'),
            "traceIDs": primary_error.get('correlation_ids_sample', 0),
            "patterns" : patterns,
        }
        
        print(f"\n📊 Formatted Result for Agent 2:")
        print(f"   Exception: {formatted_result['exceptionType']}")
        print(f"   File: {formatted_result['filePath']}:{formatted_result['lineNumber']}")
        print(f"   Function: {formatted_result['functionName']}")
        print(f"   Confidence: {formatted_result['confidence']:.0%}")
        print(f"   Error Patterns: {formatted_result['errorPatterns']}")
        
        return formatted_result
        
    except Exception as e:
        print(f"❌ Agent 1 Error: {e}")
        import traceback
        traceback.print_exc()
        raise


def extract_service_name(repo: str) -> str:
    """Extract service name from GitHub repo"""
    if '/' in repo:
        return repo.split('/')[-1]
    return repo


def calculate_confidence(result: Dict, llm_analysis: Dict) -> float:
    """Calculate confidence score"""
    confidence = 0.5
    
    patterns = result.get('error_pattern_summary', [])
    
    # More patterns = lower confidence in single root cause
    if len(patterns) == 1:
        confidence += 0.2
    elif len(patterns) <= 3:
        confidence += 0.1
    
    # Stack trace presence increases confidence
    if patterns and patterns[0].get('stack_trace_sample'):
        confidence += 0.2
    
    # LLM confidence adjustment
    llm_conf = llm_analysis.get('overall_confidence', 'MEDIUM')
    if llm_conf == 'HIGH':
        confidence += 0.15
    elif llm_conf == 'LOW':
        confidence -= 0.15
    
    return min(1.0, max(0.0, confidence))