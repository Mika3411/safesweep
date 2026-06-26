# SafeSweep License Portal

Application web complete d'espace client et console admin pour la gestion de licences logicielles.

Stack retenue:

- Frontend: Next.js App Router + React + CSS natif
- Backend: API Routes Next.js sur Node.js
- Base de donnees: PostgreSQL via Prisma
- Paiement: Stripe Billing, Checkout Sessions et Customer Portal
- Authentification: mot de passe hashe avec bcrypt, session JWT signee en cookie `httpOnly`

## 1. Architecture du projet

```text
license-portal/
  app/                       Pages Next.js et routes API
    api/auth/                inscription, connexion, reset password
    api/licenses/            espace client et validation logicielle
    api/admin/               console admin
    api/billing/             Stripe Checkout et Billing Portal
    api/stripe/webhook/      synchronisation Stripe
    dashboard/               tableau de bord client
    admin/                   console admin
    demo/                    demo UI sans base de donnees
  components/                shell, formulaires, dashboard client/admin
  lib/                       auth, session, licence, Stripe, Prisma, formatters
  prisma/schema.prisma       schema PostgreSQL
  prisma/seed.ts             donnees de test
  tests/                     tests essentiels Vitest
```

## 2. Schema de base de donnees

Modeles principaux:

- `User`: client ou admin, email unique, hash du mot de passe, `stripeCustomerId`, `sessionVersion` pour invalider les JWT existants apres rotation de mot de passe.
- `License`: licence rattachee a un utilisateur, `publicId`, `keyHash`, `keyPrefix`, produit, statut, expiration, limite d'appareils, sieges.
- `Device`: appareil active sur une licence, fingerprint hashe, activation/desactivation, dernier contact.
- `LicenseValidation`: historique complet des validations, refus, activations et limites atteintes.
- `Invoice`: factures locales synchronisees avec Stripe.
- `Payment`: paiements recents et sessions Stripe.
- `AuditLog`: actions admin et actions sensibles.

Les cles de licence brutes ne sont pas stockees. Le serveur stocke un HMAC SHA-256 (`keyHash`) et seulement un prefixe d'affichage.
Apres un paiement Stripe reussi, une cle est temporairement conservee sous forme chiffree (`encryptedLicenseKey`) pour une revelation unique au client, puis supprimee des que le client l'affiche.

## 3. Routes API

Auth:

- `POST /api/auth/register`
- `POST /api/auth/login`
- `POST /api/auth/logout`
- `GET /api/auth/me`
- `POST /api/auth/forgot-password`
- `POST /api/auth/reset-password`

Client:

- `GET /api/licenses`
- `GET /api/licenses/:id`
- `DELETE /api/licenses/:id/devices/:deviceId`
- `GET /api/invoices`
- `GET /api/downloads/software`
- `POST /api/billing/checkout`
- `POST /api/billing/portal`

Validation logicielle securisee:

- `POST /api/license/validate`
- `POST /api/license/activate`
- `POST /api/license/deactivate`
- Endpoint public limite pour client desktop: ne pas embarquer `LICENSE_API_SECRET` dans SafeSweep.exe.
- Protections: HTTPS, validation par cle de licence, hash `deviceId`, rate limiting IP/licence/appareil, limites d'appareils et logs `LicenseValidation`.
- Header optionnel serveur-a-serveur: `x-safesweep-client-secret: <LICENSE_API_SECRET>`
- Body:

```json
{
  "licenseKey": "ACME-25P7-Q9RK-LM2T",
  "deviceId": "machine-guid-or-hardware-fingerprint",
  "deviceName": "ACME-WS-01",
  "platform": "Windows 11"
}
```

L'ancien endpoint `POST /api/licenses/validate` est desactive et repond `410 Gone`.

Admin:

- `GET /api/admin/customers`
- `GET /api/admin/licenses`
- `POST /api/admin/licenses`
- `PATCH /api/admin/licenses/:id/status`
- `PATCH /api/admin/licenses/:id/expiration`
- `GET /api/admin/licenses/:id/devices`
- `GET /api/admin/validations`
- `GET /api/admin/payments`

