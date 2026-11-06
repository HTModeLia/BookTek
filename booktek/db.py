"""Stockage SQLite de la bibliothèque et des prêts."""
import datetime as dt
import sqlite3

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
    return dt.date.today().isoformat()


class Library:
    def __init__(self, path):
        self.con = sqlite3.connect(path)
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(SCHEMA)

    # ---- livres -------------------------------------------------------
    def book(self, book_id):
        return self.con.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()

    def book_by_isbn(self, isbn):
        return self.con.execute("SELECT * FROM books WHERE isbn = ?", (isbn,)).fetchone()

    @staticmethod
    def _values(data):
        vals = {f: str(data.get(f) or "").strip() for f in FIELDS}
        vals["isbn"] = vals["isbn"] or None
        if not vals["title"]:
            raise ValueError("Le titre est obligatoire.")
        return vals

    def add_book(self, data):
        vals = self._values(data)
        with self.con:
            cur = self.con.execute(
                f"INSERT INTO books ({', '.join(FIELDS)}, added_at) "
                f"VALUES ({', '.join('?' * len(FIELDS))}, ?)",
                (*vals.values(), dt.datetime.now().isoformat(timespec="seconds")),
            )
        return cur.lastrowid

    def update_book(self, book_id, data):
        vals = self._values(data)
        with self.con:
            self.con.execute(
                f"UPDATE books SET {', '.join(f + ' = ?' for f in FIELDS)} WHERE id = ?",
                (*vals.values(), book_id),
            )

    def delete_book(self, book_id):
        if self.active_loan(book_id):
            raise ValueError("Ce livre est actuellement prêté : enregistrez d'abord son retour.")
        with self.con:
            self.con.execute("DELETE FROM books WHERE id = ?", (book_id,))

    def search(self, text=""):
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
        return self.con.execute(
            "SELECT id, isbn FROM books WHERE isbn IS NOT NULL AND (authors = '' OR publisher = '')"
        ).fetchall()

    def fill_missing(self, book_id, info):
        """Complète uniquement les champs vides du livre avec `info`."""
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
        return self.con.execute(
            "SELECT * FROM loans WHERE book_id = ? AND return_date IS NULL", (book_id,)
        ).fetchone()

    def lend(self, book_id, borrower, due_date):
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
        loan = self.active_loan(book_id)
        if loan is None:
            return None
        with self.con:
            self.con.execute("UPDATE loans SET return_date = ? WHERE id = ?", (today(), loan["id"]))
        return loan

    def active_loans(self):
        return self.con.execute(
            """SELECT l.*, b.title, b.isbn FROM loans l JOIN books b ON b.id = l.book_id
               WHERE l.return_date IS NULL ORDER BY l.due_date"""
        ).fetchall()

    def history(self, limit=1000):
        return self.con.execute(
            """SELECT l.*, b.title, b.isbn FROM loans l JOIN books b ON b.id = l.book_id
               ORDER BY l.loan_date DESC, l.id DESC LIMIT ?""",
            (limit,),
        ).fetchall()

    def borrowers(self):
        return [r[0] for r in self.con.execute(
            "SELECT borrower FROM loans GROUP BY borrower ORDER BY MAX(loan_date) DESC"
        )]

    def stats(self):
        q = lambda sql: self.con.execute(sql, (today(),) if "?" in sql else ()).fetchone()[0]
        return {
            "books": q("SELECT COUNT(*) FROM books"),
            "lent": q("SELECT COUNT(*) FROM loans WHERE return_date IS NULL"),
            "overdue": q("SELECT COUNT(*) FROM loans WHERE return_date IS NULL AND due_date < ?"),
        }
