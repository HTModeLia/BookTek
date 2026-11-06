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

Les dates sont stockées au format ISO ``AAAA-MM-JJ`` : elles se comparent
donc directement comme des chaînes (calcul des retards en SQL).
"""
import datetime as dt
import sqlite3

#: Champs éditables d'un livre, dans l'ordre d'affichage du formulaire.
FIELDS = ("isbn", "title", "authors", "publisher", "year", "pages", "location", "notes")

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
        """Recherche plein texte simple (titre, auteurs, ISBN, emplacement, emprunteur).

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
               WHERE b.title LIKE ? OR b.authors LIKE ? OR IFNULL(b.isbn, '') LIKE ?
                  OR b.location LIKE ? OR IFNULL(l.borrower, '') LIKE ?
               ORDER BY b.authors COLLATE NOCASE, b.title COLLATE NOCASE""",
            (like,) * 5,
        ).fetchall()

    def books_missing_info(self):
        """Livres ayant un ISBN mais sans auteur ou sans éditeur (à compléter en ligne)."""
        return self.con.execute(
            "SELECT id, isbn FROM books WHERE isbn IS NOT NULL AND (authors = '' OR publisher = '')"
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
        for f in ("title", "authors", "publisher", "year", "pages"):
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
        """Noms des emprunteurs connus, le plus récent d'abord (pour l'autocomplétion)."""
        return [r[0] for r in self.con.execute(
            "SELECT borrower FROM loans GROUP BY borrower ORDER BY MAX(loan_date) DESC"
        )]

    def stats(self):
        """Compteurs affichés en pied de fenêtre : livres, prêtés, en retard."""
        # Seule la requête des retards a un paramètre (la date du jour).
        q = lambda sql: self.con.execute(sql, (today(),) if "?" in sql else ()).fetchone()[0]
        return {
            "books": q("SELECT COUNT(*) FROM books"),
            "lent": q("SELECT COUNT(*) FROM loans WHERE return_date IS NULL"),
            "overdue": q("SELECT COUNT(*) FROM loans WHERE return_date IS NULL AND due_date < ?"),
        }
