"use client";

/**
 * Configuración > Organización, con el diseño de Rynx ("Gestión de equipo"):
 * la tabla de usuarios de la empresa y "Invitar miembro".
 *
 *   Usuario | Email | Rol (se cambia ahí) | Último ingreso | Estado (interruptor)
 *
 * Desactivar a alguien cierra sus sesiones en el momento. Nadie puede cambiarse
 * el rol ni desactivarse a sí mismo (perdería el acceso en el acto).
 */
import { Plus, RefreshCw } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useMe } from "@/features/auth";
import {
  checkNewPassword,
  generatePassword,
  looksLikeEmail,
  matchesUser,
  sortUsers,
  useCreateUser,
  useUpdateUser,
  useUsers,
  type UserSort,
} from "@/features/users";
import { errorMessage } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { ROLE_HINT, ROLE_LABEL } from "@/lib/labels";
import type { CompanyRole, User } from "@/lib/types";

import { CopyButton } from "../CopyButton";
import { DataTable, type Column } from "../DataTable";
import { Sheet } from "../Sheet";
import { Button, ErrorState, Field, QueryError, Toggle, cx, inputClass } from "../ui";

const COMPANY_ROLES: CompanyRole[] = ["operator", "supervisor", "admin"];

// ---------------------------------------------------------------- alta

function NewUserForm({ onClose }: { onClose: () => void }) {
  const create = useCreateUser();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<CompanyRole>("operator");
  const [password, setPassword] = useState(() => generatePassword());
  const [errors, setErrors] = useState<Record<string, string>>({});

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const next: Record<string, string> = {};
    if (!name.trim()) next.name = "Escribí el nombre.";
    if (!looksLikeEmail(email)) next.email = "Escribí un email válido.";
    const passwordProblem = checkNewPassword(password);
    if (passwordProblem) next.password = passwordProblem;
    setErrors(next);
    if (Object.keys(next).length === 0) {
      create.mutate({ name: name.trim(), email: email.trim(), password, role });
    }
  }

  if (create.isSuccess) {
    return (
      <div role="status" className="space-y-4 text-sm">
        <h3 className="text-lg font-bold text-rynx-primary">Usuario creado</h3>
        <div className="space-y-4">
          <p>
            <span className="font-semibold">{create.data.name}</span> ya puede entrar a Mavic con estos datos.
            Pasáselos por un medio privado: la contraseña no se vuelve a mostrar. Después la puede cambiar
            desde <span className="font-medium">Configuración › Mi cuenta</span>.
          </p>
          <dl className="grid gap-3 rounded-xl border border-line bg-paper p-4 sm:grid-cols-[auto_1fr_auto] sm:items-center">
            <dt className="text-muted">Email</dt>
            <dd className="font-medium break-all">{create.data.email}</dd>
            <dd />
            <dt className="text-muted">Contraseña</dt>
            <dd>
              <code className="text-base">{password}</code>
            </dd>
            <dd>
              <CopyButton text={`Email: ${create.data.email}\nContraseña: ${password}`} />
            </dd>
          </dl>
          <Button variant="secondary" onClick={onClose}>
            Listo
          </Button>
        </div>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-5">
      <div className="space-y-5">
        <Field id="new-name" label="Nombre" error={errors.name}>
          {(aria) => (
            <input
              {...aria}
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoComplete="off"
              className={inputClass(Boolean(errors.name))}
            />
          )}
        </Field>
        <Field id="new-email" label="Email" hint="Con este email va a entrar." error={errors.email}>
          {(aria) => (
            <input
              {...aria}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="off"
              className={inputClass(Boolean(errors.email))}
            />
          )}
        </Field>
      </div>

      <fieldset>
        <legend className="text-xs font-bold text-ink">Rol</legend>
        <div className="mt-2 grid gap-2">
          {COMPANY_ROLES.map((value) => (
            <label
              key={value}
              className={cx(
                "flex cursor-pointer gap-3 rounded-xl border p-3 text-sm",
                role === value ? "border-rynx-primary bg-rynx-soft/40" : "border-line",
              )}
            >
              <input
                type="radio"
                name="role"
                value={value}
                checked={role === value}
                onChange={() => setRole(value)}
                className="mt-0.5 accent-rynx-primary"
              />
              <span>
                <span className="font-medium">{ROLE_LABEL[value]}</span>
                <span className="block text-xs text-muted">{ROLE_HINT[value]}</span>
              </span>
            </label>
          ))}
        </div>
      </fieldset>

      <Field
        id="new-password"
        label="Contraseña inicial"
        hint="Generada al azar. Podés escribir otra (mínimo 10 caracteres)."
        error={errors.password}
      >
        {(aria) => (
          <div className="flex gap-2">
            <input
              {...aria}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="new-password"
              spellCheck={false}
              className={inputClass(Boolean(errors.password), "font-mono")}
            />
            <Button type="button" variant="secondary" onClick={() => setPassword(generatePassword())}>
              <RefreshCw aria-hidden className="size-4" /> Otra
            </Button>
          </div>
        )}
      </Field>

      {create.isError && <ErrorState message={errorMessage(create.error)} />}

      <div className="flex flex-wrap gap-3">
        <Button type="submit" loading={create.isPending}>
          Crear usuario
        </Button>
        <Button type="button" variant="ghost" onClick={onClose}>
          Cancelar
        </Button>
      </div>
    </form>
  );
}

