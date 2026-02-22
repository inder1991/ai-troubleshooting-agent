"""
Deterministic post-mortem renderer — transforms DiagnosticState into
structured Markdown and Confluence Storage Format (XHTML subset).

No LLM calls; all intelligence was already captured by the diagnostic agents.
"""

import re
from datetime import datetime


class PostMortemRenderer:
    """Extracts and organizes DiagnosticState data into a post-mortem document."""

    def render_markdown(self, state) -> dict:
        """Returns {"title": str, "body_markdown": str}."""
        service = state.service_name or "unknown-service"
        incident_id = state.incident_id or state.session_id[:8]
        title = f"Post-Mortem: {incident_id} — {service}"

        sections: list[str] = []

        # 1. Incident Overview
        sections.append("## Incident Overview\n")
        sections.append(f"- **Incident ID:** {incident_id}")
        sections.append(f"- **Service:** {service}")
        if state.severity_result:
            sections.append(f"- **Severity:** {state.severity_result.recommended_severity}")
            sections.append(f"- **Reasoning:** {state.severity_result.reasoning}")
        if state.blast_radius_result:
            br = state.blast_radius_result
            sections.append(f"- **Blast Radius:** {br.scope.replace('_', ' ')}")
            if br.upstream_affected:
                sections.append(f"- **Upstream Affected:** {', '.join(br.upstream_affected)}")
            if br.downstream_affected:
                sections.append(f"- **Downstream Affected:** {', '.join(br.downstream_affected)}")
            if br.estimated_user_impact:
                sections.append(f"- **User Impact:** {br.estimated_user_impact}")
        sections.append("")

        # 2. Root Cause Analysis
        sections.append("## Root Cause Analysis\n")
        if state.log_analysis and state.log_analysis.primary_pattern:
            pp = state.log_analysis.primary_pattern
            sections.append(f"- **Exception:** `{pp.exception_type}`")
            sections.append(f"- **Error Message:** {pp.error_message}")
            sections.append(f"- **Frequency:** {pp.frequency} occurrences")
            sections.append(f"- **Affected Components:** {', '.join(pp.affected_components)}")
            if pp.causal_role:
                sections.append(f"- **Causal Role:** {pp.causal_role}")
        if state.code_analysis and state.code_analysis.root_cause_location:
            rcl = state.code_analysis.root_cause_location
            sections.append(f"- **Root Cause File:** `{rcl.file_path}`")
            sections.append(f"- **Relationship:** {rcl.relationship}")
        change_correlations = []
        if hasattr(state, 'change_correlations') and state.change_correlations:
            # DiagnosticStateV5 has change_correlations as a direct attribute
            change_correlations = state.change_correlations
        elif state.change_analysis and isinstance(state.change_analysis, dict):
            # DiagnosticState stores them inside change_analysis dict
            change_correlations = state.change_analysis.get("change_correlations", [])
        if change_correlations:
            sections.append("\n### Change Correlations\n")
            for cc in change_correlations[:3]:
                if isinstance(cc, dict):
                    desc = cc.get("description", str(cc))
                    risk = cc.get("risk_score", 0)
                else:
                    desc = cc.description if hasattr(cc, 'description') else str(cc)
                    risk = cc.risk_score if hasattr(cc, 'risk_score') else 0
                sections.append(f"- {desc} (risk: {risk:.0%})")
        if state.reasoning_chain:
            sections.append("\n### Reasoning Chain\n")
            for step in state.reasoning_chain[:5]:
                if isinstance(step, dict):
                    sections.append(f"- {step.get('step', step.get('reasoning', str(step)))}")
                else:
                    sections.append(f"- {step}")
        sections.append("")

        # 3. Timeline
        sections.append("## Timeline\n")
        if state.patient_zero:
            pz = state.patient_zero
            if isinstance(pz, dict):
                sections.append(f"- **Patient Zero:** {pz.get('service', 'unknown')} — {pz.get('operation', '')}")
                if pz.get('timestamp'):
                    sections.append(f"- **First Error:** {pz['timestamp']}")
        if state.service_flow:
            sections.append("\n### Service Flow\n")
            for step in state.service_flow[:10]:
                if isinstance(step, dict):
                    svc = step.get('service', '?')
                    op = step.get('operation', '?')
                    status = step.get('status', '?')
                    ts = step.get('timestamp', '')
                    sections.append(f"- `{ts}` **{svc}** → {op} [{status}]")
        sections.append("")

        # 4. Evidence Summary
        sections.append("## Evidence Summary\n")
        findings_count = len(state.all_findings) if state.all_findings else 0
        sections.append(f"- **Total Findings:** {findings_count}")
        if state.metrics_analysis:
            sections.append(f"- **Metric Anomalies:** {len(state.metrics_analysis.anomalies)}")
        if state.k8s_analysis:
            sections.append(f"- **K8s Events:** {len(state.k8s_analysis.events)}")
        if state.critic_verdicts:
            validated = sum(1 for v in state.critic_verdicts if v.verdict == "validated")
            challenged = sum(1 for v in state.critic_verdicts if v.verdict == "challenged")
            sections.append(f"- **Critic Verdicts:** {validated} validated, {challenged} challenged")
        if state.all_findings:
            sections.append("\n### Top Findings\n")
            for f in state.all_findings[:5]:
                sections.append(f"- [{f.severity.upper()}] {f.summary} (confidence: {f.confidence_score}%)")
        sections.append("")

        # 5. Resolution
        sections.append("## Resolution\n")
        if state.fix_result:
            fr = state.fix_result
            if fr.fix_explanation:
                sections.append(f"- **Fix:** {fr.fix_explanation}")
            if fr.pr_url:
                sections.append(f"- **PR:** [{fr.pr_url}]({fr.pr_url})")
            if fr.diff:
                sections.append(f"\n```diff\n{fr.diff[:2000]}\n```\n")
        else:
            sections.append("- No automated fix was generated.")
        sections.append("")

        # 6. Action Items
        sections.append("## Action Items\n")
        if state.closure_state:
            cs = state.closure_state
            if cs.jira_result.status == "success":
                sections.append(f"- [x] Jira issue: [{cs.jira_result.issue_key}]({cs.jira_result.issue_url})")
            if cs.remedy_result.status == "success":
                sections.append(f"- [x] Remedy incident: {cs.remedy_result.incident_number}")
        sections.append(f"- [ ] Verify fix in production")
        sections.append(f"- [ ] Update runbook if applicable")
        sections.append(f"- [ ] Schedule follow-up review")
        sections.append("")

        sections.append(f"\n---\n*Generated at {datetime.utcnow().isoformat()}Z by AI Troubleshooting System*\n")

        body = "\n".join(sections)
        return {"title": title, "body_markdown": body}

    def markdown_to_storage_format(self, markdown: str) -> str:
        """Convert markdown to Confluence Storage Format (XHTML subset).

        Hand-rolled for the limited subset we generate — no external dependency.
        """
        lines = markdown.split("\n")
        html_parts: list[str] = []
        in_code_block = False
        in_list = False
        code_lang = ""

        for line in lines:
            # Code blocks
            if line.startswith("```"):
                if in_code_block:
                    html_parts.append("</ac:plain-text-body></ac:structured-macro>")
                    in_code_block = False
                else:
                    code_lang = line[3:].strip() or "text"
                    html_parts.append(
                        f'<ac:structured-macro ac:name="code">'
                        f'<ac:parameter ac:name="language">{code_lang}</ac:parameter>'
                        f'<ac:plain-text-body><![CDATA['
                    )
                    in_code_block = True
                continue

            if in_code_block:
                html_parts.append(line)
                continue

            # Close list if this line is not a list item
            if in_list and not line.startswith("- ") and not line.startswith("* "):
                html_parts.append("</ul>")
                in_list = False

            # Headings
            if line.startswith("## "):
                html_parts.append(f"<h2>{self._inline(line[3:].strip())}</h2>")
                continue
            if line.startswith("### "):
                html_parts.append(f"<h3>{self._inline(line[4:].strip())}</h3>")
                continue
            if line.startswith("# "):
                html_parts.append(f"<h1>{self._inline(line[2:].strip())}</h1>")
                continue

            # Horizontal rule
            if line.strip() == "---":
                html_parts.append("<hr />")
                continue

            # List items
            if line.startswith("- ") or line.startswith("* "):
                if not in_list:
                    html_parts.append("<ul>")
                    in_list = True
                content = line[2:].strip()
                # Checkbox handling
                if content.startswith("[x] "):
                    content = "&#9745; " + content[4:]
                elif content.startswith("[ ] "):
                    content = "&#9744; " + content[4:]
                html_parts.append(f"<li>{self._inline(content)}</li>")
                continue

            # Empty lines
            if not line.strip():
                html_parts.append("")
                continue

            # Paragraph
            html_parts.append(f"<p>{self._inline(line)}</p>")

        if in_list:
            html_parts.append("</ul>")
        if in_code_block:
            html_parts.append("]]></ac:plain-text-body></ac:structured-macro>")

        return "\n".join(html_parts)

    def _inline(self, text: str) -> str:
        """Apply inline formatting: bold, code, links."""
        # Bold: **text** → <strong>text</strong>
        text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
        # Inline code: `text` → <code>text</code>
        text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
        # Links: [text](url) → <a href="url">text</a>
        text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
        # Italic: *text* → <em>text</em>
        text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
        return text
