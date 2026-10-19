"use client";

/**
 * Empresas cliente (solo el dueño de la plataforma). Cada empresa nace con su
 * primer usuario de administración, que después da de alta al resto del equipo.
 */
import { Plus, RefreshCw } from "lucide-react";
import { useState, type FormEvent } from "react";

import { CopyButton } from "@/components/CopyButton";
import {
  Button,
  EmptyState,
  ErrorState,
  Field,
  LoadingState,
  Panel,
  QueryError,
  inputClass,
} from "@/components/ui";
import { can, useMe } from "@/features/auth";
import {
  checkNewPassword,
  generatePassword,
  looksLikeEmail,
  useCompanies,
  useCreateCompany,
} from "@/features/users";
import { errorMessage } from "@/lib/api";
import { formatDate } from "@/lib/format";

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
      <Panel title="Empresa creada">
        <div className="space-y-4 text-sm">
          <p>
            <span className="font-semibold">{create.data.company.name}</span> ya está lista. Pasale a{" "}
            {create.data.admin.name} estos datos por un medio privado (la contraseña no se vuelve a
            mostrar):
          </p>
          <dl className="grid gap-3 rounded-md border border-line bg-paper p-4 sm:grid-cols-[auto_1fr_auto] sm:items-center">
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
      </Panel>
    );
  }

  const input = (
    id: string,
    label: string,
    value: string,
    onChange: (v: string) => void,
    type = "text",
  ) => (
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
    <Panel title="Nueva empresa">
      <form onSubmit={handleSubmit} noValidate className="space-y-5">
        {input("company", "Nombre de la empresa", company, setCompany)}
        <fieldset className="space-y-4 rounded-md border border-line p-4">
          <legend className="px-1 text-sm font-medium">Primera persona de administración</legend>
          <div className="grid gap-4 sm:grid-cols-2">
            {input("name", "Nombre", name, setName)}
            {input("email", "Email", email, setEmail, "email")}
          </div>
          <Field
            id="password"
            label="Contraseña inicial"
            hint="Generada al azar. La puede cambiar desde Mi cuenta."
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
    </Panel>
  );
}

export default function CompaniesPage() {
  const me = useMe();
  const companies = useCompanies();
  const [adding, setAdding] = useState(false);

  if (!can(me.data, "manage_companies")) {
    return <EmptyState title="Esta pantalla es solo para el dueño de la plataforma" />;
  }

  return (
    <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <h1 className="text-2xl font-bold tracking-tight">Empresas</h1>
          <p className="mt-1 text-sm text-muted">
            Las empresas que usan Mavic. Cada una ve solo sus propios datos y administra su equipo.
          </p>
        </div>
        {!adding && (
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden className="size-4" /> Nueva empresa
          </Button>
        )}
      </div>
      <div className="mt-6 space-y-6">
        {adding && <NewCompanyForm onClose={() => setAdding(false)} />}
        {companies.isPending && <LoadingState />}
        {companies.isError && <QueryError error={companies.error} retry={companies.refetch} />}
        {companies.isSuccess && companies.data.length === 0 && (
          <EmptyState title="Todavía no hay empresas" />
        )}
        {companies.isSuccess && companies.data.length > 0 && (
          <ul className="divide-y divide-line rounded-lg border border-line bg-surface">
            {companies.data.map((company) => (
              <li key={company.id} className="flex flex-wrap items-baseline justify-between gap-2 px-5 py-4">
                <span className="font-medium">{company.name}</span>
                <span className="text-sm text-muted">
                  {company.is_active ? "Activa" : "Desactivada"} · desde el{" "}
                  {formatDate(company.created_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </>
  );
}
