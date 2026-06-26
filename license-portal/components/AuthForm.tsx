"use client";

import {
  ArchiveRestore,
  ArrowRight,
  ExternalLink,
  Eye,
  EyeOff,
  FileSpreadsheet,
  FolderSearch,
  KeyRound,
  LockKeyhole,
  Mail,
  ShieldCheck,
  User
} from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";
import { PublicFooter } from "@/components/PublicFooter";

type AuthMode = "login" | "register" | "forgot" | "reset";

type AuthFormProps = {
  mode: AuthMode;
  token?: string;
};

const titles: Record<AuthMode, string> = {
  login: "Connexion",
  register: "Cr\u00e9ation de compte",
  forgot: "Mot de passe oubli\u00e9",
  reset: "Nouveau mot de passe"
};

const introCopy: Record<AuthMode, string> = {
  login: "Connectez-vous pour t\u00e9l\u00e9charger SafeSweep.exe, activer votre licence et r\u00e9cup\u00e9rer vos factures.",
  register: "Cr\u00e9ez votre espace pour obtenir l'ex\u00e9cutable Windows, activer votre licence et suivre vos appareils.",
  forgot: "Recevez un lien de r\u00e9initialisation s\u00e9curis\u00e9 pour retrouver l'acc\u00e8s \u00e0 vos t\u00e9l\u00e9chargements.",
  reset: "Choisissez un nouveau mot de passe robuste pour prot\u00e9ger votre compte SafeSweep."
};

