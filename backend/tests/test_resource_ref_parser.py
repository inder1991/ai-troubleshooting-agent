import pytest
from src.utils.resource_ref_parser import extract_resource_refs, strip_resource_ref_syntax


class TestExtractResourceRefs:
    def test_fully_qualified(self):
        text = "Pod @[pod:payment-api/auth-5b6q] is crashing"
        refs = extract_resource_refs(text)
        assert len(refs) == 1
        assert refs[0].type == "pod"
        assert refs[0].name == "auth-5b6q"
        assert refs[0].namespace == "payment-api"

    def test_short_format_with_default_ns(self):
        text = "Check @[service:auth-svc]"
        refs = extract_resource_refs(text, default_namespace="default")
        assert len(refs) == 1
        assert refs[0].namespace == "default"

    def test_short_format_no_default_ns(self):
        text = "Check @[service:auth-svc]"
        refs = extract_resource_refs(text)
        assert refs[0].namespace is None

    def test_multiple_refs(self):
        text = "Pod @[pod:ns/auth-5b6q] crashed due to @[pvc:ns/auth-data-vol] exhaustion"
        refs = extract_resource_refs(text)
        assert len(refs) == 2
        assert {r.type for r in refs} == {"pod", "pvc"}

    def test_deduplication(self):
        text = "@[pod:ns/auth] and again @[pod:ns/auth]"
        refs = extract_resource_refs(text)
        assert len(refs) == 1

    def test_invalid_kind_ignored(self):
        text = "@[invalid_kind:ns/name]"
        refs = extract_resource_refs(text)
        assert len(refs) == 0

    def test_openshift_types(self):
        text = "@[deploymentconfig:myns/auth-dc] and @[route:myns/auth-route]"
        refs = extract_resource_refs(text)
        assert len(refs) == 2
        assert {r.type for r in refs} == {"deploymentconfig", "route"}

    def test_no_refs(self):
        refs = extract_resource_refs("No resource references here")
        assert refs == []

    def test_mixed_case_kind(self):
        text = "@[Pod:ns/auth]"
        refs = extract_resource_refs(text)
        assert len(refs) == 1
        assert refs[0].type == "pod"


class TestStripResourceRefSyntax:
    def test_strips_to_name(self):
        text = "Pod @[pod:payment-api/auth-5b6q] is crashing"
        result = strip_resource_ref_syntax(text)
        assert result == "Pod auth-5b6q is crashing"

    def test_strips_multiple(self):
        text = "@[pod:ns/auth] uses @[pvc:ns/vol]"
        result = strip_resource_ref_syntax(text)
        assert result == "auth uses vol"

    def test_no_refs_unchanged(self):
        text = "No references"
        assert strip_resource_ref_syntax(text) == text
