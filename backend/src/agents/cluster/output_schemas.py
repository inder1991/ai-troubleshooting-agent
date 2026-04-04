"""Anthropic tool definitions for structured LLM output.

These are passed as the `tools` argument to Anthropic API calls.
The LLM MUST call the tool to return findings — it cannot return free text.
Parse from tool_use.input (always valid JSON) instead of response.text.
"""

SUBMIT_DOMAIN_FINDINGS_TOOL: dict = {
    "name": "submit_domain_findings",
    "description": (
        "Submit your diagnostic findings for this domain. "
        "You MUST call this tool when your analysis is complete. "
        "Do NOT return findings as free text — only via this tool."
    ),
    "input_schema": {
        "type": "object",
        "required": ["anomalies", "ruled_out", "confidence"],
        "properties": {
            "anomalies": {
                "type": "array",
                "description": "List of anomalies found. Empty array if none.",
                "items": {
                    "type": "object",
                    "required": ["domain", "anomaly_id", "description", "evidence_ref", "severity"],
                    "properties": {
                        "domain": {"type": "string"},
                        "anomaly_id": {"type": "string", "description": "Unique ID e.g. ctrl-001"},
                        "description": {"type": "string"},
                        "evidence_ref": {"type": "string", "description": "e.g. pod/my-pod or operator/dns"},
                        "severity": {"enum": ["high", "medium", "low"]},
                        "evidence_sources": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "api_call": {"type": "string"},
                                    "resource": {"type": "string"},
                                    "data_snippet": {"type": "string"},
                                    "tool_call_id": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
            "ruled_out": {
                "type": "array",
                "description": "Items checked and found healthy.",
                "items": {"type": "string"},
            },
            "confidence": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "0-100. Reflects data quality and coverage.",
            },
        },
    },
}

SUBMIT_CAUSAL_ANALYSIS_TOOL: dict = {
    "name": "submit_causal_analysis",
    "description": (
        "Submit causal chains and uncorrelated findings. "
        "You MUST call this tool — do not return analysis as free text."
    ),
    "input_schema": {
        "type": "object",
        "required": ["causal_chains", "uncorrelated_findings"],
        "properties": {
            "causal_chains": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["chain_id", "confidence", "root_cause", "cascading_effects"],
                    "properties": {
                        "chain_id": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "root_cause": {
                            "type": "object",
                            "required": ["domain", "anomaly_id", "description", "evidence_ref"],
                            "properties": {
                                "domain": {"type": "string"},
                                "anomaly_id": {"type": "string"},
                                "description": {"type": "string"},
                                "evidence_ref": {"type": "string"},
                            },
                        },
                        "cascading_effects": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "order": {"type": "integer"},
                                    "domain": {"type": "string"},
                                    "anomaly_id": {"type": "string"},
                                    "description": {"type": "string"},
                                    "link_type": {"type": "string"},
                                    "evidence_ref": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
            "uncorrelated_findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "domain": {"type": "string"},
                        "anomaly_id": {"type": "string"},
                        "description": {"type": "string"},
                        "evidence_ref": {"type": "string"},
                        "severity": {"enum": ["high", "medium", "low"]},
                    },
                },
            },
        },
    },
}

SUBMIT_VERDICT_TOOL: dict = {
    "name": "submit_verdict",
    "description": (
        "Submit the cluster health verdict and remediation plan. "
        "You MUST call this tool — do not return the verdict as free text."
    ),
    "input_schema": {
        "type": "object",
        "required": ["platform_health", "blast_radius", "remediation", "re_dispatch_needed", "re_dispatch_domains"],
        "properties": {
            "platform_health": {
                "enum": ["HEALTHY", "DEGRADED", "CRITICAL", "UNKNOWN"],
            },
            "blast_radius": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "affected_namespaces": {"type": "array", "items": {"type": "string"}},
                    "affected_pods": {"type": "array", "items": {"type": "string"}},
                    "affected_nodes": {"type": "array", "items": {"type": "string"}},
                },
            },
            "remediation": {
                "type": "object",
                "properties": {
                    "immediate": {"type": "array"},
                    "long_term": {"type": "array"},
                },
            },
            "re_dispatch_needed": {"type": "boolean"},
            "re_dispatch_domains": {
                "type": "array",
                "items": {"enum": ["ctrl_plane", "node", "network", "storage", "rbac"]},
                "description": "Only valid domain names. Leave empty if re_dispatch_needed=false.",
            },
        },
    },
}