Stripe:

- `POST /api/billing/checkout` pour acheter ou renouveler une licence via Checkout.
- `POST /api/billing/portal` pour ouvrir le portail Stripe Customer Portal.
- `POST /api/stripe/webhook` pour synchroniser paiements, abonnements, factures et licences.

## 4. Code backend

Points d'entree principaux:

- Auth: `app/api/auth/*`
- Licences client: `app/api/licenses/*`
- Validation licence desktop: `app/api/license/*/route.ts`
- Admin: `app/api/admin/*`
- Stripe: `app/api/billing/*` et `app/api/stripe/webhook/route.ts`
- Logique de licence: `lib/license.ts`
- Sessions securisees: `lib/session.ts` et `lib/auth.ts`
- Rate limiting: `lib/rate-limit.ts`

## 5. Code frontend

Pages principales:

- `/login`, `/register`, `/forgot-password`, `/reset-password/:token`
- `/dashboard`
- `/admin`
- `/demo`

Composants:

- `components/ClientPortal.tsx`
- `components/AdminPortal.tsx`
- `components/AuthForm.tsx`
- `components/AppShell.tsx`
- `components/StatusBadge.tsx`

## 6. Systeme admin

La console admin permet de:

- voir tous les clients;
- creer une licence manuellement;
- recuperer la cle brute une seule fois lors de la creation;
- suspendre, revoquer ou reactiver une licence;
- modifier la date d'expiration;
- consulter les appareils lies;
- consulter l'historique de validation;
- consulter les paiements.

## 7. Tests essentiels

Tests inclus:

- format de cle `XXXX-XXXX-XXXX-XXXX`;
- normalisation et masquage de cle;
- hashing de cle et fingerprint;
- refus licence expiree/suspendue/revoquee;
- rate limiting Redis/Upstash avec fallback local limite au developpement.

Commandes:

```bash
npm run typecheck
npm test
npm run build
```

## 8. Instructions de deploiement

Guide Render detaille: `docs/deploiement-render.md`.

Local:

```bash
cd license-portal
cp .env.example .env
docker compose up -d
npm install
npm run db:push
npm run db:seed
npm run dev
```

Rate limiting:

`lib/rate-limit.ts` utilise Redis via l'API REST Upstash pour partager les compteurs entre instances. Les routes sensibles suivantes sont protegees:

- login et inscription;
- demande et execution de reset password;
- checkout Stripe;
- validation, activation et desactivation de licence.

Variables:

- `UPSTASH_REDIS_REST_URL`: URL REST Upstash Redis.
- `UPSTASH_REDIS_REST_TOKEN`: token REST Upstash Redis.

En production et en test, si Redis/Upstash est absent ou indisponible, le rate limiter echoue ferme et les endpoints proteges repondent `503`. En `NODE_ENV=development` uniquement, un fallback memoire local est utilise pour faciliter le developpement; il n'est pas partage entre processus et ne doit pas etre utilise en production.

Backups PostgreSQL:

```powershell
npm run backup:db
npm run restore:db
```

`backup:db` cree un dump PostgreSQL custom dans `backups/`, avec un nom du type `safesweep_portal-2026-06-25_21-45-00.dump`.
`restore:db` restaure le dump le plus recent dans une base de test separee nommee par defaut `safesweep_portal_restore_test`; cette base est supprimee puis recreee a chaque test de restauration.

Les scripts lisent `DATABASE_URL` depuis l'environnement ou depuis `.env`. Ils utilisent les outils PostgreSQL locaux (`pg_dump`, `pg_restore`, `dropdb`, `createdb`) s'ils sont disponibles, sinon ils utilisent le service Docker Compose `postgres`. Pour forcer Docker Compose:

```powershell
npm run backup:db -- -UseDocker
npm run restore:db -- -UseDocker
```

