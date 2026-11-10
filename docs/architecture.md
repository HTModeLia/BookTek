# Architecture de BookTek

Ce document s'adresse aux développeurs. Le détail de chaque fonction est dans les docstrings du code ; ici, on donne la vue d'ensemble et les choix de conception.

## Principes

- **Python presque sans dépendances** : Tkinter pour l'interface, SQLite pour les données, urllib pour le réseau. Seule exception, Pillow, pour afficher les couvertures en JPEG (que Tk 8.6 ne lit pas) ; sans lui, l'application fonctionne mais n'affiche pas les couvertures. PyInstaller ne sert qu'à construire l'exe.
- **Un seul exécutable** (`BookTek.exe`, PyInstaller `--onefile`) et des données à côté : la base `booktek.db` et le dossier `covers/` (une image `<id du livre>.jpg` par couverture), et `settings.json` (réglages d'affichage : thème sombre, grands caractères). Une installation se fait par simple copie, et une sauvegarde aussi, à condition de copier les deux.
- **L'ISBN-13 normalisé comme clé** : tout code saisi, scanné ou importé passe par `isbn.normalize()` avant d'être comparé ou stocké.
- **L'interface ne bloque jamais** : tout ce qui touche au réseau tourne dans un thread.

## Modules

```
main.py                 point d'entrée (sources et PyInstaller)
booktek/
├── __init__.py         __version__
├── app.py              interface Tkinter, orchestration
├── db.py               base SQLite : livres, prêts
├── isbn.py             validation et normalisation des ISBN
├── lookup.py           recherche des fiches en ligne
├── bkc_import.py       lecture des fichiers Book Collector
└── updater.py          mise à jour automatique
tests/                  tests unitaires (unittest)
tools/release.py        publication d'une version
```

Dépendances entre modules :

```
app ──► db
 │ ──► isbn ◄── bkc_import
 │ ──► lookup ──► isbn
 │ ──► bkc_import
 └──► updater
```

Seul `app.py` dépend de Tkinter. Les autres modules sont testables sans interface.

## Données (`db.py`)

```
books                                   loans
─────────────────────                   ──────────────────────────
id          INTEGER PK  ◄──────────┐    id           INTEGER PK
isbn        TEXT UNIQUE (NULL ok)  └─── book_id      INTEGER FK (ON DELETE CASCADE)
title       TEXT NOT NULL               borrower     TEXT NOT NULL
authors     TEXT                        loan_date    TEXT  AAAA-MM-JJ
publisher   TEXT                        due_date     TEXT  AAAA-MM-JJ (NULL = sans échéance)
year        TEXT                        return_date  TEXT  NULL = prêt en cours
pages       TEXT
location    TEXT  meuble / pièce        index unique partiel :
shelf       TEXT  étage (1 = haut)        loans(book_id) WHERE return_date IS NULL
box         TEXT
depth       TEXT  rangée (1 = devant)   borrowers (annuaire)
read_date   TEXT  AAAA-MM-JJ            ──────────────────────────
notes       TEXT                        name   TEXT PK  ◄── loans.borrower (par valeur)
added_at    TEXT                        phone, email, notes  TEXT
```

Le code d'emplacement affiché (`Salon › É2 › B3 › R2`) est calculé par `app.place()` : rien n'est stocké sous cette forme.

Choix de conception :

- **Prêt en cours = `return_date IS NULL`**. L'index unique partiel garantit au niveau de la base qu'un livre n'a qu'un seul prêt en cours. Les prêts rendus forment l'historique.
- **ISBN vide stocké en `NULL`**, et non en chaîne vide : la contrainte `UNIQUE` autorise plusieurs `NULL`, donc plusieurs livres sans ISBN.
- **Dates en texte ISO** : elles se comparent comme des chaînes, et les retards se calculent en SQL (`due_date < date du jour`).
- **`year` et `pages` en texte** : les catalogues renvoient des valeurs approximatives ou vides.
- **Prêts reliés à l'annuaire par le nom**, et non par une clé : `loans.borrower` contient le nom. Un prêt ajoute le nom à `borrowers` s'il n'y est pas. Un renommage (`save_borrower`) met aussi à jour les prêts. Supprimer un contact conserve ses prêts passés.
- **Durées non stockées** : le temps écoulé d'un prêt est calculé à l'affichage (`app.days_since()`).

Toutes les écritures passent par `Library`, qui valide les entrées et lève `ValueError` avec un message en français, affichable tel quel.

### Faire évoluer le schéma

`SCHEMA` décrit le schéma initial (version 1.0). Les évolutions suivantes sont des scripts SQL ajoutés à la liste `db.MIGRATIONS`. À l'ouverture, `Library.__init__` applique les migrations que la base n'a pas encore reçues, en se basant sur `PRAGMA user_version`. Chaque migration et son numéro sont écrits dans une même transaction.

Pour faire évoluer le schéma, **ajoutez** une migration en fin de liste, sans jamais modifier une migration déjà publiée. Testez ensuite l'ouverture d'une base au format précédent (voir `V12Test.test_migration_keeps_old_data`).

| `user_version` | Version | Contenu |
|---|---|---|
| 0 | 1.0, 1.1 | Schéma initial |
| 1 | 1.2 | Rangement (`shelf`, `box`, `depth`), `read_date`, table `borrowers` |

## Tri des tableaux

Un clic sur un en-tête trie la colonne avec `app.sort_key()` :
- les nombres sont comparés en valeur (É2 avant É10) ;
- les dates `JJ/MM/AAAA` sont triées chronologiquement ;
- les auteurs sont triés par le dernier mot du premier auteur, supposé être le nom de famille.

Le tri en cours (`tree._sort_state`) est réappliqué après chaque rafraîchissement par `App._resort()`.

## Interface (`app.py`)

- `App` (fenêtre principale) construit l'interface dans `_build()` et recharge tout depuis la base avec `refresh()` après chaque modification. C'est simple et suffisant pour quelques milliers de livres.
- Les fenêtres modales héritent de `Dialog` : `show()` bloque jusqu'à la fermeture et retourne `result` (`None` si annulé).
  - `BookForm` : saisie ou modification d'une fiche ;
  - `LendDialog` : saisie d'un prêt ;
  - `BookCard` : fiche d'un livre scanné, avec ses actions.
- **Douchette** : elle tape le code puis Entrée dans le champ qui a le focus. Le champ de scan récupère donc le focus après chaque action (`refocus()`, touche F2). Entrée n'est pas liée dans `BookCard`, pour qu'un scan fait par erreur ne déclenche pas d'action.
- **Flux d'un scan** : `on_scan()` normalise le code puis, selon le mode et l'existence du livre, ouvre `BookCard`, enregistre un retour, ou appelle `register()` pour lancer la recherche en ligne.

### Threads

Ni Tkinter ni la connexion SQLite ne peuvent être utilisés hors du thread principal. Règle unique : **un thread secondaire n'appelle que `App.post(fn, *args)`**, qui dépose l'appel dans une file. `App._poll()` vide cette file toutes les 100 ms dans le thread principal.

```
thread secondaire                     thread principal (Tkinter)
─────────────────                     ──────────────────────────
info = lookup.fetch(isbn)
self.post(self._registered, …) ──►  queue ──► _poll() ──► _registered(…) ──► base, interface
```

Trois traitements utilisent ce schéma :

| Traitement | Méthode lancée dans le thread | Méthode de retour |
|---|---|---|
| Recherche d'un nouveau livre | `lookup.fetch` (dans `register`) | `_registered` |
| Complément des fiches | `work` (dans `enrich`) | `apply` |
| Mises à jour | `_update_worker` | `_update_done`, `_update_failed` |

## Recherche en ligne (`lookup.py`)

Chaque source est une fonction `source(isbn) -> dict` qui retourne les champs trouvés (`title`, `authors`, `publisher`, `year`, `pages`). `fetch()` interroge les sources dans l'ordre et garde, pour chaque champ, la première valeur trouvée. Une source en erreur est ignorée.

| Source | Ordre (ISBN 978-2 / 979-10) | Ordre (autres) | Remarques |
|---|---|---|---|
| BnF (API SRU, Dublin Core) | 1 | 3 | Excellente pour les éditions françaises, y compris les clubs. Repli sur l'ISBN-10 pour les anciennes notices. |
| Google Books | 2 | 1 | Erreur 429 fréquente sans clé d'API |
| Open Library | 3 | 2 | Surtout anglophone |

Ajouter une source : écrire une fonction avec la même signature, puis l'insérer dans les tuples `sources` de `fetch()`.

## Import Book Collector (`bkc_import.py`)

Le format `.bkc` est binaire et non documenté. On n'en fait pas un décodage complet : on extrait l'ISBN et le titre en s'appuyant sur une structure observée.

- Les textes sont en UTF-16 LE. Les chaînes courtes sont précédées de l'octet `0x02` puis de leur longueur en caractères.
- Chaque livre contient le chemin de sa vignette (`...\Thumbnails\<hash>.png`), qui sert de point de repère :
  - l'ISBN est la dernière chaîne de type ISBN dans les 600 octets qui précèdent ;
  - le titre est la première chaîne lisible préfixée par sa longueur dans les 80 octets qui suivent.
- Les auteurs sont reliés aux livres par des index binaires non décodés. Ils sont récupérés ensuite en ligne (`App.enrich()`).

Le test `BkcImportTest.test_parse_sample` vérifie l'extraction sur un fichier réel (59 livres). Ce fichier contient des données personnelles et n'est pas versionné : le test est sauté s'il est absent.

## Mise à jour automatique (`updater.py`)

Voir [mises-a-jour.md](mises-a-jour.md).

## Tests

```
python -m unittest discover -s tests
```

| Fichier | Couverture |
|---|---|
| `tests/test_core.py` | ISBN (normalisation, conversion, clés), base (prêts, retours, recherche, complément), import `.bkc`, analyse des auteurs BnF |
| `tests/test_updater.py` | Comparaison de versions, téléchargement et vérification SHA-256, rejet d'un fichier altéré, remplacement de l'exe |

Ne sont pas couverts automatiquement : l'interface Tkinter et les appels réels aux catalogues en ligne. Ils se vérifient en lançant l'application (`python main.py`).
