# BookTek

Gestion de bibliothèque personnelle sous Windows, pilotée par la lecture d'ISBN : on scanne le code-barres d'un livre pour l'enregistrer, le prêter ou noter son retour.

- **Scan d'ISBN** avec une douchette code-barres ou au clavier.
- **Fiches remplies automatiquement** grâce aux catalogues en ligne (BnF, Google Books, Open Library).
- **Prêts** : emprunteur, date de retour prévue, retards signalés, historique.
- **Import** d'une collection *Book Collector* (`.bkc`), **export** CSV pour Excel.
- **Mise à jour automatique** depuis ce dépôt.

## Installation

1. Télécharger `BookTek.exe` depuis la [dernière release](https://github.com/HTModeLia/BookTek/releases/latest).
2. Le placer dans un dossier personnel (par exemple `Documents\BookTek`), puis le lancer.

Aucune installation n'est nécessaire. La base de données `booktek.db` est créée à côté de l'exécutable.

## Documentation

| Document | Pour qui | Contenu |
|---|---|---|
| [Guide d'utilisation](docs/guide-utilisateur.md) | Utilisateurs | Scanner, prêter, importer, sauvegarder, dépannage |
| [Mises à jour](docs/mises-a-jour.md) | Utilisateurs et développeurs | Fonctionnement de la mise à jour automatique |
| [Architecture](docs/architecture.md) | Développeurs | Modules, base de données, threads, sources en ligne, format `.bkc` |
| [Publier une version](docs/publier-une-version.md) | Mainteneurs | Procédure de release |
| [Historique des versions](CHANGELOG.md) | Tous | Nouveautés de chaque version |

## Développement

Python 3.10 ou plus récent ; seule la bibliothèque standard est utilisée (Tkinter, SQLite, urllib).

```
python main.py                              # lancer depuis les sources
python -m unittest discover -s tests        # tests
python tools/release.py --dry-run           # construire l'exe sans publier
```