Restaurer un dump specifique ou choisir une base de test:

```powershell
npm run restore:db -- -DumpFile .\backups\safesweep_portal-2026-06-25_21-45-00.dump
npm run restore:db -- -TargetDatabase safesweep_portal_restore_test
```

La restauration dans la base source est bloquee par securite sans `-Force`. Le dossier `backups/` et les fichiers `*.dump` sont ignores par Git.

Backups PostgreSQL production:

```powershell
$env:BACKUP_ENCRYPTION_KEY="une-cle-longue-stockee-dans-votre-gestionnaire-de-secrets"
npm run backup:db:prod
```

`backup:db:prod` genere un dump PostgreSQL custom compresse (`pg_dump --format=custom --compress 9`), chiffre le fichier avec AES-256, supprime le dump clair temporaire et conserve uniquement des fichiers `*.dump.enc` sous `backups/production/`.

Variables disponibles:

- `BACKUP_ENCRYPTION_KEY`: secret de chiffrement, 32 caracteres minimum, obligatoire.
- `BACKUP_COMPRESSION_LEVEL`: niveau `pg_dump --compress`, `9` par defaut.
- `BACKUP_UPLOAD_ENABLED`: `true` pour activer l'upload S3.
- `BACKUP_S3_BUCKET`: bucket S3 ou compatible.
- `BACKUP_S3_PREFIX`: prefixe objet, par exemple `license-portal/postgresql`.
- `BACKUP_S3_ENDPOINT_URL`: endpoint S3 compatible optionnel, par exemple MinIO, Scaleway ou Backblaze.
- `AWS_REGION`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: credentials lus par l'AWS CLI, sauf si vous utilisez un role IAM ou un profil machine.

Retention appliquee localement, et aussi sur S3 quand l'upload est active:

- `daily/`: 7 derniers backups quotidiens.
- `weekly/`: 4 derniers backups hebdomadaires, crees le lundi.
- `monthly/`: 12 derniers backups mensuels, crees le premier jour du mois.

Pour forcer une copie hebdomadaire ou mensuelle lors d'un test:

```powershell
npm run backup:db:prod -- -ForceWeekly
npm run backup:db:prod -- -ForceMonthly
```

Upload S3 ou compatible:

```powershell
$env:BACKUP_UPLOAD_ENABLED="true"
$env:BACKUP_S3_BUCKET="safesweep-db-backups"
$env:BACKUP_S3_PREFIX="license-portal/postgresql"
$env:AWS_REGION="eu-west-3"
$env:AWS_ACCESS_KEY_ID="..."
$env:AWS_SECRET_ACCESS_KEY="..."
npm run backup:db:prod
```

Pour un stockage compatible S3, ajoutez `BACKUP_S3_ENDPOINT_URL`, par exemple `https://s3.fr-par.scw.cloud`. Le script utilise l'AWS CLI et echoue si l'upload est active mais que `aws` n'est pas disponible.

Restauration d'un backup production:

```powershell
# 1. Recuperer le fichier depuis S3 si necessaire.
aws s3 cp s3://safesweep-db-backups/license-portal/postgresql/daily/safesweep_portal-2026-06-25_21-45-00.dump.enc .\backups\restore\

# 2. Dechiffrer le backup en dump PostgreSQL temporaire.
$env:BACKUP_ENCRYPTION_KEY="la-meme-cle-que-lors-du-backup"
npm run decrypt:db:backup -- -InputFile .\backups\restore\safesweep_portal-2026-06-25_21-45-00.dump.enc

# 3. Restaurer dans une base de test.
npm run restore:db -- -DumpFile .\backups\restore\safesweep_portal-2026-06-25_21-45-00.dump -TargetDatabase safesweep_portal_restore_test
```

Pour restaurer volontairement dans une base existante sensible, passez `-Force` a `restore:db` apres verification manuelle. Supprimez le dump clair `*.dump` apres restauration. `backups/`, `*.dump`, `*.dump.enc`, `*.sql.gz` et `*.backup*` sont ignores par Git au niveau du projet.

