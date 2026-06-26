# SafeSweep

Application Windows pour repérer les fichiers probablement inutilisés afin de les vérifier puis les envoyer à la Corbeille.

## Important

Windows ne garantit pas toujours que la date de dernier accès est mise à jour. L'application utilise donc la dernière activité connue, c'est-à-dire le plus récent entre dernier accès et dernière modification. Elle ne supprime rien sans confirmation.

## Fonctionnalités

- Analyse récursive d'un dossier choisi.
- Filtre par nombre de jours sans activité.
- Filtre par taille minimale et extensions.
- Profils d'analyse : Bureau rapide, Téléchargements, Applications désinstallables, Photos/vidéos lourdes, Archives anciennes et Nettoyage prudent.
- Analyse de doublons exacts par taille puis hash SHA-256.
- Détection de gros dossiers : caches, exports, dépendances et anciens projets volumineux.
- Détection d'installateurs oubliés dans `Downloads`/`Téléchargements` : vieux `.exe`, `.msi`, `.zip`, `.iso` et archives assimilées.
- Recherche d'applications désinstallables via le registre Windows et les désinstallateurs courants : `uninstall.exe`, `uninst.exe`, `uninstaller.exe`, `unins000.exe`, etc., avec lancement depuis le clic droit après confirmation.
- Tri par risque de dégâts en cas de suppression : Faible, Moyen, Élevé, Critique.
- Recommandation d'action : Garder, Quarantaine, Supprimable, Désinstaller, ou Nettoyer via Windows.
- Rapport de simulation avant action : espace concerné, risques et dossiers touchés.
- Historique local des actions : quarantaine, restauration et envoi à la Corbeille.
- Aperçu rapide : texte, images, PDF via l'application Windows, et ouverture de l'emplacement.
- Liste blanche persistante pour ghoster des dossiers, fichiers ou extensions à ne jamais analyser.
- Ignore par défaut les dossiers système, caches techniques, caches développeur, fichiers cachés et jonctions.
- Ignore par défaut `Windows.old` et les dossiers système Windows ; utilisez le nettoyage Windows pour les anciennes installations.
- Sélection manuelle des fichiers trouvés.
- Sélection automatique des copies de doublons en gardant le fichier le plus récent de chaque groupe.
- Export CSV et HTML propre : risque, taille, raison et action recommandée.
- Mode ligne de commande pour automatiser scan, CSV et rapport HTML sans ouvrir l'interface graphique.
- Interface multilingue : Français, English et Español, avec choix sauvegardé depuis la barre supérieure.
- Quarantaine restaurable avec délai configurable, 30 jours par défaut.
- Proposition automatique d'envoi à la Corbeille des fichiers de quarantaine expirés, avec confirmation.
- Envoi des fichiers sélectionnés vers la Corbeille Windows.

## Quarantaine

La quarantaine déplace les fichiers hors de leur emplacement d'origine et conserve un manifeste local avec le chemin initial. Cela permet de tester pendant quelques jours si un programme signale un manque, puis de restaurer le fichier ou de l'envoyer à la Corbeille.

Par défaut, un fichier mis en quarantaine est considéré comme expiré après 30 jours. Au démarrage, l'application peut proposer d'envoyer les fichiers expirés à la Corbeille ; rien n'est fait sans validation. Le délai et cette demande automatique se règlent dans la fenêtre `Quarantaine`.

Compatibilité : les réglages existants restent stockés dans `%LOCALAPPDATA%\NettoyeurFichiers\...` afin de ne pas perdre la quarantaine ou la liste blanche créées avant le renommage SafeSweep.

## Risque

Le score de risque est une aide à la décision. Il classe notamment les fichiers Windows, exécutables, bibliothèques et pilotes en `Critique`, les fichiers de configuration/applications en `Élevé`, les documents/projets en `Moyen`, et les journaux/temporaires en `Faible`. Pour tout fichier `Élevé` ou `Critique`, préférez la quarantaine.

## Profils D'Analyse

Les profils préremplissent le dossier, le type d'analyse, l'ancienneté, la taille minimale et les extensions. Ils servent de point de départ accessible : après application, chaque réglage reste modifiable manuellement avant de lancer l'analyse.

