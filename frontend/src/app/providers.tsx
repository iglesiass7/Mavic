"use client";

/**
 * TanStack Query: guarda en memoria lo que se pidió al backend y maneja
 * "cargando", "error" y "reintentar" de forma uniforme en todas las pantallas.
 *
 * Regla global: si cualquier pedido responde 401 (sesión vencida), se manda a
 * la persona al login y, al volver a entrar, regresa a la pantalla donde estaba.
 */
import { QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { ApiError, isTransient } from "@/lib/api";

function redirectToLogin() {
  const { pathname, search } = window.location;
  if (pathname.startsWith("/login")) return;
  const next = encodeURIComponent(pathname + search);
  window.location.assign(`/login?next=${next}`);
}

export function makeQueryClient(): QueryClient {
  return new QueryClient({
    queryCache: new QueryCache({
      onError: (error) => {
        if (error instanceof ApiError && error.isUnauthorized) redirectToLogin();
      },
    }),
    defaultOptions: {
      queries: {
        // Reintentar solo si falló la red o el servidor (5xx). Un 403 o 404 no
        // se arregla reintentando.
        retry: (failureCount, error) => failureCount < 2 && isTransient(error),
        refetchOnWindowFocus: false,
      },
    },
  });
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(makeQueryClient);
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
