"""Historical fixture opt-in must never renew production report authority."""

import time
from datetime import UTC, datetime

import pytest
from conftest import apply_approved_report_authorization_clock
from pydantic import ValidationError
from test_foundry_report_runtime import approval

from apbra_api import api, application, auth_boundary, authorization, oidc_adapter
from apbra_api import foundry_report_runtime as report


def test_synthetic_clock_is_explicit_coherent_and_restored():
    wall_time, utc_time = time.time, time.gmtime
    modules = (api, application, auth_boundary, authorization, oidc_adapter)
    original_datetime = {module: module.datetime for module in modules}
    with pytest.MonkeyPatch.context() as patch:
        apply_approved_report_authorization_clock(patch)
        assert time.strftime("%Y-%m", time.gmtime()) == report.PERIOD
        for module in modules:
            assert abs(module.datetime.now(UTC).timestamp() - time.time()) < 1
        # A historical synthetic grant is valid only inside the opted-in context.
        report.ReportApproval.model_validate(approval().model_dump())
    assert time.time is wall_time and time.gmtime is utc_time
    assert all(module.datetime is original_datetime[module] for module in modules)


def test_expired_historical_grant_is_denied_after_restoring_real_clock():
    real_time = time.time
    # Do not skip or hide a global clock leak: this execution is after the
    # existing fixed approval window, and the normal clock must remain visible.
    assert real_time() >= report.BUDGET_END
    with pytest.MonkeyPatch.context() as patch:
        apply_approved_report_authorization_clock(patch)
        raw = approval().model_dump()
    assert time.time is real_time
    assert datetime.now(UTC).timestamp() >= report.BUDGET_END
    with pytest.raises(ValidationError, match="FOUNDRY_REPORT_AUTHORIZATION_UNAVAILABLE"):
        report.ReportApproval.model_validate(raw)