Comptes seed:

- Client: `client@safesweep.test` / `Password123!`
- Admin: `admin@safesweep.test` / `Password123!`
- Cle de test: `ACME-25P7-Q9RK-LM2T`

Stripe:

1. Creer les produits et prix recurrents dans Stripe Billing.
2. Placer les prix dans `STRIPE_ENDPOINT_PRICE_ID`, `STRIPE_SERVER_PRICE_ID`, `STRIPE_MOBILE_PRICE_ID`. `STRIPE_PRICE_ID` reste un fallback si vous utilisez un seul prix.
3. Lancer le forwarding webhook local:

```bash
npm run stripe:webhook
```

4. Copier le secret `whsec_...` dans `STRIPE_WEBHOOK_SECRET`.
5. Activer au minimum ces evenements webhook:
   - `checkout.session.completed`
   - `invoice.payment_succeeded`
   - `invoice.paid`
   - `payment_intent.succeeded`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`

Apres une facture d'abonnement payee, le webhook genere une licence, stocke uniquement son hash, la rattache au client et synchronise son statut avec l'abonnement Stripe. Les retries Stripe restent idempotents via `subscriptionId`, `stripeInvoiceId`, `stripePaymentIntentId` et `stripeCheckoutSessionId`.
La cle brute n'est jamais stockee en clair: elle est chiffree pour une seule revelation dans l'espace client, puis le champ chiffre est efface et l'action est journalisee.
Un e-mail transactionnel est aussi envoye au client avec la cle brute au moment exact de la creation de licence Stripe. Cet envoi utilise la cle uniquement en memoire; une erreur Resend est journalisee mais ne casse pas le webhook Stripe.

Production:

Checklist production:

- Provisionner PostgreSQL hors du poste de developpement, avec stockage persistant, sauvegardes et supervision disque.
- Configurer les variables obligatoires: `DATABASE_URL`, `AUTH_SECRET`, `LICENSE_HASH_SECRET`, `LICENSE_KEY_ENCRYPTION_SECRET`, `APP_URL`, `STRIPE_SECRET_KEY` et `STRIPE_WEBHOOK_SECRET`.
- `LICENSE_API_SECRET` est optionnel et reserve a des clients serveur-a-serveur. Ne jamais le distribuer dans l'executable desktop.
- Utiliser uniquement des secrets longs, aleatoires et stockes dans un gestionnaire de secrets. Ne pas reutiliser les valeurs de `.env.example`, les secrets `dev-only`, `change-me`, `sk_test_...`, `localhost`, ni les comptes seed.
- Definir `APP_URL` avec l'origin public HTTPS exact, par exemple `https://licenses.votre-domaine.com`.
- Configurer `UPSTASH_REDIS_REST_URL` et `UPSTASH_REDIS_REST_TOKEN` pour le rate limiting distribue.
- Configurer `STRIPE_PRICE_ID` ou les prix par produit `STRIPE_ENDPOINT_PRICE_ID`, `STRIPE_SERVER_PRICE_ID`, `STRIPE_MOBILE_PRICE_ID`.
- Configurer `RESEND_API_KEY` et `EMAIL_FROM` si l'envoi automatique des cles de licence est actif.
- Configurer `BACKUP_ENCRYPTION_KEY`, puis planifier `npm run backup:db:prod` avec upload S3 ou compatible et restauration de test reguliere.
- Servir exclusivement en HTTPS, forcer la redirection HTTP vers HTTPS au niveau du proxy/CDN et activer HSTS quand le domaine est stable.
- Centraliser les logs applicatifs, les erreurs Next.js/Prisma, les `AuditLog` sensibles et les entrees `stripe_webhook_events`.
- Surveiller au minimum: disponibilite HTTP, erreurs 5xx, latence, saturation PostgreSQL, Redis/Upstash, echecs Stripe webhook, echecs d'e-mail, age du dernier backup et espace disque.
- Ne jamais stocker `.env`, `backups/`, `*.dump`, `*.dump.enc` ou exports de base dans Git.

