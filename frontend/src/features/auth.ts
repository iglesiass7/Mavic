/**
 * Sesión del usuario.
 *
 * Diferencia con el original: Rynx guardaba el usuario en `localStorage`, donde
 * cualquier script de la página puede leerlo y donde queda aunque la sesión del
 * servidor ya haya vencido. Acá la única fuente de verdad es el backend:
 * GET /auth/me responde quién está conectado (o 401 si nadie).
 */
import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Me, Permission } from "@/lib/types";

export const ME_QUERY_KEY = ["me"] as const;

export function getMe(): Promise<Me> {
  return apiFetch<Me>("/auth/me");
}

export function login(email: string, password: string): Promise<Me> {
  return apiFetch<Me>("/auth/login", { method: "POST", json: { email, password } });
}

export function logout(): Promise<void> {
  return apiFetch<void>("/auth/logout", { method: "POST" });
}

export function useMe() {
  return useQuery({ queryKey: ME_QUERY_KEY, queryFn: getMe, staleTime: 5 * 60_000 });
}

/**
 * ¿Puede ver/usar algo? Sirve para mostrar u ocultar botones.
 * Es solo comodidad: el backend vuelve a verificar el permiso en cada pedido.
 */
export function can(me: Me | undefined, permission: Permission): boolean {
  return me?.permissions.includes(permission) ?? false;
}

/**
 * A dónde volver después del login. Solo se aceptan rutas internas ("/cases"),
 * nunca otra página ("//sitio-malo.com" o "https://..."): si no, un link
 * armado por un atacante podría llevar a alguien a un sitio falso al entrar.
 */
export function safeNextPath(next: string | null): string {
  // "//sitio.com" y "/\sitio.com" los navegadores los toman como OTRO sitio.
  if (!next || !next.startsWith("/") || /^\/[/\\]/.test(next) || next.startsWith("/login")) {
    return "/";
  }
  return next;
}
