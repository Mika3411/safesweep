"use client";

import {
  Bell,
  CreditCard,
  Download,
  FileText,
  Gauge,
  HelpCircle,
  KeyRound,
  LayoutDashboard,
  ListChecks,
  Monitor,
  Settings,
  ShieldCheck,
  User,
  Users
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { ReactNode } from "react";

type AppShellProps = {
  mode: "client" | "admin";
  title: string;
  userName: string;
  userRole: string;
  children: ReactNode;
};

const clientNav = [
  { href: "/dashboard", label: "Tableau de bord", icon: LayoutDashboard },
  { href: "/licenses", label: "Mes licences", icon: KeyRound },
  { href: "/devices", label: "Mes appareils", icon: Monitor },
  { href: "/download", label: "Telechargements", icon: Download },
  { href: "/invoices", label: "Factures", icon: FileText },
  { href: "/account", label: "Parametres", icon: Settings }
];

const adminNav = [
  { href: "/admin", label: "Tableau de bord", icon: Gauge },
  { href: "/admin#customers", label: "Clients", icon: Users },
  { href: "/admin#licenses", label: "Licences", icon: KeyRound },
  { href: "/admin#devices", label: "Appareils", icon: Monitor },
  { href: "/admin#payments", label: "Paiements", icon: CreditCard },
  { href: "/admin#invoices", label: "Factures", icon: FileText },
  { href: "/admin#validations", label: "Validations", icon: ListChecks },
  { href: "/admin#settings", label: "Parametres", icon: Settings }
];

export function AppShell({ mode, title, userName, userRole, children }: AppShellProps) {
  const pathname = usePathname();
  const router = useRouter();
  const navItems = mode === "admin" ? adminNav : clientNav;

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.push("/login");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href={mode === "admin" ? "/admin" : "/dashboard"}>
          <span className="brand-mark">
            <ShieldCheck size={24} />
          </span>
          <span>
            <strong>SafeSweep</strong>
            <small>License Portal</small>
          </span>
        </Link>

        <nav className="nav-list" aria-label="Navigation principale">
          {navItems.map((item) => {
            const Icon = item.icon;
            const selected = pathname === item.href.split("#")[0] || pathname.startsWith(item.href);

            return (
              <Link className={`nav-link ${selected ? "active" : ""}`} href={item.href} key={item.label}>
                <Icon size={16} />
                <span>{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <button className="sidebar-footer" type="button" onClick={logout}>
          <User size={16} />
          Deconnexion
        </button>
      </aside>

      <div className="workspace">
        <header className="topbar">
          <div>
            <p className="topbar-kicker">{mode === "admin" ? "Console admin" : "Portail client"}</p>
            <h1>{title}</h1>
          </div>
          <div className="topbar-actions">
            <button className="icon-button" type="button" aria-label="Aide">
              <HelpCircle size={16} />
            </button>
            <button className="icon-button notification-button" type="button" aria-label="Notifications">
              <Bell size={16} />
              <span>{mode === "admin" ? "6" : "3"}</span>
            </button>
            <div className="account-chip">
              <User size={16} />
              <span>
                <strong>{userName}</strong>
                <small>{userRole}</small>
              </span>
            </div>
          </div>
        </header>

        {children}
      </div>
    </div>
  );
}
