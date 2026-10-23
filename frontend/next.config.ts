/**
 * Configuración de Next.js.
 *
 * EL FRONTEND LE PASA LOS PEDIDOS AL BACKEND ("rewrites")
 * --------------------------------------------------------
 * El navegador solo habla con el frontend (localhost:3000). Todo lo que empieza
 * con /api lo reenvía el servidor de Next al backend:
 *
 *     navegador ──► localhost:3000/api/cases ──► (Next) ──► backend:8000/cases
 *
 * Ventajas frente a llamar al backend directo (como hacía el original):
 * - Una sola dirección: no hay CORS ni configuración extra.
 * - La cookie de sesión es "de la misma página": el navegador la manda sola.
 *
 * API_INTERNAL_URL es la dirección del backend VISTA DESDE EL SERVIDOR de Next.
 * En Docker es http://backend:8000; corriendo en tu PC sin Docker, localhost:8000.
 * Se lee al construir (`next build`), por eso el Dockerfile la recibe como ARG.
 *
 * DIRECCIONES VIEJAS ("redirects")
 * --------------------------------
 * "Mi cuenta" y "Usuarios" ahora son pestañas de Configuración (como en Rynx).
 * Los links viejos siguen andando: el servidor responde "esto se mudó" (308).
 */
import type { NextConfig } from "next";

const apiUrl = (process.env.API_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Genera un servidor mínimo (carpeta .next/standalone) para la imagen de Docker.
  output: "standalone",
  // No anunciar "X-Powered-By: Next.js": no hace falta contarle a nadie qué usamos.
  poweredByHeader: false,
  async redirects() {
    return [
      { source: "/account", destination: "/settings", permanent: true },
      { source: "/users", destination: "/settings?pestana=organizacion", permanent: true },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default nextConfig;
