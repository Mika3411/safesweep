import type { Metadata } from "next";
import { InfoGrid, PublicList, PublicPageShell, PublicSection } from "@/components/PublicPage";

export const metadata: Metadata = {
  title: "Mentions legales | SafeSweep",
  description: "Mentions legales du portail SafeSweep."
};

export default function LegalNoticePage() {
  return (
    <PublicPageShell
      eyebrow="Enterprise"
      title="Mentions legales"
      description="Informations d'identification et responsabilites relatives au portail SafeSweep. Les champs administratifs doivent etre completes avant publication."
      primaryAction={{ href: "/contact", label: "Demander une precision" }}
      secondaryAction={{ href: "/politique-confidentialite", label: "Confidentialite" }}
    >
      <PublicSection title="Editeur du service">
        <InfoGrid
          items={[
            {
              title: "Societe",
              body: "SafeSweep - denomination sociale, forme juridique et capital social a completer."
            },
            {
              title: "Siege social",
              body: "Adresse complete du siege social a renseigner avant mise en production."
            },
            {
              title: "Contact",
              body: "Adresse e-mail de contact, numero d'immatriculation et directeur de publication a completer."
            }
          ]}
        />
      </PublicSection>

      <PublicSection title="Hebergement et responsabilite">
        <PublicList
          items={[
            "L'hebergeur du service, son adresse et ses coordonnees doivent etre ajoutes dans cette section.",
            "Les informations du portail sont fournies pour faciliter la gestion des licences et peuvent evoluer.",
            "L'utilisateur reste responsable de la confidentialite de ses identifiants et de l'utilisation de son compte.",
            "Toute reproduction non autorisee des marques, interfaces ou contenus SafeSweep est interdite."
          ]}
        />
      </PublicSection>
    </PublicPageShell>
  );
}
