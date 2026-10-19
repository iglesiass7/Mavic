/** Usuarios de la empresa, cambio de contraseña y empresas (dueño de la plataforma). */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { Company, CompanyRole, CompanyWithAdmin, User } from "@/lib/types";

import { ME_QUERY_KEY } from "./auth";

// El mismo mínimo que exige el backend (identity/domain/rules.py).
export const PASSWORD_MIN_LENGTH = 10;

/** Revisión de contraseña nueva antes de mandarla. null = está bien. */
export function checkNewPassword(password: string): string | null {
  if (password.length < PASSWORD_MIN_LENGTH) {
    return `Tiene que tener al menos ${PASSWORD_MIN_LENGTH} caracteres.`;
  }
  if (password.length > 128) return "Máximo 128 caracteres.";
  if (!password.trim()) return "No puede ser solo espacios.";
  return null;
}

/** Un email con forma de email. El backend lo valida de verdad. */
export function looksLikeEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}

// Sin letras que se confunden al dictarlas o leerlas (l, 1, I, O, 0).
const ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";

/**
 * Contraseña inicial al azar para un usuario nuevo, en grupos de 4 para que
 * sea fácil de pasar ("Hk7m-p2Qa-9xTe"). Usa el generador seguro del navegador.
 */
export function generatePassword(groups = 3): string {
  // 256 no es múltiplo de 56: si se usaran todos los bytes con "%", algunas
  // letras saldrían más seguido. Se descartan los bytes del "sobrante".
  const limit = 256 - (256 % ALPHABET.length);
  const chars: string[] = [];
  while (chars.length < groups * 4) {
    const bytes = crypto.getRandomValues(new Uint8Array(32));
    for (const b of bytes) {
      if (b < limit && chars.length < groups * 4) chars.push(ALPHABET[b % ALPHABET.length]!);
    }
  }
  const parts: string[] = [];
  for (let i = 0; i < chars.length; i += 4) parts.push(chars.slice(i, i + 4).join(""));
  return parts.join("-");
}

// ---------------------------------------------------------------- usuarios

export function useUsers() {
  return useQuery({
    queryKey: ["users"],
    queryFn: ({ signal }) => apiFetch<User[]>("/users", { signal }),
  });
}

export interface NewUser {
  name: string;
  email: string;
  password: string;
  role: CompanyRole;
}

export function useCreateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (user: NewUser) => apiFetch<User>("/users", { method: "POST", json: user }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...changes }: { id: string; role?: CompanyRole; is_active?: boolean }) =>
      apiFetch<User>(`/users/${id}`, { method: "PATCH", json: changes }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });
}

// ---------------------------------------------------------------- mi contraseña

export function useChangePassword() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      apiFetch<void>("/auth/password", { method: "PUT", json: body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY }),
  });
}

// ---------------------------------------------------------------- empresas

export function useCompanies() {
  return useQuery({
    queryKey: ["companies"],
    queryFn: ({ signal }) => apiFetch<Company[]>("/platform/companies", { signal }),
  });
}

export interface NewCompany {
  name: string;
  admin: { name: string; email: string; password: string };
}

export function useCreateCompany() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: NewCompany) =>
      apiFetch<CompanyWithAdmin>("/platform/companies", { method: "POST", json: body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["companies"] }),
  });
}
