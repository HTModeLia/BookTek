# Reprendre le projet BookTek

Ce fichier sert de point d'entrée pour toute personne ou IA (Claude Code ou autre) qui reprend le projet. Il est volontairement court : le détail est dans les documents cités.

## En bref

BookTek est un logiciel Windows de gestion de bibliothèque personnelle : on scanne l'ISBN d'un livre (douchette ou clavier) pour l'ajouter, le prêter ou noter son retour. Le projet est en Python et Tkinter, avec une base SQLite, et il est distribué sous forme d'un seul `BookTek.exe` qui se met à jour depuis les releases GitHub de `HTModeLia/BookTek`.

- **Utilisateur final** : particulier, notamment une personne de 65 ans. Interface simple, textes en français, fort contraste, rien de technique à l'écran.
- **Mainteneur** : le propriétaire du dépôt. Il échange en français, demande des évolutions courtes (« possibilité de… ») et dit « publie » pour sortir une version.
- **État** : version **1.10.0** (11/11/2026). L'historique complet est dans [CHANGELOG.md](CHANGELOG.md).

## Où trouver quoi

| Besoin | Document |
|---|---|
| Fonctionnalités vues par l'utilisateur | [docs/guide-utilisateur.md](docs/guide-utilisateur.md) |
| Modules, base, threads, interface, thèmes, pièges Tkinter | [docs/architecture.md](docs/architecture.md) |
| Mise à jour automatique (updater, SHA-256, remplacement de l'exe) | [docs/mises-a-jour.md](docs/mises-a-jour.md) |
| Sortir une version | [docs/publier-une-version.md](docs/publier-une-version.md) |
| Détail de chaque fonction | les docstrings du code (en français) |

Code : `booktek/app.py` (interface, environ 1400 lignes), `db.py` (SQLite + migrations), `lookup.py` (BnF, Google Books, Open Library), `isbn.py`, `bkc_import.py` (Book Collector), `updater.py`. Tests : `tests/`. Release : `tools/release.py`.

## Commandes

```
python main.py                              # lancer depuis les sources
python -m unittest discover -s tests        # tests (pas de pytest installé)
python tools/release.py --dry-run           # tests + construction de dist/BookTek.exe, sans publier
python tools/release.py                     # publier (tag + release GitHub) : seulement sur demande explicite
```

Environnement de développement : Windows 11, Python 3.15 (`C:\Python315`), Pillow et PyInstaller installés.

## Conventions

- **Tout en français** : interface, messages, docstrings, commentaires, documentation, messages de commit.
- **Messages de commit** : résumé des nouveautés suivi de la version, par exemple `Fiche sous la liste, compteur, thème sombre et grands caractères (version 1.6.0)`.
- **Chaque évolution livrée** :
  1. incrémenter `booktek/__init__.py` (`__version__`) : correctif → `x.y.Z`, fonctionnalité → `x.Y.0` ;
  2. ajouter une section en haut de `CHANGELOG.md` (`## [x.y.z] - AAAA-MM-JJ`, sous-titres `Ajouts`, `Modifications`, `Corrections`), **rédigée pour l'utilisateur final**, car elle s'affiche dans l'application au moment de la mise à jour ;
  3. mettre à jour `docs/guide-utilisateur.md` et, si la structure change, `docs/architecture.md` ;
  4. lancer les tests ; pour l'interface, faire en plus un contrôle visuel (voir plus bas).
- **Publier** uniquement quand le mainteneur le demande (« publie ») : commit, `git push`, puis `python tools/release.py`. Une release publiée est installée chez tout le monde : on ne remplace jamais une release, on publie une version corrective.
- **Interface** : pas de couleur ni de police écrite en dur, utiliser `COLORS[...]` et `ui_font(...)` (voir « Affichage » dans l'architecture), sinon le thème sombre et les grands caractères ne s'appliquent pas.
- **Base** : ne jamais modifier une migration publiée, en ajouter une à la fin de `db.MIGRATIONS`.
- **Threads** : un thread secondaire n'appelle que `App.post(...)`, jamais Tkinter ni SQLite directement.
- **Style de code** : changements minimaux, réutiliser l'existant, pas de dépendance nouvelle (Pillow est la seule, et elle reste optionnelle à l'exécution). Une simplification assumée porte un commentaire `# shortcut: <limite>, <quand l'améliorer>`.

## Fichiers sensibles (jamais commités)

Ils sont déjà exclus par `.gitignore` :

- `booktek/_key.py` : clé d'API Google Books (`GOOGLE_KEY = "..."`), embarquée dans l'exe ; sans elle, `release.py` refuse de construire.
- `*.bkc`, `Book Collector/`, `livres*.csv`, `*.db` : données personnelles du mainteneur (collection réelle, exports). Le test d'import `.bkc` est sauté si le fichier d'exemple est absent.

## Vérifier une modification de l'interface sans clic

Les tests ne couvrent pas Tkinter. Un script jetable, à garder hors du dépôt, suffit à voir la vraie fenêtre :

```python
import tempfile, os
from PIL import ImageGrab
from booktek import app as A

w = A.App(os.path.join(tempfile.mkdtemp(), "t.db"))
w.lib.add_book({"title": "Livre test", "authors": "Auteur", "isbn": "", "summary": "Résumé…"})
w.refresh(); w.geometry("1100x750+0+0"); w.update()
w.books.selection_set(w.books.get_children()[0]); w.update()
w.set_setting("dark", True); w.update()          # tester aussi le thème sombre et "large"
ImageGrab.grab((w.winfo_rootx(), w.winfo_rooty(),
                w.winfo_rootx() + w.winfo_width(), w.winfo_rooty() + w.winfo_height())).save("capture.png")
w.destroy()
```

`set_setting()` écrit `settings.json` à côté de la base : avec une base temporaire, rien ne touche aux réglages réels.

## Limites connues et idées en attente

Rien de cela n'a été demandé ferme : à proposer au mainteneur, pas à faire d'office.

- **Jaquette d'un nouveau livre** : elle ne se choisit qu'après le premier enregistrement (via *Modifier…*), car le fichier est nommé d'après l'id du livre.
- **Supprimer une jaquette** sans la remplacer : non prévu.
- **Changer de thème** vide le champ de recherche, à cause de la reconstruction de l'interface.
- **Menus et boîtes de dialogue Windows** (fichiers, messages) restent clairs en thème sombre : limite de Tk sous Windows.
- **Tri par auteur** : le nom de famille est supposé être le dernier mot du premier auteur (faux pour « Ben Jelloun »).
- **Import `.bkc`** : seuls l'ISBN et le titre sont extraits, le reste vient de *Compléter les fiches via Internet*. Les couvertures de Book Collector ne sont pas importées.
- **Écartés volontairement** (inspirés de Book Collector) : fiche auteur avec photo et Wikipédia, colonnes Format / Pays / Illustrateur, barre de lettres A à Z, image de fond derrière le résumé.
- **Exe non testé à la main** avant les dernières releases : seuls les tests et les captures depuis les sources ont été faits. Prévoir l'étape 5 de [publier-une-version.md](docs/publier-une-version.md) en cas de doute.
