import type { Metadata } from "next";
import { InfoGrid, PublicList, PublicPageShell, PublicSection } from "@/components/PublicPage";

export const metadata: Metadata = {
  title: "Politique de confidentialite | SafeSweep",
  description: "Politique de confidentialite du portail SafeSweep."
};

export default function PrivacyPolicyPage() {
  return (
    <PublicPageShell
      eyebrow="Enterprise"
      title="Politique de confidentialite"
      description="Cette page presente les grandes categories de donnees traitees par le portail. Elle doit etre adaptee aux traitements reels avant publication."
      primaryAction={{ href: "/contact", label: "Exercer mes droits" }}
      secondaryAction={{ href: "/mentions-legales", label: "Mentions legales" }}
    >
      <PublicSection title="Donnees traitees">
        <InfoGrid
          items={[
            {
              title: "Compte client",
              body: "Nom, e-mail, societe, role et informations necessaires a l'authentification au portail."
            },
            {
              title: "Licences et appareils",
              body: "Cles de licence, produits, statuts, expirations, appareils rattaches et historiques d'activation."
            },
            {
              title: "Facturation",
              body: "References de paiement, factures, abonnements et informations utiles au suivi administratif."
            }
          ]}
        />
      </PublicSection>

      <PublicSection title="Utilisation et droits">
        <PublicList
          items={[
            "Les donnees sont utilisees pour fournir le portail, securiser l'acces et assurer le support client.",
            "Les acces sont limites aux utilisateurs autorises et aux equipes ayant besoin de traiter la demande.",
            "Les durees de conservation doivent etre definies selon les obligations applicables et les besoins du service.",
            "Les demandes d'acces, rectification, suppression ou opposition peuvent etre adressees via la page Contact."
          ]}
        />
      </PublicSection>
    </PublicPageShell>
  );
}
