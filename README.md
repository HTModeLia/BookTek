# BookTek

Gestion de bibliothèque personnelle sous Windows, pilotée par la lecture d'ISBN (douchette code-barres ou clavier) : enregistrement des livres, prêts, retours et suivi des retards.

## Fonctionnalités

- **Scan d'ISBN** : ISBN-10, ISBN-13 avec ou sans tirets, codes EAN avec extension de prix. La clé de contrôle est vérifiée.
- **Trois modes de scan** :
  - *Automatique* : un livre inconnu est recherché en ligne puis enregistré après validation ; un livre connu ouvre sa fiche avec **Prêter** ou **Enregistrer le retour**.
  - *Ajout rapide* : chaque scan enregistre le livre directement, pour saisir une étagère entière.
  - *Retour rapide* : chaque scan clôt le prêt en cours.
- **Recherche en ligne** des informations (titre, auteurs, éditeur, année, pages), dans l'ordre :
  1. catalogue de la BnF (prioritaire pour les ISBN français 978-2 / 979-10, avec repli sur l'ISBN-10 pour les anciennes notices) ;
  2. Google Books (souvent limité sans clé d'API : erreur 429) ;
  3. Open Library.
- **Prêts** : emprunteur (avec mémoire des noms déjà saisis), date de retour prévue (21 jours par défaut), retards en rouge, historique complet.
- **Import** d'une collection Collectorz *Book Collector* (`.bkc`) : ISBN et titre de chaque fiche, puis complément automatique via Internet.
- **Export CSV** compatible Excel (séparateur `;`).

Les données sont stockées dans `booktek.db` (SQLite), à côté de l'exécutable, ou dans `%APPDATA%\BookTek` si ce dossier n'est pas accessible en écriture.

## Utilisation

Lancer `BookTek.exe`, ou depuis les sources :

```
python main.py
```

Seule la bibliothèque standard de Python est nécessaire (Python 3.10 ou plus récent, Tkinter inclus).

## Tests

```
python -m unittest discover -s tests
```

## Construire l'exécutable

```
pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name BookTek main.py
```

L'exécutable est généré dans `dist\BookTek.exe`.

## Structure

| Fichier | Rôle |
|---|---|
| `booktek/app.py` | Interface graphique (Tkinter) |
| `booktek/db.py` | Base SQLite : livres et prêts |
| `booktek/isbn.py` | Validation et normalisation des ISBN |
| `booktek/lookup.py` | Recherche en ligne (BnF, Google Books, Open Library) |
| `booktek/bkc_import.py` | Import des fichiers Book Collector `.bkc` |
| `tests/test_core.py` | Tests unitaires |
