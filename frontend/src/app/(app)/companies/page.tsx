"use client";

/**
 * Empresas cliente (solo el dueño de la plataforma), con el diseño de Rynx: la
 * tabla y "Nueva empresa" en un panel a la derecha. Cada empresa nace con su
 * primer usuario de administración, que después da de alta al resto del equipo.
 */
import { Plus, RefreshCw } from "lucide-react";
import { useState, type FormEvent } from "react";

import { CopyButton } from "@/components/CopyButton";
import { DataTable, type Column } from "@/components/DataTable";
import { Sheet } from "@/components/Sheet";
import { Button, EmptyState, ErrorState, Field, PageHeader, QueryError, inputClass } from "@/components/ui";
import { can, useMe } from "@/features/auth";
import {
  checkNewPassword,
  generatePassword,
  looksLikeEmail,
  useCompanies,
  useCreateCompany,
} from "@/features/users";
import { errorMessage } from "@/lib/api";
import { businessDay, formatDate } from "@/lib/format";
import type { Company } from "@/lib/types";

function NewCompanyForm({ onClose }: { onClose: () => void }) {
  const create = useCreateCompany();
  const [company, setCompany] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(() => generatePassword());
  const [errors, setErrors] = useState<Record<string, string>>({});

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const found: Record<string, string> = {};
    if (!company.trim()) found.company = "Escribí el nombre de la empresa.";
    if (!name.trim()) found.name = "Escribí el nombre de la persona.";
    if (!looksLikeEmail(email)) found.email = "Escribí un email válido.";
    const problem = checkNewPassword(password);
    if (problem) found.password = problem;
    setErrors(found);
    if (Object.keys(found).length === 0) {
      create.mutate({
        name: company.trim(),
        admin: { name: name.trim(), email: email.trim(), password },
      });
    }
  }

  if (create.isSuccess) {
    return (
      <div role="status" className="space-y-4 text-sm">
        <h3 className="text-lg font-bold text-rynx-primary">Empresa creada</h3>
        <div className="space-y-4">
          <p>
            <span className="font-semibold">{create.data.company.name}</span> ya está lista. Pasale a{" "}
            {create.data.admin.name} estos datos por un medio privado (la contraseña no se vuelve a mostrar):
          </p>
          <dl className="grid gap-3 rounded-xl border border-line bg-paper p-4 sm:grid-cols-[auto_1fr_auto] sm:items-center">
            <dt className="text-muted">Email</dt>
            <dd className="font-medium break-all">{create.data.admin.email}</dd>
            <dd />
            <dt className="text-muted">Contraseña</dt>
            <dd>
              <code className="text-base">{password}</code>
            </dd>
            <dd>
              <CopyButton text={`Email: ${create.data.admin.email}\nContraseña: ${password}`} />
            </dd>
          </dl>
          <Button variant="secondary" onClick={onClose}>
            Listo
          </Button>
        </div>
      </div>
    );
  }

  const input = (id: string, label: string, value: string, onChange: (v: string) => void, type = "text") => (
    <Field id={id} label={label} error={errors[id]}>
      {(aria) => (
        <input
          {...aria}
          type={type}
          value={value}
          autoComplete="off"
          onChange={(e) => onChange(e.target.value)}
          className={inputClass(Boolean(errors[id]))}
        />
      )}
    </Field>
  );

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      {input("company", "Nombre de la empresa", company, setCompany)}
      <fieldset className="space-y-4 rounded-xl border border-line p-4">
        <legend className="px-1 text-xs font-bold text-ink">Primera persona de administración</legend>
        <div className="space-y-4">
          {input("name", "Nombre", name, setName)}
          {input("email", "Email", email, setEmail, "email")}
        </div>
        <Field
          id="password"
          label="Contraseña inicial"
          hint="Generada al azar. La puede cambiar desde Configuración › Mi cuenta."
          error={errors.password}
        >
          {(aria) => (
            <div className="flex gap-2">
              <input
                {...aria}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                spellCheck={false}
                autoComplete="new-password"
                className={inputClass(Boolean(errors.password), "font-mono")}
              />
              <Button type="button" variant="secondary" onClick={() => setPassword(generatePassword())}>
                <RefreshCw aria-hidden className="size-4" /> Otra
              </Button>
            </div>
          )}
        </Field>
      </fieldset>
      {create.isError && <ErrorState message={errorMessage(create.error)} />}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={create.isPending}>
          Crear empresa
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

export default function CompaniesPage() {
  const me = useMe();
  const companies = useCompanies();
  const [adding, setAdding] = useState(false);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState("name");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  if (!can(me.data, "manage_companies")) {
    return <EmptyState title="Esta pantalla es solo para el dueño de la plataforma" />;
  }

  const text = search.trim().toLowerCase();
  const matching = (companies.data ?? [])
    .filter((company) => !text || company.name.toLowerCase().includes(text))
    .sort((a, b) => {
      const desc = sort.startsWith("-");
      const order =
        sort.replace("-", "") === "created"
          ? a.created_at.localeCompare(b.created_at)
          : a.name.localeCompare(b.name, "es");
      return desc ? -order : order;
    });
  const rows = matching.slice((page - 1) * pageSize, page * pageSize);

  const columns: Column<Company>[] = [
    {
      key: "name",
      header: "Empresa",
      sortKey: "name",
      className: "font-bold",
      cell: (c) => c.name,
    },
    {
      key: "status",
      header: "Estado",
      cell: (c) => (
        <span
          className={c.is_active ? "text-xs font-bold text-rynx-primary" : "text-xs font-bold text-muted"}
        >
          {c.is_active ? "Activa" : "Desactivada"}
        </span>
      ),
    },
    {
      key: "created",
      header: "Alta",
      sortKey: "created",
      className: "whitespace-nowrap tabular",
      cell: (c) => formatDate(businessDay(c.created_at)),
    },
  ];

  return (
    <>
      <PageHeader
        title="Empresas"
        subtitle="Las empresas que usan Mavic. Cada una ve solo sus propios datos y administra su equipo."
        actions={
          <Button onClick={() => setAdding(true)} className="px-8 py-3">
            <Plus aria-hidden className="size-4" /> Nueva empresa
          </Button>
        }
      />
      {companies.isError ? (
        <QueryError error={companies.error} retry={companies.refetch} />
      ) : (
        <DataTable
          caption="Empresas"
          columns={columns}
          rows={rows}
          rowKey={(c) => c.id}
          loading={companies.isPending}
          search={{
            value: search,
            onChange: (value) => {
              setSearch(value);
              setPage(1);
            },
            placeholder: "Buscar por nombre...",
          }}
          sort={sort}
          onSort={setSort}
          page={page}
          pageSize={pageSize}
          total={matching.length}
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size);
            setPage(1);
          }}
          empty={text ? "Ninguna empresa coincide con la búsqueda." : "Todavía no hay empresas."}
        />
      )}
      <Sheet title="Nueva empresa" open={adding} onClose={() => setAdding(false)}>
        {adding && <NewCompanyForm onClose={() => setAdding(false)} />}
      </Sheet>
    </>
  );
}
