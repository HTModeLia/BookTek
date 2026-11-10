"""Stockage SQLite de la bibliothèque et des prêts.

Le modèle tient en deux tables :

* ``books`` : une ligne par livre, identifiée par ``id``. L'ISBN (forme
  ISBN-13 normalisée, voir :mod:`booktek.isbn`) est unique mais facultatif,
  pour les livres anciens sans ISBN. Tous les champs descriptifs sont du texte
  (y compris ``year`` et ``pages``, souvent approximatifs ou absents).
* ``loans`` : un prêt par ligne. Un prêt est **en cours** tant que
  ``return_date`` est ``NULL`` ; un index unique partiel garantit qu'un livre
  n'a jamais plus d'un prêt en cours. Les prêts rendus constituent
  l'historique.
* ``borrowers`` : l'annuaire (nom unique, téléphone, e-mail, notes). Les
  prêts y font référence par le nom.

Les évolutions du schéma sont des scripts de :data:`MIGRATIONS`, appliqués
à l'ouverture selon ``PRAGMA user_version``.

Les dates sont stockées au format ISO ``AAAA-MM-JJ`` : elles se comparent
donc directement comme des chaînes (calcul des retards en SQL).
"""
import datetime as dt
import sqlite3

#: Champs éditables d'un livre, dans l'ordre d'affichage du formulaire.
#: Rangement : location (meuble/pièce) › shelf (étage) › box › depth (rangée, 1 = devant).
FIELDS = ("isbn", "title", "authors", "publisher", "year", "genre", "pages",
          "location", "shelf", "box", "depth", "read_date", "summary", "notes")

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id        INTEGER PRIMARY KEY,
    isbn      TEXT UNIQUE,
    title     TEXT NOT NULL,
    authors   TEXT DEFAULT '',
    publisher TEXT DEFAULT '',
    year      TEXT DEFAULT '',
    pages     TEXT DEFAULT '',
    location  TEXT DEFAULT '',
    notes     TEXT DEFAULT '',
    added_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS loans (
    id          INTEGER PRIMARY KEY,
    book_id     INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    borrower    TEXT NOT NULL,
    loan_date   TEXT NOT NULL,
    due_date    TEXT,
    return_date TEXT
);
-- Un livre ne peut avoir qu'un seul prêt en cours.
CREATE UNIQUE INDEX IF NOT EXISTS one_active_loan ON loans(book_id) WHERE return_date IS NULL;
"""

#: Migrations successives ; l'indice + 1 est la valeur de PRAGMA user_version
#: atteinte. Ne jamais modifier une migration publiée : en ajouter une.
MIGRATIONS = [
    # 1 : rangement détaillé, date de lecture, annuaire des emprunteurs
    """
    ALTER TABLE books ADD COLUMN shelf TEXT DEFAULT '';
    ALTER TABLE books ADD COLUMN box TEXT DEFAULT '';
    ALTER TABLE books ADD COLUMN depth TEXT DEFAULT '';
    ALTER TABLE books ADD COLUMN read_date TEXT DEFAULT '';
    CREATE TABLE borrowers (
        name  TEXT PRIMARY KEY,
        phone TEXT DEFAULT '',
        email TEXT DEFAULT '',
        notes TEXT DEFAULT ''
    );
    INSERT OR IGNORE INTO borrowers (name) SELECT DISTINCT borrower FROM loans;
    """,
    # 2 : résumé (la couverture est un fichier, voir App.cover_path)
    "ALTER TABLE books ADD COLUMN summary TEXT DEFAULT ''",
    # 3 : genre (filtre et tri de la bibliothèque)
    "ALTER TABLE books ADD COLUMN genre TEXT DEFAULT ''",
]


def today():
    """Date du jour au format ISO (``AAAA-MM-JJ``)."""
    return dt.date.today().isoformat()


class Library:
    """Accès à la base : livres, prêts et statistiques.

    Les lignes retournées sont des :class:`sqlite3.Row` (accès par nom de
    colonne, ex. ``row["title"]``). Les méthodes d'écriture valident leurs
    entrées et lèvent :class:`ValueError` avec un message en français,
    directement affichable à l'utilisateur.

    La connexion n'est utilisable que depuis le thread qui a créé l'objet
    (contrainte de :mod:`sqlite3`) : dans l'interface, toutes les écritures se
    font dans le thread Tkinter.
    """

    def __init__(self, path):
        """Ouvre (ou crée) la base ``path`` ; ``":memory:"`` pour une base temporaire."""
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")  # active ON DELETE CASCADE
        self.con.executescript(SCHEMA)
        version = self.con.execute("PRAGMA user_version").fetchone()[0]
        for i, script in enumerate(MIGRATIONS[version:], version + 1):
            # executescript valide la transaction en cours : migration + version dans le même script
            self.con.executescript(f"BEGIN; {script}; PRAGMA user_version = {i}; COMMIT;")

    # ---- livres -------------------------------------------------------
    def book(self, book_id):
        """Retourne le livre ``book_id``, ou ``None``."""
        return self.con.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()

    def book_by_isbn(self, isbn):
        """Retourne le livre d'ISBN ``isbn`` (forme normalisée), ou ``None``."""
        return self.con.execute("SELECT * FROM books WHERE isbn = ?", (isbn,)).fetchone()

    @staticmethod
    def _values(data):
        """Prépare les valeurs de :data:`FIELDS` à partir du dict ``data``.

        Les valeurs sont converties en texte et nettoyées ; un ISBN vide
        devient ``NULL`` (sinon la contrainte d'unicité empêcherait d'avoir
        plusieurs livres sans ISBN).
        """
        vals = {f: str(data.get(f) or "").strip() for f in FIELDS}
        vals["isbn"] = vals["isbn"] or None
        if not vals["title"]:
            raise ValueError("Le titre est obligatoire.")
        return vals

    def add_book(self, data):
        """Ajoute un livre décrit par le dict ``data`` et retourne son ``id``.

        Lève :class:`sqlite3.IntegrityError` si l'ISBN existe déjà : vérifier
        au préalable avec :meth:`book_by_isbn`.
        """
        vals = self._values(data)
        with self.con:
            cur = self.con.execute(
                f"INSERT INTO books ({', '.join(FIELDS)}, added_at) "
                f"VALUES ({', '.join('?' * len(FIELDS))}, ?)",
                (*vals.values(), dt.datetime.now().isoformat(timespec="seconds")),
            )
        return cur.lastrowid

    def update_book(self, book_id, data):
        """Remplace tous les champs de :data:`FIELDS` du livre ``book_id``."""
        vals = self._values(data)
        with self.con:
            self.con.execute(
                f"UPDATE books SET {', '.join(f + ' = ?' for f in FIELDS)} WHERE id = ?",
                (*vals.values(), book_id),
            )

    def delete_book(self, book_id):
        """Supprime un livre et son historique de prêts.

        Refusé (:class:`ValueError`) si le livre est prêté, pour ne pas perdre
        la trace d'un livre qui n'est pas rentré.
        """
        if self.active_loan(book_id):
            raise ValueError("Ce livre est actuellement prêté : enregistrez d'abord son retour.")
        with self.con:
            self.con.execute("DELETE FROM books WHERE id = ?", (book_id,))

    def search(self, text=""):
        """Recherche plein texte simple (titre, auteurs, année, genre, ISBN, emplacement, emprunteur).

        Chaque ligne contient les colonnes de ``books`` plus ``borrower`` et
        ``due_date`` du prêt en cours (``None`` si le livre est disponible).
        Sans ``text``, retourne toute la bibliothèque, triée par auteur puis
        titre.
        """
        like = f"%{text.strip()}%"
        return self.con.execute(
            """SELECT b.*, l.borrower, l.due_date
               FROM books b
               LEFT JOIN loans l ON l.book_id = b.id AND l.return_date IS NULL
               WHERE b.title LIKE ? OR b.authors LIKE ? OR b.year LIKE ? OR b.genre LIKE ?
                  OR IFNULL(b.isbn, '') LIKE ? OR b.location LIKE ? OR IFNULL(l.borrower, '') LIKE ?
               ORDER BY b.authors COLLATE NOCASE, b.title COLLATE NOCASE""",
            (like,) * 7,
        ).fetchall()

    def books_missing_info(self):
        """Livres ayant un ISBN mais sans auteur, éditeur, nombre de pages, résumé ou genre (à compléter en ligne)."""
        return self.con.execute(
            "SELECT id, isbn FROM books WHERE isbn IS NOT NULL"
            " AND (authors = '' OR publisher = '' OR pages = '' OR summary = '' OR genre = '')"
        ).fetchall()

    def fill_missing(self, book_id, info):
        """Complète uniquement les champs vides du livre avec ``info``.

        Les données déjà saisies (titre importé, corrections manuelles…) ne
        sont jamais écrasées. Retourne ``True`` si au moins un champ a changé.
        """
        row = self.book(book_id)
        if row is None:
            return False
        data = {f: row[f] for f in FIELDS}
        changed = False
        for f in ("title", "authors", "publisher", "year", "genre", "pages", "summary"):
            if not data[f] and info.get(f):
                data[f] = info[f]
                changed = True
        if changed:
            self.update_book(book_id, data)
        return changed

    # ---- prêts --------------------------------------------------------
    def active_loan(self, book_id):
        """Prêt en cours du livre, ou ``None`` s'il est disponible."""
        return self.con.execute(
            "SELECT * FROM loans WHERE book_id = ? AND return_date IS NULL", (book_id,)
        ).fetchone()

    def lend(self, book_id, borrower, due_date):
        """Enregistre le prêt du livre à ``borrower``, daté d'aujourd'hui.

        ``due_date`` est la date de retour prévue (ISO) ou ``None``. Lève
        :class:`ValueError` si l'emprunteur est vide ou si le livre est déjà
        prêté.
        """
        borrower = borrower.strip()
        if not borrower:
            raise ValueError("Le nom de l'emprunteur est obligatoire.")
        if self.active_loan(book_id):
            raise ValueError("Ce livre est déjà prêté.")
        with self.con:
            self.con.execute("INSERT OR IGNORE INTO borrowers (name) VALUES (?)", (borrower,))
            self.con.execute(
                "INSERT INTO loans (book_id, borrower, loan_date, due_date) VALUES (?, ?, ?, ?)",
                (book_id, borrower, today(), due_date),
            )

    def return_book(self, book_id):
        """Clôt le prêt en cours (retour daté d'aujourd'hui).

        Retourne la ligne du prêt clôturé (utile pour afficher l'emprunteur),
        ou ``None`` si le livre n'était pas prêté.
        """
        loan = self.active_loan(book_id)
        if loan is None:
            return None
        with self.con:
            self.con.execute("UPDATE loans SET return_date = ? WHERE id = ?", (today(), loan["id"]))
        return loan

    def active_loans(self):
        """Prêts en cours avec titre et ISBN du livre, les échéances les plus proches d'abord."""
        return self.con.execute(
            """SELECT l.*, b.title, b.isbn FROM loans l JOIN books b ON b.id = l.book_id
               WHERE l.return_date IS NULL ORDER BY l.due_date"""
        ).fetchall()

    def history(self, limit=1000):
        """Tous les prêts (en cours et rendus), du plus récent au plus ancien."""
        return self.con.execute(
            """SELECT l.*, b.title, b.isbn FROM loans l JOIN books b ON b.id = l.book_id
               ORDER BY l.loan_date DESC, l.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    def borrowers(self):
        """Noms de l'annuaire, le dernier emprunteur d'abord (pour l'autocomplétion)."""
        return [r[0] for r in self.con.execute(
            """SELECT b.name FROM borrowers b LEFT JOIN loans l ON l.borrower = b.name
               GROUP BY b.name ORDER BY MAX(l.id) DESC, b.name COLLATE NOCASE"""
        )]

    # ---- annuaire -----------------------------------------------------
    def directory(self):
        """Annuaire : contact, prêts en cours, total des prêts et date du plus ancien prêt en cours."""
        return self.con.execute(
            """SELECT b.*,
                      COUNT(l.id) AS total,
                      COUNT(l.id) - COUNT(l.return_date) AS active,
                      MIN(CASE WHEN l.return_date IS NULL THEN l.loan_date END) AS oldest_active
               FROM borrowers b LEFT JOIN loans l ON l.borrower = b.name
               GROUP BY b.name ORDER BY b.name COLLATE NOCASE"""
        ).fetchall()

    def borrower(self, name):
        return self.con.execute("SELECT * FROM borrowers WHERE name = ?", (name,)).fetchone()

    def save_borrower(self, old_name, data):
        """Ajoute (``old_name`` None) ou modifie un contact ; un renommage suit dans les prêts."""
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("Le nom est obligatoire.")
        vals = (name, *((data.get(k) or "").strip() for k in ("phone", "email", "notes")))
        try:
            with self.con:
                if old_name is None:
                    self.con.execute("INSERT INTO borrowers (name, phone, email, notes) VALUES (?, ?, ?, ?)", vals)
                else:
                    self.con.execute("UPDATE borrowers SET name = ?, phone = ?, email = ?, notes = ? WHERE name = ?",
                                     (*vals, old_name))
                    self.con.execute("UPDATE loans SET borrower = ? WHERE borrower = ?", (name, old_name))
        except sqlite3.IntegrityError:
            raise ValueError(f"« {name} » existe déjà dans l'annuaire.") from None

    def delete_borrower(self, name):
        """Retire un contact de l'annuaire (l'historique de ses prêts est conservé)."""
        if self.con.execute("SELECT 1 FROM loans WHERE borrower = ? AND return_date IS NULL", (name,)).fetchone():
            raise ValueError("Cette personne a des livres en cours de prêt.")
        with self.con:
            self.con.execute("DELETE FROM borrowers WHERE name = ?", (name,))

    def stats(self):
        """Compteurs affichés en pied de fenêtre : livres, prêtés, en retard."""
        # Seule la requête des retards a un paramètre (la date du jour).
        q = lambda sql: self.con.execute(sql, (today(),) if "?" in sql else ()).fetchone()[0]
        return {
            "books": q("SELECT COUNT(*) FROM books"),
            "lent": q("SELECT COUNT(*) FROM loans WHERE return_date IS NULL"),
            "overdue": q("SELECT COUNT(*) FROM loans WHERE return_date IS NULL AND due_date < ?"),
        }
