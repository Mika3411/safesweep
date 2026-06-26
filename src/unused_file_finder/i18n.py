from __future__ import annotations

import json
import locale
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable


SUPPORTED_LANGUAGES = ("fr", "en", "es")
DEFAULT_LANGUAGE = "fr"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NettoyeurFichiers"
PREFERENCES_PATH = APP_DATA_DIR / "preferences.json"

LANGUAGE_NAMES = {
    "fr": {"fr": "Français", "en": "French", "es": "Francés"},
    "en": {"fr": "Anglais", "en": "English", "es": "Inglés"},
    "es": {"fr": "Espagnol", "en": "Spanish", "es": "Español"},
}


def _translations(en: str, es: str) -> dict[str, str]:
    return {"en": en, "es": es}


_SOURCE_TRANSLATIONS: dict[str, dict[str, str]] = {
    "Langue": _translations("Language", "Idioma"),
    "Français": _translations("French", "Francés"),
    "Anglais": _translations("English", "Inglés"),
    "Espagnol": _translations("Spanish", "Español"),
    "La langue sera appliquée au prochain démarrage de SafeSweep.": _translations(
        "The language will be applied the next time SafeSweep starts.",
        "El idioma se aplicará la próxima vez que se inicie SafeSweep.",
    ),
    "Langue enregistrée. Redémarrez SafeSweep pour tout afficher dans cette langue.": _translations(
        "Language saved. Restart SafeSweep to show everything in this language.",
        "Idioma guardado. Reinicia SafeSweep para mostrar todo en este idioma.",
    ),
    "Redémarrage nécessaire": _translations("Restart required", "Reinicio necesario"),
    "Annuler": _translations("Cancel", "Cancelar"),
    "Fermer": _translations("Close", "Cerrar"),
    "Continuer": _translations("Continue", "Continuar"),
    "Enregistrer": _translations("Save", "Guardar"),
    "Supprimer": _translations("Delete", "Eliminar"),
    "Retirer": _translations("Remove", "Quitar"),
    "Actualiser": _translations("Refresh", "Actualizar"),
    "Parcourir": _translations("Browse", "Examinar"),
    "Bureau": _translations("Desktop", "Escritorio"),
    "Dossier": _translations("Folder", "Carpeta"),
    "Fichier": _translations("File", "Archivo"),
    "Chemin": _translations("Path", "Ruta"),
    "Extension": _translations("Extension", "Extensión"),
    "Nom": _translations("Name", "Nombre"),
    "Type": _translations("Type", "Tipo"),
    "Action": _translations("Action", "Acción"),
    "Actions": _translations("Actions", "Acciones"),
    "Résultats": _translations("Results", "Resultados"),
    "Sélection": _translations("Selection", "Selección"),
    "Profil": _translations("Profile", "Perfil"),
    "Version": _translations("Version", "Versión"),
    "Mode": _translations("Mode", "Modo"),
    "Inactif": _translations("Inactive", "Inactivo"),
    "jours": _translations("days", "días"),
    "Taille": _translations("Size", "Tamaño"),
    "Mo": _translations("MB", "MB"),
    "Ext.": _translations("Ext.", "Ext."),
    "Date": _translations("Date", "Fecha"),
    "Caches/système": _translations("Caches/system", "Cachés/sistema"),
    "Fichiers cachés": _translations("Hidden files", "Archivos ocultos"),
    "Mot-clé": _translations("Keyword", "Palabra clave"),
    "Réinitialiser": _translations("Reset", "Restablecer"),
    "à": _translations("to", "a"),
    "Groupe/Indice": _translations("Group/Hint", "Grupo/Indicio"),
    "Dernier accès": _translations("Last access", "Último acceso"),
    "Date retenue": _translations("Retained date", "Fecha usada"),
    "Modifié": _translations("Modified", "Modificado"),
    "Détails": _translations("Details", "Detalles"),
    "Statut": _translations("Status", "Estado"),
    "Signal utilisé : dernière modification seulement.": _translations(
        "Signal used: last modification only.",
        "Señal usada: solo última modificación.",
    ),
    "Choisissez un dossier, puis lancez l'analyse.": _translations(
        "Choose a folder, then start the scan.",
        "Elige una carpeta y luego inicia el análisis.",
    ),
    "Annulation demandée...": _translations("Cancellation requested...", "Cancelación solicitada..."),
    "Analyse en cours...": _translations("Scan in progress...", "Análisis en curso..."),
    "Analyse interrompue.": _translations("Scan interrupted.", "Análisis interrumpido."),
    "Analyse terminée": _translations("Scan complete", "Análisis completado"),
    "Analyse annulée": _translations("Scan cancelled", "Análisis cancelado"),
    "Paramètres invalides": _translations("Invalid settings", "Parámetros no válidos"),
    "Erreur d'analyse": _translations("Scan error", "Error de análisis"),
    "Erreur interface": _translations("Interface error", "Error de interfaz"),
    "Erreur interface. Consultez le journal.": _translations(
        "Interface error. Check the log.",
        "Error de interfaz. Consulta el registro.",
    ),
    "Journal": _translations("Log", "Registro"),
    "0 fichier - 0 o": _translations("0 files - 0 B", "0 archivos - 0 B"),
    "Tout cocher": _translations("Check all", "Marcar todo"),
    "Tout décocher": _translations("Uncheck all", "Desmarcar todo"),
    "Inverser": _translations("Invert", "Invertir"),
    "Cocher sélection": _translations("Check selection", "Marcar selección"),
    "Décocher sélection": _translations("Uncheck selection", "Desmarcar selección"),
    "Cocher doublons sauf plus récent": _translations(
        "Check duplicates except newest",
        "Marcar duplicados excepto el más reciente",
    ),
    "Trier par risque": _translations("Sort by risk", "Ordenar por riesgo"),
    "Exporter CSV": _translations("Export CSV", "Exportar CSV"),
    "Exporter HTML": _translations("Export HTML", "Exportar HTML"),
    "Aperçu rapide": _translations("Quick preview", "Vista rápida"),
    "Ouvrir l'emplacement": _translations("Open location", "Abrir ubicación"),
    "Copier le chemin": _translations("Copy path", "Copiar ruta"),
    "Copier les chemins": _translations("Copy paths", "Copiar rutas"),
    "Rapport de simulation...": _translations("Simulation report...", "Informe de simulación..."),
    "Mettre en quarantaine...": _translations("Quarantine...", "Poner en cuarentena..."),
    "Envoyer à la Corbeille...": _translations("Send to Recycle Bin...", "Enviar a la Papelera..."),
    "Quarantaine": _translations("Quarantine", "Cuarentena"),
    "Gérer la quarantaine": _translations("Manage quarantine", "Gestionar cuarentena"),
    "Historique des actions": _translations("Action history", "Historial de acciones"),
    "Liste blanche": _translations("Whitelist", "Lista blanca"),
    "Gérer la liste blanche": _translations("Manage whitelist", "Gestionar lista blanca"),
    "Planification": _translations("Scheduling", "Programación"),
    "Tableau de bord": _translations("Dashboard", "Panel"),
    "Dossier à analyser": _translations("Folder to scan", "Carpeta para analizar"),
    "Analyses rapides": _translations("Quick scans", "Análisis rápidos"),
    "Choisissez un nettoyage, surveillez la quarantaine et lancez les actions courantes.": _translations(
        "Choose a cleanup, monitor quarantine, and run common actions.",
        "Elige una limpieza, supervisa la cuarentena y ejecuta acciones habituales.",
    ),
    "Expirés": _translations("Expired", "Expirados"),
    "Ouvrir sans lancer": _translations("Open without starting", "Abrir sin iniciar"),
    "Profil courant": _translations("Current profile", "Perfil actual"),
    "Profil appliqué": _translations("Profile applied", "Perfil aplicado"),
    "personnalisé": _translations("custom", "personalizado"),
    "Analyse": _translations("Scan", "Análisis"),
    "Ancienneté": _translations("Age", "Antigüedad"),
    "jour(s)": _translations("day(s)", "día(s)"),
    "taille min.": _translations("min. size", "tamaño mín."),
    "Extensions": _translations("Extensions", "Extensiones"),
    "Rapports": _translations("Reports", "Informes"),
    "le": _translations("on", "el"),
    "Analyser": _translations("Scan", "Analizar"),
    "Analyser doublons": _translations("Scan duplicates", "Analizar duplicados"),
    "Analyser dossiers": _translations("Scan folders", "Analizar carpetas"),
    "Analyser installateurs": _translations("Scan installers", "Analizar instaladores"),
    "Rechercher désinstallateurs": _translations("Find uninstallers", "Buscar desinstaladores"),
    "Analyse des doublons en cours...": _translations(
        "Duplicate scan in progress...",
        "Análisis de duplicados en curso...",
    ),
    "Analyse des gros dossiers en cours...": _translations(
        "Large folder scan in progress...",
        "Análisis de carpetas grandes en curso...",
    ),
    "Recherche d'installateurs oubliés en cours...": _translations(
        "Searching for forgotten installers...",
        "Buscando instaladores olvidados...",
    ),
    "Recherche de désinstallateurs en cours...": _translations(
        "Searching for uninstallers...",
        "Buscando desinstaladores...",
    ),
    "Aucune sélection": _translations("No selection", "Sin selección"),
    "Cochez au moins un fichier.": _translations("Check at least one file.", "Marca al menos un archivo."),
    "Sélectionnez au moins un fichier.": _translations(
        "Select at least one file.",
        "Selecciona al menos un archivo.",
    ),
    "Dossier manquant": _translations("Missing folder", "Falta la carpeta"),
    "Dossier introuvable": _translations("Folder not found", "Carpeta no encontrada"),
    "Choisissez un dossier à analyser.": _translations(
        "Choose a folder to scan.",
        "Elige una carpeta para analizar.",
    ),
    "Le nombre de jours doit être un entier.": _translations(
        "The number of days must be an integer.",
        "El número de días debe ser un entero.",
    ),
    "La taille minimale doit être un nombre.": _translations(
        "The minimum size must be a number.",
        "El tamaño mínimo debe ser un número.",
    ),
    "Erreur": _translations("Error", "Error"),
    "Modification seule": _translations("Modification only", "Solo modificación"),
    "Dernier accès seul": _translations("Last access only", "Solo último acceso"),
    "Accès ou modification": _translations("Access or modification", "Acceso o modificación"),
    "Fichiers inactifs": _translations("Inactive files", "Archivos inactivos"),
    "Doublons exacts": _translations("Exact duplicates", "Duplicados exactos"),
    "Gros dossiers": _translations("Large folders", "Carpetas grandes"),
    "Installateurs": _translations("Installers", "Instaladores"),
    "Installateur": _translations("Installer", "Instalador"),
    "Installateurs oubliés": _translations("Forgotten installers", "Instaladores olvidados"),
    "Désinstallateurs": _translations("Uninstallers", "Desinstaladores"),
    "Applications désinstallables": _translations("Uninstallable apps", "Aplicaciones desinstalables"),
    "Tous": _translations("All", "Todos"),
    "Toutes": _translations("All", "Todas"),
    "toutes": _translations("all", "todas"),
    "Faible": _translations("Low", "Bajo"),
    "Moyen": _translations("Medium", "Medio"),
    "Élevé": _translations("High", "Alto"),
    "Critique": _translations("Critical", "Crítico"),
    "Supprimable": _translations("Deletable", "Eliminable"),
    "Désinstaller": _translations("Uninstall", "Desinstalar"),
    "Garder": _translations("Keep", "Conservar"),
    "Nettoyer via Windows": _translations("Clean with Windows", "Limpiar con Windows"),
    "Fichier temporaire, journal ou archive peu liée au fonctionnement système.": _translations(
        "Temporary file, log, or archive with little system impact.",
        "Archivo temporal, registro o archivo poco relacionado con el sistema.",
    ),
    "Fichier utilisateur ou projet : vérifier le contenu avant suppression.": _translations(
        "User file or project: check the contents before deletion.",
        "Archivo de usuario o proyecto: revisa el contenido antes de eliminar.",
    ),
    "Peut appartenir à une application, un cache actif, une configuration ou des données.": _translations(
        "May belong to an app, active cache, configuration, or data.",
        "Puede pertenecer a una aplicación, caché activa, configuración o datos.",
    ),
    "Fichier Windows, pilote, exécutable ou bibliothèque : ne pas supprimer directement.": _translations(
        "Windows file, driver, executable, or library: do not delete directly.",
        "Archivo de Windows, controlador, ejecutable o biblioteca: no eliminar directamente.",
    ),
    "Faible risque : peut aller à la Corbeille après vérification rapide.": _translations(
        "Low risk: can go to the Recycle Bin after a quick check.",
        "Riesgo bajo: puede ir a la Papelera tras una revisión rápida.",
    ),
    "À isoler d'abord pour tester quelques jours avant suppression.": _translations(
        "Isolate first and test for a few days before deletion.",
        "Aislar primero y probar unos días antes de eliminar.",
    ),
    "À conserver : suppression directe déconseillée.": _translations(
        "Keep it: direct deletion is not recommended.",
        "Conservar: no se recomienda la eliminación directa.",
    ),
    "À supprimer avec l'outil de nettoyage Windows plutôt que fichier par fichier.": _translations(
        "Remove with the Windows cleanup tool instead of file by file.",
        "Eliminar con la herramienta de limpieza de Windows en lugar de archivo por archivo.",
    ),
    "Installateur ancien trouvé dans Téléchargements : vérifiez qu'il n'est plus nécessaire avant suppression.": _translations(
        "Old installer found in Downloads: check that it is no longer needed before deletion.",
        "Instalador antiguo encontrado en Descargas: comprueba que ya no sea necesario antes de eliminarlo.",
    ),
    "À isoler d'abord si vous avez un doute ; sinon la Corbeille reste restaurable tant qu'elle n'est pas vidée.": _translations(
        "Isolate it first if unsure; otherwise the Recycle Bin remains restorable until emptied.",
        "Aíslalo primero si tienes dudas; si no, la Papelera permite restaurar hasta vaciarse.",
    ),
    "Désinstallateur détecté : lancer ce programme peut modifier ou retirer une application.": _translations(
        "Uninstaller detected: running this program may modify or remove an app.",
        "Desinstalador detectado: ejecutar este programa puede modificar o quitar una aplicación.",
    ),
    "Lancez le désinstallateur depuis le clic droit uniquement si vous reconnaissez l'application.": _translations(
        "Run the uninstaller from the right-click menu only if you recognize the app.",
        "Ejecuta el desinstalador desde el clic derecho solo si reconoces la aplicación.",
    ),
    "Lancez le désinstallateur uniquement si vous reconnaissez l'application.": _translations(
        "Run the uninstaller only if you recognize the app.",
        "Ejecuta el desinstalador solo si reconoces la aplicación.",
    ),
    "Cache": _translations("Cache", "Caché"),
    "Dépendances": _translations("Dependencies", "Dependencias"),
    "Export": _translations("Export", "Exportación"),
    "Ancien projet": _translations("Old project", "Proyecto antiguo"),
    "Ancien": _translations("Old", "Antiguo"),
    "Image disque": _translations("Disk image", "Imagen de disco"),
    "Archive d'installation": _translations("Installation archive", "Archivo de instalación"),
    "Archive": _translations("Archive", "Archivo comprimido"),
    "Pilote": _translations("Driver", "Controlador"),
    "Mise à jour": _translations("Update", "Actualización"),
    "Registre": _translations("Registry", "Registro"),
    "Nettoyage prudent": _translations("Careful cleanup", "Limpieza prudente"),
    "Bureau rapide": _translations("Quick desktop", "Escritorio rápido"),
    "Téléchargements": _translations("Downloads", "Descargas"),
    "Photos/vidéos lourdes": _translations("Large photos/videos", "Fotos/vídeos pesados"),
    "Archives anciennes": _translations("Old archives", "Archivos antiguos"),
    "Analyse limitée aux documents, avec fichiers système et cachés ignorés.": _translations(
        "Limited to documents, with system and hidden files ignored.",
        "Limitado a documentos, ignorando archivos del sistema y ocultos.",
    ),
    "Retrouve les vieux éléments du Bureau sans scanner tout le disque.": _translations(
        "Finds old desktop items without scanning the whole drive.",
        "Encuentra elementos antiguos del Escritorio sin analizar todo el disco.",
    ),
    "Compare les fichiers par taille puis hash pour retrouver les copies identiques.": _translations(
        "Compares files by size, then hash, to find identical copies.",
        "Compara archivos por tamaño y luego hash para encontrar copias idénticas.",
    ),
    "Mesure les dossiers volumineux pour repérer caches, exports et anciens projets.": _translations(
        "Measures large folders to spot caches, exports, and old projects.",
        "Mide carpetas grandes para detectar cachés, exportaciones y proyectos antiguos.",
    ),
    "Cible les installateurs, ISO et archives oubliés dans les téléchargements.": _translations(
        "Targets installers, ISOs, and archives forgotten in Downloads.",
        "Busca instaladores, ISO y archivos olvidados en Descargas.",
    ),
    "Recherche les applications désinstallables via le registre Windows et les fichiers uninstall/uninst.": _translations(
        "Finds uninstallable apps through the Windows registry and uninstall/uninst files.",
        "Busca aplicaciones desinstalables mediante el registro de Windows y archivos uninstall/uninst.",
    ),
    "Cherche les médias volumineux anciens dans Images/Vidéos ou le profil utilisateur.": _translations(
        "Looks for old large media in Pictures/Videos or the user profile.",
        "Busca medios grandes antiguos en Imágenes/Vídeos o en el perfil de usuario.",
    ),
    "Cherche les anciennes archives et images disque souvent oubliées.": _translations(
        "Looks for old archives and disk images that are often forgotten.",
        "Busca archivos comprimidos e imágenes de disco antiguas que suelen olvidarse.",
    ),
    "Documents anciens et fichiers sûrs": _translations("Old documents and safer files", "Documentos antiguos y archivos seguros"),
    "Copies identiques par hash SHA-256": _translations("Identical copies by SHA-256 hash", "Copias idénticas por hash SHA-256"),
    "Caches, exports et projets volumineux": _translations("Caches, exports, and large projects", "Cachés, exportaciones y proyectos grandes"),
    "Installateurs, archives et ISO oubliés": _translations("Forgotten installers, archives, and ISOs", "Instaladores, archivos e ISO olvidados"),
    "Registre Windows et désinstallateurs": _translations("Windows registry and uninstallers", "Registro de Windows y desinstaladores"),
    "ZIP, ISO et sauvegardes anciennes": _translations("Old ZIPs, ISOs, and backups", "ZIP, ISO y copias antiguas"),
    "Lundi": _translations("Monday", "Lunes"),
    "Mardi": _translations("Tuesday", "Martes"),
    "Mercredi": _translations("Wednesday", "Miércoles"),
    "Jeudi": _translations("Thursday", "Jueves"),
    "Vendredi": _translations("Friday", "Viernes"),
    "Samedi": _translations("Saturday", "Sábado"),
    "Dimanche": _translations("Sunday", "Domingo"),
    "Hebdomadaire": _translations("Weekly", "Semanal"),
    "Mensuelle": _translations("Monthly", "Mensual"),
    "Fréquence": _translations("Frequency", "Frecuencia"),
    "Rythme": _translations("Cadence", "Ritmo"),
    "Heure": _translations("Time", "Hora"),
    "Jour semaine": _translations("Weekday", "Día de la semana"),
    "Jour mois": _translations("Day of month", "Día del mes"),
    "Analyse planifiée": _translations("Scheduled scan", "Análisis programado"),
    "Ouvrir rapports": _translations("Open reports", "Abrir informes"),
    "Analyse planifiée enregistrée.": _translations("Scheduled scan saved.", "Análisis programado guardado."),
    "Supprimer la planification actuelle ?": _translations(
        "Delete the current schedule?",
        "¿Eliminar la programación actual?",
    ),
    "Planification supprimée.": _translations("Schedule deleted.", "Programación eliminada."),
    "Planification active dans le Planificateur de tâches Windows.": _translations(
        "Schedule active in Windows Task Scheduler.",
        "Programación activa en el Programador de tareas de Windows.",
    ),
    "Configuration enregistrée, mais tâche Windows introuvable.": _translations(
        "Configuration saved, but the Windows task was not found.",
        "Configuración guardada, pero no se encontró la tarea de Windows.",
    ),
    "Aucune planification active.": _translations("No active schedule.", "No hay programación activa."),
    "Notification uniquement : aucune suppression, quarantaine ou Corbeille automatique.": _translations(
        "Notification only: no automatic deletion, quarantine, or Recycle Bin action.",
        "Solo notificación: sin eliminación, cuarentena ni Papelera automática.",
    ),
    "Exporter les résultats": _translations("Export results", "Exportar resultados"),
    "Exporter le rapport HTML": _translations("Export HTML report", "Exportar informe HTML"),
    "Tous les fichiers": _translations("All files", "Todos los archivos"),
    "Rapport SafeSweep": _translations("SafeSweep report", "Informe de SafeSweep"),
    "Rapport d'analyse": _translations("Scan report", "Informe de análisis"),
    "Rapport de simulation": _translations("Simulation report", "Informe de simulación"),
    "Simulation avant action": _translations("Simulation before action", "Simulación antes de la acción"),
    "Sélectionné": _translations("Selected", "Seleccionado"),
    "Score risque": _translations("Risk score", "Puntuación de riesgo"),
    "Raison risque": _translations("Risk reason", "Motivo de riesgo"),
    "Action recommandée": _translations("Recommended action", "Acción recomendada"),
    "Rang action": _translations("Action rank", "Rango de acción"),
    "Raison action": _translations("Action reason", "Motivo de acción"),
    "Groupe ou indice": _translations("Group or hint", "Grupo o indicio"),
    "Taille octets": _translations("Size bytes", "Tamaño en bytes"),
    "Fichiers dans dossier": _translations("Files in folder", "Archivos en carpeta"),
    "Sous-dossiers": _translations("Subfolders", "Subcarpetas"),
    "Hash doublon": _translations("Duplicate hash", "Hash duplicado"),
    "oui": _translations("yes", "sí"),
    "non": _translations("no", "no"),
    "Dossier analysé": _translations("Scanned folder", "Carpeta analizada"),
    "Type d'analyse": _translations("Scan type", "Tipo de análisis"),
    "Généré le": _translations("Generated on", "Generado el"),
    "Résumé": _translations("Summary", "Resumen"),
    "Éléments": _translations("Items", "Elementos"),
    "Sélectionnés": _translations("Selected", "Seleccionados"),
    "Taille totale": _translations("Total size", "Tamaño total"),
    "Risques": _translations("Risks", "Riesgos"),
    "Actions recommandées": _translations("Recommended actions", "Acciones recomendadas"),
    "Raison": _translations("Reason", "Motivo"),
    "Recommandations": _translations("Recommendations", "Recomendaciones"),
    "Dossiers concernés": _translations("Affected folders", "Carpetas afectadas"),
    "Risque maximal": _translations("Maximum risk", "Riesgo máximo"),
    "Raison principale": _translations("Main reason", "Motivo principal"),
    "Aucun": _translations("None", "Ninguno"),
    "Aucune": _translations("None", "Ninguna"),
    "Quarantaine recommandée": _translations("Quarantine recommended", "Cuarentena recomendada"),
    "Mise en quarantaine conseillée": _translations("Quarantine advised", "Cuarentena recomendada"),
    "Mettre en quarantaine": _translations("Quarantine", "Poner en cuarentena"),
    "Envoyer à la Corbeille": _translations("Send to Recycle Bin", "Enviar a la Papelera"),
    "Corbeille": _translations("Recycle Bin", "Papelera"),
    "Sélection risquée": _translations("Risky selection", "Selección arriesgada"),
    "Risque élevé": _translations("High risk", "Riesgo alto"),
    "Confirmer la quarantaine": _translations("Confirm quarantine", "Confirmar cuarentena"),
    "Confirmer l'envoi à la Corbeille": _translations(
        "Confirm sending to Recycle Bin",
        "Confirmar envío a la Papelera",
    ),
    "Erreur quarantaine": _translations("Quarantine error", "Error de cuarentena"),
    "Erreur Corbeille": _translations("Recycle Bin error", "Error de Papelera"),
    "Erreur restauration": _translations("Restore error", "Error de restauración"),
    "Restaurer": _translations("Restore", "Restaurar"),
    "Ouvrir origine": _translations("Open original", "Abrir origen"),
    "Corbeille expirés": _translations("Recycle expired", "Enviar expirados"),
    "Ouvrir le dossier": _translations("Open folder", "Abrir carpeta"),
    "Proposer la Corbeille après": _translations("Suggest Recycle Bin after", "Sugerir Papelera después de"),
    "Demander au démarrage": _translations("Ask at startup", "Preguntar al inicio"),
    "Enregistrer délai": _translations("Save delay", "Guardar plazo"),
    "Mis en quarantaine": _translations("Quarantined", "En cuarentena"),
    "Expire le": _translations("Expires on", "Expira el"),
    "Chemin d'origine": _translations("Original path", "Ruta original"),
    "Chemin quarantaine": _translations("Quarantine path", "Ruta de cuarentena"),
    "Expiré": _translations("Expired", "Expirado"),
    "En attente": _translations("Pending", "Pendiente"),
    "Historique": _translations("History", "Historial"),
    "Ajouter dossier": _translations("Add folder", "Añadir carpeta"),
    "Ajouter fichier": _translations("Add file", "Añadir archivo"),
    "Ajouter extension": _translations("Add extension", "Añadir extensión"),
    "Ajouter un dossier à la liste blanche": _translations(
        "Add a folder to the whitelist",
        "Añadir una carpeta a la lista blanca",
    ),
    "Ajouter un fichier à la liste blanche": _translations(
        "Add a file to the whitelist",
        "Añadir un archivo a la lista blanca",
    ),
    "Ajouter une extension": _translations("Add an extension", "Añadir una extensión"),
    "Extension à protéger, par exemple .psd ou .blend :": _translations(
        "Extension to protect, for example .psd or .blend:",
        "Extensión que proteger, por ejemplo .psd o .blend:",
    ),
    "Aperçu": _translations("Preview", "Vista previa"),
    "Aperçu désinstallateur": _translations("Uninstaller preview", "Vista de desinstalador"),
    "Aperçu dossier": _translations("Folder preview", "Vista de carpeta"),
    "Aperçu non disponible": _translations("Preview unavailable", "Vista no disponible"),
    "Aperçu texte": _translations("Text preview", "Vista de texto"),
    "Ouvrir le fichier": _translations("Open file", "Abrir archivo"),
    "Désinstallateur": _translations("Uninstaller", "Desinstalador"),
    "Ouvrir rapports": _translations("Open reports", "Abrir informes"),
    "Analyse les fichiers sans ouvrir l'interface graphique.": _translations(
        "Scans files without opening the graphical interface.",
        "Analiza archivos sin abrir la interfaz gráfica.",
    ),
    "Lister les profils d'analyse disponibles.": _translations(
        "List available scan profiles.",
        "Lista los perfiles de análisis disponibles.",
    ),
    "Lancer une analyse et exporter un rapport.": _translations(
        "Run a scan and export a report.",
        "Ejecuta un análisis y exporta un informe.",
    ),
    "Profil d'analyse à appliquer.": _translations("Scan profile to apply.", "Perfil de análisis que aplicar."),
    "Dossier à analyser. Remplace le dossier du profil.": _translations(
        "Folder to scan. Overrides the profile folder.",
        "Carpeta que analizar. Sustituye la carpeta del perfil.",
    ),
    "Type d'analyse. Remplace le mode du profil.": _translations(
        "Scan type. Overrides the profile mode.",
        "Tipo de análisis. Sustituye el modo del perfil.",
    ),
    "Ancienneté minimale en jours.": _translations("Minimum age in days.", "Antigüedad mínima en días."),
    "Taille minimale en Mo.": _translations("Minimum size in MB.", "Tamaño mínimo en MB."),
    "Extensions à inclure, séparées par virgule, point-virgule ou espace.": _translations(
        "Extensions to include, separated by comma, semicolon, or space.",
        "Extensiones que incluir, separadas por coma, punto y coma o espacio.",
    ),
    "Date utilisée pour l'âge.": _translations("Date used for age.", "Fecha usada para la antigüedad."),
    "Nombre maximal de résultats.": _translations("Maximum number of results.", "Número máximo de resultados."),
    "Chemin du rapport CSV à écrire.": _translations("CSV report path to write.", "Ruta del informe CSV que escribir."),
    "Chemin du rapport HTML à écrire.": _translations("HTML report path to write.", "Ruta del informe HTML que escribir."),
    "Inclure les fichiers cachés/système.": _translations("Include hidden/system files.", "Incluir archivos ocultos/del sistema."),
    "Inclure les emplacements système.": _translations("Include system locations.", "Incluir ubicaciones del sistema."),
    "Ignorer la liste blanche configurée.": _translations("Ignore the configured whitelist.", "Ignorar la lista blanca configurada."),
    "Afficher uniquement les erreurs.": _translations("Only show errors.", "Mostrar solo errores."),
    "taille_min": _translations("min_size", "tamaño_mín"),
    "extensions": _translations("extensions", "extensiones"),
    "résultat(s)": _translations("result(s)", "resultado(s)"),
    "fichier(s) analysé(s)": _translations("file(s) scanned", "archivo(s) analizado(s)"),
    "dossier(s) refusé(s)": _translations("folder(s) denied", "carpeta(s) denegada(s)"),
    "erreur(s)": _translations("error(s)", "error(es)"),
    "Limite de résultats atteinte.": _translations("Result limit reached.", "Límite de resultados alcanzado."),
}

