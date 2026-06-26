import type { Metadata } from "next";
import { InfoGrid, PublicList, PublicPageShell, PublicSection } from "@/components/PublicPage";

export const metadata: Metadata = {
  title: "Centre d'aide | SafeSweep",
  description: "Ressources d'aide SafeSweep pour gerer les licences, appareils, telechargements et factures."
};

export default function HelpCenterPage() {
  return (
    <PublicPageShell
      eyebrow="Assistance"
      title="Centre d'aide"
      description="Les reponses essentielles pour utiliser le portail de licences SafeSweep sans attendre une reponse du support."
      primaryAction={{ href: "/support", label: "Voir le support" }}
      secondaryAction={{ href: "/contact", label: "Nous contacter" }}
    >
      <PublicSection title="Rubriques principales">
        <InfoGrid
          items={[
            {
              title: "Activation de licence",
              body: "Retrouvez les etapes pour activer une licence, changer d'appareil ou verifier le statut d'une cle."
            },
            {
              title: "Gestion des appareils",
              body: "Comprenez les limites d'appareils, les suppressions autorisees et les controles de securite."
            },
            {
              title: "Telechargements",
              body: "Accedez aux versions officielles, aux mises a jour et aux recommandations d'installation."
            },
            {
              title: "Factures",
              body: "Consultez les factures, l'historique des paiements et les informations de renouvellement."
            },
            {
              title: "Compte client",
              body: "Mettez a jour vos informations, recuperez un mot de passe et securisez vos sessions."
            },
            {
              title: "Confidentialite",
              body: "Identifiez les donnees traitees par le portail et les options disponibles pour votre compte."
            }
          ]}
        />
      </PublicSection>

      <PublicSection title="Questions frequentes">
        <PublicList
          items={[
            "Une licence active peut etre consultee depuis la page Mes licences du portail client.",
            "Les appareils rattaches a une licence sont visibles dans Mes appareils ou dans le detail de la licence.",
            "Les factures sont disponibles depuis la page Factures apres connexion.",
            "Un lien de reinitialisation peut etre demande depuis la page Mot de passe oublie."
          ]}
        />
      </PublicSection>
    </PublicPageShell>
  );
}
