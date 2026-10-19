"use client";

/**
 * Cargar facturas, en tres pasos:
 *
 *   1. Elegir archivo  ──►  2. Revisar (POST /imports/preview, no guarda nada)
 *                                 │
 *                    ¿tiene errores? ── sí ──► se muestran fila por fila; volver a 1
 *                                 │ no
 *                                 ▼
 *                       3. Cargar (POST /imports) ──► listo + "Generar casos"
 *
 * El backend vuelve a revisar todo al cargar: si entre la revisión y la carga
 * algo cambió y el archivo ya no es válido, responde 422 con el informe y no
 * guarda ninguna fila.
 */
import { useMutation } from "@tanstack/react-query";
import { CheckCircle2, Download, FileSpreadsheet, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState, type DragEvent } from "react";

import { GenerateCases } from "@/components/GenerateCases";
import { ImportCounts, ImportErrors } from "@/components/ImportReportView";
import {
  Button,
  EmptyState,
  ErrorState,
  LoadingState,
  Panel,
  QueryError,
  buttonClass,
  cx,
} from "@/components/ui";
import { can, useMe } from "@/features/auth";
import {
  ACCEPTED_EXTENSIONS,
  checkFile,
  previewImport,
  useImportHistory,
  useImportInvoices,
} from "@/features/invoices";
import { ApiError, errorMessage } from "@/lib/api";
import { count, formatDateTime } from "@/lib/format";
import { IMPORT_COLUMNS } from "@/lib/labels";
import type { ImportReport } from "@/lib/types";

/** Si la carga se rechazó porque el archivo tiene errores, el informe viene en el error. */
function reportFromError(error: unknown): ImportReport | null {
  if (error instanceof ApiError && error.code === "IMPORT_HAS_ERRORS") {
    const report = error.body.report;
    if (report && typeof report === "object") return report as ImportReport;
  }
  return null;
}

const STEPS = ["Elegir archivo", "Revisar", "Cargar"];

function Steps({ current }: { current: number }) {
  return (
    <ol className="flex flex-wrap gap-x-8 gap-y-2 text-sm">
      {STEPS.map((label, index) => {
        const state = index < current ? "done" : index === current ? "current" : "next";
        return (
          <li
            key={label}
            aria-current={state === "current" ? "step" : undefined}
            className={cx("flex items-center gap-2", state === "next" && "text-muted")}
          >
            <span
              className={cx(
                "grid size-6 place-items-center rounded-full border text-xs font-semibold",
                state === "done" && "border-petrol bg-petrol text-white",
                state === "current" && "border-petrol text-petrol",
                state === "next" && "border-line",
              )}
            >
              {state === "done" ? <CheckCircle2 aria-hidden className="size-4" /> : index + 1}
            </span>
            <span className={state === "current" ? "font-semibold" : undefined}>{label}</span>
          </li>
        );
      })}
    </ol>
  );
}

function FilePicker({ onFile, error }: { onFile: (file: File) => void; error: string | null }) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const file = event.dataTransfer.files[0];
    if (file) onFile(file);
  }

  return (
    <div className="space-y-5">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        className={cx(
          "flex flex-col items-center gap-3 rounded-lg border-2 border-dashed px-6 py-12 text-center transition-colors",
          dragging ? "border-petrol bg-petrol-soft" : "border-line bg-surface",
        )}
      >
        <FileSpreadsheet aria-hidden className="size-8 text-petrol" />
        {/* En el celular no se puede arrastrar: ahí queda solo el botón. */}
        <p className="hidden font-semibold sm:block">Arrastrá el archivo acá</p>
        <p className="hidden text-sm text-muted sm:block">o</p>
        <Button variant="secondary" onClick={() => input.current?.click()}>
          <Upload aria-hidden className="size-4" /> Elegir archivo
        </Button>
        <p className="text-xs text-muted">.csv o .xlsx (Excel), hasta 5 MB</p>
        <input
          ref={input}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="sr-only"
          aria-label="Archivo de facturas"
          tabIndex={-1}
          onChange={(e) => {
            const file = e.target.files?.[0];
            e.target.value = ""; // para poder volver a elegir el mismo archivo después de corregirlo
            if (file) onFile(file);
          }}
        />
      </div>

      {error && <ErrorState message={error} />}

      <details className="text-sm">
        <summary className="cursor-pointer text-petrol">¿Qué columnas tiene que tener?</summary>
        <p className="mt-3 text-muted">
          La primera fila lleva estos nombres, tal cual. Una factura por fila; si un deudor tiene
          varias facturas, se repiten sus datos.
        </p>
        <ul className="mt-2 grid gap-x-6 gap-y-1 sm:grid-cols-2">
          {IMPORT_COLUMNS.map((column) => (
            <li key={column.name}>
              <code className="text-xs">{column.name}</code>{" "}
              <span className="text-muted">— {column.label}</span>
            </li>
          ))}
        </ul>
        <a href="/api/imports/template" download className={buttonClass("ghost", "mt-3 -ml-4")}>
          <Download aria-hidden className="size-4" /> Descargar la plantilla
        </a>
      </details>
    </div>
  );
}

