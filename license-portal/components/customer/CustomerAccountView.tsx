"use client";

import { Save, User } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { apiFetch, CustomerUser, getCurrentCustomer } from "@/lib/customer-api";
import { ErrorState, LoadingState } from "@/components/customer/CustomerStates";
import { BillingPortalButton } from "@/components/customer/LicenseActions";

export function CustomerAccountView() {
  const [user, setUser] = useState<CustomerUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);

    try {
      setUser(await getCurrentCustomer());
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Chargement impossible.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const form = new FormData(event.currentTarget);
    const newPassword = String(form.get("newPassword") ?? "");
    const currentPassword = String(form.get("currentPassword") ?? "");
    const payload = {
      name: String(form.get("name") ?? ""),
      company: String(form.get("company") ?? "") || null,
      ...(newPassword ? { currentPassword, newPassword } : {})
    };

    setSaving(true);
    setMessage(null);
    setError(null);

    try {
      const data = await apiFetch<{ user: CustomerUser }>("/api/auth/me", {
        method: "PATCH",
        body: JSON.stringify(payload)
      });
      setUser(data.user);
      const currentPasswordInput = event.currentTarget.elements.namedItem("currentPassword");
      const newPasswordInput = event.currentTarget.elements.namedItem("newPassword");

      if (currentPasswordInput instanceof HTMLInputElement) {
        currentPasswordInput.value = "";
      }

      if (newPasswordInput instanceof HTMLInputElement) {
        newPasswordInput.value = "";
      }

      setMessage("Parametres enregistres.");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Enregistrement impossible.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <LoadingState label="Chargement du compte..." />;
  }

  if (error && !user) {
    return <ErrorState message={error} onRetry={load} />;
  }

  return (
    <main className="customer-page">
      <section className="main-panel account-panel">
        <div className="panel-heading">
          <h2>Parametres du compte</h2>
          <span className="account-avatar">
            <User size={18} />
          </span>
        </div>

        <form className="settings-form" onSubmit={save}>
          <label>
            Nom
            <input name="name" required minLength={2} defaultValue={user?.name ?? ""} />
          </label>
          <label>
            Societe
            <input name="company" defaultValue={user?.company ?? ""} />
          </label>
          <label>
            E-mail
            <input value={user?.email ?? ""} disabled />
          </label>

          <div className="form-divider" />

          <label>
            Mot de passe actuel
            <input name="currentPassword" type="password" autoComplete="current-password" />
          </label>
          <label>
            Nouveau mot de passe
            <input name="newPassword" type="password" minLength={10} autoComplete="new-password" />
          </label>

          <button className="primary-button" type="submit" disabled={saving}>
            <Save size={16} />
            {saving ? "Enregistrement..." : "Enregistrer"}
          </button>
        </form>

        {message ? <p className="form-message">{message}</p> : null}
        {error ? <p className="form-message error-message">{error}</p> : null}

        <section className="mini-section">
          <h3>Abonnements</h3>
          <p className="muted-copy">Ouvrez le portail securise Stripe pour modifier vos moyens de paiement et abonnements.</p>
          <div className="quick-actions">
            <BillingPortalButton />
          </div>
        </section>
      </section>
    </main>
  );
}
