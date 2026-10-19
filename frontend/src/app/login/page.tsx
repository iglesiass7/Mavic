"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState, type FormEvent } from "react";

import { Button, ErrorState } from "@/components/ui";
import { login, ME_QUERY_KEY, safeNextPath } from "@/features/auth";
import { errorMessage } from "@/lib/api";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const mutation = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: (me) => {
      // Ya sabemos quién es: se guarda para no volver a pedirlo.
      queryClient.setQueryData(ME_QUERY_KEY, me);
      router.replace(safeNextPath(searchParams.get("next")));
    },
  });

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <form onSubmit={handleSubmit} className="mt-8 space-y-5" noValidate>
      <div>
        <label htmlFor="email" className="text-sm font-medium">
          Email
        </label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="mt-1.5 w-full rounded-md border border-line bg-surface px-3 py-2.5 text-sm"
        />
      </div>
      <div>
        <label htmlFor="password" className="text-sm font-medium">
          Contraseña
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1.5 w-full rounded-md border border-line bg-surface px-3 py-2.5 text-sm"
        />
      </div>

      {mutation.isError && <ErrorState message={errorMessage(mutation.error)} />}

      <Button
        type="submit"
        loading={mutation.isPending}
        disabled={!email || !password}
        className="w-full py-2.5"
      >
        Entrar
      </Button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-screen md:grid-cols-[minmax(0,5fr)_minmax(0,4fr)]">
      <section className="flex items-center px-6 py-16 md:px-16">
        <div className="w-full max-w-sm">
          <p className="text-3xl font-bold tracking-tight">Mavic</p>
          <h1 className="mt-6 text-lg font-semibold">Iniciá sesión</h1>
          <p className="mt-1 text-sm text-muted">Con el email y la contraseña de tu empresa.</p>
          <Suspense>
            <LoginForm />
          </Suspense>
        </div>
      </section>

      {/* Lado decorativo: qué hace Mavic, con el lenguaje del producto. */}
      <aside className="hidden flex-col justify-end bg-ink px-14 py-16 text-white md:flex">
        <p className="max-w-sm text-2xl leading-snug font-light">
          El agente llama, verifica que habla con el titular y ofrece pagar{" "}
          <span className="font-semibold">dentro de las reglas que define tu empresa</span>.
        </p>
        <p className="mt-6 max-w-sm text-sm text-white/60">
          Los montos y las ofertas los calcula Mavic, no la inteligencia artificial.
        </p>
      </aside>
    </main>
  );
}
