# API licences logicielles

Toutes les routes logicielles acceptent et retournent du JSON.

Les routes desktop sont publiques mais limitees. SafeSweep.exe ne doit jamais embarquer
`LICENSE_API_SECRET`: ce secret serveur ne peut pas etre protege dans un binaire PyInstaller.

Le mecanisme retenu pour le client desktop est:

- la cle de licence client est le secret utilisateur et circule uniquement via HTTPS;
- le serveur normalise puis hash la cle de licence avant toute recherche;
- le `deviceId` genere par l'application est hashe avant stockage;
- les routes ont un rate limiting par IP, par cle de licence hashee et par couple cle/appareil;
- chaque validation, activation, refus ou desactivation est journalisee dans `LicenseValidation`.

Un header optionnel `x-safesweep-client-secret: <LICENSE_API_SECRET>` peut exister pour une
integration serveur-a-serveur controlee, mais il n'est pas requis par les routes desktop et ne
doit pas etre place dans le logiciel Windows.

Le rate limiting est stocke dans Redis via Upstash (`UPSTASH_REDIS_REST_URL` et `UPSTASH_REDIS_REST_TOKEN`). Les headers proxy (`x-forwarded-for`, `x-real-ip`) ne sont utilises pour l'adresse client que si l'IP directe du proxy est listee dans `TRUSTED_PROXY_IPS`.

Les mutations web qui utilisent ou definissent un cookie de session verifient le header `Origin`. L'origin doit correspondre a `APP_URL` ou a une entree de `CSRF_TRUSTED_ORIGINS`.

Les cles de licence et identifiants appareils ne sont pas stockes en clair:

- `licenseKey` est normalisee puis hashee avec HMAC SHA-256;
- `deviceId` est hashe avant stockage;
- l'adresse IP est hashee dans les logs.

## POST /api/license/validate

Verifie qu'une licence peut etre utilisee par un appareil, sans creer d'activation.

Body:

```json
{
  "licenseKey": "XXXX-XXXX-XXXX-XXXX",
  "deviceId": "PC-123456",
  "deviceName": "Ordinateur de Jean"
}
```

Reponse valide:

```json
{
  "valid": true,
  "status": "active",
  "expiresAt": "2027-06-25",
  "remainingActivations": 2,
  "deviceAuthorized": false,
  "requiresActivation": true
}
```

Controle effectue:

- format de cle;
- licence existante;
- statut `active`;
- date d'expiration;
- appareil deja active ou activation encore disponible;
- nombre maximal d'activations.

## POST /api/license/activate

Active ou reactive l'appareil si la licence est utilisable et si la limite n'est pas atteinte.

Body identique a `/api/license/validate`.

Reponse:

```json
{
  "valid": true,
  "activated": true,
  "status": "active",
  "expiresAt": "2027-06-25",
  "remainingActivations": 1
}
```

## POST /api/license/deactivate

Desactive l'appareil associe a la licence.

Body identique a `/api/license/validate`.

Reponse:

```json
{
  "valid": true,
  "deactivated": true,
  "status": "active",
  "expiresAt": "2027-06-25",
  "remainingActivations": 2
}
```

## GET /api/customer/licenses

Retourne les licences du client connecte. Requiert une session utilisateur.

## GET /api/customer/licenses/:id

Retourne une licence du client connecte par `id` UUID ou `publicId`.

## POST /api/admin/licenses

Cree une licence. Requiert un compte admin.

Body:

```json
{
  "userId": "uuid-client",
  "product": "ENDPOINT",
  "expiresAt": "2027-06-25",
  "maxActivations": 3,
  "seatCount": 3
}
```

La reponse contient `rawKey` une seule fois. Le hash interne n'est jamais expose.

## PATCH /api/admin/licenses/:id

Modifie une licence. Requiert un compte admin.

Champs acceptes:

- `userId`
- `product`
- `status`
- `expiresAt`
- `maxActivations`
- `deviceLimit`
- `seatCount`

## DELETE /api/admin/licenses/:id

Effectue une suppression logique: la licence passe en `revoked` et les appareils actifs sont desactives.
Cette approche conserve l'historique de validation et les factures.

## Erreurs et logs

Erreurs courantes:

- `400`: format de licence invalide ou corps incomplet;
- `401`: utilisateur non connecte sur les routes d'espace client;
- `403`: licence inactive, expiree, suspendue, revoquee ou limite atteinte;
- `403`: origin absent ou non autorise sur une mutation web;
- `404`: licence ou appareil introuvable;
- `429`: rate limit atteint;
- `503`: backend Redis/Upstash de rate limiting indisponible ou non configure;
- `422`: validation de schema echouee.

Chaque validation, activation, reactivation, refus ou desactivation est journalisee dans `LicenseValidation`.
Les actions admin sont journalisees dans `AuditLog`.
