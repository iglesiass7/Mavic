"use client";

/**
 * Carga de facturas, con el diseño de Rynx: tres pasos.
 *
 *   (⇧) Subir ──────────► (🛡) Validar ──────────► (✓) Cargar
 *   elegir la planilla     POST /imports/preview     POST /imports
 *                          (revisa, no guarda)       (guarda todo o nada)
 *
 * Si la revisión encuentra errores, se muestran fila por fila y no se puede
 * cargar: hay que corregir la planilla y volver a subirla.
 *
 * El backend vuelve a revisar todo al cargar: si entre la revisión y la carga
 * algo cambió y el archivo ya no es válido, responde 422 con el informe y no
 * guarda ninguna fila.
 */
import { useMutation } from "@tanstack/react-query";
import { CircleCheck, CloudUpload, FileText, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useRef, useState, type DragEvent } from "react";

import { GenerateCases } from "@/components/GenerateCases";
import { ImportCounts, ImportErrors } from "@/components/ImportReportView";
import { Stepper, type Step } from "@/components/Stepper";
import {
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  PageHeader,
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
import type { ImportReport } from "@/lib/types";

type StepValue = "upload" | "validate" | "load";

const STEPS: Step<StepValue>[] = [
  { value: "upload", title: "Subir", subtitle: "Seleccionar archivo", icon: CloudUpload },
  { value: "validate", title: "Validar", subtitle: "Revisar cada fila", icon: ShieldCheck },
  { value: "load", title: "Cargar", subtitle: "Guardar las facturas", icon: CircleCheck },
];

/** Si la carga se rechazó porque el archivo tiene errores, el informe viene en el error. */
function reportFromError(error: unknown): ImportReport | null {
  if (error instanceof ApiError && error.code === "IMPORT_HAS_ERRORS") {
    const report = error.body.report;
    if (report && typeof report === "object") return report as ImportReport;
  }
  return null;
}

// ---------------------------------------------------------------- paso 1: subir

function FilePicker({
  file,
  onFile,
  onClear,
  onValidate,
  error,
}: {
  file: File | null;
  onFile: (file: File) => void;
  onClear: () => void;
  onValidate: () => void;
  error: string | null;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  function handleDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) onFile(dropped);
  }

  return (
    <Card
      className={cx(
        "flex flex-col items-center px-6 py-16 text-center transition-colors",
        dragging && "border-rynx-primary bg-rynx-soft/30",
      )}
    >
      <div
        className="flex w-full max-w-md flex-col items-center"
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
      >
        <CloudUpload aria-hidden className="size-11 text-ink" strokeWidth={1.5} />
        <h2 className="mt-5 text-lg text-ink">Cargar planilla de facturas</h2>
        <p className="mt-1 text-sm text-muted">Formatos soportados: CSV o XLSX (hasta 5 MB)</p>

        {file ? (
          <>
            <div className="mt-8 flex w-full items-center gap-3 rounded-xl bg-sunken px-4 py-3 text-left">
              <FileText aria-hidden className="size-5 shrink-0 text-ink" />
              <span className="min-w-0 flex-1 truncate text-sm font-bold" title={file.name}>
                {file.name}
              </span>
              <button
                type="button"
                aria-label="Quitar el archivo"
                onClick={onClear}
                className="rounded-full p-1 text-ink hover:bg-white"
              >
                <X aria-hidden className="size-4" />
              </button>
            </div>
            <Button className="mt-4 w-full py-3.5 shadow-lg" onClick={onValidate}>
              Validar planilla
            </Button>
            <button
              type="button"
              onClick={() => input.current?.click()}
              className="mt-4 text-xs font-semibold text-muted hover:text-ink"
            >
              O subir un archivo distinto
            </button>
          </>
        ) : (
          <>
            <Button className="mt-8 w-full py-3.5 shadow-lg" onClick={() => input.current?.click()}>
              Seleccionar planilla de facturas
            </Button>
            <a
              href="/api/imports/template"
              download
              className="mt-4 text-xs font-bold text-rynx-primary underline hover:text-rynx-primary-hover"
            >
              Descargar archivo modelo
            </a>
          </>
        )}

        <input
          ref={input}
          type="file"
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="sr-only"
          aria-label="Archivo de facturas"
          tabIndex={-1}
          onChange={(event) => {
            const chosen = event.target.files?.[0];
            event.target.value = ""; // para poder volver a elegir el mismo archivo después de corregirlo
            if (chosen) onFile(chosen);
          }}
        />
        {error && (
          <div className="mt-6 w-full text-left">
            <ErrorState message={error} />
          </div>
        )}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- historial

function ImportHistory() {
  const history = useImportHistory();
  return (
    <Card className="mt-8 p-6">
      <h2 className="text-lg font-bold text-rynx-primary">Cargas anteriores</h2>
      {history.isPending && <LoadingState />}
      {history.isError && <QueryError error={history.error} retry={history.refetch} />}
      {history.isSuccess && history.data.length === 0 && (
        <p className="mt-3 text-sm text-muted">Todavía no se cargó ningún archivo.</p>
      )}
      {history.isSuccess && history.data.length > 0 && (
        <div className="mt-4 overflow-x-auto rounded-xl border border-line">
          <table className="w-full text-sm">
            <caption className="sr-only">Cargas anteriores</caption>
            <thead className="bg-sunken text-left">
              <tr>
                <th scope="col" className="px-4 py-3 font-bold">Fecha</th>
                <th scope="col" className="px-4 py-3 font-bold">Archivo</th>
                <th scope="col" className="hidden px-4 py-3 text-right font-bold sm:table-cell">Filas</th>
                <th scope="col" className="px-4 py-3 text-right font-bold">Nuevas</th>
                <th scope="col" className="hidden px-4 py-3 text-right font-bold sm:table-cell">Actualizadas</th>
              </tr>
            </thead>
            <tbody>
              {history.data.map((record) => (
                <tr key={record.id} className="border-t border-line">
                  <td className="px-4 py-3 whitespace-nowrap">{formatDateTime(record.created_at)}</td>
                  <td className="max-w-64 truncate px-4 py-3" title={record.filename}>
                    {record.filename}
                  </td>
                  <td className="hidden px-4 py-3 text-right sm:table-cell">{record.total_rows}</td>
                  <td className="px-4 py-3 text-right">{record.invoices_created}</td>
                  <td className="hidden px-4 py-3 text-right sm:table-cell">{record.invoices_updated}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- el flujo

function Uploader() {
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const preview = useMutation({ mutationFn: previewImport });
  const load = useImportInvoices();

  function choose(next: File) {
    const problem = checkFile(next);
    setFileError(problem);
    preview.reset();
    load.reset();
    setFile(problem ? null : next);
  }

  function startOver() {
    setFile(null);
    setFileError(null);
    preview.reset();
    load.reset();
  }

  const validating = preview.isPending || preview.isSuccess || preview.isError;

  // ---- paso 3 terminado
  if (file && load.isSuccess) {
    return (
      <>
        <Stepper label="Pasos de la carga" steps={STEPS} current="load" done={["upload", "validate", "load"]} />
        <Card className="p-8">
          <div className="flex items-start gap-3">
            <CircleCheck aria-hidden className="mt-0.5 size-6 shrink-0 text-rynx-primary" />
            <div className="min-w-0 flex-1">
              <h2 className="text-lg font-bold">Se cargó {file.name}</h2>
              <p className="text-sm text-muted">
                {count(load.data.total_rows, "fila revisada", "filas revisadas")}.
              </p>
              <div className="mt-6">
                <ImportCounts report={load.data} />
              </div>
            </div>
          </div>
        </Card>
        <div className="mt-6">
          <GenerateCases canOperate />
        </div>
        <div className="mt-6 flex flex-wrap gap-3">
          <Link href="/invoices" className={buttonClass("secondary")}>
            Ver facturas
          </Link>
          <Button variant="ghost" onClick={startOver}>
            Cargar otro archivo
          </Button>
        </div>
      </>
    );
  }

  // ---- paso 1
  if (!file || !validating) {
    return (
      <>
        <Stepper label="Pasos de la carga" steps={STEPS} current="upload" />
        <FilePicker
          file={file}
          onFile={choose}
          onClear={startOver}
          onValidate={() => file && preview.mutate(file)}
          error={fileError}
        />
      </>
    );
  }

  // ---- paso 2 (revisión) y paso 3 (cargando)
  const rejected = reportFromError(load.error);
  const report = rejected ?? preview.data;

  return (
    <>
      <Stepper
        label="Pasos de la carga"
        steps={STEPS}
        current={load.isPending ? "load" : "validate"}
        done={load.isPending ? ["upload", "validate"] : ["upload"]}
      />
      <Card className="p-8">
        <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div className="flex min-w-0 items-center gap-3">
            <FileText aria-hidden className="size-5 shrink-0" />
            <h2 className="truncate text-lg font-bold" title={file.name}>
              {file.name}
            </h2>
          </div>
          <Button variant="secondary" onClick={startOver} disabled={load.isPending}>
            Elegir otro archivo
          </Button>
        </header>

        {preview.isPending && <LoadingState label="Revisando cada fila…" />}
        {preview.isError && <ErrorState message={errorMessage(preview.error)} />}

        {report && !report.ok && <ImportErrors report={report} />}

        {report?.ok && (
          <div className="space-y-6">
            <p className="text-sm">
              Está todo bien: {count(report.total_rows, "fila", "filas")} sin problemas. Esto es lo
              que se va a guardar:
            </p>
            <ImportCounts report={report} />
            {load.isError && !rejected && (
              <ErrorState message={errorMessage(load.error)} onRetry={() => load.mutate(file)} />
            )}
            <div className="flex justify-end">
              <Button loading={load.isPending} onClick={() => load.mutate(file)} className="px-8 py-3">
                {report.invoices_created + report.invoices_updated > 0
                  ? `Cargar ${count(report.invoices_created + report.invoices_updated, "factura", "facturas")}`
                  : "Cargar igual (no hay cambios)"}
              </Button>
            </div>
          </div>
        )}
      </Card>
    </>
  );
}

export default function UploadPage() {
  const me = useMe();
  const allowed = can(me.data, "operate_portfolio");

  return (
    <>
      <PageHeader
        title="Carga de facturas"
        subtitle="Subí la planilla de facturas (.xlsx o .csv). Antes de guardar, se revisa cada fila."
      />
      {allowed ? (
        <Uploader />
      ) : (
        <EmptyState title="Tu rol no puede cargar facturas">
          Lo hace alguien con rol de operador o administración. Vos podés ver las facturas
          cargadas en{" "}
          <Link href="/invoices" className="font-semibold text-rynx-primary underline">
            Facturas
          </Link>
          .
        </EmptyState>
      )}
      <ImportHistory />
    </>
  );
}
