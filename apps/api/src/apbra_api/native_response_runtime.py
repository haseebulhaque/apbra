"""Bind a fresh finite analysis grant exclusively to one native receive route.

This factory does not create approval, acquire credentials or reuse an old grant.
The owner launcher must provide a new verified approval and reservation object.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import FastAPI, Request, Response

from .foundry_report_runtime import ReportApproval, Reservations, ReservedCredentials, require


def native_application_factory(
    approval: ReportApproval, reservations: Reservations, create: Callable[..., FastAPI]
) -> Callable[..., FastAPI]:
    require(ReportApproval.model_validate(approval.model_dump()) == approval)
    require(reservations.approval == approval)
    require(len(approval.slots) == 1)
    require(approval.slots[0].stage in {"REQUIREMENT_ANALYSIS", "REPORT_DESIGN"})
    require(approval.slots[0].attempts == 1)

    def factory(**kwargs: Any) -> FastAPI:
        credentials = kwargs.get("foundry_credentials")
        require(credentials is not None)
        assert credentials is not None
        kwargs["foundry_credentials"] = ReservedCredentials(credentials, reservations)
        kwargs["native_receive_enabled"] = True
        app = create(**kwargs)
        path = f"/api/cases/{approval.case_id}/native-response-checks"

        @app.middleware("http")
        async def native_context(
            request: Request, call_next: Callable[[Request], Awaitable[Response]]
        ) -> Response:
            if request.method == "POST" and request.url.path == path:
                with reservations.operation(approval.case_id, approval.slots[0].stage):
                    return await call_next(request)
            # Interpretation/design/build routes receive no operation authority.
            return await call_next(request)

        return app

    return factory
