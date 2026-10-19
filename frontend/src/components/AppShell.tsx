"use client";

/**
 * Armazón de las pantallas con sesión: menú lateral + contenido.
 *
 * El menú muestra solo lo que el rol puede usar (según los permisos que
 * devuelve /auth/me). Ocultar es comodidad: el backend igual rechaza con 403.
 */
import { useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  FileText,
  FolderOpen,
  LayoutDashboard,
  LogOut,
  Scale,
  Upload,
  UserCircle,
  Users,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { can, logout, useMe } from "@/features/auth";
import { ROLE_LABEL } from "@/lib/labels";
import type { Permission } from "@/lib/types";

import { LoadingState, QueryError, cx } from "./ui";

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  permission: Permission;
}

// Cada pantalla nueva se agrega acá, con el permiso que la habilita.
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Inicio", icon: LayoutDashboard, permission: "view_portfolio" },
  { href: "/cases", label: "Casos", icon: FolderOpen, permission: "view_portfolio" },
  { href: "/invoices", label: "Facturas", icon: FileText, permission: "view_portfolio" },
  { href: "/invoices/upload", label: "Cargar facturas", icon: Upload, permission: "operate_portfolio" },
  { href: "/rules", label: "Reglas", icon: Scale, permission: "view_portfolio" },
  { href: "/users", label: "Usuarios", icon: Users, permission: "manage_users" },
  { href: "/companies", label: "Empresas", icon: Building2, permission: "manage_companies" },
];

/**
 * Qué ítem del menú corresponde a la dirección actual: el más específico.
 * En /invoices/upload se marca "Cargar facturas", no "Facturas".
 */
export function activeHref(pathname: string, hrefs: string[]): string | undefined {
  return hrefs
    .filter((href) => pathname === href || pathname.startsWith(`${href}/`))
    .sort((a, b) => b.length - a.length)[0];
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const me = useMe();
  const [leaving, setLeaving] = useState(false);

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

  const items = NAV_ITEMS.filter((item) => can(me.data, item.permission));
  const current = activeHref(
    pathname,
    items.map((item) => item.href),
  );
  const { user, company } = me.data;

  return (
    <div className="min-h-screen md:grid md:grid-cols-[232px_minmax(0,1fr)]">
      <aside className="flex flex-col bg-ink text-white md:sticky md:top-0 md:h-screen">
        <div className="flex items-start justify-between gap-4 px-5 pt-6 pb-4">
          <div>
            <p className="text-xl font-bold tracking-tight">Mavic</p>
            {company && <p className="mt-0.5 text-sm text-white/60">{company.name}</p>}
          </div>
          {/* En celular no hay pie del menú: la cuenta y cerrar sesión van arriba. */}
          <div className="flex items-center gap-4 md:hidden">
            <Link
              href="/account"
              aria-current={pathname === "/account" ? "page" : undefined}
              className="inline-flex items-center gap-2 text-sm text-white/75 hover:text-white"
            >
              <UserCircle aria-hidden className="size-4" />
              Mi cuenta
            </Link>
            <button
              type="button"
              onClick={handleLogout}
              disabled={leaving}
              className="inline-flex items-center gap-2 text-sm text-white/75 hover:text-white"
            >
              <LogOut aria-hidden className="size-4" />
              Salir
            </button>
          </div>
        </div>

        <nav aria-label="Secciones" className="flex flex-wrap gap-1 px-3 pb-3 md:flex-1 md:flex-col md:flex-nowrap md:pb-0">
          {items.map(({ href, label, icon: Icon }) => {
            const active = href === current;
            return (
              <Link
                key={href}
                href={href}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex items-center gap-3 rounded-md px-3 py-2 text-sm whitespace-nowrap",
                  active ? "bg-white/12 font-semibold" : "text-white/75 hover:bg-white/6 hover:text-white",
                )}
              >
                <Icon aria-hidden className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="hidden border-t border-white/10 px-5 py-4 md:block">
          <Link
            href="/account"
            aria-current={pathname === "/account" ? "page" : undefined}
            className={cx(
              "-mx-2 block rounded-md px-2 py-1.5 hover:bg-white/6",
              pathname === "/account" && "bg-white/12",
            )}
          >
            <span className="flex items-center gap-2 truncate text-sm font-medium">
              <UserCircle aria-hidden className="size-4 shrink-0" />
              {user.name}
            </span>
            <span className="mt-0.5 block pl-6 text-xs text-white/60">
              {ROLE_LABEL[user.role]} · Mi cuenta
            </span>
          </Link>
          <button
            type="button"
            onClick={handleLogout}
            disabled={leaving}
            className="mt-3 inline-flex items-center gap-2 text-sm text-white/75 hover:text-white"
          >
            <LogOut aria-hidden className="size-4" />
            {leaving ? "Cerrando sesión…" : "Cerrar sesión"}
          </button>
        </div>
      </aside>

      <main className="min-w-0 px-4 py-6 md:px-10 md:py-8">
        <div className="mx-auto max-w-6xl">{children}</div>
      </main>
    </div>
  );
}
