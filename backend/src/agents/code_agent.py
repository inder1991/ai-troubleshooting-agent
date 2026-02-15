import json
import os
import re
from pathlib import Path
from typing import Any

from src.agents.react_base import ReActAgent
from src.models.schemas import ImpactedFile, LineRange, FixArea, CodeAnalysisResult, TokenUsage


class CodeNavigatorAgent(ReActAgent):
    """ReAct agent for multi-file code impact analysis."""

    def __init__(self, max_iterations: int = 10):
        super().__init__(agent_name="code_agent", max_iterations=max_iterations)
        self.repo_path: str = ""

    async def _define_tools(self) -> list[dict]:
        return [
            {
                "name": "search_file",
                "description": "Search for files in the repository matching a filename pattern.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Filename or glob pattern to search for"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "read_file",
                "description": "Read the contents of a file (or a range of lines).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path relative to repo root"},
                        "start_line": {"type": "integer", "description": "Start line (1-indexed)", "default": 1},
                        "end_line": {"type": "integer", "description": "End line (0 = entire file)", "default": 0},
                    },
                    "required": ["path"],
                },
            },
            {
                "name": "search_code",
                "description": "Search for a pattern (regex) across all files in the repository.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern to search for in code"},
                        "file_glob": {"type": "string", "description": "Limit search to files matching this glob", "default": "*"},
                    },
                    "required": ["pattern"],
                },
            },
            {
                "name": "find_callers",
                "description": "Find all files/locations that call a specific function or method.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "function_name": {"type": "string"},
                    },
                    "required": ["function_name"],
                },
            },
            {
                "name": "find_callees",
                "description": "Find all functions/methods called within a specific file and function.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "function_name": {"type": "string"},
                    },
                    "required": ["path", "function_name"],
                },
            },
        ]

    async def _build_system_prompt(self) -> str:
        return """You are a Code Navigator Agent for SRE troubleshooting. You use the ReAct pattern.

Your goals:
1. Find the error location in the codebase (file + function + line)
2. Trace upstream: who calls the broken function (find_callers)
3. Trace downstream: what does the broken function call (find_callees)
4. Identify shared resources: config files, connection pools, utilities
5. Find related test files
6. Build a complete impact map

For each impacted file, classify:
- direct_error: the file where the error occurs
- caller: calls the broken function
- callee: called by the broken function
- shared_resource: utility/helper used by the error path
- config: configuration file that affects behavior
- test: test file for impacted code

After analysis, provide your final answer as JSON:
{
    "root_cause_location": {"file_path": "...", "impact_type": "direct_error", "relevant_lines": [{"start": 45, "end": 60}], "code_snippet": "...", "relationship": "error origin", "fix_relevance": "must_fix"},
    "impacted_files": [...],
    "call_chain": ["caller.py:handler()", "service.py:process()", "db.py:query()"],
    "dependency_graph": {"service.py": ["db.py", "cache.py"]},
    "shared_resource_conflicts": [],
    "suggested_fix_areas": [{"file_path": "...", "description": "...", "suggested_change": "..."}],
    "mermaid_diagram": "graph TD; A-->B;",
    "overall_confidence": 85
}"""

    async def _build_initial_prompt(self, context: dict) -> str:
        self.repo_path = context.get("repo_path", "")
        parts = [f"Analyze code impact for error in: {context.get('service_name', 'unknown')}"]
        if context.get("repo_path"):
            parts.append(f"Repository path: {context['repo_path']}")
        if context.get("error_location"):
            parts.append(f"Error location from logs: {context['error_location']}")
        if context.get("stack_trace"):
            parts.append(f"Stack trace:\n{context['stack_trace']}")
        if context.get("exception_type"):
            parts.append(f"Exception type: {context['exception_type']}")
        return "\n".join(parts)

    async def _handle_tool_call(self, tool_name: str, tool_input: dict) -> str:
        if tool_name == "search_file":
            return self._search_file(tool_input)
        elif tool_name == "read_file":
            return self._read_file(tool_input)
        elif tool_name == "search_code":
            return self._search_code(tool_input)
        elif tool_name == "find_callers":
            return self._find_callers_tool(tool_input)
        elif tool_name == "find_callees":
            return self._find_callees_tool(tool_input)
        return f"Unknown tool: {tool_name}"

    def _parse_final_response(self, text: str) -> dict:
        try:
            json_match = re.search(r'\{[\s\S]*\}', text)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = json.loads(text)
        except (json.JSONDecodeError, AttributeError):
            return {"error": "Failed to parse response", "raw_response": text}

        return {
            **data,
            "breadcrumbs": [b.model_dump(mode="json") for b in self.breadcrumbs],
            "negative_findings": [n.model_dump(mode="json") for n in self.negative_findings],
            "tokens_used": self.get_token_usage().model_dump(),
        }

    # --- Tool implementations ---

    def _search_file(self, params: dict) -> str:
        pattern = params["pattern"]
        if not self.repo_path:
            return json.dumps({"error": "No repo_path set"})

        matches = []
        repo = Path(self.repo_path)
        for path in repo.rglob(pattern):
            if ".git" in path.parts or "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            matches.append(str(path.relative_to(repo)))

        if not matches:
            self.add_negative_finding(
                what_was_checked=f"Files matching '{pattern}' in repo",
                result="No files found",
                implication=f"No files matching pattern '{pattern}' in the repository",
                source_reference=f"repo: {self.repo_path}",
            )

        self.add_breadcrumb(
            action="search_file",
            source_type="code",
            source_reference=f"pattern: {pattern}",
            raw_evidence=f"Found {len(matches)} files",
        )

        return json.dumps({"matches": matches[:50], "total": len(matches)})

    def _read_file(self, params: dict) -> str:
        rel_path = params["path"]
        start = params.get("start_line", 1)
        end = params.get("end_line", 0)

        full_path = Path(self.repo_path) / rel_path
        if not full_path.exists():
            return json.dumps({"error": f"File not found: {rel_path}"})

        try:
            lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
            if end > 0:
                selected = lines[max(0, start - 1):end]
            else:
                selected = lines

            # Limit to prevent huge responses
            if len(selected) > 200:
                selected = selected[:200]
                truncated = True
            else:
                truncated = False

            self.add_breadcrumb(
                action="read_file",
                source_type="code",
                source_reference=f"{rel_path}:{start}-{end or 'EOF'}",
                raw_evidence=f"Read {len(selected)} lines",
            )

            return json.dumps({
                "path": rel_path,
                "lines": selected,
                "start_line": start,
                "total_lines": len(lines),
                "truncated": truncated,
            })

        except Exception as e:
            return json.dumps({"error": str(e)})

    def _search_code(self, params: dict) -> str:
        pattern = params["pattern"]
        file_glob = params.get("file_glob", "*")

        if not self.repo_path:
            return json.dumps({"error": "No repo_path set"})

        matches = []
        repo = Path(self.repo_path)
        try:
            regex = re.compile(pattern)
        except re.error:
            return json.dumps({"error": f"Invalid regex: {pattern}"})

        for path in repo.rglob(file_glob):
            if path.is_dir() or ".git" in path.parts or "node_modules" in path.parts:
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if regex.search(line):
                        matches.append({
                            "file": str(path.relative_to(repo)),
                            "line_number": i,
                            "line": line.strip()[:200],
                        })
            except Exception:
                continue

        self.add_breadcrumb(
            action="search_code",
            source_type="code",
            source_reference=f"pattern: {pattern}",
            raw_evidence=f"Found {len(matches)} matches",
        )

        return json.dumps({"matches": matches[:100], "total": len(matches)})

    def _find_callers_tool(self, params: dict) -> str:
        func_name = params["function_name"]
        callers = self._find_callers(self.repo_path, func_name)

        self.add_breadcrumb(
            action="find_callers",
            source_type="code",
            source_reference=f"function: {func_name}",
            raw_evidence=f"Found {len(callers)} callers",
        )

        return json.dumps({"function": func_name, "callers": callers})

    def _find_callees_tool(self, params: dict) -> str:
        rel_path = params["path"]
        func_name = params["function_name"]

        full_path = Path(self.repo_path) / rel_path
        if not full_path.exists():
            return json.dumps({"error": f"File not found: {rel_path}"})

        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
            callees = self._extract_callees(content, func_name)

            self.add_breadcrumb(
                action="find_callees",
                source_type="code",
                source_reference=f"{rel_path}:{func_name}",
                raw_evidence=f"Found {len(callees)} callees",
            )

            return json.dumps({"function": func_name, "file": rel_path, "callees": callees})

        except Exception as e:
            return json.dumps({"error": str(e)})

    # --- Pure logic ---

    @staticmethod
    def _find_callers(repo_path: str, func_name: str) -> list[dict]:
        """Find all files that call a function (simple text search)."""
        if not repo_path:
            return []

        callers = []
        repo = Path(repo_path)
        pattern = re.compile(rf'\b{re.escape(func_name)}\s*\(')

        for path in repo.rglob("*"):
            if path.is_dir() or ".git" in path.parts or "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix not in (".py", ".java", ".js", ".ts", ".go", ".rs", ".rb", ".kt"):
                continue
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    # Skip function definitions
                    if re.match(rf'\s*def\s+{re.escape(func_name)}', line):
                        continue
                    if re.match(rf'\s*(public|private|protected)?\s*\w+\s+{re.escape(func_name)}\s*\(', line):
                        continue
                    if pattern.search(line):
                        callers.append({
                            "file_path": str(path.relative_to(repo)),
                            "line_number": i,
                            "line": line.strip()[:200],
                        })
            except Exception:
                continue

        return callers

    @staticmethod
    def _extract_callees(content: str, func_name: str) -> list[str]:
        """Extract function calls within a specific function body."""
        lines = content.splitlines()
        in_function = False
        indent_level = 0
        callees = set()

        for line in lines:
            # Detect function start (Python-style)
            if re.match(rf'\s*def\s+{re.escape(func_name)}\s*\(', line):
                in_function = True
                indent_level = len(line) - len(line.lstrip())
                continue

            if in_function:
                # Check if we've exited the function
                if line.strip() and not line.startswith(' ' * (indent_level + 1)) and not line.strip().startswith('#'):
                    if re.match(r'\s*def\s+', line) or re.match(r'\s*class\s+', line):
                        break

                # Find function calls in the line
                calls = re.findall(r'(\w+)\s*\(', line)
                for call in calls:
                    if call not in ('if', 'for', 'while', 'with', 'except', 'print', 'return', 'def', 'class', func_name):
                        callees.add(call)

        return sorted(callees)

    @staticmethod
    def _classify_impact(description: str) -> str:
        """Classify the impact type based on a description."""
        desc_lower = description.lower()
        if "direct" in desc_lower or "error location" in desc_lower or "error origin" in desc_lower:
            return "direct_error"
        if "call" in desc_lower and ("broken" in desc_lower or "upstream" in desc_lower):
            return "caller"
        if "called by" in desc_lower or "downstream" in desc_lower or "callee" in desc_lower:
            return "callee"
        if "config" in desc_lower or "configuration" in desc_lower or "settings" in desc_lower:
            return "config"
        if "test" in desc_lower:
            return "test"
        if "shared" in desc_lower or "utility" in desc_lower or "helper" in desc_lower or "common" in desc_lower:
            return "shared_resource"
        return "shared_resource"
