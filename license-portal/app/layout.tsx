import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SafeSweep License Portal",
  description: "Espace client et console admin pour la gestion de licences logicielles."
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr">
      <body>{children}</body>
    </html>
  );
}