// ---------------------------------------------------------------- controles de cada fila

function RoleControl({ user, isMe }: { user: User; isMe: boolean }) {
  const update = useUpdateUser();
  if (user.role === "platform_admin" || isMe) return <>{ROLE_LABEL[user.role]}</>;
  return (
    <div>
      <select
        aria-label={`Rol de ${user.name}`}
        value={user.role}
        disabled={update.isPending}
        onChange={(e) => update.mutate({ id: user.id, role: e.target.value as CompanyRole })}
        className={inputClass(false, "w-auto py-1.5 text-sm")}
      >
        {COMPANY_ROLES.map((value) => (
          <option key={value} value={value}>
            {ROLE_LABEL[value]}
          </option>
        ))}
      </select>
      {update.isError && (
        <p role="alert" className="mt-1 max-w-56 text-xs text-red-700">
          {errorMessage(update.error)}
        </p>
      )}
    </div>
  );
}

function StatusControl({ user, isMe }: { user: User; isMe: boolean }) {
  const update = useUpdateUser();
  return (
    <div>
      <div className="flex items-center gap-3">
        <span className={cx("w-14 text-xs font-bold", user.is_active ? "text-rynx-primary" : "text-muted")}>
          {user.is_active ? "Activo" : "Inactivo"}
        </span>
        {/* Desactivarse a uno mismo cerraría la sesión en el acto: no se ofrece. */}
        {!isMe && (
          <Toggle
            checked={user.is_active}
            disabled={update.isPending}
            label={user.is_active ? `Desactivar a ${user.name}` : `Reactivar a ${user.name}`}
            onChange={(active) => update.mutate({ id: user.id, is_active: active })}
          />
        )}
      </div>
      {update.isError && (
        <p role="alert" className="mt-1 max-w-56 text-xs text-red-700">
          {errorMessage(update.error)}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- la tabla

export function TeamSettings() {
  const me = useMe();
  const users = useUsers();
  const [inviting, setInviting] = useState(false);
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<UserSort>("status");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const matching = sortUsers(
    (users.data ?? []).filter((user) => matchesUser(user, search)),
    sort,
  );
  const rows = matching.slice((page - 1) * pageSize, page * pageSize);
  const myId = me.data?.user.id;

  const columns: Column<User>[] = [
    {
      key: "name",
      header: "Usuario",
      sortKey: "name",
      cell: (user) => (
        <span className={cx("font-bold", !user.is_active && "text-muted")}>
          {user.name}
          {user.id === myId && <span className="ml-2 text-xs font-normal text-muted">(vos)</span>}
        </span>
      ),
    },
    {
      key: "email",
      header: "Email",
      sortKey: "email",
      className: "whitespace-nowrap",
      cell: (user) => user.email,
    },
    {
      key: "role",
      header: "Rol",
      sortKey: "role",
      cell: (user) => <RoleControl user={user} isMe={user.id === myId} />,
    },
    {
      key: "last_login",
      header: "Último ingreso",
      className: "whitespace-nowrap text-muted",
      cell: (user) => (user.last_login_at ? formatDateTime(user.last_login_at) : "Nunca entró"),
    },
    {
      key: "status",
      header: "Estado",
      sortKey: "status",
      cell: (user) => <StatusControl user={user} isMe={user.id === myId} />,
    },
  ];

  return (
    <section aria-labelledby="team-title">
      <div className="mb-5 flex flex-wrap items-start justify-between gap-4">
        <div className="max-w-2xl">
          <h2 id="team-title" className="text-xl font-bold text-ink">
            Gestión de equipo
          </h2>
          <p className="mt-1 text-sm text-muted">
            Quién puede entrar a Mavic
            {me.data?.company ? ` en ${me.data.company.name}` : ""} y qué puede hacer. Al desactivar a alguien
            se cierran sus sesiones en el momento.
          </p>
        </div>
        <Button onClick={() => setInviting(true)} className="px-8 py-3">
          <Plus aria-hidden className="size-4" /> Invitar miembro
        </Button>
      </div>

      {users.isError ? (
        <QueryError error={users.error} retry={users.refetch} />
      ) : (
        <DataTable
          caption="Usuarios de la empresa"
          columns={columns}
          rows={rows}
          rowKey={(user) => user.id}
          loading={users.isPending}
          search={{
            value: search,
            onChange: (value) => {
              setSearch(value);
              setPage(1);
            },
            placeholder: "Buscar por nombre o email...",
          }}
          sort={sort}
          onSort={(next) => setSort(next as UserSort)}
          page={page}
          pageSize={pageSize}
          total={matching.length}
          onPage={setPage}
          onPageSize={(size) => {
            setPageSize(size);
            setPage(1);
          }}
          empty={search.trim() ? "Nadie coincide con la búsqueda." : "Todavía no hay usuarios."}
        />
      )}

      <Sheet title="Invitar miembro" open={inviting} onClose={() => setInviting(false)}>
        {/* key: cada vez que se abre, el formulario arranca de cero (otra contraseña). */}
        {inviting && <NewUserForm key={String(inviting)} onClose={() => setInviting(false)} />}
      </Sheet>
    </section>
  );
}
