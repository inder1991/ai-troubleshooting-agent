"""Tests for bi-directional diagnosis."""
import pytest
from src.api.network_models import DiagnoseRequest


def test_diagnose_request_has_bidirectional_flag():
    req = DiagnoseRequest(
        src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443,
        bidirectional=True,
    )
    assert req.bidirectional is True


def test_diagnose_request_defaults_unidirectional():
    req = DiagnoseRequest(src_ip="10.0.0.1", dst_ip="10.0.1.1", port=443)
    assert req.bidirectional is False
