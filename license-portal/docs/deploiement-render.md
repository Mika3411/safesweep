# Deploiement production sur Render

Guide complet pour deployer SafeSweep License Portal sur Render avec Next.js, Prisma, PostgreSQL, Stripe, Redis/Upstash, e-mails et backups.

Date de verification des docs Render: 2026-06-25.

## Architecture cible

- Render Web Service: application Next.js.
- Render PostgreSQL: base de donnees production.
- Upstash Redis: rate limiting distribue.
- Resend ou SMTP: envoi automatique des cles de licence apres paiement.
- S3 ou stockage compatible: backups PostgreSQL chiffres.
- Stripe live mode: Checkout, Customer Portal et webhooks.
- Domaine HTTPS: domaine client ou sous-domaine Render au premier deploy.

Region recommandee pour une audience France/Europe: `Frankfurt, Germany`. Garder le Web Service et PostgreSQL dans la meme region.

## 1. Prerequis

Avant d'ouvrir Render:

1. Le code doit etre pousse sur GitHub, GitLab ou Bitbucket.
2. Les migrations Prisma doivent etre presentes dans `prisma/migrations/`.
3. Aucun backup, dump ou fichier `.env` ne doit etre versionne.
4. Les cles Stripe doivent etre en mode live.
5. Upstash, Resend et le bucket S3 doivent etre crees ou planifies.

Commandes locales avant push:

```bash
npm install
npm run typecheck
npm test
npm run build
```

Si ton depot Git contient le dossier parent et pas seulement `license-portal`, il faudra renseigner `license-portal` comme Root Directory dans Render.

## 2. Creer la base PostgreSQL Render

Dans le Dashboard Render:

1. Cliquer sur `New +`.
2. Choisir `PostgreSQL`.
3. Nom conseille: `safesweep-postgres-prod`.
4. Region: `Frankfurt`.
5. Database name: `safesweep_prod`.
6. User: `safesweep_prod`.
7. Plan: choisir un plan payant pour la production.

Important:

- Ne pas utiliser le plan gratuit en production.
- Render indique que les bases payantes beneficient de sauvegardes continues et de point-in-time recovery.
- Render ne propose pas de PITR sur le type gratuit.
- Le nom de base, l'utilisateur, la region et la version majeure PostgreSQL se planifient avant creation.

Une fois la base creee, recuperer:

- `Internal Database URL`: a utiliser dans `DATABASE_URL` pour l'application Render.
- `External Database URL`: a garder pour les operations locales exceptionnelles, avec TLS.

Dans l'application Render, toujours utiliser l'URL interne pour eviter de sortir du reseau prive Render.

## 3. Creer le Web Service Next.js

Dans Render:

1. Cliquer sur `New +`.
2. Choisir `Web Service`.
3. Connecter le depot Git.
4. Choisir la branche de production, par exemple `main`.
5. Region: `Frankfurt`.
6. Root Directory:
   - laisser vide si le depot pointe directement sur `license-portal`;
   - mettre `license-portal` si le depot contient ce projet dans un sous-dossier.
7. Runtime: `Node`.
8. Build Command:

```bash
npm ci && npm run build
```

9. Pre-Deploy Command:

```bash
npm run preflight:prod && npx prisma migrate deploy
```

10. Start Command:

```bash
npx next start -H 0.0.0.0 -p $PORT
```

11. Health Check Path:

```text
/login
```

Pourquoi ce start command: Render recommande de binder le serveur HTTP sur `0.0.0.0` et sur le port fourni par `PORT`. Le script local `npm run start` utilise `3000`, ce qui est pratique en local mais moins explicite pour Render.

## 4. Variables d'environnement Render

Dans le Web Service, ouvrir `Environment`.

Configurer ces variables obligatoires:

| Variable | Valeur |
| --- | --- |
| `DATABASE_URL` | Internal Database URL de Render PostgreSQL |
| `AUTH_SECRET` | secret aleatoire 32 caracteres minimum |
| `LICENSE_HASH_SECRET` | secret aleatoire distinct |
| `LICENSE_KEY_ENCRYPTION_SECRET` | secret aleatoire distinct, 32 caracteres minimum |
| `STRIPE_SECRET_KEY` | cle live Stripe `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | secret webhook Stripe `whsec_...` |
| `APP_URL` | `https://nom-service.onrender.com`, puis le domaine final |

Variables fortement recommandees:

| Variable | Valeur |
| --- | --- |
| `NODE_ENV` | `production` |
| `NODE_VERSION` | `22` |
| `LICENSE_API_SECRET` | optionnel, uniquement pour clients serveur-a-serveur; jamais dans SafeSweep.exe |
| `UPSTASH_REDIS_REST_URL` | URL REST Upstash |
| `UPSTASH_REDIS_REST_TOKEN` | token REST Upstash |
| `RESEND_API_KEY` | cle API Resend |
| `EMAIL_FROM` | exemple: `SafeSweep <licences@votre-domaine.com>` |
| `EMAIL_REPLY_TO` | adresse support |
| `STRIPE_PRICE_ID` | fallback prix Stripe |
| `STRIPE_ENDPOINT_PRICE_ID` | prix produit Endpoint |
| `STRIPE_SERVER_PRICE_ID` | prix produit Server |
| `STRIPE_MOBILE_PRICE_ID` | prix produit Mobile |
| `CSRF_TRUSTED_ORIGINS` | origins HTTPS additionnelles, separees par virgules |
| `TRUSTED_PROXY_IPS` | seulement si un proxy additionnel est devant Render |
| `BACKUP_ENCRYPTION_KEY` | secret de chiffrement backups, 32 caracteres minimum |
| `BACKUP_UPLOAD_ENABLED` | `true` si upload S3 actif |
| `BACKUP_S3_BUCKET` | bucket S3 |
| `BACKUP_S3_PREFIX` | exemple: `license-portal/postgresql` |
| `BACKUP_S3_ENDPOINT_URL` | endpoint S3 compatible si necessaire |
| `AWS_REGION` | region AWS ou compatible |
| `AWS_ACCESS_KEY_ID` | acces S3 |
| `AWS_SECRET_ACCESS_KEY` | secret S3 |

Generer des secrets depuis n'importe quel terminal avec Node:

```bash
node -e "console.log(require('crypto').randomBytes(48).toString('base64url'))"
```

Ne jamais reutiliser:

- les valeurs de `.env.example`;
- `dev-only...`;
- `change-me...`;
- `sk_test_...`;
- `localhost`;
- les comptes seed `client@safesweep.test` ou `admin@safesweep.test`.

## 5. Lancer le premier deploy

Dans Render:

1. Sauvegarder les variables.
2. Cliquer sur `Manual Deploy`.
3. Surveiller les logs.
4. Verifier que le pre-deploy passe:

```bash
npm run preflight:prod
npx prisma migrate deploy
```

5. Verifier que le build passe:

```bash
npm ci && npm run build
```

6. Verifier que le service devient `Live`.

Si le deploy echoue:

- `APP_URL must use https`: mettre une URL `https://...`.
- `STRIPE_SECRET_KEY must be a live key`: utiliser une cle `sk_live_...`.
- `DATABASE_URL must not point to localhost`: utiliser l'URL interne Render.
- erreur Prisma migration: ouvrir les logs du pre-deploy, corriger la migration, redeployer.
- erreur de port: verifier que le Start Command utilise bien `$PORT` et `0.0.0.0`.

## 6. Configurer le domaine HTTPS

Au premier deploy, `APP_URL` peut etre:

```text
https://safesweep-license-portal.onrender.com
```

Pour un domaine final:

1. Dans le Web Service Render, ouvrir `Settings`.
2. Aller dans `Custom Domains`.
3. Ajouter le domaine, par exemple:

```text
licenses.votre-domaine.com
```

4. Configurer le DNS chez le registrar ou Cloudflare.
5. Attendre la verification Render.
6. Render provisionne le certificat TLS et redirige HTTP vers HTTPS.
7. Mettre a jour `APP_URL`:

