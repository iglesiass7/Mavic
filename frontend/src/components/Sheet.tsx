"use client";

/**
 * Panel que entra por la derecha sobre la pantalla (el "Detalle del caso" de
 * Rynx). Se cierra con la X, con Escape o tocando el fondo. Mientras está
 * abierto, el foco queda adentro y la página de atrás no se desplaza.
 */
import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

export function Sheet({
  title,
  open,
  onClose,
  children,
}: {
  title: string;
  open: boolean;
  onClose: () => void;
  children: ReactNode;
}) {
  const panel = useRef<HTMLDivElement>(null);
  // La última función para cerrar, sin que el efecto de abajo dependa de ella:
  // si dependiera, cada vez que la pantalla de atrás se redibuja (por ejemplo,
  // al refrescar datos) el foco saltaría al panel y se perdería lo que se escribe.
  const close = useRef(onClose);
  useEffect(() => {
    close.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    panel.current?.focus();
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") close.current();
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, [open]);

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <button
        type="button"
        aria-label="Cerrar"
        tabIndex={-1}
        className="absolute inset-0 bg-black/20 backdrop-blur-sm"
        onClick={onClose}
      />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="sheet-title"
        tabIndex={-1}
        className="rynx-scroll absolute inset-y-0 right-0 flex w-full max-w-[460px] flex-col overflow-y-auto bg-white shadow-2xl outline-none"
      >
        <header className="sticky top-0 z-10 flex items-center justify-between border-b border-line bg-white px-5 py-4">
          <h2 id="sheet-title" className="text-2xl font-bold">
            {title}
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded-lg p-1.5 hover:bg-sunken"
          >
            <X aria-hidden className="size-5" />
          </button>
        </header>
        <div className="flex-1 px-5 py-5">{children}</div>
      </div>
    </div>
  );
}
