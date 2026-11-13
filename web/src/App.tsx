// Interface BookTek : visuel de la maquette Electron, données et logique en Python (booktek/web.py).
import { useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, Search, Plus, Grid3X3, List, Handshake, BarChart3, Library, Barcode, Pencil, Trash2, RotateCcw, Download, Upload, X, Users, Mail, Phone, CalendarDays, UserRound, Info, RefreshCw, ImageIcon, Moon, Type, FileText, Globe, ArrowUpCircle, ShieldCheck, Clock } from 'lucide-react'

type Book = { id: number; isbn: string | null; title: string; authors: string; publisher: string; year: string; genre: string; pages: string; location: string; shelf: string; box: string; depth: string; read_date: string; summary: string; notes: string; borrower: string | null; due_date: string | null; place: string; cover: string }
type Loan = { id: number; book_id: number; borrower: string; loan_date: string; due_date: string | null; return_date: string | null; title: string }
type Borrower = { name: string; phone: string; email: string; notes: string; total: number; active: number; oldest_active: string | null }
type Data = { books: Book[]; loans: Loan[]; borrowers: Borrower[]; stats: { books: number; lent: number; overdue: number }; version: string; settings: Record<string, any>; today: string; loanDays: number; dbPath: string; backupDir: string; sources: string[][]; update: string | null }
type Kind = 'ok' | 'warn' | 'err' | 'info'
type Form = { id: number | null; data: Record<string, string>; cover: string; coverData?: string }

const api = () => (window as any).pywebview.api
const FIELDS = ['isbn', 'title', 'authors', 'publisher', 'year', 'genre', 'pages', 'location', 'shelf', 'box', 'depth', 'read_date', 'summary', 'notes']
const LABELS: Record<string, string> = { isbn: 'ISBN', title: 'Titre *', authors: 'Auteur(s)', publisher: 'Éditeur', year: 'Année', genre: 'Genre', pages: 'Pages', location: 'Meuble / pièce', shelf: 'Étage (1 = haut)', box: 'Box', depth: 'Rangée (1 = devant)', read_date: 'Lu le (JJ/MM/AAAA)', summary: 'Résumé', notes: 'Notes' }
// Champs remplacés par « Actualiser les informations » (comme BookForm.ONLINE de la version Tkinter)
const ONLINE = ['title', 'authors', 'publisher', 'year', 'genre', 'pages', 'summary']
const SEARCH_IN: Record<string, string> = { all: 'Tout', title: 'Titre', authors: 'Auteur', year: 'Année', genre: 'Genre' }
const SORTS: Record<string, string> = { title: 'Titre', authors: 'Auteur', year: 'Année', genre: 'Genre', place: 'Emplacement', read_date: 'Lu le' }
const GROUPS: Record<string, string> = { '': 'Pas de regroupement', authors: 'Par auteur', year: 'Par année', genre: 'Par genre' }
const NO_VALUE = '(non renseigné)'

const fmt = (iso?: string | null) => iso ? iso.split('-').reverse().join('/') : '—'
const days = (from: string, to: string) => Math.round((Date.parse(to) - Date.parse(from)) / 86400000)
const addDays = (iso: string, n: number) => new Date(Date.parse(iso) + n * 86400000).toISOString().slice(0, 10)
const errText = (e: any) => String(e?.message ?? e)

/** Clé de tri « naturelle » (voir sort_key de app.py) : nombres en valeur, dates JJ/MM/AAAA dans l'ordre, auteur par nom de famille. */
function sortKey(text: string, col = ''): (string | number)[] {
  text = text || ''
  // shortcut: nom = dernier mot du 1er auteur, faux pour « Ben Jelloun » ; ajouter un champ dédié si gênant
  if (col === 'authors') text = (text.split(',')[0].trim().split(/\s+/).pop() || '') + ' ' + text
  if (/^\d{2}\/\d{2}\/\d{4}$/.test(text)) text = text.split('/').reverse().join('-')
  return text.split(/(\d+)/).map(t => /^\d+$/.test(t) ? Number(t) : t.toLocaleLowerCase('fr'))
}
function compareKeys(a: (string | number)[], b: (string | number)[]) {
  for (let i = 0; i < Math.min(a.length, b.length); i++) {
    if (a[i] === b[i]) continue
    return typeof a[i] === 'number' ? (a[i] as number) - (b[i] as number) : String(a[i]).localeCompare(String(b[i]), 'fr')
  }
  return a.length - b.length
}
/** Groupes d'un livre : un par auteur, sinon la valeur du champ, NO_VALUE si vide. */
const groupNames = (value: string, field: string) => {
  const names = (field === 'authors' ? (value || '').split(',') : [value || '']).map(n => n.trim()).filter(Boolean)
  return names.length ? names : [NO_VALUE]
}
const readImage = (file: File) => new Promise<string>((ok, ko) => { const r = new FileReader(); r.onload = () => ok(String(r.result)); r.onerror = ko; r.readAsDataURL(file) })