function ImportHistory() {
  const history = useImportHistory();
  return (
    <Panel title="Cargas anteriores">
      {history.isPending && <LoadingState />}
      {history.isError && <QueryError error={history.error} retry={history.refetch} />}
      {history.isSuccess && history.data.length === 0 && (
        <p className="text-sm text-muted">Todavía no se cargó ningún archivo.</p>
      )}
      {history.isSuccess && history.data.length > 0 && (
        <div className="-mx-5 -my-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="border-b border-line text-left text-xs text-muted">
              <tr>
                <th scope="col" className="px-5 py-2.5 font-medium">Fecha</th>
                <th scope="col" className="px-5 py-2.5 font-medium">Archivo</th>
                <th scope="col" className="hidden px-5 py-2.5 text-right font-medium sm:table-cell">Filas</th>
                <th scope="col" className="px-5 py-2.5 text-right font-medium">Nuevas</th>
                <th scope="col" className="hidden px-5 py-2.5 text-right font-medium sm:table-cell">Actualizadas</th>
              </tr>
            </thead>
            <tbody>
              {history.data.map((record) => (
                <tr key={record.id} className="border-b border-line last:border-0">
                  <td className="px-5 py-2.5 whitespace-nowrap">{formatDateTime(record.created_at)}</td>
                  <td className="max-w-56 truncate px-5 py-2.5" title={record.filename}>
                    {record.filename}
                  </td>
                  <td className="hidden px-5 py-2.5 text-right sm:table-cell">{record.total_rows}</td>
                  <td className="px-5 py-2.5 text-right">{record.invoices_created}</td>
                  <td className="hidden px-5 py-2.5 text-right sm:table-cell">{record.invoices_updated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function Uploader() {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const preview = useMutation({ mutationFn: previewImport });
  const load = useImportInvoices();

  function choose(next: File) {
    const problem = checkFile(next);
    setFileError(problem);
    if (problem) return;
    setFile(next);
    load.reset();
    preview.mutate(next);
  }

  function startOver() {
    setFile(null);
    setFileError(null);
    preview.reset();
    load.reset();
  }

  // ---- paso 3 terminado
  if (file && load.isSuccess) {
    return (
      <div className="space-y-6">
        <Steps current={3} />
        <Panel>
          <div className="flex items-start gap-3">
            <CheckCircle2 aria-hidden className="mt-0.5 size-5 shrink-0 text-status-agreement" />
            <div className="min-w-0 flex-1">
              <p className="font-semibold">Se cargó {file.name}</p>
              <p className="text-sm text-muted">
                {count(load.data.total_rows, "fila revisada", "filas revisadas")}.
              </p>
              <div className="mt-5">
                <ImportCounts report={load.data} />
              </div>
            </div>
          </div>
        </Panel>
        <GenerateCases canOperate />
        <div className="flex flex-wrap gap-3">
          <Link href="/invoices" className={buttonClass("secondary")}>
            Ver facturas
          </Link>
          <Button variant="ghost" onClick={startOver}>
            Cargar otro archivo
          </Button>
        </div>
      </div>
    );
  }

  // ---- paso 1
  if (!file) {
    return (
      <div className="space-y-6">
        <Steps current={0} />
        <FilePicker onFile={choose} error={fileError} />
      </div>
    );
  }

  // ---- paso 2 (revisión) y paso 3 (cargando)
  const rejected = reportFromError(load.error);
  const report = rejected ?? preview.data;

  return (
    <div className="space-y-6">
      <Steps current={load.isPending ? 2 : 1} />
      <Panel
        title={file.name}
        action={
          <Button
            variant="ghost"
            className="shrink-0 px-0 py-0"
            onClick={startOver}
            disabled={load.isPending}
          >
            Elegir otro archivo
          </Button>
        }
      >
        {preview.isPending && <LoadingState label="Revisando cada fila…" />}
        {preview.isError && <ErrorState message={errorMessage(preview.error)} />}

        {report && !report.ok && <ImportErrors report={report} />}

        {report?.ok && (
          <div className="space-y-6">
            <p className="text-sm">
              Está todo bien: {count(report.total_rows, "fila", "filas")} sin problemas. Esto es lo que se
              va a guardar:
            </p>
            <ImportCounts report={report} />
            {load.isError && !rejected && (
              <ErrorState message={errorMessage(load.error)} onRetry={() => load.mutate(file)} />
            )}
            <Button loading={load.isPending} onClick={() => load.mutate(file)}>
              {report.invoices_created + report.invoices_updated > 0
                ? `Cargar ${count(report.invoices_created + report.invoices_updated, "factura", "facturas")}`
                : "Cargar igual (no hay cambios)"}
            </Button>
          </div>
        )}
      </Panel>
    </div>
  );
}

export default function UploadPage() {
  const me = useMe();
  const allowed = can(me.data, "operate_portfolio");

  return (
    <>
      <h1 className="text-2xl font-bold tracking-tight">Cargar facturas</h1>
      <p className="mt-1 max-w-2xl text-sm text-muted">
        Subí la planilla con las facturas de tus clientes. Antes de guardar nada, Mavic revisa cada
        fila y te muestra qué va a pasar.
      </p>

      <div className="mt-6 space-y-8">
        {allowed ? (
          <Uploader />
        ) : (
          <EmptyState title="Tu rol no puede cargar facturas">
            Lo hace alguien con rol de operador o administración. Vos podés ver las facturas
            cargadas en <Link href="/invoices" className="text-petrol underline">Facturas</Link>.
          </EmptyState>
        )}
        <ImportHistory />
      </div>
    </>
  );
}