## Liste Blanche

La liste blanche permet de protéger des dossiers, fichiers ou extensions. Ces règles sont ghostées pendant l'analyse : elles ne sont pas parcourues et n'apparaissent pas dans les résultats.

Pour `C:\Windows.old`, préférez `Paramètres > Système > Stockage > Fichiers temporaires > Installation(s) précédente(s) de Windows`. Cela supprime l'ancienne installation proprement, avec les règles Windows.

## Utilisation

L'exécutable généré se trouve dans `dist/SafeSweep.exe`.

Pour reconstruire l'exécutable :

```powershell
.\Build-Exe.ps1
```

Le build embarque l'icône Windows et l'icône de fenêtre depuis `src/unused_file_finder/assets/`.
Il crée aussi un raccourci `SafeSweep` sur le Bureau Windows. Utilisez `.\Build-Exe.ps1 -NoDesktopShortcut` pour générer seulement l'exécutable.

## Langues

L'exécutable propose trois langues : Français, English et Español. Le choix se fait dans la barre supérieure de l'application ; il est enregistré et appliqué au prochain démarrage.

Pour forcer une langue depuis un raccourci ou un script sans changer la préférence enregistrée :

```powershell
.\dist\SafeSweep.exe --lang=en
.\dist\SafeSweep.exe --lang=es
.\dist\SafeSweep.exe --lang=fr
```

## Ligne De Commande

Pour automatiser sans interface graphique, générez une version console :

```powershell
.\Build-Exe.ps1 -Name "SafeSweep-CLI" -Console -NoDesktopShortcut
```

Utilisez `SafeSweep.exe` pour l'interface graphique. `SafeSweep-CLI.exe` est réservé aux scripts ; lancé sans commande, il affiche l'aide puis quitte.

Lister les profils :

```powershell
.\dist\SafeSweep-CLI.exe profiles
```

Scanner avec un profil et écrire CSV + HTML :

```powershell
.\dist\SafeSweep-CLI.exe scan --profile "Téléchargements" --csv "$env:USERPROFILE\Desktop\rapport.csv" --html "$env:USERPROFILE\Desktop\rapport.html"
```

Scanner un dossier précis :

```powershell
.\dist\SafeSweep-CLI.exe scan --root "$env:USERPROFILE\Desktop" --mode unused --days 730 --min-size-mb 1 --csv ".\bureau.csv" --html ".\bureau.html"
```

Options utiles : `--mode unused|duplicates|folders|installers|uninstallers`, `--extensions ".zip,.iso"`, `--age-basis modified|accessed|activity`, `--include-hidden`, `--include-system`, `--no-whitelist`, `--quiet`.

## Licence

SafeSweep stocke l'état de licence local dans `%LOCALAPPDATA%\NettoyeurFichiers\license.json`.
La clé de licence locale est protégée avec Windows DPAPI quand disponible ; les anciens fichiers avec clé en clair restent lisibles puis sont migrés au prochain enregistrement.
L'identifiant appareil est un UUID généré localement pour SafeSweep ; aucun identifiant matériel brut ni secret serveur n'est embarqué dans l'exécutable.

Depuis la version console :

```powershell
.\dist\SafeSweep-CLI.exe license status
.\dist\SafeSweep-CLI.exe license activate "ABCD-EFGH-IJKL-MNOP"
```

Le portail de licences peut être défini avec `SAFESWEEP_LICENSE_API_URL` ou avec `--server-url` sur les commandes `license`.

## Installer Windows

Pour générer un installateur Windows propre :

```powershell
.\Build-Installer.ps1
```

Si Inno Setup n'est pas encore installé sur la machine :

```powershell
.\Build-Installer.ps1 -InstallInnoSetup
```

Le setup généré se trouve dans `dist/installer/SafeSweep-Setup-1.0.0.exe`.
Il installe l'application pour l'utilisateur courant, ajoute l'entrée de désinstallation Windows, crée le raccourci du menu Démarrer, et propose le raccourci Bureau pendant l'installation.
L'installateur propose aussi les langues français, anglais et espagnol.
Le setup n'est pas signé numériquement ; pour une distribution commerciale plus sérieuse, signez l'exécutable et l'installateur avec un certificat de signature de code.
