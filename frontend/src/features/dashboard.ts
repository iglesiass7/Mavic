/** El tablero: un solo pedido (GET /dashboard) con todos los números ya calculados. */
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Dashboard } from "@/lib/types";

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: ({ signal }) => apiFetch<Dashboard>("/dashboard", { signal }),
  });
}

/**
 * Qué parte de `total` es `part`, entre 0 y 1. SOLO para dibujar (el largo de
 * una barra): el número que lee la persona siempre es el texto del backend.
 * Por eso acá sí se usa Number: un error de un centavo no cambia un píxel.
 */
export function share(part: string, total: string): number {
  const t = Number(total);
  if (!Number.isFinite(t) || t <= 0) return 0;
  return Math.min(Math.max(Number(part) / t, 0), 1);
}