_TRANSLATIONS: dict[str, dict[str, str]] = {
    language: {
        source: values[language]
        for source, values in _SOURCE_TRANSLATIONS.items()
        if language in values
    }
    for language in SUPPORTED_LANGUAGES
    if language != DEFAULT_LANGUAGE
}
_REVERSE_TRANSLATIONS: dict[str, dict[str, str]] = {
    language: {translated: source for source, translated in values.items()}
    for language, values in _TRANSLATIONS.items()
}


def normalize_language(value: str | None) -> str:
    if not value:
        return DEFAULT_LANGUAGE
    code = value.strip().replace("_", "-").split("-", 1)[0].casefold()
    return code if code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def detect_language() -> str:
    env_value = os.environ.get("SAFESWEEP_LANG") or os.environ.get("LANGUAGE") or os.environ.get("LANG")
    if env_value:
        detected = normalize_language(env_value)
        if detected in SUPPORTED_LANGUAGES:
            return detected

    try:
        locale_value = locale.getlocale()[0] or locale.getdefaultlocale()[0]
    except (ValueError, TypeError):
        locale_value = None
    return normalize_language(locale_value)


def load_language(path: str | Path = PREFERENCES_PATH) -> str:
    env_value = os.environ.get("SAFESWEEP_LANG")
    if env_value:
        return normalize_language(env_value)

    source = Path(path)
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return detect_language() if getattr(sys, "frozen", False) else DEFAULT_LANGUAGE
    return normalize_language(str(payload.get("language", "")))


