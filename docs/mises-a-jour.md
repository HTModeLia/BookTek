# Mises à jour automatiques

BookTek se met à jour à partir des [releases GitHub](https://github.com/HTModeLia/BookTek/releases) du dépôt. Ce document décrit le fonctionnement complet. Le code se trouve dans [`booktek/updater.py`](../booktek/updater.py), et l'intégration dans l'interface dans la section « mises à jour » de [`booktek/app.py`](../booktek/app.py).

## Côté utilisateur

```
 démarrage ──► mise à jour en attente ? ──oui──► installation ──► relance ──► nouvelle version
                      │ non
                      ▼
               interface ouverte
                      │  (3 s après, puis toutes les 6 h)
                      ▼
         vérification à chaud (arrière-plan)
                      │ nouvelle version publiée
                      ▼
          téléchargement + vérification SHA-256
                      │
                      ▼
          bouton « ⬆ Mettre à jour vers x.y.z »
            │ clic                       │ rien
            ▼                            ▼
   installation + relance     installation au prochain démarrage
```

| Situation | Comportement |
|---|---|
| Vérification automatique, déjà à jour | Rien n'est affiché |
| Vérification automatique, pas de réseau | Rien n'est affiché ; nouvel essai 6 h plus tard |
| Nouvelle version trouvée | Téléchargement silencieux, puis bouton et message dans la ligne de statut |
| **Aide > Rechercher une mise à jour** | Même vérification, avec progression du téléchargement et messages d'erreur visibles ; propose d'installer tout de suite |
| Lancement depuis les sources, ou exe dans un dossier protégé | La nouvelle version est signalée, mais pas installée automatiquement |

## Fonctionnement technique

### 1. Vérification

`updater.latest_release()` interroge `https://api.github.com/repos/HTModeLia/BookTek/releases/latest` : dernière release publiée, hors brouillons et pré-versions. On y cherche un fichier joint nommé exactement `BookTek.exe`.

La version de la release est son tag sans le `v` (`v1.2.0` → `1.2.0`). Elle est comparée numériquement à `booktek.__version__` (`1.10.0` est plus récent que `1.9.0`).

La vérification tourne dans un thread, pour ne jamais bloquer les scans. L'API GitHub sans authentification autorise 60 requêtes par heure et par adresse IP, très au-delà d'une vérification toutes les 6 heures.

### 2. Téléchargement et vérification

`updater.download()` télécharge l'exe à côté de l'exe courant :

1. dans `BookTek.exe.part` pendant le téléchargement ;
2. contrôle de la **taille** et de l'**empreinte SHA-256**. GitHub calcule cette empreinte lui-même pour chaque fichier de release (champ `digest` de l'API) ;
3. si tout correspond, renommage en `BookTek.exe.new`, et écriture de `BookTek.exe.update.json` (version et empreinte).

Un fichier incomplet ou altéré est supprimé et n'est jamais installé. Avant toute installation, `pending_version()` recalcule l'empreinte du `.new` : un fichier modifié entre-temps est rejeté.

### 3. Installation

Windows interdit d'écraser un exécutable en cours d'exécution, mais autorise à le **renommer**. `updater.apply_and_restart()` :

1. renomme `BookTek.exe` en `BookTek.exe.old-<horodatage>` ;
2. renomme `BookTek.exe.new` en `BookTek.exe`. En cas d'échec, l'ancien exe est remis en place ;
3. lance le nouvel exe avec `PYINSTALLER_RESET_ENVIRONMENT=1`. Sans cette variable, l'exe PyInstaller relancé réutiliserait le dossier temporaire de l'instance courante, supprimé à sa fermeture ;
4. l'instance courante se ferme.

Au démarrage suivant, `cleanup_old()` supprime les fichiers `.old-*`, qui ne sont alors plus verrouillés.

Il y a deux points d'entrée :

- **au démarrage** : `main()` appelle `updater.install_pending_on_startup()` avant d'ouvrir la base et l'interface. Une mise à jour qui échoue à s'installer est supprimée, puis sera retéléchargée à la vérification suivante ;
- **bouton « Mettre à jour »** : `App.install_update()` demande confirmation en affichant les notes de version, ferme la base puis appelle `apply_and_restart()`.

