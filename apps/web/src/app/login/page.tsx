"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Alert, Field } from "@/components/ui";
import { api, saveSession, type SessionUser } from "@/lib/api";
import { useAction } from "@/lib/hooks";

type Token = { access_token: string; username: string; role: SessionUser["role"] };

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const { busy, error, run } = useAction();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const ok = await run(async () => {
      const token = await api<Token>("/auth/login", {
        method: "POST",
        body: { username, password },
        auth: false,
      });
      saveSession(token.access_token, { username: token.username, role: token.role });
    });
    if (ok) router.replace("/");
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink-950 px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl bg-white p-8 shadow-xl">
        <div>
          <h1>Neural Memory Core</h1>
          <p className="mt-1 text-sm text-slate-500">Inicia sesión para acceder a tu memoria.</p>
        </div>
        {error && <Alert>{error}</Alert>}
        <Field label="Usuario">
          <input className="input" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus />
        </Field>
        <Field label="Contraseña">
          <input className="input" type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required />
        </Field>
        <button className="btn-primary w-full" disabled={busy}>
          {busy ? "Entrando…" : "Entrar"}
        </button>
      </form>
    </div>
  );
}