_current_language = load_language()


def current_language() -> str:
    return _current_language


def set_language(language: str) -> str:
    global _current_language
    _current_language = normalize_language(language)
    return _current_language


def save_language(language: str, path: str | Path = PREFERENCES_PATH) -> Path:
    code = normalize_language(language)
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"language": code}
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def translate(value: object) -> object:
    if not isinstance(value, str):
        return value
    if _current_language == DEFAULT_LANGUAGE:
        return value
    return _TRANSLATIONS.get(_current_language, {}).get(value, value)


def _(value: object) -> Any:
    return translate(value)


def source_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    if _current_language == DEFAULT_LANGUAGE:
        return value
    return _REVERSE_TRANSLATIONS.get(_current_language, {}).get(value, value)


def translate_sequence(values: Iterable[object]) -> tuple[object, ...]:
    return tuple(translate(value) for value in values)


def language_label(language: str | None = None) -> str:
    code = normalize_language(language or _current_language)
    return LANGUAGE_NAMES.get(code, LANGUAGE_NAMES[DEFAULT_LANGUAGE]).get(_current_language, code)


def language_choices() -> tuple[str, ...]:
    return tuple(language_label(code) for code in SUPPORTED_LANGUAGES)


def language_code_from_label(label: str) -> str:
    normalized = label.strip().casefold()
    for code, names in LANGUAGE_NAMES.items():
        if normalized == code.casefold():
            return code
        if any(normalized == name.casefold() for name in names.values()):
            return code
    source = source_text(label)
    if isinstance(source, str):
        for code, names in LANGUAGE_NAMES.items():
            if source.casefold() in {name.casefold() for name in names.values()}:
                return code
    return _current_language


