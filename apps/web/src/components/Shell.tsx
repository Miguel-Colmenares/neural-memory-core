"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { clearSession, getSessionUser, getToken, type SessionUser } from "@/lib/api";

const NAV = [
  { href: "/", label: "Panel" },
  { href: "/search", label: "Buscador" },
  { href: "/memories", label: "Recuerdos" },
  { href: "/projects", label: "Proyectos" },
  { href: "/documents", label: "Documentos" },
  { href: "/graph", label: "Relaciones" },
  { href: "/history", label: "Historial" },
  { href: "/settings", label: "Proveedores de IA" },
  { href: "/storage", label: "Almacenamiento" },
  { href: "/data", label: "Exportar e importar" },
];

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<SessionUser | null>(null);
  const [ready, setReady] = useState(false);
  const isLogin = pathname === "/login";

  useEffect(() => {
    if (isLogin) {
      setReady(true);
      return;
    }
    if (!getToken()) {
      router.replace("/login");
      return;
    }
    setUser(getSessionUser());
    setReady(true);
  }, [isLogin, pathname, router]);

  if (isLogin) return <>{children}</>;
  if (!ready) return null;

  const logout = () => {
    clearSession();
    router.replace("/login");
  };

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 flex-col bg-ink-950 text-slate-300 md:flex">
        <div className="px-5 py-5">
          <p className="text-sm font-semibold tracking-wide text-white">Neural Memory Core</p>
          <p className="text-xs text-slate-400">Segundo cerebro digital</p>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-lg px-3 py-2 text-sm transition ${
                  active ? "bg-ink-800 font-medium text-white" : "hover:bg-ink-900 hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="border-t border-ink-800 px-5 py-4 text-xs">
          <p className="text-slate-200">{user?.username ?? "—"}</p>
          <p className="text-slate-500">Rol: {user?.role ?? "—"}</p>
          <button onClick={logout} className="mt-2 text-slate-400 underline hover:text-white">
            Cerrar sesión
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-3 overflow-x-auto border-b border-slate-200 bg-white px-4 py-2 md:hidden">
          {NAV.map((item) => (
            <Link key={item.href} href={item.href} className="whitespace-nowrap text-sm text-slate-600">
              {item.label}
            </Link>
          ))}
          <button onClick={logout} className="whitespace-nowrap text-sm text-slate-400">
            Salir
          </button>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 md:px-8">{children}</main>
      </div>
    </div>
  );
}
