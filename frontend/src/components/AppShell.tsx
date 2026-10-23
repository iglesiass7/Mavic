"use client";

/**
 * Armazón de las pantallas con sesión, con el diseño de Rynx:
 *
 *   ┌───────────────┬──────────────────────────────┐
 *   │ logo          │                              │
 *   │ menú          │   contenido de la pantalla   │
 *   │ …             │                              │
 *   │ usuario  ⎋    │                              │
 *   └───────────────┴──────────────────────────────┘
 *
 * En celular el menú se abre desde un botón arriba (no entra al costado).
 * El menú muestra solo lo que el rol puede usar (según /auth/me). Ocultar es
 * comodidad: el backend igual rechaza con 403.
 */
import { useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CloudUpload,
  FileStack,
  FileText,
  Gauge,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquare,
  Scale,
  Settings,
  X,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { can, logout, useMe } from "@/features/auth";
import { ROLE_LABEL } from "@/lib/labels";
import type { Permission } from "@/lib/types";

import { BrandLogo } from "./Brand";
import { LoadingState, QueryError, cx } from "./ui";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  permission: Permission | null; // null: cualquier usuario con sesión
}

// El orden y los nombres son los del menú de Rynx. Cada pantalla nueva se
// agrega acá, con el permiso que la habilita.
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, permission: "view_portfolio" },
  {
    href: "/invoices/upload",
    label: "Carga de facturas",
    icon: CloudUpload,
    permission: "operate_portfolio",
  },
  { href: "/invoices", label: "Facturas", icon: FileStack, permission: "view_portfolio" },
  { href: "/rules", label: "Reglas de negocio", icon: Scale, permission: "view_portfolio" },
  { href: "/cases", label: "Casos", icon: FileText, permission: "view_portfolio" },
  {
    href: "/conversations",
    label: "Conversaciones",
    icon: MessageSquare,
    permission: "view_portfolio",
  },
  { href: "/audit", label: "Auditoría", icon: History, permission: "view_audit" },
  { href: "/costs", label: "Medidor de costos", icon: Gauge, permission: "view_costs" },
  { href: "/companies", label: "Empresas", icon: Building2, permission: "manage_companies" },
  { href: "/settings", label: "Configuración", icon: Settings, permission: null },
];

/** Pantallas que ocupan todo el espacio a la derecha del menú (sin márgenes), como en Rynx. */
const FULL_BLEED = ["/conversations"];

/**
 * Qué ítem del menú corresponde a la dirección actual: el más específico.
 * En /invoices/upload se marca "Carga de facturas", no "Facturas".
 */
export function activeHref(pathname: string, hrefs: string[]): string | undefined {
  return hrefs
    .filter((href) => pathname === href || pathname.startsWith(`${href}/`))
    .sort((a, b) => b.length - a.length)[0];
}

