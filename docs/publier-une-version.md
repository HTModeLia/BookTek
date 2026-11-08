# Publier une version

Chaque release GitHub publiée est **immédiatement proposée à toutes les installations** par la mise à jour automatique. Une release ratée est donc distribuée à tout le monde : suivez cette procédure.

## Prérequis

- Python 3.10 ou plus récent, PyInstaller et Pillow (`pip install pyinstaller pillow`). Pillow sert à afficher les couvertures, et le script refuse de construire l'exe sans lui.
- Une clé d'API Google Books dans le fichier `booktek/_key.py`, sur une ligne : `GOOGLE_KEY = "votre-clé"`. Ce fichier est ignoré par git et ne doit jamais être commité. Il est embarqué dans l'exe : restreignez la clé à la seule API Books dans la console Google Cloud. Sans clé, les recherches Google partagent un quota anonyme presque toujours épuisé, et le script refuse de construire l'exe.
- Des droits d'écriture sur le dépôt `HTModeLia/BookTek`, avec un `git push` qui fonctionne. Le script réutilise ces identifiants ; sinon, définissez la variable d'environnement `GITHUB_TOKEN`.

## Procédure

1. **Incrémenter la version** dans [`booktek/__init__.py`](../booktek/__init__.py) :
   ```python
   __version__ = "1.2.0"
   ```
   Numérotation `majeur.mineur.correctif` :
   - **correctif** pour une correction de bug ;
   - **mineur** pour une nouvelle fonctionnalité ;
   - **majeur** pour un changement incompatible, par exemple une migration de base irréversible.

2. **Décrire les changements** dans [`CHANGELOG.md`](../CHANGELOG.md), dans une nouvelle section en haut du fichier :
   ```markdown
   ## [1.2.0] - 2026-12-01

   ### Ajouts
   - ...

   ### Corrections
   - ...
   ```
   Ce texte devient la description de la release, et il est affiché à l'utilisateur au moment d'installer la mise à jour. Écrivez-le pour lui.

3. **Commiter et pousser** sur `main` :
   ```
   git commit -am "Version 1.2.0"
   git push
   ```

4. **Vérifier à blanc** :
   ```
   python tools/release.py --dry-run
   ```
   Le script vérifie que la copie de travail est propre et synchronisée avec GitHub, et que le tag n'existe pas. Il lance ensuite les tests, construit `dist/BookTek.exe` et affiche les notes de version, sans rien publier.

5. **Tester l'exe** `dist/BookTek.exe` : lancement, scan, prêt, retour. Pour tester la mise à jour elle-même sans publier, voir [Tester une mise à jour sans publier](mises-a-jour.md#tester-une-mise-à-jour-sans-publier).

6. **Publier** :
   ```
   python tools/release.py
   ```
   Le script reprend les vérifications, reconstruit l'exe, crée et pousse le tag `v1.2.0`, puis crée la release GitHub avec `BookTek.exe` en pièce jointe.

Dans les 6 heures (ou au prochain lancement), les installations existantes téléchargent la nouvelle version.

## Règles à respecter

- Le fichier joint doit s'appeler exactement **`BookTek.exe`** : c'est le nom que cherche le programme de mise à jour.
- Le tag doit correspondre à `__version__` : `v` suivi de la version. La comparaison est numérique.
- Ne publiez pas en **brouillon** ni en **pré-version** si vous voulez que la version soit distribuée : l'API `releases/latest` les ignore. À l'inverse, une pré-version permet de faire tester une version sans la distribuer automatiquement.
- Ne remplacez jamais l'exe d'une release existante : publiez une nouvelle version.

## En cas de release défectueuse

1. Publiez au plus vite une version corrective avec un numéro supérieur, par exemple `1.2.1`. C'est la seule façon de corriger les installations déjà mises à jour.
2. En attendant, vous pouvez repasser la release fautive en brouillon sur GitHub. Elle ne sera plus proposée, mais les installations déjà mises à jour la conservent.
