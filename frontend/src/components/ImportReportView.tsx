/**
 * El informe de una carga de facturas: qué se va a guardar (o qué se guardó)
 * y, si el archivo tiene problemas, la lista de errores fila por fila.
 *
 * La fila es la misma que ve la persona en Excel: la 1 es el encabezado, así
 * que la primera factura es la fila 2.
 */
import { IMPORT_COLUMNS } from "@/lib/labels";
import type { ImportReport } from "@/lib/types";

// El backend devuelve como máximo 200 errores (ver import_rows.MAX_ERRORS).
const MAX_ERRORS_SHOWN = 200;

const COLUMN_LABEL = new Map(IMPORT_COLUMNS.map((c) => [c.name, c.label]));

export function ImportCounts({ report }: { report: ImportReport }) {
  const items: [string, number][] = [
    ["Facturas nuevas", report.invoices_created],
    ["Facturas actualizadas", report.invoices_updated],
    ["Facturas sin cambios", report.invoices_unchanged],
    ["Deudores nuevos", report.debtors_created],
    ["Deudores actualizados", report.debtors_updated],
  ];
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-5">
      {items.map(([label, value]) => (
        <div key={label}>
          <dt className="text-xs text-muted">{label}</dt>
          <dd className="mt-0.5 text-2xl font-bold">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ImportErrors({ report }: { report: ImportReport }) {
  const { errors } = report;
  return (
    <div>
      <p className="text-sm">
        {errors.length >= MAX_ERRORS_SHOWN
          ? `Se muestran los primeros ${MAX_ERRORS_SHOWN} problemas.`
          : `${errors.length === 1 ? "Hay 1 problema" : `Hay ${errors.length} problemas`} en ${report.total_rows === 1 ? "la fila" : `las ${report.total_rows} filas`} del archivo.`}{" "}
        Corregilos en tu planilla y volvé a subirla: hasta entonces no se guarda nada.
      </p>
      <div className="mt-4 max-h-[420px] overflow-auto rounded-md border border-line">
        <table className="w-full text-sm">
          <thead className="sticky top-0 border-b border-line bg-surface text-left text-xs text-muted">
            <tr>
              <th scope="col" className="px-4 py-2.5 text-right font-medium">Fila</th>
              <th scope="col" className="hidden px-4 py-2.5 font-medium sm:table-cell">Columna</th>
              <th scope="col" className="px-4 py-2.5 font-medium">Problema</th>
            </tr>
          </thead>
          <tbody>
            {errors.map((error, index) => (
              <tr key={index} className="border-b border-line align-top last:border-0">
                <td className="px-4 py-2.5 text-right font-semibold">{error.row || "—"}</td>
                <td className="hidden px-4 py-2.5 whitespace-nowrap sm:table-cell">
                  {error.column ? (
                    <>
                      <code className="text-xs">{error.column}</code>
                      {COLUMN_LABEL.has(error.column) && (
                        <span className="block text-xs text-muted">{COLUMN_LABEL.get(error.column)}</span>
                      )}
                    </>
                  ) : (
                    <span className="text-muted">Toda la fila</span>
                  )}
                </td>
                <td className="px-4 py-2.5">
                  {/* En el celular la columna "Columna" no entra: va arriba del problema. */}
                  {error.column && (
                    <code className="block text-xs text-muted sm:hidden">{error.column}</code>
                  )}
                  {error.message}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
