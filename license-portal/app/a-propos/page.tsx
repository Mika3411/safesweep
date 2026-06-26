import type { Metadata } from "next";
import { InfoGrid, PublicList, PublicPageShell, PublicSection } from "@/components/PublicPage";

export const metadata: Metadata = {
  title: "A propos | SafeSweep",
  description: "Presentation de SafeSweep et du portail de gestion de licences."
};

export default function AboutPage() {
  return (
    <PublicPageShell
      eyebrow="Enterprise"
      title="A propos de SafeSweep"
      description="SafeSweep centralise la distribution logicielle, les licences, les appareils et la facturation dans un portail client securise."
      primaryAction={{ href: "/demo", label: "Voir la demo" }}
      secondaryAction={{ href: "/contact", label: "Parler a l'equipe" }}
    >
      <PublicSection
        title="Notre role"
        intro="Le portail accompagne les clients apres l'achat, quand la fiabilite operationnelle compte autant que la licence elle-meme."
      >
        <InfoGrid
          items={[
            {
              title: "Licences visibles",
              body: "Chaque client retrouve ses droits, dates d'expiration, appareils rattaches et actions disponibles au meme endroit."
            },
            {
              title: "Distribution maitrisee",
              body: "Les telechargements officiels et les informations de version restent accessibles depuis un espace controle."
            },
            {
              title: "Support contextualise",
              body: "Les demandes peuvent etre reliees a une licence, une facture ou un appareil pour limiter les allers-retours."
            }
          ]}
        />
      </PublicSection>

      <PublicSection title="Principes produit">
        <PublicList
          items={[
            "Proteger les acces sans rendre les workflows quotidiens pesants.",
            "Donner une lecture claire des droits logiciels et des renouvellements.",
            "Garder les donnees client utiles, limitees et comprehensibles.",
            "Faciliter les operations recurrentes des clients et des administrateurs."
          ]}
        />
      </PublicSection>
    </PublicPageShell>
  );
}