export default function App() {
  const [data, setData] = useState<Data | null>(null)
  const [selected, setSelected] = useState<number | null>(null)
  const [section, setSection] = useState<'library' | 'loans' | 'borrowers' | 'stats' | 'backups' | 'about'>('library')
  const [backups, setBackups] = useState<{ name: string; date: string; size: number }[]>([])
  const [backupBusy, setBackupBusy] = useState(false)
  const [query, setQuery] = useState('')
  const [searchIn, setSearchIn] = useState('all')
  const [sortBy, setSortBy] = useState('authors')
  const [desc, setDesc] = useState(false)
  const [groupBy, setGroupBy] = useState('')
  const [groupValue, setGroupValue] = useState<string | null>(null)
  const [view, setView] = useState<'grid' | 'list'>('grid')
  const [scan, setScan] = useState('')
  const [mode, setMode] = useState<'auto' | 'add' | 'return'>('auto')
  const [status, setStatusState] = useState<{ text: string; kind: Kind }>({ text: 'Prêt. Scannez un ISBN.', kind: 'info' })
  const [busy, setBusy] = useState(false)
  const [form, setForm] = useState<Form | null>(null)
  const [picker, setPicker] = useState<{ images: string[]; title: string; pick: (img: string) => void } | null>(null)
  const [zoom, setZoom] = useState(170)
  const [lendBook, setLendBook] = useState<Book | null>(null)
  const [lendWho, setLendWho] = useState('')
  const [lendDue, setLendDue] = useState('')
  const [person, setPerson] = useState<{ old: string | null; data: Record<string, string> } | null>(null)
  const [menu, setMenu] = useState<{ x: number; y: number; book: Book } | null>(null)
  const [loanFilter, setLoanFilter] = useState<'all' | 'active' | 'overdue' | 'returned'>('active')
  const [loanQuery, setLoanQuery] = useState('')
  const [update, setUpdate] = useState<{ version: string; notes: string } | null>(null)
  const scanRef = useRef<HTMLInputElement>(null)
  const actionRef = useRef<HTMLButtonElement>(null)
  const [focusAction, setFocusAction] = useState(0)

  const setStatus = (text: string, kind: Kind = 'info') => setStatusState({ text, kind })
  useEffect(() => { if (section === 'backups') loadBackups() }, [section])
  const refocus = () => setTimeout(() => scanRef.current?.focus(), 0)
  async function reload() { const d: Data = await api().load(); setData(d); return d }
  /** Appel à Python avec message d'erreur dans la ligne de statut ; retourne undefined en cas d'échec. */
  async function call(fn: () => Promise<any>): Promise<any> {
    try { return await fn() } catch (e) { setStatus(errText(e), 'err'); return undefined }
  }
  function setting(key: string, value: any) { api().set_setting(key, value); setData(d => d && { ...d, settings: { ...d.settings, [key]: value } }) }

  useEffect(() => {
    const start = async () => {
      const d = await reload()
      if (d.settings.view) setView(d.settings.view)
      if (d.update) setUpdate({ version: d.update, notes: '' })
      setStatus(`Prêt. Scannez un ISBN. (Base : ${d.dbPath})`)
      refocus()
    }
    if ((window as any).pywebview?.api) start(); else window.addEventListener('pywebviewready', start, { once: true })
    ;(window as any).onPush = (m: any) => {
      if (m.kind === 'status') { setStatus(m.text, m.level); if (m.refresh) reload() }
      if (m.kind === 'update') { setUpdate({ version: m.version, notes: m.notes }); setStatus(`Mise à jour ${m.version} prête : elle sera installée au prochain démarrage, ou cliquez sur « Mettre à jour ».`) }
    }
    // F2 : retour au champ ISBN ; un chiffre tapé hors d'un champ (douchette) y est redirigé
    const keys = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      const typing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(t.tagName)
      if (e.key === 'F2' || (!typing && /^[0-9]$/.test(e.key) && !document.querySelector('.modalback'))) scanRef.current?.focus()
      if (e.key === 'Escape') setMenu(null)
    }
    window.addEventListener('keydown', keys)
    window.addEventListener('click', () => setMenu(null))
    return () => window.removeEventListener('keydown', keys)
  }, [])
  useEffect(() => { if (focusAction) actionRef.current?.focus() }, [focusAction])
  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('dark', !!data?.settings.dark)
    root.classList.toggle('large', !!data?.settings.large)
  }, [data?.settings.dark, data?.settings.large])

  const books = data?.books ?? []
  const loans = data?.loans ?? []
  const today = data?.today ?? new Date().toISOString().slice(0, 10)
  const isOverdue = (l: { due_date: string | null; return_date?: string | null }) => !l.return_date && !!l.due_date && l.due_date < today

  const searched = useMemo(() => {
    const q = query.trim().toLocaleLowerCase('fr')
    if (!q) return books
    const text = (b: Book) => searchIn === 'all'
      ? [b.title, b.authors, b.year, b.genre, b.isbn, b.location, b.borrower].join(' ')
      : String((b as any)[searchIn] || '')
    return books.filter(b => text(b).toLocaleLowerCase('fr').includes(q))
  }, [books, query, searchIn])
  const groups = useMemo(() => {
    if (!groupBy) return []
    const count = new Map<string, number>()
    for (const b of searched) for (const n of groupNames((b as any)[groupBy], groupBy)) count.set(n, (count.get(n) || 0) + 1)
    return [...count].sort((a, b) => compareKeys(sortKey(a[0], groupBy), sortKey(b[0], groupBy)))
  }, [searched, groupBy])
  const filtered = useMemo(() => {
    const list = groupBy && groupValue !== null ? searched.filter(b => groupNames((b as any)[groupBy], groupBy).includes(groupValue)) : searched
    const sorted = [...list].sort((a, b) => compareKeys(sortKey((a as any)[sortBy], sortBy), sortKey((b as any)[sortBy], sortBy)))
    return desc ? sorted.reverse() : sorted
  }, [searched, groupBy, groupValue, sortBy, desc])
  const current = books.find(b => b.id === selected) ?? filtered[0]
  const activeLoans = loans.filter(l => !l.return_date)
  const overdueLoans = activeLoans.filter(isOverdue)
  const returnedLoans = loans.filter(l => l.return_date)
  const filteredLoans = loans.filter(l => {
    const ok = loanFilter === 'all' || (loanFilter === 'active' && !l.return_date) || (loanFilter === 'overdue' && isOverdue(l)) || (loanFilter === 'returned' && !!l.return_date)
    return ok && `${l.title} ${l.borrower}`.toLocaleLowerCase('fr').includes(loanQuery.toLocaleLowerCase('fr'))
  })
  // Noms pour l'autocomplétion du prêt : le dernier emprunteur d'abord
  const borrowerNames = [...new Set([...loans.map(l => l.borrower), ...(data?.borrowers ?? []).map(p => p.name)])]
  const genres = new Set(books.map(b => b.genre).filter(Boolean))

  /** Montre un livre dans la bibliothèque ; quitte le groupe affiché s'il n'en fait pas partie. */
  function show(id: number, d = data) {
    setSection('library')
    setSelected(id)
    const b = d?.books.find(x => x.id === id)
    if (b && groupBy && groupValue !== null && !groupNames((b as any)[groupBy], groupBy).includes(groupValue)) setGroupValue(null)
    setTimeout(() => document.querySelector(`[data-id="${id}"]`)?.scrollIntoView({ block: 'nearest' }), 50)
  }

  async function onScan() {
    const raw = scan.trim()
    setScan('')
    if (!raw) return
    const res = await call(() => api().scan(raw, mode))
    if (!res) return
    if (res.status) setStatus(res.status, res.kind)
    const d = await reload()
    if (res.select) show(res.select, d)
    if (res.open) setFocusAction(n => n + 1)
    if (res.form) setForm({ id: null, data: res.form, cover: res.form.coverData || '', coverData: res.form.coverData })
  }

  async function saveForm(e: React.FormEvent) {
    e.preventDefault()
    if (!form) return
    const id = await call(() => api().save_book(form.id, form.data, form.coverData || null))
    if (id === undefined) return
    setStatus(form.id ? `Fiche modifiée : « ${form.data.title} ».` : `Ajouté : « ${form.data.title} ».`, 'ok')
    setForm(null)
    show(id, await reload())
    refocus()
  }
  async function formRefreshInfo() {
    if (!form?.data.isbn) { setStatus('Ce livre n’a pas d’ISBN : impossible de chercher ses informations.', 'err'); return }
    setBusy(true)
    const info = await call(() => api().fetch_info(form.data.isbn))
    setBusy(false)
    if (!info) { if (info === null) setStatus('Rien trouvé en ligne pour cet ISBN.', 'warn'); return }
    setForm(f => f && { ...f, data: { ...f.data, ...Object.fromEntries(ONLINE.filter(k => info[k]).map(k => [k, info[k]])) } })
    setStatus('Informations actualisées dans le formulaire : vérifiez puis enregistrez.', 'info')
  }
  async function searchCovers(isbn: string, title: string, authors: string, pick: (img: string) => void) {
    setBusy(true)
    setStatus(`Recherche de jaquettes pour « ${title} »…`)
    const images = await call(() => api().find_covers(isbn, title, authors))
    setBusy(false)
    if (!images) return
    if (!images.length) { setStatus(`Aucune jaquette trouvée en ligne pour « ${title} ».`, 'warn'); return }
    setStatus(`${images.length} jaquette(s) trouvée(s) : cliquez sur celle de votre édition.`)
    setPicker({ images, title: [title, authors].filter(Boolean).join(' - '), pick })
  }
  function refreshCover(b: Book) {
    searchCovers(b.isbn || '', b.title, b.authors, async img => {
      if (await call(() => api().set_cover(b.id, img)) === undefined) return
      setStatus(`Jaquette actualisée : « ${b.title} ».`, 'ok'); reload()
    })
  }
  async function refreshInfo(b: Book) {
    if (!b.isbn) { setStatus(`« ${b.title} » n’a pas d’ISBN : impossible de chercher ses informations.`, 'err'); return }
    setStatus(`Recherche des informations de « ${b.title} »…`)
    const info = await call(() => api().fetch_info(b.isbn))
    if (info === undefined) return
    const changes = ONLINE.filter(k => info?.[k] && info[k] !== ((b as any)[k] || ''))
    if (!changes.length) { setStatus(`Rien de nouveau en ligne pour « ${b.title} ».`); return }
    const cut = (s: string) => s.length <= 90 ? s : s.slice(0, 89).trimEnd() + '…'
    if (!confirm(`Remplacer dans la fiche « ${b.title} » :\n\n${changes.map(k => `${LABELS[k].replace(' *', '')} : ${cut(info[k])}`).join('\n')}`)) { setStatus('Fiche inchangée.'); return }
    const merged = { ...Object.fromEntries(FIELDS.map(k => [k, (b as any)[k] ?? ''])), ...Object.fromEntries(changes.map(k => [k, info[k]])) }
    if (await call(() => api().save_book(b.id, merged, null)) === undefined) return
    setStatus(`Informations actualisées : « ${merged.title} ».`, 'ok'); reload()
  }
  async function deleteBook(b: Book) {
    if (!confirm(`Supprimer « ${b.title} » ?\nL’historique de ses prêts sera aussi effacé.`)) return
    if (await call(() => api().delete_book(b.id)) === undefined) return
    setStatus(`Supprimé : « ${b.title} ».`, 'ok'); setSelected(null); reload()
  }
  function openLend(b: Book) { setLendBook(b); setLendWho(''); setLendDue(addDays(today, data?.loanDays ?? 21)) }
  async function lend(e: React.FormEvent) {
    e.preventDefault()
    if (!lendBook || await call(() => api().lend(lendBook.id, lendWho, lendDue)) === undefined) return
    setStatus(`« ${lendBook.title} » prêté à ${lendWho.trim()}${lendDue ? `, retour prévu le ${fmt(lendDue)}` : ''}.`, 'ok')
    setLendBook(null); reload(); refocus()
  }
  async function giveBack(bookId: number, title: string) {
    const who = await call(() => api().return_book(bookId))
    if (who === undefined) return
    setStatus(`Retour enregistré : « ${title} » (rendu par ${who}).`, 'ok'); reload(); refocus()
  }
  async function saveBorrower(e: React.FormEvent) {
    e.preventDefault()
    if (!person || await call(() => api().save_borrower(person.old, person.data)) === undefined) return
    setStatus(`Contact enregistré : ${person.data.name}.`, 'ok'); setPerson(null); reload()
  }
  async function deleteBorrower(name: string) {
    if (!confirm(`Retirer « ${name} » de l’annuaire ?\n(L’historique de ses prêts est conservé.)`)) return
    if (await call(() => api().delete_borrower(name)) === undefined) return
    setStatus(`Contact supprimé : ${name}.`, 'ok'); reload()
  }
  async function enrich() {
    const n = await call(() => api().enrich())
    if (n !== undefined) setStatus(n ? `Recherche en ligne de ${n} fiche(s)…` : 'Toutes les fiches sont déjà complètes.', n ? 'info' : 'ok')
  }
  async function importFile(kind: 'import_bkc' | 'import_isbn_list', note: string) {
    const res = await call(() => api()[kind]())
    if (!res) return
    const msg = `${res.added} livre(s) importé(s), ${res.skipped} déjà présent(s).`
    setStatus(msg, 'ok'); reload()
    if (res.added && confirm(`${msg}\n\n${note}\nCompléter maintenant les fiches (titre, auteur, éditeur, couverture…) via Internet ?`)) enrich()
  }
  async function exportCsv() { const path = await call(() => api().export_csv()); if (path) setStatus(`Exporté : ${path}`, 'ok') }
  async function loadBackups() { setBackups(await call(() => api().backups()) ?? []) }
  async function createBackup() {
    setBackupBusy(true); const name = await call(() => api().create_backup()); setBackupBusy(false)
    if (name) { setStatus(`Sauvegarde créée : ${name}`, 'ok'); loadBackups() }
  }
  async function restoreBackup(name: string) {
    if (!confirm('Restaurer cette sauvegarde ? Les données actuelles seront remplacées. Une copie de sécurité sera créée avant la restauration.')) return
    setBackupBusy(true); const done = await call(() => api().restore_backup(name)); setBackupBusy(false)
    if (done !== undefined) { setSelected(null); setStatus('Sauvegarde restaurée.', 'ok'); reload(); loadBackups() }
  }
  async function checkUpdate() { setStatus('Recherche de mise à jour…'); const msg = await call(() => api().check_update(true)); if (msg) setStatus(msg, msg.startsWith('Mise à jour impossible') ? 'err' : 'info') }
  async function installUpdate() {
    if (!update || !confirm(`Installer la version ${update.version} (actuelle : ${data?.version}) ?\n\n${update.notes}\n\nBookTek va redémarrer.`)) return
    await call(() => api().install_update())
  }

  const cover = (b: Book, size: number) => b.cover ? <img src={b.cover} loading="lazy" /> : <BookOpen size={size} />
  const loanStatus = (l: Loan) => <span className={`status ${l.return_date ? 'returned' : isOverdue(l) ? 'overdue' : 'ongoing'}`}>{l.return_date ? 'Rendu' : isOverdue(l) ? `${days(l.due_date!, today)} j de retard` : 'En cours'}</span>
  const currentLoan = current && activeLoans.find(l => l.book_id === current.id)
  const nav = (key: typeof section, icon: JSX.Element, label: string) => <button className={section === key ? 'active' : ''} onClick={() => setSection(key)}>{icon}{label}</button>

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><BookOpen size={42} /><b>BookTek</b><small>Gestion de ma bibliothèque personnelle</small></div>
      <nav>
        {nav('library', <Library />, 'Bibliothèque')}
        {nav('loans', <Handshake />, 'Mes prêts')}
        {nav('borrowers', <Users />, 'Emprunteurs')}
        {nav('stats', <BarChart3 />, 'Statistiques')}
        {nav('backups', <ShieldCheck />, 'Sauvegardes')}
        {nav('about', <Info />, 'À propos')}
      </nav>
      <div className="sidebottom">
        <button onClick={() => importFile('import_bkc', 'Le fichier .bkc ne contient pas les auteurs de façon exploitable.')}><Upload />Importer Book Collector</button>
        <button onClick={() => importFile('import_isbn_list', 'Le fichier ne contient que les ISBN.')}><FileText />Importer une liste d’ISBN</button>
        <button onClick={enrich}><Globe />Compléter via Internet</button>
        <button onClick={exportCsv}><Download />Exporter en CSV</button>
        <button className={data?.settings.dark ? 'on' : ''} onClick={() => setting('dark', !data?.settings.dark)}><Moon />Thème sombre</button>
        <button className={data?.settings.large ? 'on' : ''} onClick={() => setting('large', !data?.settings.large)}><Type />Grands caractères</button>
        <small>Vos données restent sur cet ordinateur.</small>
      </div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div className="isbn"><Barcode />
          <input ref={scanRef} value={scan} onChange={e => setScan(e.target.value)} onKeyDown={e => e.key === 'Enter' && onScan()} placeholder="Scanner ou saisir un ISBN… (F2)" />
          <select value={mode} onChange={e => { setMode(e.target.value as typeof mode); refocus() }} title="Mode de scan">
            <option value="auto">Automatique</option><option value="add">Ajout rapide</option><option value="return">Retour rapide</option>
          </select>
          <button onClick={onScan}>OK</button>
        </div>
        <div className="topmeta">
          <span>{data?.stats.books ?? 0} livres</span><span>{data?.stats.lent ?? 0} prêts en cours</span>
          <span className={data?.stats.overdue ? 'late-count' : ''}>{data?.stats.overdue ?? 0} retard(s)</span>
          {update && <button className="primary" onClick={installUpdate}><ArrowUpCircle size={16} />Mettre à jour vers {update.version}</button>}
        </div>
      </header>
      {status.text && <div className={`notice notice-${status.kind}`}>{status.text}<button onClick={() => setStatus('')}><X size={15} /></button></div>}

      {section === 'library' && <>
        <div className="toolbar">
          <div className="search"><Search /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Rechercher un livre, un auteur, un emprunteur…" /></div>
          <select value={searchIn} onChange={e => setSearchIn(e.target.value)} title="Chercher dans">{Object.entries(SEARCH_IN).map(([k, v]) => <option key={k} value={k}>Chercher dans : {v}</option>)}</select>
          <select value={sortBy} onChange={e => setSortBy(e.target.value)} title="Trier par">{Object.entries(SORTS).map(([k, v]) => <option key={k} value={k}>Trier par : {v}</option>)}</select>
          <label className="check"><input type="checkbox" checked={desc} onChange={e => setDesc(e.target.checked)} />Décroissant</label>
          <div className="viewtoggle">
            <button className={view === 'grid' ? 'chosen' : ''} title="Miniatures" onClick={() => { setView('grid'); setting('view', 'grid') }}><Grid3X3 /></button>
            <button className={view === 'list' ? 'chosen' : ''} title="Liste" onClick={() => { setView('list'); setting('view', 'list') }}><List /></button>
          </div>
          <button className="primary" onClick={() => setForm({ id: null, data: {}, cover: '' })}><Plus />Ajouter</button>
        </div>
        <div className="content">
          <section className="catalog">
            <div className="sectionhead"><div><h2>Ma collection</h2><small>{filtered.length} livre(s) affiché(s)</small></div>
              <select value={groupBy} onChange={e => { setGroupBy(e.target.value); setGroupValue(null) }}>{Object.entries(GROUPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>
            </div>
            {groupBy && <select className="groupselect" value={groupValue ?? ''} onChange={e => setGroupValue(e.target.value || null)}>
              <option value="">(Tous les livres) ({searched.length})</option>
              {groups.map(([n, c]) => <option key={n} value={n}>{n} ({c})</option>)}
            </select>}
            <div className={view === 'grid' ? 'bookgrid' : 'booklist'}>
              {filtered.map(b => <button key={b.id} data-id={b.id} className={`booktile ${current?.id === b.id ? 'selected' : ''}`}
                onClick={() => setSelected(b.id)} onDoubleClick={() => setForm({ id: b.id, data: Object.fromEntries(FIELDS.map(k => [k, (b as any)[k] ?? ''])), cover: b.cover })}
                onContextMenu={e => { e.preventDefault(); setSelected(b.id); setMenu({ x: e.clientX, y: e.clientY, book: b }) }}>
                <div className="cover">{b.cover ? <img src={b.cover} loading="lazy" /> : <span className="notitle">{b.title}</span>}</div>
                <b>{b.title}</b><small>{b.authors}</small>
                {view === 'list' && <small className="listmeta">{[b.year, b.genre, b.place, b.borrower && `Prêté à ${b.borrower}`].filter(Boolean).join(' · ')}</small>}
              </button>)}
              {!filtered.length && <div className="empty">Aucun livre ne correspond à la recherche.</div>}
            </div>
          </section>
          <section className="detail">
            {current ? <div className="detailtop">
              <div className="bigcover">{cover(current, 60)}</div>
              <div className="bookinfo">
                <div className="eyebrow">FICHE DU LIVRE</div>
                <h1>{current.title}</h1><h3>{current.authors || 'Auteur inconnu'}</h3>
                <div className="metadata">
                  <span><BookOpen /> {current.pages || '—'} pages</span>
                  <span>Éditeur : {current.publisher || '—'}</span>
                  <span>Genre : {current.genre || '—'}</span>
                  <span>Emplacement : <b>{current.place || 'Non renseigné'}</b></span>
                  <span>Parution : {current.year || '—'}</span>
                  <span>ISBN : {current.isbn || '—'}</span>
                  {current.read_date && <span>Lu le : {current.read_date}</span>}
                  <span>{currentLoan ? <b className={isOverdue(currentLoan) ? 'late-text' : ''}>Prêté à {currentLoan.borrower} depuis le {fmt(currentLoan.loan_date)}{currentLoan.due_date ? `, retour prévu le ${fmt(currentLoan.due_date)}` : ''}</b> : 'Disponible'}</span>
                </div>
                <div className="actions">
                  {/* Entrée ne fait rien : un scan pendant que ce bouton a le focus ne déclenche pas d'action (Espace oui) */}
                  {currentLoan
                    ? <button ref={actionRef} className="primary" onKeyDown={e => e.key === 'Enter' && e.preventDefault()} onClick={() => giveBack(current.id, current.title)}><RotateCcw />Enregistrer le retour</button>
                    : <button ref={actionRef} className="primary" onKeyDown={e => e.key === 'Enter' && e.preventDefault()} onClick={() => openLend(current)}><Handshake />Prêter…</button>}
                  <button onClick={() => setForm({ id: current.id, data: Object.fromEntries(FIELDS.map(k => [k, (current as any)[k] ?? ''])), cover: current.cover })}><Pencil />Modifier…</button>
                  <button className="danger" onClick={() => deleteBook(current)}><Trash2 />Supprimer</button>
                </div>
              </div>
            </div> : <div className="empty">Scannez un livre ou ajoutez votre premier ouvrage.</div>}
            {current && <div className="summary"><h3>Résumé</h3><p>{current.summary || 'Aucun résumé renseigné pour ce livre.'}</p>{current.notes && <><h3>Notes</h3><p>{current.notes}</p></>}</div>}
            {current && <div className="loanspanel"><div className="panelhead"><h2><Handshake /> Prêts de ce livre</h2></div>
              <div className="loanrows">{loans.filter(l => l.book_id === current.id).map(l => <div className="loanrow" key={l.id}>
                <div><b>{l.borrower}</b><small>Prêté le {fmt(l.loan_date)} · {l.return_date ? `rendu le ${fmt(l.return_date)} (${days(l.loan_date, l.return_date)} j)` : `retour prévu ${fmt(l.due_date)}`}</small></div>
                {loanStatus(l)}
                {!l.return_date && <button className="iconbutton" title="Enregistrer le retour" onClick={() => giveBack(current.id, current.title)}><RotateCcw /></button>}
              </div>)}{!loans.some(l => l.book_id === current.id) && <small className="muted">Jamais prêté.</small>}</div>
            </div>}
          </section>
        </div>
      </>}

      {section === 'loans' && <section className="fullpanel">
        <div className="pagehead"><div><h1>Suivi des prêts</h1><p className="muted">Tous les prêts, retours et échéances de votre bibliothèque.</p></div></div>
        <div className="loan-summary">
          <button className={loanFilter === 'active' ? 'picked' : ''} onClick={() => setLoanFilter('active')}><small>En cours</small><b>{activeLoans.length}</b></button>
          <button className={loanFilter === 'overdue' ? 'picked' : ''} onClick={() => setLoanFilter('overdue')}><small>En retard</small><b className="late-text">{overdueLoans.length}</b></button>
          <button className={loanFilter === 'returned' ? 'picked' : ''} onClick={() => setLoanFilter('returned')}><small>Rendus</small><b>{returnedLoans.length}</b></button>
          <button className={loanFilter === 'all' ? 'picked' : ''} onClick={() => setLoanFilter('all')}><small>Total historique</small><b>{loans.length}</b></button>
        </div>
        <div className="loan-tools"><input value={loanQuery} onChange={e => setLoanQuery(e.target.value)} placeholder="Rechercher un livre, un emprunteur…" /></div>
        {filteredLoans.map(l => <div className={`allloan ${isOverdue(l) ? 'allloan-late' : ''}`} key={l.id}>
          <div className="loan-book"><b>{l.title}</b>
            <small><UserRound size={13} /> {l.borrower} · prêté le {fmt(l.loan_date)} · {l.return_date ? `rendu le ${fmt(l.return_date)}, durée ${days(l.loan_date, l.return_date)} j` : `depuis ${days(l.loan_date, today)} j`}</small>
            <small><CalendarDays size={13} /> Retour prévu le {fmt(l.due_date)}</small>
          </div>
          {loanStatus(l)}
          {!l.return_date && <button className="return-button" onClick={() => giveBack(l.book_id, l.title)}><RotateCcw size={15} /> Enregistrer le retour</button>}
        </div>)}
        {!filteredLoans.length && <div className="empty">Aucun prêt ne correspond à ce filtre.</div>}
      </section>}

      {section === 'borrowers' && <section className="fullpanel">
        <div className="pagehead"><div><h1>Emprunteurs</h1><p className="muted">Les personnes à qui vous prêtez vos livres. Celles qui ont un livre en retard sont en rouge.</p></div>
          <button className="primary" onClick={() => setPerson({ old: null, data: { name: '', phone: '', email: '', notes: '' } })}><Plus />Nouvel emprunteur</button></div>
        <div className="borrower-grid">{(data?.borrowers ?? []).map(p => {
          const late = overdueLoans.some(l => l.borrower === p.name)
          return <article className={`borrower-card ${late ? 'borrower-late' : ''}`} key={p.name}>
            <div className="borrower-avatar"><UserRound /></div>
            <div className="borrower-title"><h3>{p.name}</h3><small>{p.total} prêt(s) · {p.active} en cours</small></div>
            {p.oldest_active && <p className={late ? 'late-text' : ''}><CalendarDays size={14} />Plus ancien prêt en cours : {days(p.oldest_active, today)} j</p>}
            {p.email && <p><Mail size={14} />{p.email}</p>}
            {p.phone && <p><Phone size={14} />{p.phone}</p>}
            {p.notes && <p className="borrower-notes">{p.notes}</p>}
            <div className="borrower-actions">
              <button onClick={() => setPerson({ old: p.name, data: { name: p.name, phone: p.phone, email: p.email, notes: p.notes } })}><Pencil size={15} /> Modifier</button>
              <button className="danger" onClick={() => deleteBorrower(p.name)}><Trash2 size={15} /> Supprimer</button>
            </div>
          </article>
        })}{!data?.borrowers.length && <div className="empty">Aucun emprunteur. Un emprunteur saisi lors d’un prêt est ajouté automatiquement.</div>}</div>
      </section>}

      {section === 'stats' && <section className="stats"><h1>Statistiques</h1><div className="statgrid">
        <div><small>Livres dans la collection</small><strong>{books.length}</strong></div>
        <div><small>Prêts en cours</small><strong>{activeLoans.length}</strong></div>
        <div><small>Prêts en retard</small><strong className={overdueLoans.length ? 'late-text' : ''}>{overdueLoans.length}</strong></div>
        <div><small>Retours effectués</small><strong>{returnedLoans.length}</strong></div>
        <div><small>Emprunteurs</small><strong>{data?.borrowers.length ?? 0}</strong></div>
        <div><small>Livres lus</small><strong>{books.filter(b => b.read_date).length}</strong></div>
        <div><small>Genres représentés</small><strong>{genres.size}</strong></div>
      </div></section>}

      {section === 'backups' && <section className="fullpanel backup-panel">
        <div className="pagehead"><div><h1>Sauvegardes</h1><p className="muted">Copies de la base de données et des jaquettes.</p></div>
          <button className="primary" onClick={createBackup} disabled={backupBusy}><Download size={16} />{backupBusy ? 'En cours…' : 'Créer une sauvegarde'}</button></div>
        <div className="backup-info"><ShieldCheck /><div><b>Sauvegarde automatique</b><p>BookTek crée une sauvegarde au lancement, au maximum une fois par jour. Les 10 dernières sont conservées.</p><small>Dossier : {data?.backupDir}</small></div></div>
        <div className="backup-list-head"><h2>Historique des sauvegardes</h2><button onClick={loadBackups}><RefreshCw size={15} /> Actualiser</button></div>
        {backups.map(item => <div className="backup-row" key={item.name}><div><b><Clock size={15} />{new Date(item.date).toLocaleString('fr-FR')}</b><small>{item.name} · {(item.size / 1024).toFixed(1)} Ko</small></div><button disabled={backupBusy} onClick={() => restoreBackup(item.name)}><RotateCcw size={15} /> Restaurer</button></div>)}
        {backups.length === 0 && <div className="empty">Aucune sauvegarde pour le moment.</div>}
      </section>}

      {section === 'about' && <section className="fullpanel">
        <div className="pagehead"><div><h1>BookTek {data?.version}</h1><p className="muted">Gestion de bibliothèque par lecture d’ISBN.</p></div>
          <button className="primary" onClick={checkUpdate}><RefreshCw size={16} />Rechercher une mise à jour</button></div>
        <p><a href="#" onClick={e => { e.preventDefault(); api().open_url('https://github.com/HTModeLia/BookTek') }}>https://github.com/HTModeLia/BookTek</a></p>
        <p className="muted">Base de données : {data?.dbPath}</p>
        <h2>Sources des données</h2><p className="muted">Cliquez sur une ligne pour ouvrir la page du service.</p>
        {data?.sources.map(([name, use, url]) => <div className="backup-row source-row" key={url} onClick={() => api().open_url(url)}><div><b>{name}</b><small>{use} · {url}</small></div></div>)}
      </section>}
    </main>

    {menu && <div className="contextmenu" style={{ left: menu.x, top: menu.y }}>
      <button onClick={() => refreshCover(menu.book)}><ImageIcon size={15} />Actualiser la jaquette…</button>
      <button onClick={() => refreshInfo(menu.book)}><RefreshCw size={15} />Actualiser les informations…</button>
      <button onClick={() => setForm({ id: menu.book.id, data: Object.fromEntries(FIELDS.map(k => [k, (menu.book as any)[k] ?? ''])), cover: menu.book.cover })}><Pencil size={15} />Modifier…</button>
    </div>}

    {form && <div className="modalback"><form className="modal bookform" onSubmit={saveForm}>
      <div className="modalhead"><h2>{form.id ? 'Modifier le livre' : 'Nouveau livre'}</h2><button type="button" onClick={() => { setForm(null); refocus() }}><X /></button></div>
      <div className="formbody">
        <div className="formgrid">{FIELDS.map(k => <label key={k} className={k === 'summary' || k === 'notes' ? 'wide' : ''}>{LABELS[k]}
          {k === 'summary' || k === 'notes'
            ? <textarea rows={k === 'summary' ? 5 : 2} value={form.data[k] || ''} onChange={e => setForm({ ...form, data: { ...form.data, [k]: e.target.value } })} />
            : <input required={k === 'title'} autoFocus={k === 'title'} value={form.data[k] || ''} onChange={e => setForm({ ...form, data: { ...form.data, [k]: e.target.value } })} />}
        </label>)}</div>
        <div className="formcover">
          <div className="bigcover">{form.cover ? <img src={form.cover} /> : <BookOpen size={50} />}</div>
          <label className="sidebutton formbutton"><ImageIcon size={15} />Changer la jaquette…<input type="file" accept="image/*" onChange={async e => { const f = e.target.files?.[0]; if (f) { const img = await readImage(f); setForm(x => x && { ...x, cover: img, coverData: img }) } }} /></label>
          <button type="button" disabled={busy} onClick={() => searchCovers(form.data.isbn || '', form.data.title || '', form.data.authors || '', img => setForm(x => x && { ...x, cover: img, coverData: img }))}><Search size={15} />Rechercher une jaquette…</button>
          <button type="button" disabled={busy} onClick={formRefreshInfo}><RefreshCw size={15} />Actualiser les informations</button>
        </div>
      </div>
      <div className="modalactions"><button type="button" onClick={() => { setForm(null); refocus() }}>Annuler</button><button className="primary" type="submit">Enregistrer</button></div>
    </form></div>}

    {picker && <div className="modalback picker"><div className="modal">
      <div className="modalhead"><h2>Choisir une jaquette</h2><button type="button" onClick={() => setPicker(null)}><X /></button></div>
      <p className="muted">{picker.title} — cliquez sur la jaquette de votre édition.</p>
      <div className="zoom">Taille des images <button onClick={() => setZoom(z => Math.max(100, z - 40))}>−</button><button onClick={() => setZoom(z => Math.min(420, z + 40))}>+</button></div>
      <div className="pickgrid">{picker.images.map((img, i) => <button key={i} style={{ width: zoom }} onClick={() => { picker.pick(img); setPicker(null) }}>
        <img src={img} onLoad={e => { const t = e.currentTarget; t.nextElementSibling!.textContent = `${t.naturalWidth} × ${t.naturalHeight} px` }} /><small></small>
      </button>)}</div>
    </div></div>}

    {lendBook && <div className="modalback"><form className="modal compact" onSubmit={lend}>
      <div className="modalhead"><h2>Prêter un livre</h2><button type="button" onClick={() => setLendBook(null)}><X /></button></div>
      <p>Livre : <b>{lendBook.title}</b></p>
      <label>Emprunteur<input required autoFocus list="borrower-names" value={lendWho} onChange={e => setLendWho(e.target.value)} placeholder="Prénom et nom" /></label>
      <datalist id="borrower-names">{borrowerNames.map(n => <option key={n} value={n} />)}</datalist>
      <label>Date de retour prévue (vide : sans échéance)<input type="date" value={lendDue} onChange={e => setLendDue(e.target.value)} /></label>
      <div className="modalactions"><button type="button" onClick={() => setLendBook(null)}>Annuler</button><button className="primary">Prêter</button></div>
    </form></div>}

    {person && <div className="modalback"><form className="modal compact" onSubmit={saveBorrower}>
      <div className="modalhead"><h2>{person.old ? 'Modifier le contact' : 'Nouveau contact'}</h2><button type="button" onClick={() => setPerson(null)}><X /></button></div>
      {[['name', 'Nom *'], ['phone', 'Téléphone'], ['email', 'Adresse e-mail']].map(([k, label]) => <label key={k}>{label}
        <input required={k === 'name'} autoFocus={k === 'name'} value={person.data[k]} onChange={e => setPerson({ ...person, data: { ...person.data, [k]: e.target.value } })} /></label>)}
      <label>Notes<textarea rows={3} value={person.data.notes} onChange={e => setPerson({ ...person, data: { ...person.data, notes: e.target.value } })} /></label>
      <div className="modalactions"><button type="button" onClick={() => setPerson(null)}>Annuler</button><button className="primary">Enregistrer</button></div>
    </form></div>}
  </div>
}