export function AuthForm({ mode, token }: AuthFormProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [message, setMessage] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const visibleMessage =
    message ??
    (mode === "login" && searchParams.get("reset") === "done"
      ? "Votre mot de passe a \u00e9t\u00e9 mis \u00e0 jour. Vous pouvez vous connecter."
      : null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setMessage(null);

    const form = new FormData(event.currentTarget);
    const body = Object.fromEntries(form.entries());
    const endpoint =
      mode === "register"
        ? "/api/auth/register"
        : mode === "forgot"
          ? "/api/auth/forgot-password"
          : mode === "reset"
            ? "/api/auth/reset-password"
            : "/api/auth/login";

    if (token) {
      body.token = token;
    }

    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const data = (await response.json()) as { error?: string; redirectTo?: string; resetUrl?: string; ok?: boolean };

    setLoading(false);

    if (!response.ok) {
      setMessage(data.error ?? "Action impossible.");
      return;
    }

    if (mode === "forgot") {
      setMessage(
        data.resetUrl
          ? `Lien de test g\u00e9n\u00e9r\u00e9: ${data.resetUrl}`
          : "Si le compte existe, un e-mail de r\u00e9initialisation a \u00e9t\u00e9 envoy\u00e9."
      );
      return;
    }

    if (mode === "reset") {
      router.push("/login?reset=done");
      return;
    }

    router.push(searchParams.get("next") ?? data.redirectTo ?? "/dashboard");
  }

  return (
    <main className="auth-landing">
      <header className="auth-header">
        <Link className="auth-brand auth-header-brand" href="/demo" aria-label="SafeSweep application Windows">
          <span className="brand-mark">
            <ShieldCheck size={26} />
          </span>
          <span>
            <strong>SafeSweep</strong>
            <small>Application Windows</small>
          </span>
        </Link>

        <nav className="auth-nav" aria-label="Navigation principale">
          <Link className="auth-nav-cta" href="/download">
            T&eacute;l&eacute;charger SafeSweep.exe
            <ExternalLink size={15} />
          </Link>
        </nav>
      </header>

      <section className="auth-hero" id="product">
        <div className="auth-hero-content">
          <div className="auth-hero-copy">
            <h1>
              Nettoyez Windows.
              <span>Sans supprimer &agrave; l'aveugle.</span>
            </h1>
            <p>
              SafeSweep.exe rep&egrave;re les fichiers inutilis&eacute;s, doublons, gros dossiers et installateurs oubli&eacute;s,
              puis vous laisse valider chaque action avant la quarantaine ou la Corbeille.
            </p>
          </div>

          <ProductPreview />
        </div>

        <section className="auth-panel landing-auth-card" aria-labelledby="auth-title">
          <Link className="auth-brand auth-card-brand" href="/demo">
            <span className="brand-mark">
              <ShieldCheck size={26} />
            </span>
            <span>
              <strong>SafeSweep</strong>
              <small>Application Windows</small>
            </span>
          </Link>

          <div className="auth-copy">
            <h2 id="auth-title">{titles[mode]}</h2>
            <p>{introCopy[mode]}</p>
          </div>

          <form className="auth-form" id="auth-form" onSubmit={submit}>
            {mode === "register" ? (
              <>
                <label>
                  Nom
                  <span className="auth-input-shell">
                    <User size={17} />
                    <input name="name" required minLength={2} placeholder="Camille Martin" autoComplete="name" />
                  </span>
                </label>
                <label>
                  Soci&eacute;t&eacute;
                  <span className="auth-input-shell">
                    <ShieldCheck size={17} />
                    <input
                      name="company"
                      required
                      minLength={2}
                      placeholder="Acme Industries"
                      autoComplete="organization"
                    />
                  </span>
                </label>
              </>
            ) : null}

            {mode !== "reset" ? (
              <label>
                E-mail
                <span className="auth-input-shell">
                  <Mail size={17} />
                  <input name="email" type="email" required placeholder="client@safesweep.test" autoComplete="email" />
                </span>
              </label>
            ) : null}

            {mode !== "forgot" ? (
              <label>
                Mot de passe
                <span className="auth-input-shell password-shell">
                  <KeyRound size={17} />
                  <input
                    name="password"
                    type={showPassword ? "text" : "password"}
                    required
                    minLength={10}
                    placeholder={mode === "login" ? "Password123!" : "10 caract\u00e8res minimum"}
                    autoComplete={mode === "login" ? "current-password" : "new-password"}
                  />
                  <button
                    aria-label={showPassword ? "Masquer le mot de passe" : "Afficher le mot de passe"}
                    className="password-toggle"
                    type="button"
                    onClick={() => setShowPassword((value) => !value)}
                  >
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </span>
              </label>
            ) : null}

            <button className="primary-button auth-submit" type="submit" disabled={loading}>
              {loading ? "Traitement..." : titles[mode]}
              <ArrowRight size={17} />
            </button>
          </form>

          {visibleMessage ? <p className="form-message">{visibleMessage}</p> : null}

          <div className="auth-links">
            {mode !== "login" ? (
              <Link href="/login">Se connecter</Link>
            ) : (
              <Link href="/forgot-password">Mot de passe oubli&eacute;</Link>
            )}
            {mode !== "register" ? <Link href="/register">Cr&eacute;er un compte</Link> : null}
          </div>
        </section>
      </section>

      <section className="auth-benefits" id="benefits" aria-label="Avantages de SafeSweep.exe">
        <article>
          <span>
            <FolderSearch size={25} />
          </span>
          <div>
            <h2>Analyse locale intelligente</h2>
            <p>Scannez un dossier, vos t&eacute;l&eacute;chargements ou un profil pr&eacute;rempli sans envoyer vos fichiers ailleurs.</p>
          </div>
        </article>
        <article>
          <span>
            <ArchiveRestore size={25} />
          </span>
          <div>
            <h2>Quarantaine restaurable</h2>
            <p>Testez avant suppression avec un historique local, restauration possible et d&eacute;lai configurable.</p>
          </div>
        </article>
        <article>
          <span>
            <FileSpreadsheet size={25} />
          </span>
          <div>
            <h2>Rapports et mode CLI</h2>
            <p>Exportez CSV/HTML et automatisez les scans avec SafeSweep-CLI.exe pour les usages avanc&eacute;s.</p>
          </div>
        </article>
      </section>

      <section className="auth-security" id="security">
        <LockKeyhole size={24} />
        <strong>Contr&ocirc;le avant action</strong>
        <p>SafeSweep ne supprime rien sans confirmation : simulation, risque, quarantaine et Corbeille restent sous votre main.</p>
      </section>

      <PublicFooter />
    </main>
  );
}

function ProductPreview() {
  return (
    <figure className="product-preview real-product-preview" aria-label="Capture reelle de SafeSweep.exe">
      <img
        alt="Fenetre reelle de SafeSweep.exe affichant les resultats d'analyse, risques, actions et chemins des elements detectes"
        src="/product/safesweep-real-results.png"
      />
      <figcaption>Capture r&eacute;elle apr&egrave;s analyse : d&eacute;sinstallateurs d&eacute;tect&eacute;s, risques, actions et chemins.</figcaption>
    </figure>
  );
}