### Fichiers créés à côté de l'exe

| Fichier | Rôle | Durée de vie |
|---|---|---|
| `BookTek.exe.part` | Téléchargement en cours | Supprimé à la fin du téléchargement |
| `BookTek.exe.new` | Nouvelle version vérifiée | Jusqu'à l'installation |
| `BookTek.exe.update.json` | Version et empreinte du `.new` | Jusqu'à l'installation |
| `BookTek.exe.old-<horodatage>` | Version précédente | Supprimé au démarrage suivant |

La base `booktek.db` n'est jamais modifiée par une mise à jour. Si une version future fait évoluer le schéma, la migration devra être faite à l'ouverture de la base (`Library.__init__`).

## Sécurité

- Le téléchargement se fait uniquement en HTTPS, depuis le dépôt configuré dans `updater.REPO`.
- L'intégrité du fichier est vérifiée par l'empreinte SHA-256 publiée par GitHub.
- La confiance repose sur le compte GitHub du dépôt : quiconque peut publier une release peut distribuer du code à toutes les installations. Protégez ce compte (authentification à deux facteurs).
- L'exe n'est pas signé (pas de certificat Authenticode), d'où l'avertissement SmartScreen au premier lancement d'une nouvelle version téléchargée manuellement.

## Configuration

| Réglage | Emplacement | Valeur par défaut |
|---|---|---|
| Dépôt suivi | `updater.REPO` | `HTModeLia/BookTek` |
| Nom du fichier attendu dans la release | `updater.ASSET_NAME` | `BookTek.exe` |
| Intervalle de vérification | `updater.CHECK_INTERVAL` | 6 heures |
| Délai avant la première vérification | `App.__init__` | 3 secondes |
| URL de l'API (tests uniquement) | variable d'environnement `BOOKTEK_UPDATE_API` | API GitHub |

## Tester une mise à jour sans publier

La variable `BOOKTEK_UPDATE_API` redirige la vérification vers un serveur local qui imite l'API GitHub :

1. Construire un exe « ancien », par exemple en passant `__version__` à `1.0.5` dans une copie des sources, et l'exe « nouveau » avec la version courante.
2. Servir un fichier `api.json` et le nouvel exe avec un serveur HTTP local (`python -m http.server`). Le fichier `api.json` doit contenir :
   ```json
   {
     "tag_name": "v1.1.0",
     "html_url": "http://127.0.0.1:8765/",
     "body": "Version de test",
     "assets": [{
       "name": "BookTek.exe",
       "size": 12783269,
       "digest": "sha256:<empreinte du nouvel exe>",
       "browser_download_url": "http://127.0.0.1:8765/BookTek.exe"
     }]
   }
   ```
3. Lancer l'ancien exe avec `BOOKTEK_UPDATE_API=http://127.0.0.1:8765/api.json`. Après quelques secondes, `BookTek.exe.new` apparaît et le bouton **Mettre à jour** s'affiche.
4. Fermer puis relancer : la nouvelle version s'installe et démarre. Le titre de la fenêtre affiche le nouveau numéro de version.

Les tests unitaires de [`tests/test_updater.py`](../tests/test_updater.py) couvrent le téléchargement, le rejet d'un fichier altéré et le remplacement de l'exe, sans réseau.

## Limites

- **Passage de 1.0.0 à 1.1.0** : la version 1.0.0 ne contenait pas le système de mise à jour. Il faut installer une fois la 1.1.0 à la main.
- **Plusieurs instances ouvertes** : chaque instance peut télécharger la mise à jour. L'installation reste sûre, mais les autres instances continuent de tourner sur l'ancienne version jusqu'à leur fermeture.
- **Retour à une version antérieure** : pas de retour arrière automatique. Pour revenir en arrière, téléchargez l'ancienne version depuis la page des releases. Elle sera de nouveau mise à jour à la vérification suivante, sauf si la release fautive est retirée de GitHub.
