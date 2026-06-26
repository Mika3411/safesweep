import type { Metadata } from "next";
import { InfoGrid, PublicList, PublicPageShell, PublicSection } from "@/components/PublicPage";

export const metadata: Metadata = {
  title: "Nous contacter | SafeSweep",
  description: "Contacter SafeSweep pour le support, la facturation ou une demande entreprise."
};

export default function ContactPage() {
  return (
    <PublicPageShell
      eyebrow="Assistance"
      title="Nous contacter"
      description="Indiquez le sujet, le compte concerne et les elements de contexte afin que l'equipe puisse traiter votre demande rapidement."
      primaryAction={{ href: "mailto:support@safesweep.fr", label: "Envoyer un e-mail" }}
      secondaryAction={{ href: "/support", label: "Preparer ma demande" }}
    >
      <PublicSection title="Adresses utiles">
        <InfoGrid
          items={[
            {
              title: "Support",
              body: "support@safesweep.fr - licences, activations, appareils et acces au portail client."
            },
            {
              title: "Facturation",
              body: "billing@safesweep.fr - factures, paiements, renouvellements et informations administratives."
            },
            {
              title: "Entreprise",
              body: "enterprise@safesweep.fr - demandes commerciales, deploiements equipes et besoins specifiques."
            }
          ]}
        />
      </PublicSection>

      <PublicSection title="Informations a joindre">
        <PublicList
          items={[
            "Votre nom, votre societe et l'e-mail du compte SafeSweep concerne.",
            "La reference de licence, de commande ou de facture si elle est disponible.",
            "Une description courte du probleme, avec le message d'erreur complet si necessaire.",
            "Le niveau d'urgence et l'impact concret sur votre activite."
          ]}
        />
      </PublicSection>
    </PublicPageShell>
  );
}
