"""Endpoints de la cartera: importación de facturas, facturas y casos.

Todos requieren sesión (se registran en el router protegido). Los permisos se
verifican en los casos de uso:
- VIEW_PORTFOLIO    -> ver facturas, casos e historial de cargas
- OPERATE_PORTFOLIO -> importar archivos y generar casos
"""

import csv
import io
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.api.error_handlers import error_body
from mavic.api.pagination import AmountPageOut, Limit, Offset
from mavic.modules.portfolio.api.schemas import (
    CaseDetailOut,
    CaseSummaryOut,
    GenerationOut,
    ImportOut,
    ImportReportOut,
    InvoiceOut,
)
from mavic.modules.portfolio.application import cases, imports
from mavic.modules.portfolio.application.cases import CaseSort, InvoiceSort
from mavic.modules.portfolio.domain.cases import CaseStatus, InvoiceStage
from mavic.modules.portfolio.domain.import_rows import REQUIRED_COLUMNS

router = APIRouter()

UploadedFile = Annotated[UploadFile, File(description="Archivo .csv o .xlsx")]
MinAmount = Annotated[Decimal | None, Query(ge=0, description="Monto mínimo (inclusive)")]
MaxAmount = Annotated[Decimal | None, Query(ge=0, description="Monto máximo (inclusive)")]


def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    # Se lee como máximo 1 byte más que el límite: alcanza para saber si se pasó
    # sin cargar en memoria un archivo de 2 GB.
    content = file.file.read(imports.MAX_FILE_BYTES + 1)
    return file.filename or "archivo", content


# ---------------------------------------------------------------- importación


@router.get("/imports/template", tags=["imports"], response_class=Response)
def download_template() -> Response:
    """Plantilla CSV con las columnas obligatorias y dos filas de ejemplo."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(REQUIRED_COLUMNS)
    writer.writerow(
        ["F-0001", "Abono internet septiembre", "Ana Pérez", "30111222", "+5491122334455",
         "ana@example.com", "18500.00", "ARS", "2026-09-10"]
    )  # fmt: skip
    writer.writerow(
        ["F-0002", "Abono internet octubre", "Ana Pérez", "30111222", "+5491122334455",
         "ana@example.com", "18500.00", "ARS", "10/10/2026"]
    )  # fmt: skip
    return Response(
        # utf-8-sig agrega la marca BOM: así Excel abre bien los acentos.
        content=buffer.getvalue().encode("utf-8-sig"),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="plantilla-facturas.csv"'},
    )


@router.post("/imports/preview", response_model=ImportReportOut, tags=["imports"])
def preview_import(file: UploadedFile, session: SessionDep, actor: ActorDep) -> ImportReportOut:
    """Valida el archivo y muestra qué se cargaría. No guarda nada."""
    filename, content = _read_upload(file)
    report = imports.preview_import(session, actor=actor, filename=filename, content=content)
    return ImportReportOut.from_report(report)


@router.post(
    "/imports",
    response_model=ImportReportOut,
    status_code=status.HTTP_201_CREATED,
    tags=["imports"],
    responses={422: {"description": "El archivo tiene errores: no se cargó nada"}},
)
def import_invoices(
    file: UploadedFile, session: SessionDep, actor: ActorDep, clock: ClockDep
) -> ImportReportOut | JSONResponse:
    """Carga el archivo. Todo o nada: con un solo error no se guarda ninguna fila."""
    filename, content = _read_upload(file)
    report = imports.import_invoices(
        session, actor=actor, filename=filename, content=content, clock=clock
    )
    out = ImportReportOut.from_report(report)
    if not report.is_valid:
        body = error_body(
            "El archivo tiene errores. No se cargó ninguna fila.",
            "IMPORT_HAS_ERRORS",
            report=out.model_dump(mode="json"),
        )
        return JSONResponse(status_code=422, content=body)
    return out


@router.get("/imports", response_model=list[ImportOut], tags=["imports"])
def list_imports(session: SessionDep, actor: ActorDep) -> list[ImportOut]:
    """Últimas cargas de la empresa (historial / auditoría)."""
    return [ImportOut.from_view(v) for v in imports.recent_imports(session, actor=actor)]


# ---------------------------------------------------------------- facturas


@router.get("/invoices", response_model=AmountPageOut[InvoiceOut], tags=["invoices"])
def list_invoices(
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
    limit: Limit = 50,
    offset: Offset = 0,
    in_case: Annotated[
        bool | None, Query(description="true: solo en un caso · false: solo sin caso")
    ] = None,
    overdue_only: Annotated[bool, Query(description="Solo facturas vencidas")] = False,
    stage: Annotated[
        InvoiceStage | None,
        Query(description="upcoming: por vencer · due_today: vencen hoy · overdue: vencidas"),
    ] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Busca en número, concepto, deudor y DNI")
    ] = None,
    min_amount: MinAmount = None,
    max_amount: MaxAmount = None,
    sort: InvoiceSort = "due_date",
) -> AmountPageOut[InvoiceOut]:
    page = cases.list_invoices(
        session,
        actor=actor,
        clock=clock,
        filters=cases.InvoiceFilters(
            in_case=in_case,
            stage=stage,
            search=q,
            min_amount=min_amount,
            max_amount=max_amount,
        ),
        overdue_only=overdue_only,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return AmountPageOut(
        items=[InvoiceOut.from_view(i) for i in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        amount_max=page.amount_max,
    )


# ---------------------------------------------------------------- casos


@router.post("/cases/generate", response_model=GenerationOut, tags=["cases"])
def generate_cases(session: SessionDep, actor: ActorDep, clock: ClockDep) -> GenerationOut:
    """Agrupa las facturas vencidas sin caso en casos (uno por deudor)."""
    return GenerationOut.from_result(cases.generate_cases(session, actor=actor, clock=clock))


@router.get("/cases", response_model=AmountPageOut[CaseSummaryOut], tags=["cases"])
def list_cases(
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
    limit: Limit = 50,
    offset: Offset = 0,
    case_status: Annotated[CaseStatus | None, Query(alias="status")] = None,
    q: Annotated[
        str | None, Query(max_length=100, description="Busca por deudor, DNI o número de caso")
    ] = None,
    min_amount: MinAmount = None,
    max_amount: MaxAmount = None,
    sort: CaseSort = "oldest_debt",
) -> AmountPageOut[CaseSummaryOut]:
    page = cases.list_cases(
        session,
        actor=actor,
        clock=clock,
        filters=cases.CaseFilters(
            status=case_status, search=q, min_amount=min_amount, max_amount=max_amount
        ),
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return AmountPageOut(
        items=[CaseSummaryOut.from_view(c) for c in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        amount_max=page.amount_max,
    )


@router.post("/cases/{case_id}/escalate", response_model=CaseDetailOut, tags=["cases"])
def escalate_case(
    case_id: UUID, session: SessionDep, actor: ActorDep, clock: ClockDep
) -> CaseDetailOut:
    """Derivar a humano: el caso pasa a "derivado" y el agente deja de llamarlo."""
    return CaseDetailOut.from_detail(
        cases.escalate_case(session, actor=actor, clock=clock, case_id=case_id)
    )


@router.get("/cases/{case_id}", response_model=CaseDetailOut, tags=["cases"])
def get_case(case_id: UUID, session: SessionDep, actor: ActorDep, clock: ClockDep) -> CaseDetailOut:
    return CaseDetailOut.from_detail(
        cases.get_case(session, actor=actor, clock=clock, case_id=case_id)
    )