```text
https://licenses.votre-domaine.com
```

8. Redeployer.

Si vous utilisez aussi des previews ou aliases:

```text
CSRF_TRUSTED_ORIGINS=https://preview.votre-domaine.com,https://alias.votre-domaine.com
```

Ne pas ajouter d'origine HTTP ou localhost en production.

## 7. Configurer Stripe production

Dans Stripe Dashboard, en mode live:

1. Creer les produits et prix d'abonnement.
2. Copier les prix dans Render:
   - `STRIPE_ENDPOINT_PRICE_ID`
   - `STRIPE_SERVER_PRICE_ID`
   - `STRIPE_MOBILE_PRICE_ID`
   - ou `STRIPE_PRICE_ID` comme fallback.
3. Aller dans `Developers > Webhooks`.
4. Ajouter un endpoint:

```text
https://licenses.votre-domaine.com/api/stripe/webhook
```

5. Activer au minimum:

```text
checkout.session.completed
invoice.payment_succeeded
invoice.paid
payment_intent.succeeded
customer.subscription.created
customer.subscription.updated
customer.subscription.deleted
```

6. Copier le secret `whsec_...` dans `STRIPE_WEBHOOK_SECRET`.
7. Redeployer le Web Service.

Apres paiement reussi, l'application:

- cree la licence;
- stocke uniquement le hash de la cle;
- chiffre temporairement la cle pour revelation unique;
- envoie l'e-mail client;
- journalise les actions;
- stocke l'evenement Stripe dans `stripe_webhook_events`;
- evite le retraitement du meme `eventId`.

## 8. Creer le premier compte admin

Ne pas utiliser le seed en production.

Option recommandee: one-off job Render.

Commande du job:

```bash
ADMIN_EMAIL="admin@votre-domaine.com" ADMIN_NAME="Administrateur" ADMIN_COMPANY="Votre societe" ADMIN_PASSWORD="mot-de-passe-long-unique" npm run admin:create
```

Alternative locale:

1. Recuperer l'External Database URL Render.
2. Exporter `DATABASE_URL` localement avec cette URL.
3. Exporter les variables `ADMIN_*`.
4. Lancer:

```bash
npm run admin:create
```

Preferer le one-off job Render pour ne pas exposer l'URL externe de base sur un poste local.

## 9. Backups et restauration

Render fournit PITR sur les bases payantes. Cela ne remplace pas un backup exporte vers un stockage controle par vous.

Strategie recommandee:

1. Activer Render Postgres payant pour PITR.
2. Planifier un backup chiffre quotidien vers S3 ou compatible.
3. Tester une restauration au moins une fois par mois.
4. Garder la retention:
   - 7 backups quotidiens;
   - 4 hebdomadaires;
   - 12 mensuels.

Attention: les scripts actuels du projet sont en PowerShell:

```bash
npm run backup:db:prod
npm run decrypt:db:backup
npm run restore:db
```

Un Render Cron Job natif Node/Linux ne lance pas PowerShell par defaut. Vous avez donc deux options:

### Option A: runner externe

Utiliser GitHub Actions, un serveur Windows, un runner CI ou une machine d'exploitation avec:

- PowerShell;
- PostgreSQL client tools;
- AWS CLI;
- `DATABASE_URL` externe Render;
- `BACKUP_ENCRYPTION_KEY`;
- variables S3.

Puis lancer:

```bash
npm run backup:db:prod
```

### Option B: Render Cron Job Docker

Creer plus tard une image Docker dediee contenant:

- PowerShell;
- PostgreSQL client tools;
- AWS CLI;
- le code du projet.

Puis creer un Render Cron Job avec une planification UTC, par exemple:

```text
0 2 * * *
```

Commande:

```bash
npm run backup:db:prod
```

Dans tous les cas, verifier le backup:

```bash
npm run decrypt:db:backup -- -InputFile ./backups/restore/backup.dump.enc
npm run restore:db -- -DumpFile ./backups/restore/backup.dump -TargetDatabase safesweep_portal_restore_test
```

