"""Interface graphique BookTek (Tkinter)."""
import csv
import datetime as dt
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, bkc_import, lookup
from .db import FIELDS, Library
from .isbn import normalize

LOAN_DAYS = 21
LABELS = {
    "isbn": "ISBN", "title": "Titre", "authors": "Auteur(s)", "publisher": "Éditeur",
    "year": "Année", "pages": "Pages", "location": "Emplacement", "notes": "Notes",
}
COLORS = {"ok": "#1b7f3b", "warn": "#b36b00", "err": "#c0262d", "info": "#1f5fa8"}

try:
    import winsound
except ImportError:  # hors Windows
    winsound = None


def data_dir():
    """Dossier de la base : à côté de l'exe s'il est inscriptible, sinon %APPDATA%\\BookTek."""
    base = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0]))
    if os.access(base, os.W_OK):
        return base
    alt = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "BookTek")
    os.makedirs(alt, exist_ok=True)
    return alt


def fmt_date(iso):
    return dt.date.fromisoformat(iso).strftime("%d/%m/%Y") if iso else ""


def parse_date(text):
    return dt.datetime.strptime(text.strip(), "%d/%m/%Y").date()


# ---------------------------------------------------------------------------
# Boîtes de dialogue
# ---------------------------------------------------------------------------
class Dialog(tk.Toplevel):
    def __init__(self, master, title):
        super().__init__(master)
        self.title(title)
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self.body = ttk.Frame(self, padding=14)
        self.body.pack(fill="both", expand=True)
        self.bind("<Escape>", lambda e: self.destroy())

    def show(self):
        self.update_idletasks()
        m = self.master
        x = m.winfo_rootx() + (m.winfo_width() - self.winfo_width()) // 2
        y = m.winfo_rooty() + (m.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.wait_window()
        return self.result


class BookForm(Dialog):
    """Saisie / modification d'une fiche livre."""

    def __init__(self, master, data, title="Livre"):
        super().__init__(master, title)
        self.vars = {}
        for r, f in enumerate(FIELDS):
            ttk.Label(self.body, text=LABELS[f] + " :").grid(row=r, column=0, sticky="ne", padx=(0, 8), pady=3)
            if f == "notes":
                w = tk.Text(self.body, width=50, height=4, font=("Segoe UI", 10))
                w.insert("1.0", data.get(f) or "")
            else:
                w = ttk.Entry(self.body, width=52)
                w.insert(0, data.get(f) or "")
            w.grid(row=r, column=1, sticky="we", pady=3)
            self.vars[f] = w
        bar = ttk.Frame(self.body)
        bar.grid(row=len(FIELDS), column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(bar, text="Enregistrer", command=self.save).pack(side="left", padx=4)
        ttk.Button(bar, text="Annuler", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda e: self.save() if not isinstance(e.widget, tk.Text) else None)
        focus = "title" if data.get("isbn") and not data.get("title") else "location" if data.get("title") else "isbn"
        self.vars[focus].focus_set()

    def save(self):
        out = {f: (w.get("1.0", "end").strip() if isinstance(w, tk.Text) else w.get().strip())
               for f, w in self.vars.items()}
        if out["isbn"]:
            isbn = normalize(out["isbn"])
            if not isbn:
                messagebox.showerror("ISBN invalide", "L'ISBN saisi n'est pas valide (laisser vide si le livre n'en a pas).", parent=self)
                return
            out["isbn"] = isbn
        if not out["title"]:
            messagebox.showerror("Titre manquant", "Le titre est obligatoire.", parent=self)
            return
        self.result = out
        self.destroy()


class LendDialog(Dialog):
    def __init__(self, master, book, borrowers):
        super().__init__(master, "Prêter un livre")
        ttk.Label(self.body, text=book["title"], font=("Segoe UI", 11, "bold"), wraplength=380).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        ttk.Label(self.body, text="Emprunteur :").grid(row=1, column=0, sticky="e", padx=(0, 8), pady=3)
        self.who = ttk.Combobox(self.body, values=borrowers, width=32)
        self.who.grid(row=1, column=1, sticky="we", pady=3)
        ttk.Label(self.body, text="Retour prévu le :").grid(row=2, column=0, sticky="e", padx=(0, 8), pady=3)
        self.due = ttk.Entry(self.body, width=14)
        self.due.insert(0, (dt.date.today() + dt.timedelta(days=LOAN_DAYS)).strftime("%d/%m/%Y"))
        self.due.grid(row=2, column=1, sticky="w", pady=3)
        bar = ttk.Frame(self.body)
        bar.grid(row=3, column=0, columnspan=2, pady=(10, 0), sticky="e")
        ttk.Button(bar, text="Prêter", command=self.ok).pack(side="left", padx=4)
        ttk.Button(bar, text="Annuler", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda e: self.ok())
        self.who.focus_set()

    def ok(self):
        who = self.who.get().strip()
        if not who:
            messagebox.showerror("Emprunteur manquant", "Indiquez le nom de l'emprunteur.", parent=self)
            return
        due_text = self.due.get().strip()
        due = None
        if due_text:
            try:
                due = parse_date(due_text).isoformat()
            except ValueError:
                messagebox.showerror("Date invalide", "Format attendu : JJ/MM/AAAA.", parent=self)
                return
        self.result = (who, due)
        self.destroy()


class BookCard(Dialog):
    """Fiche d'un livre scanné, avec les actions possibles."""

    def __init__(self, master, book, loan):
        super().__init__(master, "Livre")
        ttk.Label(self.body, text=book["title"], font=("Segoe UI", 13, "bold"), wraplength=440).pack(anchor="w")
        if book["authors"]:
            ttk.Label(self.body, text=book["authors"], font=("Segoe UI", 11)).pack(anchor="w")
        details = " · ".join(x for x in (book["isbn"], book["publisher"], book["year"], book["location"]) if x)
        ttk.Label(self.body, text=details, foreground="#666").pack(anchor="w", pady=(2, 10))
        if loan:
            late = loan["due_date"] and loan["due_date"] < dt.date.today().isoformat()
            msg = f"Prêté à {loan['borrower']} depuis le {fmt_date(loan['loan_date'])}"
            if loan["due_date"]:
                msg += f" — retour prévu le {fmt_date(loan['due_date'])}"
            tk.Label(self.body, text=msg + (" (EN RETARD)" if late else ""), fg=COLORS["err" if late else "warn"],
                     font=("Segoe UI", 10, "bold"), wraplength=440, justify="left").pack(anchor="w")
        else:
            tk.Label(self.body, text="Disponible", fg=COLORS["ok"], font=("Segoe UI", 10, "bold")).pack(anchor="w")
        bar = ttk.Frame(self.body)
        bar.pack(anchor="e", pady=(14, 0))
        main = ttk.Button(bar, text="Enregistrer le retour" if loan else "Prêter…",
                          command=lambda: self.choose("return" if loan else "lend"))
        main.pack(side="left", padx=4)
        ttk.Button(bar, text="Modifier…", command=lambda: self.choose("edit")).pack(side="left", padx=4)
        ttk.Button(bar, text="Fermer", command=self.destroy).pack(side="left")
        main.focus_set()  # Espace = action principale

    def choose(self, action):
        self.result = action
        self.destroy()


# ---------------------------------------------------------------------------
# Fenêtre principale
# ---------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self, db_path):
        super().__init__()
        self.title(f"BookTek {__version__}")
        self.geometry("1100x700")
        self.minsize(820, 520)
        self.lib = Library(db_path)
        self.db_path = db_path
        self.q = queue.Queue()
        self.pending = set()  # ISBN en cours de recherche en ligne
        self._build()
        self.refresh()
        self.after(100, self._poll)
        self.set_status(f"Prêt. Scannez un ISBN. (Base : {db_path})", "info")

    # ---- construction ---------------------------------------------------
    def _build(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        style.configure("Treeview", rowheight=24)

        menubar = tk.Menu(self)
        m = tk.Menu(menubar, tearoff=False)
        m.add_command(label="Importer une collection Book Collector (.bkc)…", command=self.import_bkc)
        m.add_command(label="Compléter les fiches via Internet", command=self.enrich)
        m.add_command(label="Exporter en CSV…", command=self.export_csv)
        m.add_separator()
        m.add_command(label="Quitter", command=self.destroy)
        menubar.add_cascade(label="Fichier", menu=m)
        self.config(menu=menubar)

        top = ttk.Frame(self, padding=(12, 10, 12, 4))
        top.pack(fill="x")
        ttk.Label(top, text="ISBN :", font=("Segoe UI", 14)).pack(side="left")
        self.scan = ttk.Entry(top, font=("Consolas", 18), width=20)
        self.scan.pack(side="left", padx=8)
        self.scan.bind("<Return>", self.on_scan)
        ttk.Button(top, text="OK", command=self.on_scan).pack(side="left")

        modes = ttk.LabelFrame(top, text="Mode de scan", padding=(8, 2))
        modes.pack(side="left", padx=16)
        self.mode = tk.StringVar(value="auto")
        for val, txt in (("auto", "Automatique"), ("add", "Ajout rapide"), ("return", "Retour rapide")):
            ttk.Radiobutton(modes, text=txt, value=val, variable=self.mode,
                            command=lambda: self.scan.focus_set()).pack(side="left", padx=4)

        self.status = tk.Label(self, anchor="w", font=("Segoe UI", 12, "bold"), padx=14, pady=4)
        self.status.pack(fill="x")

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=12, pady=(4, 0))

        # Onglet bibliothèque
        lib = ttk.Frame(self.nb, padding=6)
        self.nb.add(lib, text="Bibliothèque")
        bar = ttk.Frame(lib)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Label(bar, text="Rechercher :").pack(side="left")
        self.search = tk.StringVar()
        self.search.trace_add("write", lambda *a: self.refresh_books())
        ttk.Entry(bar, textvariable=self.search, width=30).pack(side="left", padx=6)
        for txt, cmd in (("Supprimer", self.delete_selected), ("Modifier…", self.edit_selected),
                         ("Prêter / Rendre…", self.open_selected), ("Ajouter manuellement…", self.add_manual)):
            ttk.Button(bar, text=txt, command=cmd).pack(side="right", padx=3)
        self.books = self._tree(lib, (("isbn", "ISBN", 120), ("title", "Titre", 330), ("authors", "Auteur(s)", 180),
                                      ("publisher", "Éditeur", 130), ("year", "Année", 55),
                                      ("location", "Emplacement", 110), ("status", "Statut", 170)))
        self.books.bind("<Double-1>", lambda e: self.open_selected())

        # Onglet prêts en cours
        loans = ttk.Frame(self.nb, padding=6)
        self.nb.add(loans, text="Prêts en cours")
        bar = ttk.Frame(loans)
        bar.pack(fill="x", pady=(0, 6))
        ttk.Button(bar, text="Enregistrer le retour", command=self.return_selected_loan).pack(side="right")
        self.loans = self._tree(loans, (("title", "Titre", 380), ("borrower", "Emprunteur", 170),
                                        ("loan", "Prêté le", 90), ("due", "Retour prévu", 100), ("late", "Retard", 90)))
        self.loans.tag_configure("late", foreground=COLORS["err"])

        # Onglet historique
        hist = ttk.Frame(self.nb, padding=6)
        self.nb.add(hist, text="Historique des prêts")
        self.hist = self._tree(hist, (("title", "Titre", 400), ("borrower", "Emprunteur", 170),
                                      ("loan", "Prêté le", 90), ("ret", "Rendu le", 90)))

        self.footer = ttk.Label(self, padding=(14, 4))
        self.footer.pack(fill="x")
        self.bind_all("<F2>", lambda e: self.scan.focus_set())
        self.scan.focus_set()

    def _tree(self, parent, cols):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for key, label, width in cols:
            tree.heading(key, text=label, command=lambda k=key: self._sort(tree, k))
            tree.column(key, width=width, anchor="w")
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        return tree

    @staticmethod
    def _sort(tree, col):
        desc = getattr(tree, "_sort_state", None) == (col, False)
        rows = [(tree.set(i, col).lower(), i) for i in tree.get_children("")]
        rows.sort(reverse=desc)
        for idx, (_, i) in enumerate(rows):
            tree.move(i, "", idx)
        tree._sort_state = (col, desc)

    # ---- utilitaires ----------------------------------------------------
    def set_status(self, msg, kind="info"):
        self.status.config(text=msg, fg=COLORS[kind])
        if kind == "err" and winsound:
            winsound.MessageBeep(winsound.MB_ICONHAND)

    def post(self, fn, *args):
        """Appelé depuis un thread : exécute fn(*args) dans le thread de l'interface."""
        self.q.put((fn, args))

    def _poll(self):
        try:
            while True:
                fn, args = self.q.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.after(100, self._poll)

    def refocus(self):
        self.scan.focus_set()

    # ---- rafraîchissement -----------------------------------------------
    def refresh(self):
        self.refresh_books()
        today = dt.date.today()
        self.loans.delete(*self.loans.get_children())
        for r in self.lib.active_loans():
            late = (today - dt.date.fromisoformat(r["due_date"])).days if r["due_date"] else 0
            self.loans.insert("", "end", iid=str(r["book_id"]), tags=("late",) if late > 0 else (),
                              values=(r["title"], r["borrower"], fmt_date(r["loan_date"]),
                                      fmt_date(r["due_date"]), f"{late} j" if late > 0 else ""))
        self.hist.delete(*self.hist.get_children())
        for r in self.lib.history():
            self.hist.insert("", "end", values=(r["title"], r["borrower"], fmt_date(r["loan_date"]),
                                                fmt_date(r["return_date"]) or "en cours"))
        s = self.lib.stats()
        self.footer.config(text=f"{s['books']} livres · {s['lent']} prêtés · {s['overdue']} en retard")
        self.nb.tab(1, text=f"Prêts en cours ({s['lent']})")

    def refresh_books(self):
        self.books.delete(*self.books.get_children())
        for r in self.lib.search(self.search.get()):
            status = f"Prêté à {r['borrower']}" if r["borrower"] else "Disponible"
            self.books.insert("", "end", iid=str(r["id"]), values=(
                r["isbn"] or "", r["title"], r["authors"], r["publisher"], r["year"], r["location"], status))

    def select_book(self, book_id):
        self.nb.select(0)
        iid = str(book_id)
        if self.books.exists(iid):
            self.books.selection_set(iid)
            self.books.see(iid)

    # ---- scan -------------------------------------------------------------
    def on_scan(self, event=None):
        raw = self.scan.get().strip()
        self.scan.delete(0, "end")
        if not raw:
            return
        isbn = normalize(raw)
        if not isbn:
            self.set_status(f"« {raw} » n'est pas un ISBN valide.", "err")
            return
        book = self.lib.book_by_isbn(isbn)
        mode = self.mode.get()
        if mode == "return":
            if not book:
                self.set_status(f"{isbn} : livre absent de la bibliothèque.", "err")
            else:
                loan = self.lib.return_book(book["id"])
                if loan:
                    self.set_status(f"Retour enregistré : « {book['title']} » (rendu par {loan['borrower']}).", "ok")
                    self.refresh()
                else:
                    self.set_status(f"« {book['title']} » n'était pas prêté.", "warn")
            return
        if book:
            if mode == "add":
                self.set_status(f"Déjà dans la bibliothèque : « {book['title']} ».", "warn")
                self.select_book(book["id"])
            else:
                self.select_book(book["id"])
                self.book_actions(book)
            return
        self.register(isbn, quick=(mode == "add"))

    def register(self, isbn, quick):
        if isbn in self.pending:
            return
        self.pending.add(isbn)
        self.set_status(f"{isbn} : nouveau livre, recherche des informations en ligne…", "info")
        threading.Thread(target=lambda: self.post(self._registered, isbn, lookup.fetch(isbn), quick),
                         daemon=True).start()

    def _registered(self, isbn, info, quick):
        self.pending.discard(isbn)
        if self.lib.book_by_isbn(isbn):  # ajouté entre-temps
            return
        if quick and info:
            book_id = self.lib.add_book({"isbn": isbn, **info})
            self.set_status(f"Ajouté : « {info['title']} »{' — ' + info['authors'] if info.get('authors') else ''}", "ok")
        else:
            if not info:
                self.set_status(f"{isbn} : introuvable en ligne, saisie manuelle.", "warn")
            data = BookForm(self, {"isbn": isbn, **(info or {})}, "Nouveau livre").show()
            self.refocus()
            if not data:
                self.set_status("Enregistrement annulé.", "warn")
                return
            try:
                book_id = self.lib.add_book(data)
            except Exception as exc:
                messagebox.showerror("Erreur", str(exc), parent=self)
                return
            self.set_status(f"Ajouté : « {data['title']} ».", "ok")
        self.refresh()
        self.select_book(book_id)

    # ---- actions sur un livre ---------------------------------------------
    def book_actions(self, book):
        loan = self.lib.active_loan(book["id"])
        action = BookCard(self, book, loan).show()
        if action == "lend":
            self.lend(book)
        elif action == "return":
            self.lib.return_book(book["id"])
            self.set_status(f"Retour enregistré : « {book['title']} » (rendu par {loan['borrower']}).", "ok")
        elif action == "edit":
            self.edit(book)
        self.refresh()
        self.refocus()

    def lend(self, book):
        res = LendDialog(self, book, self.lib.borrowers()).show()
        if not res:
            return
        who, due = res
        try:
            self.lib.lend(book["id"], who, due)
        except ValueError as exc:
            messagebox.showerror("Prêt impossible", str(exc), parent=self)
            return
        suffix = f", retour prévu le {fmt_date(due)}" if due else ""
        self.set_status(f"« {book['title']} » prêté à {who}{suffix}.", "ok")

    def edit(self, book):
        data = BookForm(self, dict(book), "Modifier le livre").show()
        if not data:
            return
        try:
            self.lib.update_book(book["id"], data)
            self.set_status(f"Fiche modifiée : « {data['title']} ».", "ok")
        except Exception as exc:
            messagebox.showerror("Erreur", str(exc), parent=self)

    def _selected(self):
        sel = self.books.selection()
        if not sel:
            messagebox.showinfo("Aucune sélection", "Sélectionnez d'abord un livre dans la liste.", parent=self)
            return None
        return self.lib.book(int(sel[0]))

    def open_selected(self):
        book = self._selected()
        if book:
            self.book_actions(book)

    def edit_selected(self):
        book = self._selected()
        if book:
            self.edit(book)
            self.refresh()

    def delete_selected(self):
        book = self._selected()
        if not book or not messagebox.askyesno("Supprimer", f"Supprimer « {book['title']} » ?", parent=self):
            return
        try:
            self.lib.delete_book(book["id"])
            self.set_status(f"Supprimé : « {book['title']} ».", "ok")
        except ValueError as exc:
            messagebox.showerror("Suppression impossible", str(exc), parent=self)
        self.refresh()

    def add_manual(self):
        data = BookForm(self, {}, "Nouveau livre").show()
        if data:
            if data["isbn"] and self.lib.book_by_isbn(data["isbn"]):
                messagebox.showwarning("Doublon", "Un livre avec cet ISBN existe déjà.", parent=self)
            else:
                self.select_book(self.lib.add_book(data))
                self.set_status(f"Ajouté : « {data['title']} ».", "ok")
                self.refresh()
        self.refocus()

    def return_selected_loan(self):
        sel = self.loans.selection()
        if not sel:
            return
        book = self.lib.book(int(sel[0]))
        loan = self.lib.return_book(book["id"])
        if loan:
            self.set_status(f"Retour enregistré : « {book['title']} » (rendu par {loan['borrower']}).", "ok")
        self.refresh()

    # ---- import / export / enrichissement ---------------------------------
    def import_bkc(self):
        path = filedialog.askopenfilename(parent=self, title="Collection Book Collector",
                                          filetypes=[("Book Collector", "*.bkc"), ("Tous les fichiers", "*.*")])
        if not path:
            return
        try:
            items = bkc_import.parse(path)
        except Exception as exc:
            messagebox.showerror("Import impossible", str(exc), parent=self)
            return
        added = skipped = 0
        for it in items:
            if it["isbn"] and self.lib.book_by_isbn(it["isbn"]):
                skipped += 1
                continue
            self.lib.add_book(it)
            added += 1
        self.refresh()
        msg = f"{added} livre(s) importé(s), {skipped} déjà présent(s)."
        self.set_status(msg, "ok")
        if added and messagebox.askyesno(
                "Import terminé", msg + "\n\nLe fichier .bkc ne contient pas les auteurs de façon exploitable.\n"
                "Compléter maintenant les fiches (auteur, éditeur, année…) via Internet ?", parent=self):
            self.enrich()

    def enrich(self):
        todo = [(r["id"], r["isbn"]) for r in self.lib.books_missing_info()]
        if not todo:
            self.set_status("Toutes les fiches sont déjà complètes.", "ok")
            return
        self.set_status(f"Recherche en ligne de {len(todo)} fiche(s)…", "info")
        found = [0]

        def apply(book_id, info, i):
            if info and self.lib.fill_missing(book_id, info):
                found[0] += 1
            self.set_status(f"Recherche en ligne : {i}/{len(todo)} ({found[0]} complétée(s))…", "info")
            if i == len(todo):
                self.refresh()
                self.set_status(f"Terminé : {found[0]} fiche(s) complétée(s) sur {len(todo)}.", "ok")

        def work():
            for i, (book_id, isbn) in enumerate(todo, 1):
                self.post(apply, book_id, lookup.fetch(isbn), i)

        threading.Thread(target=work, daemon=True).start()

    def export_csv(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".csv", initialfile="bibliotheque.csv",
                                            filetypes=[("CSV", "*.csv")])
        if not path:
            return
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow([LABELS[k] for k in FIELDS] + ["Prêté à", "Retour prévu"])
            for r in self.lib.search():
                w.writerow([r[k] for k in FIELDS] + [r["borrower"] or "", fmt_date(r["due_date"])])
        self.set_status(f"Exporté : {path}", "ok")


def main():
    db_path = os.path.join(data_dir(), "booktek.db")
    App(db_path).mainloop()