Preflight production:

```bash
npm run preflight:prod
```

La commande charge `.env`, `.env.local`, `.env.production` et `.env.production.local` si presents, puis laisse les variables d'environnement du processus prendre le dessus. Elle echoue si une variable obligatoire manque, si `APP_URL` n'est pas en HTTPS, si `DATABASE_URL` pointe vers `localhost`, si `STRIPE_SECRET_KEY` n'est pas une cle live `sk_live_...`, ou si un secret ressemble a une valeur de developpement.

Etapes de deploiement:

1. Provisionner PostgreSQL.
2. Configurer `DATABASE_URL`, `AUTH_SECRET`, `LICENSE_HASH_SECRET`, `LICENSE_KEY_ENCRYPTION_SECRET`, `APP_URL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_ID` et les prix Stripe par produit si necessaire.
   `LICENSE_KEY_ENCRYPTION_SECRET` doit etre long, distinct de `LICENSE_HASH_SECRET`, et conserve dans votre gestionnaire de secrets.
   `LICENSE_API_SECRET` est optionnel pour des integrations serveur-a-serveur et ne doit jamais etre embarque dans SafeSweep.exe.
   Pour l'e-mail automatique de cle de licence, configurer `RESEND_API_KEY`, `EMAIL_FROM`, optionnellement `EMAIL_REPLY_TO`, et `RESEND_API_URL` seulement si vous devez cibler un endpoint compatible/proxy.
   Configurer aussi `UPSTASH_REDIS_REST_URL` et `UPSTASH_REDIS_REST_TOKEN` pour le rate limiting distribue.
   Si l'application est derriere un reverse proxy, definir `TRUSTED_PROXY_IPS` avec les IP/CIDR de ces proxies pour autoriser `x-forwarded-for`.
   Pour les domaines de preview ou aliases web, definir `CSRF_TRUSTED_ORIGINS` avec les origins autorisees en plus de `APP_URL`.
   Les routes mutantes authentifiees refusent les requetes dont `Origin` ou `Host` ne correspondent pas a `APP_URL` ou a `CSRF_TRUSTED_ORIGINS`.
3. Servir exclusivement en HTTPS.
4. Executer les migrations Prisma.
5. Configurer le webhook Stripe vers `https://votre-domaine.com/api/stripe/webhook`.
6. Creer le premier compte admin hors seed:

```powershell
$env:ADMIN_EMAIL="admin@votre-domaine.com"
$env:ADMIN_NAME="Administrateur"
$env:ADMIN_COMPANY="Votre societe"
$env:ADMIN_PASSWORD="Changez-Moi-Long-14+!"
npm run admin:create
```

Le script refuse de promouvoir automatiquement un compte client existant et ecrit un log `ADMIN_CREATED`.

7. Builder et demarrer:

```bash
npm run preflight:prod
npm run build
npm run start
```

Notes securite:

- La validation de licence est exclusivement cote serveur.
- Les cles de licence sont hashees avant stockage; la livraison post-paiement utilise une enveloppe chiffree effacee apres revelation unique et un e-mail transactionnel sans persistance en clair.
- Les appareils sont comptes par fingerprint hashe.
- Les endpoints sensibles ont du rate limiting.
- Le rate limiting utilise Redis/Upstash et echoue ferme si Redis est indisponible hors developpement local.
- `x-forwarded-for` et `x-real-ip` ne sont lus que depuis des proxies explicitement autorises.
- Les mutations web verifient `Origin` contre `APP_URL` et `CSRF_TRUSTED_ORIGINS`.
- Les JWT de session embarquent `sessionVersion`; un reset ou changement de mot de passe invalide les anciens tokens.
- Les validations et actions admin sont journalisees.
- En production, utilisez HTTPS, secrets longs et rotation periodique des secrets.
