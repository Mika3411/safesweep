import type { Metadata } from "next";
import { InfoGrid, PublicList, PublicPageShell, PublicSection } from "@/components/PublicPage";

export const metadata: Metadata = {
  title: "Support | SafeSweep",
  description: "Acces au support SafeSweep pour les licences, appareils, telechargements et factures."
};

export default function SupportPage() {
  return (
    <PublicPageShell
      eyebrow="Assistance"
      title="Support SafeSweep"
      description="Une page claire pour orienter les demandes liees aux licences, aux appareils, aux telechargements et a la facturation."
      primaryAction={{ href: "/contact", label: "Contacter le support" }}
      secondaryAction={{ href: "/centre-aide", label: "Consulter le centre d'aide" }}
    >
      <PublicSection
        title="Canaux de support"
        intro="Choisissez le bon point d'entree selon le niveau d'urgence et le sujet de votre demande."
      >
        <InfoGrid
          items={[
            {
              title: "Support client",
              body: "Pour les licences actives, les activations refusees, les limites d'appareils et les questions de compte."
            },
            {
              title: "Facturation",
              body: "Pour les factures, moyens de paiement, renouvellements, remboursements et changements d'adresse."
            },
            {
              title: "Assistance technique",
              body: "Pour l'installation, les erreurs de telechargement, les appareils bloques ou les diagnostics d'activation."
            }
          ]}
        />
      </PublicSection>

      <PublicSection title="Avant d'ouvrir un ticket">
        <PublicList
          items={[
            "Verifiez que votre e-mail de compte correspond bien a la licence concernee.",
            "Notez la cle de licence ou l'identifiant de commande si vous l'avez sous la main.",
            "Ajoutez le nom de l'appareil, le systeme utilise et le message d'erreur complet.",
            "Indiquez si la demande bloque totalement votre activite ou concerne une question non urgente."
          ]}
        />
      </PublicSection>
    </PublicPageShell>
  );
}