def install_tkinter_i18n(tk_module: Any, ttk_module: Any, messagebox_module: Any, filedialog_module: Any, simpledialog_module: Any) -> None:
    if getattr(tk_module, "_safesweep_i18n_installed", False):
        return
    setattr(tk_module, "_safesweep_i18n_installed", True)

    def translate_options(options: dict[str, Any]) -> dict[str, Any]:
        translated = dict(options)
        for key in ("text", "label", "title", "message", "detail", "prompt"):
            if key in translated:
                translated[key] = translate(translated[key])
        return translated

    def patch_widget_class(cls: type[Any]) -> None:
        original_init = cls.__init__
        original_configure = cls.configure

        def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **translate_options(kwargs))

        def configure(self: Any, cnf: Any = None, **kwargs: Any) -> Any:
            if isinstance(cnf, dict):
                cnf = translate_options(cnf)
            return original_configure(self, cnf, **translate_options(kwargs))

        cls.__init__ = __init__  # type: ignore[method-assign]
        cls.configure = configure  # type: ignore[method-assign]
        cls.config = configure  # type: ignore[method-assign]

    for cls in (
        tk_module.Label,
        tk_module.Button,
        tk_module.Checkbutton,
        tk_module.Radiobutton,
        tk_module.LabelFrame,
        ttk_module.Label,
        ttk_module.Button,
        ttk_module.Checkbutton,
        ttk_module.Radiobutton,
        ttk_module.Menubutton,
        ttk_module.LabelFrame,
        ttk_module.Labelframe,
    ):
        if not getattr(cls, "_safesweep_i18n_patched", False):
            patch_widget_class(cls)
            setattr(cls, "_safesweep_i18n_patched", True)

    original_stringvar_init = tk_module.StringVar.__init__
    original_stringvar_set = tk_module.StringVar.set

    def stringvar_init(self: Any, master: Any = None, value: Any = None, name: str | None = None) -> None:
        original_stringvar_init(self, master=master, value=translate(value), name=name)

    def stringvar_set(self: Any, value: Any) -> None:
        original_stringvar_set(self, translate(value))

    tk_module.StringVar.__init__ = stringvar_init  # type: ignore[method-assign]
    tk_module.StringVar.set = stringvar_set  # type: ignore[method-assign]

    def patch_title(cls: type[Any]) -> None:
        original_title = cls.title

        def title(self: Any, string: Any = None) -> Any:
            if string is None:
                return original_title(self)
            return original_title(self, translate(string))

        cls.title = title  # type: ignore[method-assign]

    patch_title(tk_module.Tk)
    patch_title(tk_module.Toplevel)

    def patch_menu_method(name: str) -> None:
        original = getattr(tk_module.Menu, name)

        def method(self: Any, *args: Any, **kwargs: Any) -> Any:
            return original(self, *args, **translate_options(kwargs))

        setattr(tk_module.Menu, name, method)

    for method_name in ("add_command", "add_cascade", "add_checkbutton", "add_radiobutton"):
        patch_menu_method(method_name)

    original_entryconfigure = tk_module.Menu.entryconfigure

    def entryconfigure(self: Any, index: Any, cnf: Any = None, **kwargs: Any) -> Any:
        if isinstance(index, str):
            index = translate(index)
        if isinstance(cnf, dict):
            cnf = translate_options(cnf)
        return original_entryconfigure(self, index, cnf, **translate_options(kwargs))

    tk_module.Menu.entryconfigure = entryconfigure
    tk_module.Menu.entryconfig = entryconfigure

    original_heading = ttk_module.Treeview.heading

    def heading(self: Any, column: Any, option: Any = None, **kwargs: Any) -> Any:
        return original_heading(self, column, option, **translate_options(kwargs))

    ttk_module.Treeview.heading = heading

    def patch_dialog_function(module: Any, name: str, translator: Callable[..., Any]) -> None:
        original = getattr(module, name, None)
        if not original:
            return

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            return translator(original, *args, **kwargs)

        setattr(module, name, wrapped)

    def translate_title_message(original: Callable[..., Any], title: Any = None, message: Any = None, **kwargs: Any) -> Any:
        return original(translate(title), translate(message), **translate_options(kwargs))

    for name in ("showinfo", "showerror", "showwarning", "askyesno", "askyesnocancel", "askokcancel"):
        patch_dialog_function(messagebox_module, name, translate_title_message)

    def translate_filedialog(original: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return original(*args, **translate_options(kwargs))

    for name in ("askdirectory", "askopenfilename", "asksaveasfilename"):
        patch_dialog_function(filedialog_module, name, translate_filedialog)

    def translate_askstring(original: Callable[..., Any], title: Any, prompt: Any, **kwargs: Any) -> Any:
        return original(translate(title), translate(prompt), **translate_options(kwargs))

    patch_dialog_function(simpledialog_module, "askstring", translate_askstring)