Ne jamais stocker les backups dans Git.

## 10. Monitoring minimal

Dans Render:

- surveiller `Events`;
- surveiller `Logs`;
- verifier les erreurs deploy et runtime;
- regarder les jobs one-off et cron;
- surveiller CPU, memoire et redemarrages.

Dans l'application:

- ouvrir `/admin`;
- verifier la section `Webhooks Stripe`;
- verifier les paiements recents;
- verifier les logs d'audit;
- surveiller les validations de licence refusees.

Alertes recommandees:

- erreurs HTTP 5xx;
- echecs Stripe webhook;
- echecs d'envoi e-mail;
- Redis/Upstash indisponible;
- age du dernier backup;
- espace disque PostgreSQL;
- hausse anormale des validations refusees.

Outils possibles:

- Render logs pour le minimum;
- Sentry pour exceptions applicatives;
- Better Stack ou equivalent pour uptime et alertes;
- Cloudflare pour DNS, HTTPS public et couche de protection.

## 11. Verification post-deploy

Apres chaque deploy:

1. Ouvrir:

```text
https://licenses.votre-domaine.com/login
```

2. Tester login admin.
3. Ouvrir `/admin`.
4. Verifier que la base repond.
5. Verifier que `npm run preflight:prod` est passe dans les logs.
6. Declencher un webhook Stripe de test en live uniquement si vous avez un scenario controle.
7. Verifier la creation d'une licence apres paiement.
8. Verifier l'e-mail client.
9. Verifier que la cle brute n'est affichable qu'une fois.
10. Verifier qu'un duplicate webhook n'est pas retraite.

Tests API utiles depuis une machine autorisee:

```bash
curl -I https://licenses.votre-domaine.com/login
curl -I https://licenses.votre-domaine.com/api/downloads/software
```

## 12. Rollback

Render permet de revenir a un deploy precedent depuis le Dashboard.

Attention:

- un rollback applicatif ne rollback pas automatiquement la base;
- avant une migration risquee, faire un backup exporte;
- preferer des migrations compatibles avant/apres quand possible;
- utiliser le PITR Render si une corruption ou suppression de donnees est detectee rapidement.

Procedure en cas d'incident:

1. Mettre le webhook Stripe en pause si les effets de bord continuent.
2. Rollback du Web Service vers le dernier deploy sain.
3. Examiner Render logs et `stripe_webhook_events`.
4. Si donnees corrompues: restaurer via PITR dans une nouvelle base, comparer, puis basculer `DATABASE_URL`.
5. Redeployer avec correction.

## 13. Checklist finale avant ouverture client

- Web Service en region `Frankfurt`.
- PostgreSQL en region `Frankfurt`.
- Plan PostgreSQL payant.
- `DATABASE_URL` interne configure.
- `APP_URL` en HTTPS et domaine final.
- `npm run preflight:prod` passe.
- `npx prisma migrate deploy` passe.
- `STRIPE_SECRET_KEY` en `sk_live_...`.
- `STRIPE_WEBHOOK_SECRET` en `whsec_...`.
- Webhook Stripe pointe vers `/api/stripe/webhook`.
- Upstash Redis configure.
- Resend configure.
- Admin cree hors seed.
- Backups chiffres planifies.
- Restauration testee.
- Logs et alertes configurees.
- Aucun `.env`, dump ou backup dans Git.

## Sources officielles consultees

- Render Web Services: https://render.com/docs/web-services
- Render Next.js: https://render.com/docs/deploy-nextjs-app
- Render Prisma + PostgreSQL: https://render.com/docs/deploy-prisma-orm
- Render PostgreSQL backups/PITR: https://render.com/docs/postgresql-backups
- Render backup PostgreSQL vers S3: https://render.com/docs/backup-postgresql-to-s3
- Render Cron Jobs: https://render.com/docs/cronjobs
- Render One-Off Jobs: https://render.com/docs/one-off-jobs
- Render Custom Domains: https://render.com/docs/custom-domains
- Render Logs: https://render.com/docs/logging
- Render Regions: https://render.com/docs/regions
