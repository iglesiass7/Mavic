"use client";

/** Copia un texto al portapapeles (por ejemplo, los datos de acceso de un usuario nuevo). */
import { Check, Copy } from "lucide-react";
import { useState } from "react";

import { Button } from "./ui";

export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="secondary"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
        } catch {
          setCopied(false); // sin permiso para copiar: se copia a mano
        }
      }}
    >
      {copied ? <Check aria-hidden className="size-4" /> : <Copy aria-hidden className="size-4" />}
      {copied ? "Copiado" : "Copiar"}
    </Button>
  );
}
