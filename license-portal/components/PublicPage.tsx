import { ArrowLeft, ArrowRight, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { ReactNode } from "react";
import { PublicFooter } from "@/components/PublicFooter";

type PublicAction = {
  href: string;
  label: string;
};

type PublicPageShellProps = {
  eyebrow: string;
  title: string;
  description: string;
  primaryAction?: PublicAction;
  secondaryAction?: PublicAction;
  children: ReactNode;
};

type PublicSectionProps = {
  title: string;
  intro?: string;
  children: ReactNode;
};

type InfoItem = {
  title: string;
  body: string;
};

export function PublicPageShell({
  eyebrow,
  title,
  description,
  primaryAction,
  secondaryAction,
  children
}: PublicPageShellProps) {
  return (
    <main className="auth-landing public-page">
      <PublicHeader />

      <section className="public-hero">
        <div>
          <Link className="public-back-link" href="/login">
            <ArrowLeft size={15} />
            Retour au portail
          </Link>
          <p className="topbar-kicker">{eyebrow}</p>
          <h1>{title}</h1>
          <p>{description}</p>
          {primaryAction || secondaryAction ? (
            <div className="public-hero-actions">
              {primaryAction ? (
                <Link className="primary-button hero-primary" href={primaryAction.href}>
                  {primaryAction.label}
                  <ArrowRight size={17} />
                </Link>
              ) : null}
              {secondaryAction ? (
                <Link className="secondary-button hero-secondary" href={secondaryAction.href}>
                  {secondaryAction.label}
                </Link>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>

      <div className="public-content">{children}</div>

      <PublicFooter />
    </main>
  );
}

export function PublicSection({ title, intro, children }: PublicSectionProps) {
  return (
    <section className="public-section-band">
      <div className="public-section">
        <div className="public-section-heading">
          <h2>{title}</h2>
          {intro ? <p>{intro}</p> : null}
        </div>
        {children}
      </div>
    </section>
  );
}

export function InfoGrid({ items }: { items: InfoItem[] }) {
  return (
    <div className="public-info-grid">
      {items.map((item) => (
        <article className="public-info-card" key={item.title}>
          <h3>{item.title}</h3>
          <p>{item.body}</p>
        </article>
      ))}
    </div>
  );
}

export function PublicList({ items }: { items: string[] }) {
  return (
    <ul className="public-list">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  );
}

function PublicHeader() {
  return (
    <header className="auth-header public-header">
      <Link className="auth-brand auth-header-brand" href="/demo" aria-label="SafeSweep License Portal">
        <span className="brand-mark">
          <ShieldCheck size={26} />
        </span>
        <span>
          <strong>SafeSweep</strong>
          <small>License Portal</small>
        </span>
      </Link>

      <nav className="auth-nav" aria-label="Navigation publique">
        <Link href="/support">Support</Link>
        <Link href="/centre-aide">Centre d'aide</Link>
        <Link href="/contact">Contact</Link>
        <Link className="auth-nav-cta" href="/login">
          Portail client
          <ArrowRight size={15} />
        </Link>
      </nav>
    </header>
  );
}
