"""
PRODUCTION AGENT 2: Code Navigator & Analyzer
Implements all 4 key responsibilities:
1. Codebase Mapping
2. Context Retrieval  
3. Call Chain Analysis
4. Dependency Tracking

Location: backend/src/agents/agent2_code_navigator.py
"""

import os
import json
import re
from typing import Dict, Any, List, Set, Tuple
from pathlib import Path
from langchain_openai import ChatOpenAI
from langchain_core.messages import AIMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_anthropic import ChatAnthropic

from ..tools.codebase_tools import CodebaseTools


# ============================================================================
# RESPONSIBILITY 1: CODEBASE MAPPING
# ============================================================================

class CodebaseMapper:
    """Maps stack traces and affected components to specific code locations"""
    
    def __init__(self, tools: CodebaseTools):
        self.tools = tools
        self.file_cache = {}
    
    def normalize_path(self, file_path: str) -> str:
        """
        Normalize container/deployment paths to repository paths
        
        Examples:
            /app/checkout_service.py → checkout_service.py
            /usr/src/app/service.py → service.py
            /code/src/main.py → src/main.py
        """
        # Common deployment prefixes
        prefixes = [
            '/app/', '/usr/src/app/', '/usr/local/app/',
            '/code/', '/src/', '/application/', '/opt/app/'
        ]
        
        normalized = file_path
        for prefix in prefixes:
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
        
        return normalized.lstrip('/')
    
    def find_file_in_repo(self, target_file: str) -> List[str]:
        """
        Find all possible matches for a file in the repository
        
        Returns:
            List of matching file paths (sorted by confidence)
        """
        if target_file in self.file_cache:
            return self.file_cache[target_file]
        
        # Get all files once
        all_files = self.tools.get_file_structure()
        if not all_files or all_files[0].startswith("Error"):
            return []
        
        target_filename = os.path.basename(target_file)
        matches = []
        
        # Exact filename match
        for file in all_files:
            if file.endswith(target_filename):
                matches.append(('exact', file))
        
        # Partial match
        if not matches:
            target_base = target_filename.replace('.py', '').replace('.js', '').replace('.java', '')
            for file in all_files:
                if target_base in file:
                    matches.append(('partial', file))
        
        # Sort by match quality
        result = [m[1] for m in sorted(matches, key=lambda x: (x[0] != 'exact', len(x[1])))]
        self.file_cache[target_file] = result
        
        return result
    
    def extract_stack_trace_locations(self, stack_trace: str) -> List[Dict[str, Any]]:
        """
        Extract all file:line locations from stack trace
        
        Returns:
            List of {"file": str, "line": int, "function": str, "original": str}
        """
        locations = []
        
        # Python: File "path", line 123, in function_name
        python_pattern = r'File\s+"([^"]+)",\s+line\s+(\d+)(?:,\s+in\s+(\w+))?'
        
        # Java/Kotlin: at package.Class.method(File.java:123)
        java_pattern = r'at\s+([\w\.]+)\(([\w\.]+):(\d+)\)'
        
        # JavaScript: at function (file.js:123:45)
        js_pattern = r'at\s+(\w+)?\s*\(([\w\/\.\-]+):(\d+):\d+\)'
        
        # Generic: file.py:123
        generic_pattern = r'([\w\/\.\-]+\.(?:py|js|java|ts|go|rb|cpp)):(\d+)'
        
        patterns = [
            ('python', python_pattern),
            ('java', java_pattern),
            ('javascript', js_pattern),
            ('generic', generic_pattern)
        ]
        
        for lang, pattern in patterns:
            for match in re.finditer(pattern, stack_trace):
                try:
                    if lang == 'python':
                        file_path = match.group(1)
                        line_num = int(match.group(2))
                        func_name = match.group(3) if match.lastindex >= 3 else 'unknown'
                    
                    elif lang == 'java':
                        func_name = match.group(1)
                        file_path = match.group(2)
                        line_num = int(match.group(3))
                    
                    elif lang == 'javascript':
                        func_name = match.group(1) or 'anonymous'
                        file_path = match.group(2)
                        line_num = int(match.group(3))
                    
                    else:  # generic
                        file_path = match.group(1)
                        line_num = int(match.group(2))
                        func_name = 'unknown'
                    
                    # Skip third-party libraries
                    if any(skip in file_path for skip in ['node_modules', 'site-packages', 'vendor']):
                        continue
                    
                    normalized = self.normalize_path(file_path)
                    
                    locations.append({
                        'file': normalized,
                        'line': line_num,
                        'function': func_name,
                        'original': file_path,
                        'language': lang
                    })
                
                except (ValueError, IndexError):
                    continue
        
        # Remove duplicates while preserving order
        seen = set()
        unique = []
        for loc in locations:
            key = f"{loc['file']}:{loc['line']}"
            if key not in seen:
                seen.add(key)
                unique.append(loc)
        
        return unique
    
    def map_to_repository(self, locations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Map extracted locations to actual repository files
        
        Returns:
            List of mapped locations with actual repository paths
        """
        mapped = []
        
        for loc in locations:
            matches = self.find_file_in_repo(loc['file'])
            
            if matches:
                # Use best match
                actual_file = matches[0]
                mapped.append({
                    **loc,
                    'repo_file': actual_file,
                    'mapped': True,
                    'confidence': 'high' if len(matches) == 1 else 'medium'
                })
                print(f"   ✅ {loc['file']}:{loc['line']} → {actual_file}")
            else:
                # No match found
                mapped.append({
                    **loc,
                    'repo_file': loc['file'],
                    'mapped': False,
                    'confidence': 'low'
                })
                print(f"   ⚠️  {loc['file']}:{loc['line']} → Not found in repo")
        
        return mapped


# ============================================================================
# RESPONSIBILITY 2: CONTEXT RETRIEVAL
# ============================================================================

class ContextRetriever:
    """Retrieves code context, interfaces, and function definitions"""
    
    def __init__(self, tools: CodebaseTools):
        self.tools = tools
    
    def get_function_definition(self, file_path: str, function_name: str) -> Dict[str, Any]:
        """
        Retrieve complete function definition with context
        
        Returns:
            {
                "signature": str,
                "body": str,
                "start_line": int,
                "end_line": int,
                "docstring": str
            }
        """
        # Search for function definition
        pattern = f"def {function_name}"
        matches = self.tools.grep_search(pattern, max_results=10)
        
        for match in matches:
            if 'error' in match or match.get('file') != file_path:
                continue
            
            start_line = int(match.get('line', 0))
            
            # Read function with context (up to 100 lines)
            content = self.tools.read_file(file_path, start_line, start_line + 100)
            
            if content and not content.startswith("Error"):
                # Extract docstring
                docstring_match = re.search(r'"""(.*?)"""', content, re.DOTALL)
                docstring = docstring_match.group(1).strip() if docstring_match else ""
                
                # Find function end (simple heuristic: next function or class)
                lines = content.split('\n')
                end_line = start_line
                indent_level = len(lines[0]) - len(lines[0].lstrip())
                
                for i, line in enumerate(lines[1:], 1):
                    if line.strip() and not line.startswith(' ' * (indent_level + 1)):
                        end_line = start_line + i
                        break
                
                return {
                    "signature": lines[0].strip(),
                    "body": content,
                    "start_line": start_line,
                    "end_line": end_line or start_line + len(lines),
                    "docstring": docstring
                }
        
        return {}
    
    def get_class_definition(self, file_path: str, class_name: str) -> Dict[str, Any]:
        """Retrieve complete class definition"""
        pattern = f"class {class_name}"
        matches = self.tools.grep_search(pattern, max_results=5)
        
        for match in matches:
            if 'error' in match or match.get('file') != file_path:
                continue
            
            start_line = int(match.get('line', 0))
            content = self.tools.read_file(file_path, start_line, start_line + 200)
            
            if content and not content.startswith("Error"):
                return {
                    "name": class_name,
                    "definition": content,
                    "start_line": start_line,
                    "file": file_path
                }
        
        return {}
    
    def get_imports(self, file_path: str) -> List[Dict[str, str]]:
        """
        Extract all import statements from a file
        
        Returns:
            List of {"type": "import/from", "module": str, "items": List[str]}
        """
        content = self.tools.read_file(file_path, 0, 100)
        if not content or content.startswith("Error"):
            return []
        
        imports = []
        
        # Python imports
        for line in content.split('\n')[:50]:  # Check first 50 lines
            line = line.strip()
            
            # import module
            if line.startswith('import '):
                module = line.replace('import ', '').split(' as ')[0].strip()
                imports.append({
                    "type": "import",
                    "module": module,
                    "items": []
                })
            
            # from module import items
            elif line.startswith('from '):
                match = re.match(r'from\s+([\w\.]+)\s+import\s+(.+)', line)
                if match:
                    module = match.group(1)
                    items = [i.strip() for i in match.group(2).split(',')]
                    imports.append({
                        "type": "from",
                        "module": module,
                        "items": items
                    })
        
        return imports
    
    def get_interface_usage(self, file_path: str, interface_name: str) -> List[str]:
        """Find all usages of an interface/class in a file"""
        matches = self.tools.grep_search(interface_name, max_results=20)
        
        usages = []
        for match in matches:
            if 'error' not in match and match.get('file') == file_path:
                usages.append(f"Line {match.get('line')}: {match.get('content', '')}")
        
        return usages
    
    def get_surrounding_context(self, file_path: str, line_num: int, context_lines: int = 20) -> str:
        """Get code context around a specific line"""
        start = max(0, line_num - context_lines)
        end = line_num + context_lines
        
        content = self.tools.read_file(file_path, start, end)
        return content if content and not content.startswith("Error") else ""


# ============================================================================
# RESPONSIBILITY 3: CALL CHAIN ANALYSIS
# ============================================================================

class CallChainAnalyzer:
    """Traces execution path to find exact failure point"""
    
    def __init__(self, tools: CodebaseTools, context_retriever: ContextRetriever):
        self.tools = tools
        self.context = context_retriever
    
    def extract_call_chain(self, stack_trace: str, mapped_locations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Build complete call chain from stack trace
        
        Returns:
            List of {"function": str, "file": str, "line": int, "code": str}
        """
        chain = []
        
        for loc in mapped_locations:
            function_name = loc.get('function', 'unknown')
            file_path = loc.get('repo_file', loc.get('file'))
            line_num = loc.get('line', 0)
            
            # Get code context
            code = self.context.get_surrounding_context(file_path, line_num, context_lines=10)
            
            chain.append({
                "function": function_name,
                "file": file_path,
                "line": line_num,
                "code": code[:500],  # Limit size
                "mapped": loc.get('mapped', False)
            })
        
        return chain
    
    def trace_data_flow(self, chain: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Trace how data flows through the call chain
        
        Identifies:
        - Where variables are created
        - Where they're modified
        - Where they become null/invalid
        """
        flow_analysis = {
            "entry_point": chain[0] if chain else {},
            "failure_point": chain[-1] if chain else {},
            "transformations": []
        }
        
        for i, step in enumerate(chain):
            code = step.get('code', '')
            
            # Look for variable assignments
            assignments = re.findall(r'(\w+)\s*=\s*([^\n]+)', code)
            
            # Look for function calls
            calls = re.findall(r'(\w+)\([^)]*\)', code)
            
            # Look for null checks
            null_checks = re.findall(r'if\s+(\w+)\s+is\s+None', code)
            
            if assignments or calls or null_checks:
                flow_analysis["transformations"].append({
                    "step": i,
                    "function": step.get('function'),
                    "assignments": assignments[:5],
                    "calls": calls[:5],
                    "null_checks": null_checks
                })
        
        return flow_analysis
    
    def identify_failure_point(self, chain: List[Dict[str, Any]], exception_type: str, exception_message: str) -> Dict[str, Any]:
        """
        Identify exact point where failure occurred
        
        Returns:
            {
                "location": str,
                "reason": str,
                "variable": str,
                "expected_state": str,
                "actual_state": str
            }
        """
        if not chain:
            return {}
        
        failure_step = chain[-1]
        
        analysis = {
            "location": f"{failure_step.get('file')}:{failure_step.get('line')}",
            "function": failure_step.get('function'),
            "exception": exception_type,
            "message": exception_message
        }
        
        code = failure_step.get('code', '')
        
        # Analyze based on exception type
        if 'null' in exception_type.lower() or 'none' in exception_type.lower():
            # Find variable that was null
            var_match = re.search(r"'(\w+)'", exception_message)
            if var_match:
                analysis["variable"] = var_match.group(1)
                analysis["reason"] = f"Variable '{analysis['variable']}' was None/null when it shouldn't be"
        
        elif 'timeout' in exception_type.lower():
            # Find timeout duration
            timeout_match = re.search(r'(\d+)\s*(ms|seconds?|minutes?)', exception_message)
            if timeout_match:
                analysis["timeout_duration"] = timeout_match.group(1) + timeout_match.group(2)
                analysis["reason"] = f"Operation exceeded timeout of {analysis['timeout_duration']}"
        
        elif 'pool' in exception_message.lower() and 'exhaust' in exception_message.lower():
            analysis["reason"] = "Connection pool exhausted - connections not being released"
            
            # Look for missing close() calls
            if 'close()' not in code:
                analysis["missing_cleanup"] = "No connection.close() found in error path"
        
        return analysis


# ============================================================================
# RESPONSIBILITY 4: DEPENDENCY TRACKING
# ============================================================================

class DependencyTracker:
    """Tracks external libraries and internal service dependencies"""
    
    def __init__(self, tools: CodebaseTools, repo_path: str):
        self.tools = tools
        self.repo_path = Path(repo_path)
    
    def find_dependency_files(self) -> Dict[str, str]:
        """
        Find dependency configuration files
        
        Returns:
            {"type": str, "path": str} for each found
        """
        dependency_files = {
            'python': ['requirements.txt', 'Pipfile', 'pyproject.toml', 'setup.py'],
            'node': ['package.json', 'package-lock.json', 'yarn.lock'],
            'java': ['pom.xml', 'build.gradle', 'build.gradle.kts'],
            'ruby': ['Gemfile', 'Gemfile.lock'],
            'go': ['go.mod', 'go.sum']
        }
        
        found = {}
        all_files = self.tools.get_file_structure()
        
        for lang, files in dependency_files.items():
            for dep_file in files:
                for repo_file in all_files:
                    if repo_file.endswith(dep_file):
                        found[dep_file] = {
                            "type": lang,
                            "path": repo_file
                        }
        
        return found
    
    def extract_dependencies(self, file_type: str, file_path: str) -> List[Dict[str, str]]:
        """
        Extract dependency list from configuration file
        
        Returns:
            List of {"name": str, "version": str, "type": "external/internal"}
        """
        content = self.tools.read_file(file_path)
        if not content or content.startswith("Error"):
            return []
        
        dependencies = []
        
        if file_type == 'requirements.txt':
            # Python requirements
            for line in content.split('\n'):
                line = line.strip()
                if line and not line.startswith('#'):
                    # package==version or package>=version
                    match = re.match(r'([a-zA-Z0-9\-_]+)([><=~!]+)?([\d\.]+)?', line)
                    if match:
                        dependencies.append({
                            "name": match.group(1),
                            "version": match.group(3) or "latest",
                            "type": "external"
                        })
        
        elif file_type == 'package.json':
            # Node.js dependencies
            try:
                data = json.loads(content)
                for dep, version in data.get('dependencies', {}).items():
                    dependencies.append({
                        "name": dep,
                        "version": version.lstrip('^~'),
                        "type": "external"
                    })
            except json.JSONDecodeError:
                pass
        
        return dependencies
    
    def find_internal_dependencies(self, imports: List[Dict[str, str]]) -> List[str]:
        """
        Identify internal service dependencies from imports
        
        Returns:
            List of internal service names
        """
        internal_services = []
        
        # Common patterns for internal services
        internal_patterns = [
            r'from\s+services\.(\w+)',
            r'from\s+app\.services\.(\w+)',
            r'import\s+(\w+_service)',
            r'from\s+\.\.(\w+)',
        ]
        
        for imp in imports:
            module = imp.get('module', '')
            
            # Check if it's a relative import or service import
            for pattern in internal_patterns:
                match = re.search(pattern, module)
                if match:
                    service = match.group(1)
                    if service not in internal_services:
                        internal_services.append(service)
        
        return internal_services
    
    def check_version_conflicts(self, dependencies: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """
        Check for potential version conflicts in dependencies
        
        Returns:
            List of potential conflicts
        """
        conflicts = []
        
        # Group by package name
        by_name = {}
        for dep in dependencies:
            name = dep['name']
            if name not in by_name:
                by_name[name] = []
            by_name[name].append(dep)
        
        # Find duplicates with different versions
        for name, versions in by_name.items():
            if len(versions) > 1:
                conflicts.append({
                    "package": name,
                    "versions": [v['version'] for v in versions],
                    "severity": "high"
                })
        
        return conflicts


# ============================================================================
# MAIN AGENT 2 ORCHESTRATOR
# ============================================================================

def agent2_code_navigator_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    PRODUCTION Agent 2: Complete Code Navigation & Analysis
    
    Implements all 4 key responsibilities:
    1. Codebase Mapping
    2. Context Retrieval
    3. Call Chain Analysis
    4. Dependency Tracking
    """
    
    print(f"\n{'='*80}")
    print("🔧 AGENT 2: CODE NAVIGATOR & ANALYZER")
    print(f"{'='*80}\n")
    
    # Extract inputs
    stack_trace = state.get("stack_trace", "")
    exception_type = state.get("exception_type", "Unknown")
    exception_message = state.get("exception_message", "")
    preliminary_rca = state.get("preliminary_rca", "")
    repo_path = state.get("repo_path", "/tmp/repo")
    github_repo = state.get("github_repo", "")
    confidence_score = state.get("confidence_score", 0.75)
    
    agent1_file_path = state.get('agent1_file_path', '')
    agent1_line_number = state.get('agent1_line_number', 0)
    agent1_function_name = state.get('agent1_function_name', '')
    agent1_confidence = state.get('agent1_confidence', 0.75)
    error_pattern_count = state.get('error_pattern_count', 1)

    print("\n📊 Agent 1 Insights Available:")
    if agent1_file_path:
        print(f"   File: {agent1_file_path}:{agent1_line_number}")
    if agent1_function_name:
        print(f"   Function: {agent1_function_name}()")
    
    print(f"   Agent 1 Confidence: {agent1_confidence:.0%}")
    print(f"   Error Patterns: {error_pattern_count}")
    print(f"📂 Repository: {github_repo}")
    print(f"📍 Local path: {repo_path}")
    print(f"🔍 Exception: {exception_type}")
    print(f"💬 Message: {exception_message[:100]}...")
    print()
    
    # Initialize components
    tools = CodebaseTools(repo_path=repo_path)
    mapper = CodebaseMapper(tools)
    context = ContextRetriever(tools)
    call_analyzer = CallChainAnalyzer(tools, context)
    dep_tracker = DependencyTracker(tools, repo_path)
    
    # ========================================================================
    # RESPONSIBILITY 1: CODEBASE MAPPING
    # ========================================================================
    print("="*80)
    print("1️⃣  CODEBASE MAPPING")
    print("="*80)
    
    # Extract locations from stack trace
    mapped_locations = []
    
    # Step 1: Validate Agent 1's file path if provided
    if agent1_file_path:
        print("\n🔍 Validating Agent 1's identified file...")
        print(repo_path)
        print(agent1_file_path)
        normalized_path = agent1_file_path.lstrip('/')

        # Check if file exists in repository
        full_path = os.path.join(repo_path, normalized_path)
        print(full_path)
        if os.path.exists(full_path):
            print(f"   ✅ Validated: {agent1_file_path} exists in repository")
            
            # Add as first mapped location with high confidence
            mapped_locations.append({
                'original': agent1_file_path,
                'file': agent1_file_path,
                'repo_file': agent1_file_path,
                'line': agent1_line_number if agent1_line_number else 0,
                'function': agent1_function_name if agent1_function_name else 'unknown',
                'confidence': 'high',
                'mapped': True,
                'source': 'agent1',  # Track that this came from Agent 1
                'language': 'python'  # Assume Python, adjust if needed
            })
            print(f"   📍 Starting point: {agent1_file_path}:{agent1_line_number}")
            if agent1_function_name:
                print(f"   🎯 Target function: {agent1_function_name}()")
        else:
            print(f"   ⚠️  Warning: {agent1_file_path} not found in repository")
            print(f"   Will search using stack trace instead...")
        
    # Step 2: Extract locations from stack trace
    print("\n📋 Step 2: Extracting locations from stack trace...")
    locations = mapper.extract_stack_trace_locations(stack_trace)
    print(f"   Found {len(locations)} stack trace locations")

    # Step 3: Map stack trace locations to repository
    print("\n📍 Step 3: Mapping stack trace to repository files...")
    stack_mapped = mapper.map_to_repository(locations)

    # Step 4: Combine results (avoid duplicates)
    for loc in stack_mapped:
    # Check for exact file AND line match
        is_duplicate = any(
            existing.get('repo_file') == loc.get('repo_file') and 
            existing.get('line') == loc.get('line')
            for existing in mapped_locations
        )
        
        if is_duplicate:
            print(f"   ℹ️  Skipping exact duplicate: {loc.get('repo_file')}:{loc.get('line')}")
            continue
    
        mapped_locations.append(loc)

    # ← ADD THIS LINE HERE (CRITICAL!)
    successfully_mapped = sum(1 for loc in mapped_locations if loc.get('mapped'))

    # Print summary
    print(f"\n✅ Mapping Complete:")
    print(f"   Total locations: {len(mapped_locations)}")
    print(f"   Successfully mapped: {successfully_mapped}/{len(mapped_locations)}")
    if agent1_file_path and any(loc.get('source') == 'agent1' for loc in mapped_locations):
        print(f"   🎯 Agent 1's finding validated and prioritized")
    print()



    # ← END OF AGENT 1 VALIDATION
    # ========================================================================
    # RESPONSIBILITY 2: CONTEXT RETRIEVAL
    # ========================================================================
    print("="*80)
    print("2️⃣  CONTEXT RETRIEVAL")
    print("="*80)
    
    code_snippets = {}
    function_defs = {}
    
    print("\n📖 Retrieving code context...")
    
    for loc in mapped_locations[:5]:  # Limit to top 5
        if not loc.get('mapped'):
            continue
        
        file_path = loc['repo_file']
        line_num = loc['line']
        func_name = loc.get('function', 'unknown')
        
        print(f"   Processing {file_path}:{line_num} in {func_name}()")
        
        # Get surrounding context
        context_code = context.get_surrounding_context(file_path, line_num, context_lines=20)
        if context_code:
            code_snippets[f"{file_path}:{line_num}"] = context_code
            print(f"      ✅ Context retrieved ({len(context_code)} chars)")
        
        # Get function definition
        if func_name != 'unknown':
            func_def = context.get_function_definition(file_path, func_name)
            if func_def:
                function_defs[func_name] = func_def
                print(f"      ✅ Function definition retrieved")
        
        # Get imports
        imports = context.get_imports(file_path)
        if imports:
            print(f"      ✅ Found {len(imports)} imports")
    
    print(f"\n✅ Retrieved {len(code_snippets)} code contexts")
    print(f"✅ Retrieved {len(function_defs)} function definitions")
    print()
    
    # ========================================================================
    # RESPONSIBILITY 3: CALL CHAIN ANALYSIS
    # ========================================================================
    print("="*80)
    print("3️⃣  CALL CHAIN ANALYSIS")
    print("="*80)
    
    print("\n🔗 Building call chain...")
    call_chain = call_analyzer.extract_call_chain(stack_trace, mapped_locations)
    
    print(f"Call chain ({len(call_chain)} steps):")
    for i, step in enumerate(call_chain, 1):
        print(f"   {i}. {step['function']}() in {step['file']}:{step['line']}")
    
    print("\n🔍 Tracing data flow...")
    data_flow = call_analyzer.trace_data_flow(call_chain)
    
    print("\n🎯 Identifying failure point...")
    failure_analysis = call_analyzer.identify_failure_point(call_chain, exception_type, exception_message)
    
    if failure_analysis:
        print(f"   Location: {failure_analysis.get('location')}")
        print(f"   Reason: {failure_analysis.get('reason', 'Unknown')}")
    
    print()
    
    # ========================================================================
    # RESPONSIBILITY 4: DEPENDENCY TRACKING
    # ========================================================================
    print("="*80)
    print("4️⃣  DEPENDENCY TRACKING")
    print("="*80)
    
    print("\n📦 Finding dependency files...")
    dep_files = dep_tracker.find_dependency_files()
    
    external_deps = []
    for file_name, info in dep_files.items():
        print(f"   Found: {file_name} ({info['type']})")
        
        # Extract dependencies
        deps = dep_tracker.extract_dependencies(file_name, info['path'])
        external_deps.extend(deps)
        print(f"      → {len(deps)} dependencies")
    
    print(f"\n✅ Total external dependencies: {len(external_deps)}")
    
    # Find internal dependencies
    print("\n🔗 Finding internal service dependencies...")
    all_imports = []
    for loc in mapped_locations[:3]:
        if loc.get('mapped'):
            imports = context.get_imports(loc['repo_file'])
            all_imports.extend(imports)
    
    internal_deps = dep_tracker.find_internal_dependencies(all_imports)
    print(f"   Internal services: {', '.join(internal_deps) if internal_deps else 'None'}")
    
    # Check for conflicts
    print("\n⚠️  Checking for dependency conflicts...")
    conflicts = dep_tracker.check_version_conflicts(external_deps)
    if conflicts:
        print(f"   Found {len(conflicts)} potential conflicts:")
        for conflict in conflicts[:3]:
            print(f"      • {conflict['package']}: {conflict['versions']}")
    else:
        print("   ✅ No conflicts found")
    
    print()
    
    # ========================================================================
    # LLM SYNTHESIS
    # ========================================================================
    print("="*80)
    print("🤖 LLM SYNTHESIS")
    print("="*80)
    print()
    llm = ChatAnthropic(
        model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929"),
        temperature=0,
        max_tokens=8192,
        timeout= 120,
        max_retries=3,
        api_key="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"
    )
    # llm = ChatOpenAI(
    #     temperature=0,
    #     model="llama3:8b-instruct-q2_K",
    #     base_url="http://localhost:11434/v1",
    #     api_key="ollama"
    # )
    
    prompt = ChatPromptTemplate.from_messages([
       ("system", """You are a Senior Site Reliability Engineer and Code Architect. 
        Your goal is to bridge the gap between runtime logs and source code logic.

        CRITICAL INSTRUCTIONS:
        - Do NOT use placeholders like "See manual analysis" or "Pending."
        - You must analyze the provided `code_snippets` against the `stack_trace`.
        - If a database connection is mentioned in the call chain (e.g., get_db_connection), check for connection leaks, timeouts, or missing try-finally blocks in the code context.
        - The `recommended_fix` must be a specific code suggestion (diff format or code block).

        Provide a comprehensive analysis strictly as JSON:
        {{
            "rootCause": "file.py:line_number",
            "rootCauseExplanation": "A technical explanation of the logic failure. Why did this line crash?",
            "relevantFiles": ["file1.py", "file2.py"],
            "callChain": ["function_a", "function_b", "failure_point"],
            "flowchart": "graph TD\\n  A[Start] --> B[Process]",
            "recommendedFix": "```python\\n# The corrected code here\\n```",
            "confidence": 0.0 to 1.0,
            "impactAnalysis": "How this affects the rest of the checkout-service"
        }}"""),

        ("human", """Analyze this production incident for the 'checkout-service':

        **Context from Agent 1 (Log Analysis):**
        - Exception: {exception_type}
        - Message: {exception_message}
        - Failure Analysis: {failure_analysis}

        **Code Investigation Data:**
        - Stack Trace: {stack_trace}
        - Mapped File Locations: {mapped_locations}
        - Execution Call Chain: {call_chain}
        - Internal/External Dependencies: {internal_deps}, {external_deps}

        **Source Code Snippets:**
        {code_snippets}

        Based on the code above, identify the EXACT logical flaw. If the call chain shows repeating calls to {call_chain}, investigate potential recursion or resource exhaustion.""")
            ])
    try:
        print("code 2 llm started")
        chain = prompt | llm
        response = chain.invoke({
            "exception_type": exception_type,
            "exception_message": exception_message,
            "stack_trace": stack_trace[:2000],
            "mapped_locations": json.dumps([{k: v for k, v in loc.items() if k in ['file', 'line', 'function', 'mapped']} for loc in mapped_locations[:5]]),
            "call_chain": json.dumps([{k: v for k, v in step.items() if k != 'code'} for step in call_chain]),
            "failure_analysis": json.dumps(failure_analysis),
            "external_deps": json.dumps([d['name'] for d in external_deps[:10]]),
            "internal_deps": json.dumps(internal_deps),
            "code_snippets": json.dumps({k: v[:200] for k, v in list(code_snippets.items())[:3]})
        })
        
        result_text = response.content.strip()
        print("llm response received")
        # Remove markdown
        if result_text.startswith('```'):
            result_text = re.sub(r'^```(?:json)?\s*\n?', '', result_text)
            result_text = re.sub(r'\n?```\s*$', '', result_text)
        
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            print("⚠️  Using fallback analysis")
            result = {
                "root_cause_location": failure_analysis.get('location', 'Unknown'),
                "root_cause_explanation": failure_analysis.get('reason', 'See manual analysis'),
                "call_chain_summary": [step['function'] for step in call_chain],
                "relevant_files": [loc['repo_file'] for loc in mapped_locations if loc.get('mapped')],
                "dependencies_involved": [d['name'] for d in external_deps[:5]],
                "flowchart_mermaid": "graph TD\n  A[Request] --> B[Processing]\n  B --> C[Error]"
            }
        
        print(f"\n📊 Analysis Summary:")
        print(f"   Root cause: {result.get('rootCauseExplanation')}")
        print(f"   Files involved: {len(result.get('relevantFiles', []))}")
       
        # Calculate final confidence
        base_confidence = result.get('confidence',0.75)
        
        # Adjust based on mapping success
        if successfully_mapped == len(mapped_locations):
            base_confidence += 0.1
        elif successfully_mapped < len(mapped_locations) / 2:
            base_confidence -= 0.1
    
        final_confidence = min(1.0, max(0.0, base_confidence))
        # Build final result
        return {
            **state,
            # Codebase Mapping
            "mapped_locations": mapped_locations,
            "mapping_success_rate": f"{successfully_mapped}/{len(mapped_locations)}",
            
            # Context Retrieval
            "code_snippets": code_snippets,
            "function_definitions": function_defs,
            
            # Call Chain Analysis
            "call_chain": [step['function'] for step in call_chain],
            "call_chain_detailed": call_chain,
            "data_flow_analysis": data_flow,
            "failure_point": failure_analysis,
            
            # Dependency Tracking
            "external_dependencies": [d['name'] for d in external_deps],
            "internal_dependencies": internal_deps,
            "dependency_conflicts": conflicts,
            
            # LLM Synthesis
            "root_cause_location": result.get("rootCause"),
            "root_cause_explanation": result.get("rootCauseExplanation"),
            "relevant_files": result.get("relevantFiles", []),
            "flowchart_mermaid": result.get("flowchart", ""),
            "recommended_fix": result.get("recommendedFix", ""),
            "impactAnalysis": result.get("impactAnalysis"),
            
            "confidence_score": final_confidence,
            "messages": [AIMessage(content=f"✅ Complete analysis: {result.get('root_cause_location')}")]
        }
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
        import traceback
        traceback.print_exc()
        
        return {
            **state,
            "error_occurred": True,
            "error_message": str(e),
            "mapped_locations": mapped_locations,
            "call_chain": [step['function'] for step in call_chain],
            "messages": [AIMessage(content=f"❌ Error: {str(e)}")]
        }