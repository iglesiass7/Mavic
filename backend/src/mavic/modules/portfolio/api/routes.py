"""Endpoints de la cartera: importación de facturas, facturas y casos.

Todos requieren sesión (se registran en el router protegido). Los permisos se
verifican en los casos de uso:
- VIEW_PORTFOLIO    -> ver facturas, casos e historial de cargas
- OPERATE_PORTFOLIO -> importar archivos y generar casos
"""

import csv
import io
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, File, Query, UploadFile, status
from fastapi.responses import JSONResponse, Response

from mavic.api.deps import ActorDep, ClockDep, SessionDep
from mavic.api.error_handlers import error_body
from mavic.api.pagination import Limit, Offset, PageOut
from mavic.modules.portfolio.api.schemas import (
    CaseDetailOut,
    CaseSummaryOut,
    GenerationOut,
    ImportOut,
    ImportReportOut,
    InvoiceOut,
)
from mavic.modules.portfolio.application import cases, imports
from mavic.modules.portfolio.domain.cases import CaseStatus
from mavic.modules.portfolio.domain.import_rows import REQUIRED_COLUMNS

router = APIRouter()

UploadedFile = Annotated[UploadFile, File(description="Archivo .csv o .xlsx")]


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


@router.get("/invoices", response_model=PageOut[InvoiceOut], tags=["invoices"])
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
) -> PageOut[InvoiceOut]:
    page = cases.list_invoices(
        session,
        actor=actor,
        clock=clock,
        in_case=in_case,
        overdue_only=overdue_only,
        limit=limit,
        offset=offset,
    )
    return PageOut(
        items=[InvoiceOut.from_view(i) for i in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


# ---------------------------------------------------------------- casos


@router.post("/cases/generate", response_model=GenerationOut, tags=["cases"])
def generate_cases(session: SessionDep, actor: ActorDep, clock: ClockDep) -> GenerationOut:
    """Agrupa las facturas vencidas sin caso en casos (uno por deudor)."""
    return GenerationOut.from_result(cases.generate_cases(session, actor=actor, clock=clock))


@router.get("/cases", response_model=PageOut[CaseSummaryOut], tags=["cases"])
def list_cases(
    session: SessionDep,
    actor: ActorDep,
    clock: ClockDep,
    limit: Limit = 50,
    offset: Offset = 0,
    case_status: Annotated[CaseStatus | None, Query(alias="status")] = None,
    sort: Literal["oldest_debt", "highest_amount", "newest"] = "oldest_debt",
) -> PageOut[CaseSummaryOut]:
    page = cases.list_cases(
        session,
        actor=actor,
        clock=clock,
        status=case_status,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return PageOut(
        items=[CaseSummaryOut.from_view(c) for c in page.items],
        total=page.total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/cases/{case_id}", response_model=CaseDetailOut, tags=["cases"])
def get_case(case_id: UUID, session: SessionDep, actor: ActorDep, clock: ClockDep) -> CaseDetailOut:
    return CaseDetailOut.from_detail(
        cases.get_case(session, actor=actor, clock=clock, case_id=case_id)
    )
