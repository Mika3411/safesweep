import { ShieldCheck } from "lucide-react";
import Link from "next/link";

const footerGroups = [
  {
    title: "Produit",
    links: [
      { href: "/download", label: "Télécharger l'exe" },
      { href: "/demo", label: "Démo produit" },
      { href: "/login#benefits", label: "Fonctionnalités" }
    ]
  },
  {
    title: "Licence",
    links: [
      { href: "/licenses", label: "Mes licences" },
      { href: "/devices", label: "Appareils actifs" },
      { href: "/invoices", label: "Factures" }
    ]
  },
  {
    title: "Assistance",
    links: [
      { href: "/support", label: "Support" },
      { href: "/centre-aide", label: "Centre d'aide" },
      { href: "/contact", label: "Nous contacter" }
    ]
  },
  {
    title: "Entreprise",
    links: [
      { href: "/a-propos", label: "À propos" },
      { href: "/mentions-legales", label: "Mentions légales" },
      { href: "/politique-confidentialite", label: "Politique de confidentialité" }
    ]
  }
];

export function PublicFooter() {
  return (
    <footer className="auth-footer public-footer-shell" id="support">
      <div className="public-footer-layout">
        <Link className="auth-brand auth-footer-brand" href="/demo">
          <span className="brand-mark">
            <ShieldCheck size={26} />
          </span>
          <span>
            <strong>SafeSweep</strong>
            <small>Application Windows</small>
          </span>
        </Link>

        <p className="public-footer-copy">
          &copy; 2026 SafeSweep.
          <span>Tous droits réservés.</span>
        </p>

        <div className="public-footer-groups" aria-label="Liens secondaires">
          {footerGroups.map((group) => (
            <nav aria-label={group.title} className="public-footer-group" key={group.title}>
              <h2>{group.title}</h2>
              {group.links.map((link) => (
                <Link href={link.href} key={`${group.title}-${link.label}`}>
                  {link.label}
                </Link>
              ))}
            </nav>
          ))}
        </div>
      </div>
    </footer>
  );
}
