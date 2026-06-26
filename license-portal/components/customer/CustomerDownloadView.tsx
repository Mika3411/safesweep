"use client";

import { Download, FileCheck2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { BuyLicenseButton } from "@/components/customer/LicenseActions";

export function CustomerDownloadView() {
  return (
    <main className="customer-page">
      <section className="download-panel">
        <div>
          <ShieldCheck size={34} />
          <h2>SafeSweep Endpoint</h2>
          <p>Installez la derniere version du logiciel, puis activez-la avec votre cle de licence.</p>
        </div>
        <a className="primary-button download-main-button" href="/api/downloads/software">
          <Download size={18} />
          Telecharger le logiciel
        </a>
      </section>

      <section className="customer-grid">
        <article className="main-panel">
          <h2>Avant l'installation</h2>
          <div className="check-list">
            <span>
              <FileCheck2 size={16} />
              Verifiez que votre licence est active.
            </span>
            <span>
              <FileCheck2 size={16} />
              Gardez une activation disponible pour ce poste.
            </span>
            <span>
              <FileCheck2 size={16} />
              Connectez-vous au meme compte client en cas de support.
            </span>
          </div>
        </article>
        <aside className="detail-panel">
          <h2>Liens utiles</h2>
          <div className="quick-actions">
            <BuyLicenseButton compact />
            <Link className="secondary-button" href="/licenses">
              Mes licences
            </Link>
            <Link className="secondary-button" href="/devices">
              Appareils actives
            </Link>
            <Link className="secondary-button" href="/account">
              Parametres du compte
            </Link>
          </div>
        </aside>
      </section>
    </main>
  );
}