/** Las iniciales del nombre, para el avatar: "Laura Gómez" -> "LG". */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length < 2) return name.trim().slice(0, 2).toUpperCase();
  return `${words.at(0)?.charAt(0) ?? ""}${words.at(-1)?.charAt(0) ?? ""}`.toUpperCase();
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const me = useMe();
  const [leaving, setLeaving] = useState(false);
  // El menú del celular queda abierto solo en la pantalla donde se abrió: al
  // navegar a otra, se cierra solo (sin un efecto que lo cierre después).
  const [menuOpenAt, setMenuOpenAt] = useState<string | null>(null);
  const menuOpen = menuOpenAt === pathname;
  const setMenuOpen = (open: boolean) => setMenuOpenAt(open ? pathname : null);

  async function handleLogout() {
    setLeaving(true);
    try {
      await logout();
    } finally {
      queryClient.clear(); // nada de la sesión anterior queda en memoria
      router.replace("/login");
    }
  }

  if (me.isPending) {
    return (
      <div className="px-8">
        <LoadingState label="Verificando tu sesión…" />
      </div>
    );
  }
  if (me.isError) {
    // Un 401 ya redirige al login (ver providers.tsx). Esto es para otros errores.
    return (
      <div className="p-8">
        <QueryError error={me.error} retry={me.refetch} />
      </div>
    );
  }

  const items = NAV_ITEMS.filter((item) => item.permission === null || can(me.data, item.permission));
  const current = activeHref(
    pathname,
    items.map((item) => item.href),
  );
  const { user, company } = me.data;

  const sidebar = (
    <div className="flex h-full flex-col bg-white">
      <div className="px-4 pt-5 pb-2">
        <BrandLogo className="h-8 w-auto" />
        <p className="mt-2 text-[8px] font-medium tracking-[0.2em] text-ink/80 uppercase">
          Agente de gestión de deuda con IA
        </p>
        {company && <p className="mt-3 truncate text-xs text-muted">{company.name}</p>}
        <div className="mt-5 h-px w-full bg-ink" />
      </div>

      <nav aria-label="Secciones" className="rynx-scroll flex-1 space-y-1 overflow-y-auto px-3 py-4">
        {items.map(({ href, label, icon: Icon }) => {
          const active = href === current;
          return (
            <Link
              key={href}
              href={href}
              aria-current={active ? "page" : undefined}
              className={cx(
                "group flex items-center gap-3 rounded-xl px-4 py-2.5 text-[13px] transition-colors",
                active ? "bg-rynx-dark font-bold text-white shadow-md" : "font-medium text-muted hover:bg-sunken",
              )}
            >
              <Icon
                aria-hidden
                className={cx(
                  "size-[18px]",
                  active ? "text-white" : "text-gray-400 group-hover:text-rynx-primary",
                )}
              />
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="px-4 pb-4">
        <div className="mb-4 h-px w-full bg-ink" />
        <div className="flex items-center justify-between gap-2 rounded-2xl bg-sunken/60 p-2">
          <Link href="/settings" className="flex min-w-0 items-center gap-3" title="Mi cuenta">
            <span
              aria-hidden
              className="flex size-8 shrink-0 items-center justify-center rounded-full bg-rynx-dark text-[10px] font-black text-white"
            >
              {initials(user.name)}
            </span>
            <span className="flex min-w-0 flex-col">
              <span className="truncate text-xs font-bold text-ink">{user.name}</span>
              <span className="text-[9px] font-bold tracking-tight text-gray-400 uppercase">
                {ROLE_LABEL[user.role]}
              </span>
            </span>
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            disabled={leaving}
            aria-label={leaving ? "Cerrando sesión…" : "Cerrar sesión"}
            title="Cerrar sesión"
            className="rounded-lg p-2 text-red-500 hover:bg-red-50 disabled:opacity-50"
          >
            <LogOut aria-hidden className="size-[18px]" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-paper">
      {/* Escritorio: menú fijo a la izquierda. */}
      <aside className="fixed inset-y-0 left-0 z-40 hidden w-64 border-r border-gray-300 lg:block">
        {sidebar}
      </aside>

      {/* Celular y tablet: barra arriba con el logo y el botón del menú. */}
      <header className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-white px-4 py-3 lg:hidden">
        <BrandLogo className="h-6 w-auto" />
        <button
          type="button"
          onClick={() => setMenuOpen(true)}
          aria-label="Abrir el menú"
          aria-expanded={menuOpen}
          className="rounded-lg p-2 hover:bg-sunken"
        >
          <Menu aria-hidden className="size-5" />
        </button>
      </header>
      {menuOpen && (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Menú">
          <button
            type="button"
            aria-label="Cerrar el menú"
            className="absolute inset-0 bg-black/30"
            onClick={() => setMenuOpen(false)}
          />
          <div className="absolute inset-y-0 left-0 w-72 max-w-[85vw] shadow-xl">
            {sidebar}
            <button
              type="button"
              onClick={() => setMenuOpen(false)}
              aria-label="Cerrar el menú"
              className="absolute top-4 right-3 rounded-lg p-2 hover:bg-sunken"
            >
              <X aria-hidden className="size-5" />
            </button>
          </div>
        </div>
      )}

      {FULL_BLEED.includes(pathname) ? (
        <main className="min-w-0 lg:ml-64">{children}</main>
      ) : (
        <main className="min-w-0 px-4 py-6 sm:px-6 lg:ml-64 lg:px-10 lg:py-6">
          <div className="mx-auto max-w-[1280px]">{children}</div>
        </main>
      )}
    </div>
  );
}
