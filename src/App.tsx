import { useEffect, useMemo, useState } from 'react'
import { db, type Book, type Loan, type Borrower } from './db'
import { BookOpen, Search, Plus, Grid3X3, List, Handshake, BarChart3, Library, Barcode, Pencil, Trash2, Check, RotateCcw, Download, Upload, X, Users, Mail, Phone, AlertTriangle, CalendarDays, UserRound, History, ShieldCheck, Clock, RefreshCw } from 'lucide-react'

const emptyBook: Book = { isbn:'', title:'', author:'', pages:0, summary:'', cover:'', genre:'', year:'', location:'', read:false, createdAt:new Date().toISOString() }
const demo: Book[] = [
 { ...emptyBook, isbn:'9782070612758', title:'Le Petit Prince', author:'Antoine de Saint-Exupéry', pages:96, genre:'Roman', year:'1943', location:'Étagère A1', summary:'Un aviateur tombe en panne dans le désert du Sahara. Il rencontre un petit prince venu d’une autre planète, qui lui raconte son voyage et ses rencontres.', cover:'https://covers.openlibrary.org/b/isbn/9782070612758-L.jpg', read:true },
 { ...emptyBook, isbn:'9782266286244', title:'Dune', author:'Frank Herbert', pages:832, genre:'Science-fiction', year:'1965', location:'Étagère B2', summary:'Sur la planète désertique Arrakis, les grandes maisons se disputent le contrôle de l’Épice.', cover:'https://covers.openlibrary.org/b/isbn/9782266286244-L.jpg' },
 { ...emptyBook, isbn:'9780451524935', title:'1984', author:'George Orwell', pages:328, genre:'Science-fiction', year:'1949', location:'Étagère B2', summary:'Dans une société totalitaire, Winston Smith tente de préserver sa liberté de pensée.', cover:'https://covers.openlibrary.org/b/isbn/9780451524935-L.jpg' },
 { ...emptyBook, isbn:'9782070643029', title:'Harry Potter à l’école des sorciers', author:'J. K. Rowling', pages:320, genre:'Fantastique', year:'1997', location:'Étagère A2', summary:'Un jeune garçon découvre qu’il est sorcier et rejoint Poudlard.', cover:'https://covers.openlibrary.org/b/isbn/9782070643029-L.jpg' },
 { ...emptyBook, isbn:'9782330000000', title:'Sapiens', author:'Yuval Noah Harari', pages:512, genre:'Histoire', year:'2011', location:'Étagère C1', summary:'Une histoire synthétique de l’humanité et de ses grandes transformations.', cover:'https://covers.openlibrary.org/b/isbn/9780062316097-L.jpg' },
 { ...emptyBook, isbn:'9782070408504', title:'Les Misérables', author:'Victor Hugo', pages:1488, genre:'Classique', year:'1862', location:'Étagère C2', summary:'Le destin de Jean Valjean dans la France du XIXe siècle.', cover:'https://covers.openlibrary.org/b/isbn/9782070408504-L.jpg' }
]
const fmt = (s:string) => s ? new Date(s+'T12:00:00').toLocaleDateString('fr-FR') : '—'
const today = () => { const d=new Date(); d.setMinutes(d.getMinutes()-d.getTimezoneOffset()); return d.toISOString().slice(0,10) }
const isOverdue = (loan:Loan) => !loan.returnedAt && !!loan.dueDate && loan.dueDate < today()
const emptyBorrower = ():Borrower => ({name:'',email:'',phone:'',notes:'',createdAt:new Date().toISOString()})

const normalizeIsbn = (value:string) => value.replace(/[-\s]/g,'').toUpperCase()

function isValidIsbn(value:string) {
 const code=normalizeIsbn(value)
 if (/^\d{13}$/.test(code)) {
  const sum=[...code].slice(0,12).reduce((total,digit,index)=>total+Number(digit)*(index%2===0?1:3),0)
  return (10-(sum%10))%10===Number(code[12])
 }
 if (/^\d{9}[\dX]$/.test(code)) {
  const sum=[...code].reduce((total,digit,index)=>total+(digit==='X'?10:Number(digit))*(10-index),0)
  return sum%11===0
 }
 return false
}

async function fetchGoogleBook(isbn:string) {
 const response=await fetch(`https://www.googleapis.com/books/v1/volumes?q=${encodeURIComponent(`isbn:${isbn}`)}&maxResults=5`)
 if(!response.ok) throw new Error('Google Books indisponible')
 const data=await response.json()
 const item=(data.items||[]).find((entry:any)=>(entry.volumeInfo?.industryIdentifiers||[]).some((id:any)=>normalizeIsbn(id.identifier||'')===isbn)) || data.items?.[0]
 if(!item?.volumeInfo) return null
 const info=item.volumeInfo
 const image=info.imageLinks?.thumbnail||info.imageLinks?.smallThumbnail||''
 return {
  title:info.title||'',
  author:(info.authors||[]).join(', '),
  pages:Number(info.pageCount)||0,
  year:info.publishedDate||'',
  cover:image.replace(/^http:/,'https:'),
  genre:(info.categories||[]).slice(0,2).join(', '),
  summary:info.description||''
 }
}

async function fetchOpenLibraryBook(isbn:string) {
 const response=await fetch(`https://openlibrary.org/api/books?bibkeys=ISBN:${encodeURIComponent(isbn)}&format=json&jscmd=data`)
 if(!response.ok) throw new Error('Open Library indisponible')
 const data=await response.json()
 const item=data[`ISBN:${isbn}`]
 if(!item) return null
 return {
  title:item.title||'',
  author:(item.authors||[]).map((author:any)=>author.name).filter(Boolean).join(', '),
  pages:Number(item.number_of_pages)||0,
  year:item.publish_date||'',
  cover:item.cover?.large||item.cover?.medium||item.cover?.small||`https://covers.openlibrary.org/b/isbn/${isbn}-L.jpg`,
  genre:(item.subjects||[]).slice(0,2).map((subject:any)=>subject.name).filter(Boolean).join(', '),
  summary:''
 }
}

function mergeBookMetadata(isbn:string, google:any, openLibrary:any) {
 if(!google&&!openLibrary) return null
 const primary=google||openLibrary
 const secondary=google?openLibrary:null
 return {
  isbn,
  title:primary.title||secondary?.title||'',
  author:primary.author||secondary?.author||'',
  pages:primary.pages||secondary?.pages||0,
  year:primary.year||secondary?.year||'',
  cover:primary.cover||secondary?.cover||`https://covers.openlibrary.org/b/isbn/${isbn}-L.jpg`,
  genre:primary.genre||secondary?.genre||'',
  summary:primary.summary||secondary?.summary||''
 }
}

type BackupInfo = { name: string; date: string; size: number }
declare global { interface Window { booktekBackup?: { list: () => Promise<BackupInfo[]>; create: (data: unknown) => Promise<BackupInfo>; createAutomatic: (data: unknown) => Promise<BackupInfo>; read: (name: string) => Promise<any>; beforeRestore: (data: unknown) => Promise<BackupInfo> } } }

export default function App() {
 const [books,setBooks] = useState<Book[]>([])
 const [loans,setLoans] = useState<Loan[]>([])
 const [borrowers,setBorrowers] = useState<Borrower[]>([])
 const [selected,setSelected] = useState<number|null>(null)
 const [query,setQuery] = useState('')
 const [isbn,setIsbn] = useState('')
 const [genre,setGenre] = useState('Tous les genres')
 const [location,setLocation] = useState('Tous les emplacements')
 const [view,setView] = useState<'grid'|'list'>('grid')
 const [section,setSection] = useState<'library'|'loans'|'borrowers'|'stats'|'backups'>('library')
 const [backups,setBackups] = useState<BackupInfo[]>([])
 const [backupBusy,setBackupBusy] = useState(false)
 const [edit,setEdit] = useState<Book|null>(null)
 const [loanOpen,setLoanOpen] = useState(false)
 const [borrowerId,setBorrowerId] = useState('')
 const [dueDate,setDueDate] = useState(()=>{const d=new Date();d.setDate(d.getDate()+14);d.setMinutes(d.getMinutes()-d.getTimezoneOffset());return d.toISOString().slice(0,10)})
 const [loanNotes,setLoanNotes] = useState('')
 const [editingBorrower,setEditingBorrower] = useState<Borrower|null>(null)
 const [loanFilter,setLoanFilter] = useState<'all'|'active'|'overdue'|'returned'>('all')
 const [loanQuery,setLoanQuery] = useState('')
 const [notice,setNotice] = useState('')
 const [loading,setLoading] = useState(false)

 async function refresh() { const b=await db.books.toArray(); const l=await db.loans.toArray(); const people=await db.borrowers.orderBy('name').toArray(); setBooks(b); setLoans(l); setBorrowers(people); if(selected===null && b[0]?.id) setSelected(b[0].id); if(window.booktekBackup){try{await window.booktekBackup.createAutomatic({books:b,loans:l,borrowers:people,exportedAt:new Date().toISOString()});setBackups(await window.booktekBackup.list())}catch(error){console.error('Sauvegarde automatique impossible',error)}} }
 useEffect(()=>{ (async()=>{ if(await db.books.count()===0) await db.books.bulkAdd(demo); const oldLoans=await db.loans.toArray(); for(const oldLoan of oldLoans){if(!oldLoan.bookTitle){const linkedBook=await db.books.get(oldLoan.bookId);if(linkedBook)await db.loans.update(oldLoan.id!,{bookTitle:linkedBook.title})}} const existing=await db.borrowers.toArray(); for(const name of [...new Set(oldLoans.map(l=>l.borrower.trim()).filter(Boolean))]) { const person=existing.find(p=>p.name.trim().toLocaleLowerCase('fr')===name.toLocaleLowerCase('fr')); const id=person?.id??await db.borrowers.add({...emptyBorrower(),name}); await db.loans.where('borrower').equals(name).modify({borrowerId:id}) } await refresh() })() },[])
 const current = books.find(b=>b.id===selected) ?? books[0]
 const genres = [...new Set(books.map(b=>b.genre).filter(Boolean))]
 const places = [...new Set(books.map(b=>b.location).filter(Boolean))]
 const filtered = useMemo(()=>books.filter(b=>(`${b.title} ${b.author} ${b.isbn} ${b.summary}`.toLowerCase().includes(query.toLowerCase())) && (genre==='Tous les genres'||b.genre===genre) && (location==='Tous les emplacements'||b.location===location)),[books,query,genre,location])
 const activeLoans = loans.filter(l=>!l.returnedAt)
 const overdueLoans = activeLoans.filter(isOverdue)
 const returnedLoans = loans.filter(l=>!!l.returnedAt)
 const loanForBook = (id?:number)=>loans.find(l=>l.bookId===id&&!l.returnedAt)
 const filteredLoans = loans.filter(l=>{const book=books.find(b=>b.id===l.bookId); const text=`${book?.title||''} ${l.borrower} ${l.notes||''}`.toLocaleLowerCase('fr'); return (loanFilter==='all'||(loanFilter==='active'&&!l.returnedAt)||(loanFilter==='overdue'&&isOverdue(l))||(loanFilter==='returned'&&!!l.returnedAt))&&text.includes(loanQuery.toLocaleLowerCase('fr'))}).sort((a,b)=>b.loanDate.localeCompare(a.loanDate))

 async function lookupISBN(value=isbn) {
  const code=value.replace(/[-\s]/g,'').toUpperCase()
  if(!code) { setNotice('Saisis un ISBN-10 ou ISBN-13 avant de lancer la recherche.'); return }
  if(!isValidIsbn(code)) { setNotice('Cet ISBN semble invalide. Vérifie les chiffres saisis.'); return }

  const existing=books.find(b=>b.isbn.replace(/[-\s]/g,'').toUpperCase()===code)
  if(existing) {
   setSection('library')
   setSelected(existing.id ?? null)
   setEdit(existing)
   setNotice('Ce livre est déjà dans ta bibliothèque : sa fiche est ouverte pour modification.')
   return
  }

  setLoading(true)
  setNotice('')
  try {
   const [googleResult,openLibraryResult]=await Promise.allSettled([
    fetchGoogleBook(code),
    fetchOpenLibraryBook(code)
   ])
   const google=googleResult.status==='fulfilled'?googleResult.value:null
   const openLibrary=openLibraryResult.status==='fulfilled'?openLibraryResult.value:null
   const found=mergeBookMetadata(code,google,openLibrary)
   if(found) {
    setEdit({...emptyBook,...found,isbn:code,createdAt:new Date().toISOString()})
    const sources=[google?'Google Books':'',openLibrary?'Open Library':''].filter(Boolean).join(' et ')
    setNotice(`Informations trouvées via ${sources}. Vérifie l’édition et complète l’emplacement si nécessaire.`)
   } else {
    setEdit({...emptyBook,isbn:code})
    setNotice('Aucun résultat trouvé. Tu peux compléter la fiche manuellement.')
   }
  } catch {
   setEdit({...emptyBook,isbn:code})
   setNotice('Les services de recherche sont indisponibles. Tu peux saisir la fiche manuellement.')
  } finally {
   setLoading(false)
  }
 }
 async function saveBook(e:React.FormEvent) { e.preventDefault(); if(!edit?.title.trim()) return; const data={...edit,createdAt:edit.createdAt||new Date().toISOString()}; if(data.id) await db.books.put(data); else await db.books.add(data); setEdit(null); await refresh(); setNotice('Livre enregistré.') }
 async function deleteBook(book:Book) { if(!book.id)return; if(loanForBook(book.id)){setNotice('Impossible de supprimer ce livre tant que son prêt est en cours. Enregistre d’abord son retour.');return} if(!confirm(`Supprimer « ${book.title} » ? Son historique de prêts sera conservé.`)) return; await db.books.delete(book.id); setSelected(null); await refresh() }
 async function addLoan(e:React.FormEvent) { e.preventDefault(); if(!current?.id||!borrowerId) return; if(loanForBook(current.id)){setNotice('Ce livre possède déjà un prêt en cours. Enregistre son retour avant de le prêter à nouveau.');return} const person=borrowers.find(p=>p.id===Number(borrowerId)); if(!person)return; await db.loans.add({bookId:current.id,bookTitle:current.title,borrower:person.name,borrowerId:person.id,loanDate:today(),dueDate,notes:loanNotes.trim()}); setLoanOpen(false);setBorrowerId('');setLoanNotes('');const d=new Date();d.setDate(d.getDate()+14);d.setMinutes(d.getMinutes()-d.getTimezoneOffset());setDueDate(d.toISOString().slice(0,10));await refresh();setNotice('Prêt enregistré.') }
 async function returnLoan(l:Loan) { await db.loans.put({...l,returnedAt:today()}); await refresh();setNotice(`Retour de « ${books.find(b=>b.id===l.bookId)?.title||'livre'} » enregistré.`) }
 async function saveBorrower(e:React.FormEvent) { e.preventDefault(); if(!editingBorrower?.name.trim())return; const name=editingBorrower.name.trim(); if(borrowers.some(p=>p.id!==editingBorrower.id&&p.name.trim().toLocaleLowerCase('fr')===name.toLocaleLowerCase('fr'))){setNotice('Cet emprunteur existe déjà dans le carnet.');return} if(editingBorrower.id){const old=borrowers.find(p=>p.id===editingBorrower.id); await db.transaction('rw',db.borrowers,db.loans,async()=>{await db.borrowers.put({...editingBorrower,name});if(old&&old.name!==name)await db.loans.where('borrowerId').equals(editingBorrower.id!).modify({borrower:name})})}else await db.borrowers.add({...editingBorrower,name}); setEditingBorrower(null);await refresh();setNotice('Fiche emprunteur enregistrée.') }
 async function deleteBorrower(person:Borrower) { if(!person.id||!confirm(`Supprimer la fiche de ${person.name} ? Les prêts historiques seront conservés.`))return; await db.transaction('rw',db.borrowers,db.loans,async()=>{await db.loans.where('borrowerId').equals(person.id!).modify({borrowerId:undefined});await db.borrowers.delete(person.id!)});await refresh();setNotice('Fiche emprunteur supprimée. Les prêts restent dans l’historique.') }
 async function exportData() { const payload={books,loans,borrowers,exportedAt:new Date().toISOString()}; const a=document.createElement('a'); a.href=URL.createObjectURL(new Blob([JSON.stringify(payload,null,2)],{type:'application/json'})); a.download='ma-bibliotheque-sauvegarde.json'; a.click(); URL.revokeObjectURL(a.href) }
 async function importPayload(d:any) { if(!Array.isArray(d.books)||!Array.isArray(d.loans)) throw new Error('Format de sauvegarde invalide'); if(!Array.isArray(d.borrowers))d.borrowers=[]; await db.transaction('rw',db.books,db.loans,db.borrowers,async()=>{await db.books.clear();await db.loans.clear();await db.borrowers.clear();await db.books.bulkAdd(d.books);const incomingBooks=d.books;const incomingLoans=(d.loans||[]).map((l:Loan)=>({...l,bookTitle:l.bookTitle||incomingBooks.find((b:Book)=>b.id===l.bookId)?.title||'Livre supprimé'}));if(incomingLoans.length)await db.loans.bulkAdd(incomingLoans);if(d.borrowers.length)await db.borrowers.bulkAdd(d.borrowers);const people=d.borrowers;const names=[...new Set<string>((d.loans||[]).map((l:Loan)=>String(l.borrower||'').trim()).filter(Boolean))];for(const name of names){const person=people.find((p:Borrower)=>p.name.trim().toLocaleLowerCase('fr')===name.toLocaleLowerCase('fr'));const id=person?.id??await db.borrowers.add({...emptyBorrower(),name});await db.loans.where('borrower').equals(name).modify({borrowerId:id})}});await refresh() }
 async function importData(file?:File) { if(!file)return; try { const d=JSON.parse(await file.text()); if(window.booktekBackup) await window.booktekBackup.beforeRestore({books,loans,borrowers,exportedAt:new Date().toISOString()}); await importPayload(d);setNotice('Sauvegarde importée.')}catch{setNotice('Fichier de sauvegarde invalide.')} }
 async function createManualBackup() { if(!window.booktekBackup){setNotice('Les sauvegardes automatiques sont disponibles dans la version Windows.');return} setBackupBusy(true);try{await window.booktekBackup.create({books,loans,borrowers,exportedAt:new Date().toISOString()});setBackups(await window.booktekBackup.list());setNotice('Sauvegarde créée avec succès.')}catch{setNotice('Impossible de créer la sauvegarde.')}finally{setBackupBusy(false)} }
 async function restoreBackup(name:string) { if(!window.booktekBackup)return; if(!confirm('Restaurer cette sauvegarde ? Les données actuelles seront remplacées. Une sauvegarde de sécurité sera créée avant la restauration.'))return;setBackupBusy(true);try{await window.booktekBackup.beforeRestore({books,loans,borrowers,exportedAt:new Date().toISOString()});const data=await window.booktekBackup.read(name);await importPayload(data);setBackups(await window.booktekBackup.list());setNotice('Sauvegarde restaurée avec succès.')}catch(error){console.error(error);setNotice('La restauration a échoué. Les données actuelles ont été préservées si la sauvegarde était invalide.')}finally{setBackupBusy(false)} }
 return <div className="shell">
  <aside className="sidebar">
   <div className="brand"><BookOpen size={42}/><b>Ma Bibliothèque</b><small>Gestion de ma bibliothèque personnelle</small></div>
   <nav>
    <button className={section==='library'?'active':''} onClick={()=>setSection('library')}><Library/>Bibliothèque</button>
    <button className={section==='loans'?'active':''} onClick={()=>setSection('loans')}><Handshake/>Mes prêts</button>
    <button className={section==='borrowers'?'active':''} onClick={()=>setSection('borrowers')}><Users/>Emprunteurs</button>
    <button className={section==='stats'?'active':''} onClick={()=>setSection('stats')}><BarChart3/>Statistiques</button>
    <button className={section==='backups'?'active':''} onClick={async()=>{setSection('backups');if(window.booktekBackup)setBackups(await window.booktekBackup.list())}}><ShieldCheck/>Sauvegardes</button>
   </nav>
   <div className="sidebottom"><button onClick={exportData}><Download/>Exporter la sauvegarde</button><label className="sidebutton"><Upload/>Importer une sauvegarde<input type="file" accept="application/json" onChange={e=>importData(e.target.files?.[0])}/></label><small>Vos données restent sur cet appareil.</small></div>
  </aside>
  <main className="main">
   <header className="topbar"><div className="isbn"><Barcode/><input value={isbn} onChange={e=>setIsbn(e.target.value)} onKeyDown={e=>e.key==='Enter'&&lookupISBN()} placeholder="Scanner ou saisir un ISBN…"/><button onClick={()=>lookupISBN()} disabled={loading}>{loading?'…':'Rechercher'}</button></div><div className="topmeta"><span>{books.length} livres</span><span>{activeLoans.length} prêts en cours</span><span className={overdueLoans.length?'late-count':''}>{overdueLoans.length} retard(s)</span></div></header>
   {notice&&<div className="notice">{notice}<button onClick={()=>setNotice('')}><X size={15}/></button></div>}
   {section==='library'&&<>
    <div className="toolbar"><div className="search"><Search/><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Rechercher un livre, un auteur, un mot-clé…"/></div><select value={genre} onChange={e=>setGenre(e.target.value)}><option>Tous les genres</option>{genres.map(g=><option key={g}>{g}</option>)}</select><select value={location} onChange={e=>setLocation(e.target.value)}><option>Tous les emplacements</option>{places.map(p=><option key={p}>{p}</option>)}</select><div className="viewtoggle"><button className={view==='grid'?'chosen':''} onClick={()=>setView('grid')}><Grid3X3/></button><button className={view==='list'?'chosen':''} onClick={()=>setView('list')}><List/></button></div><button className="primary" onClick={()=>setEdit({...emptyBook})}><Plus/>Ajouter</button></div>
    <div className="content">
     <section className="catalog"><div className="sectionhead"><div><h2>Ma collection</h2><small>{filtered.length} livre(s) trouvé(s)</small></div></div><div className={view==='grid'?'bookgrid':'booklist'}>
      {filtered.map(b=><button key={b.id} className={`booktile ${current?.id===b.id?'selected':''}`} onClick={()=>setSelected(b.id!)}>
       <div className="cover">{b.cover?<img src={b.cover} onError={e=>(e.currentTarget.style.display='none')} />:<BookOpen size={34}/>}</div><b>{b.title}</b><small>{b.author}</small>
      </button>)}
      {!filtered.length&&<div className="empty">Aucun livre ne correspond à la recherche.</div>}
     </div></section>
     <section className="detail">
      {current?<><div className="detailtop"><div className="bigcover">{current.cover?<img src={current.cover}/>:<BookOpen size={60}/>}</div><div className="bookinfo"><div className="eyebrow">FICHE DU LIVRE</div><h1>{current.title}</h1><h3>{current.author}</h3><div className="metadata"><span><BookOpen/> {current.pages||'—'} pages</span><span>Genre : {current.genre||'—'}</span><span>Emplacement : <b>{current.location||'Non renseigné'}</b></span><span>Parution : {current.year||'—'}</span><span>ISBN : {current.isbn||'—'}</span></div><div className="summary"><h3>Résumé</h3><p>{current.summary||'Aucun résumé renseigné pour ce livre.'}</p></div><div className="actions"><button className="primary" onClick={()=>db.books.update(current.id!,{read:!current.read}).then(refresh)}><Check/>{current.read?'Lu':'Marquer comme lu'}</button><button onClick={()=>setEdit(current)}><Pencil/>Modifier</button><button className="danger" onClick={()=>deleteBook(current)}><Trash2/>Supprimer</button></div></div></div></>:<div className="empty">Sélectionne un livre ou ajoute ton premier ouvrage.</div>}
      <div className="loanspanel"><div className="panelhead"><h2><Handshake/> Gestion des prêts</h2>{current&&<button className="primary" onClick={()=>{if(!borrowers.length){setSection('borrowers');setEditingBorrower(emptyBorrower());setNotice('Crée d’abord une fiche emprunteur.')}else if(loanForBook(current.id)){setNotice('Ce livre est déjà prêté. Enregistre son retour avant de créer un nouveau prêt.')}else setLoanOpen(true)}}><Plus/>Nouveau prêt</button>}</div>
       <div className="loanrows">{current?loans.filter(l=>l.bookId===current.id).map(l=><div className="loanrow" key={l.id}><div><b>{l.borrower}</b><small>Prêté le {fmt(l.loanDate)} · retour prévu {fmt(l.dueDate)}</small></div><span className={`status ${l.returnedAt?'returned':isOverdue(l)?'overdue':'ongoing'}`}>{l.returnedAt?'Rendu':isOverdue(l)?'En retard':'En cours'}</span>{!l.returnedAt&&<button className="iconbutton" title="Enregistrer le retour" onClick={()=>returnLoan(l)}><RotateCcw/></button>}</div>):<small>Sélectionne un livre pour voir ses prêts.</small>}</div>
      </div>
     </section>
    </div>
   </>}
   {section==='loans'&&<section className="fullpanel"><div className="pagehead"><div><h1>Suivi des prêts</h1><p className="muted">Tous les prêts, retours et échéances de ta bibliothèque.</p></div>{current&&<button className="primary" onClick={()=>{if(!borrowers.length){setSection('borrowers');setEditingBorrower(emptyBorrower());setNotice('Crée d’abord une fiche emprunteur.')}else if(current?.id&&loanForBook(current.id)){setNotice('Ce livre est déjà prêté. Enregistre son retour avant de créer un nouveau prêt.')}else setLoanOpen(true)}}><Plus/>Nouveau prêt</button>}</div><div className="loan-summary"><button className={loanFilter==='active'?'picked':''} onClick={()=>setLoanFilter('active')}><small>En cours</small><b>{activeLoans.length}</b></button><button className={loanFilter==='overdue'?'picked':''} onClick={()=>setLoanFilter('overdue')}><small>En retard</small><b className="late-text">{overdueLoans.length}</b></button><button className={loanFilter==='returned'?'picked':''} onClick={()=>setLoanFilter('returned')}><small>Rendus</small><b>{returnedLoans.length}</b></button><button className={loanFilter==='all'?'picked':''} onClick={()=>setLoanFilter('all')}><small>Total historique</small><b>{loans.length}</b></button></div><div className="loan-tools"><input value={loanQuery} onChange={e=>setLoanQuery(e.target.value)} placeholder="Rechercher un livre, un emprunteur…"/><select value={loanFilter} onChange={e=>setLoanFilter(e.target.value as typeof loanFilter)}><option value="all">Tous les prêts</option><option value="active">En cours</option><option value="overdue">En retard</option><option value="returned">Rendus</option></select></div>{filteredLoans.map(l=>{const b=books.find(x=>x.id===l.bookId);const title=b?.title||l.bookTitle||'Livre supprimé';const late=isOverdue(l);return <div className={`allloan ${late?'allloan-late':''}`} key={l.id}><div className="loan-book"><b>{title}</b><small><UserRound size={13}/> {l.borrower} · prêté le {fmt(l.loanDate)}</small><small><CalendarDays size={13}/> Retour prévu le {fmt(l.dueDate)}{l.returnedAt?` · rendu le ${fmt(l.returnedAt)}`:''}</small>{l.notes&&<small className="loan-note">Note : {l.notes}</small>}</div><span className={`status ${l.returnedAt?'returned':late?'overdue':'ongoing'}`}>{l.returnedAt?'Rendu':late?'En retard':'En cours'}</span>{!l.returnedAt&&<button className="return-button" onClick={()=>returnLoan(l)}><RotateCcw size={15}/> Enregistrer le retour</button>}</div>})}{!filteredLoans.length&&<div className="empty">Aucun prêt ne correspond à ce filtre.</div>}</section>}
   {section==='borrowers'&&<section className="fullpanel"><div className="pagehead"><div><h1>Emprunteurs</h1><p className="muted">Carnet des personnes à qui tu prêtes tes livres.</p></div><button className="primary" onClick={()=>setEditingBorrower(emptyBorrower())}><Plus/>Nouvel emprunteur</button></div><div className="borrower-grid">{borrowers.map(person=>{const personLoans=loans.filter(l=>l.borrowerId===person.id||(!l.borrowerId&&l.borrower===person.name));const active=personLoans.filter(l=>!l.returnedAt);return <article className="borrower-card" key={person.id}><div className="borrower-avatar"><UserRound/></div><div className="borrower-title"><h3>{person.name}</h3><small>{personLoans.length} prêt(s) · {active.length} en cours</small></div>{person.email&&<p><Mail size={14}/>{person.email}</p>}{person.phone&&<p><Phone size={14}/>{person.phone}</p>}{person.notes&&<p className="borrower-notes">{person.notes}</p>}<div className="borrower-actions"><button onClick={()=>setEditingBorrower(person)}><Pencil size={15}/> Modifier</button><button className="danger" onClick={()=>deleteBorrower(person)}><Trash2 size={15}/> Supprimer</button></div></article>})}{!borrowers.length&&<div className="empty">Aucun emprunteur enregistré. Ajoute une personne pour commencer à gérer les prêts.</div>}</div></section>}
   {section==='backups'&&<section className="fullpanel backup-panel"><div className="pagehead"><div><h1>Sauvegardes</h1><p className="muted">Copies locales de tes livres, emprunteurs et prêts.</p></div><button className="primary" onClick={createManualBackup} disabled={backupBusy}><Download size={16}/>{backupBusy?'En cours…':'Créer une sauvegarde'}</button></div><div className="backup-info"><ShieldCheck/><div><b>Sauvegarde automatique activée</b><p>BookTek crée une sauvegarde au démarrage ou après une modification, au maximum une fois par jour. Les 10 dernières sauvegardes sont conservées.</p><small>Les fichiers sont stockés localement dans le dossier de données de BookTek sur ce PC.</small></div></div><div className="backup-list-head"><h2>Historique des sauvegardes</h2><button onClick={async()=>{if(window.booktekBackup)setBackups(await window.booktekBackup.list())}}><RefreshCw size={15}/> Actualiser</button></div>{!window.booktekBackup?<div className="empty">Les sauvegardes automatiques sont disponibles dans l'application Windows.</div>:backups.map(item=><div className="backup-row" key={item.name}><div><b><Clock size={15}/> {new Date(item.date).toLocaleString('fr-FR')}</b><small>{item.name} · {(item.size/1024).toFixed(1)} Ko</small></div><button disabled={backupBusy} onClick={()=>restoreBackup(item.name)}><RotateCcw size={15}/> Restaurer</button></div>)}{window.booktekBackup&&backups.length===0&&<div className="empty">Aucune sauvegarde pour le moment. Une sauvegarde sera créée automatiquement.</div>}</section>}
   {section==='stats'&&<section className="stats"><h1>Statistiques</h1><div className="statgrid"><div><small>Livres dans la collection</small><strong>{books.length}</strong></div><div><small>Prêts en cours</small><strong>{activeLoans.length}</strong></div><div><small>Prêts en retard</small><strong className={overdueLoans.length?'late-text':''}>{overdueLoans.length}</strong></div><div><small>Retours effectués</small><strong>{returnedLoans.length}</strong></div><div><small>Emprunteurs enregistrés</small><strong>{borrowers.length}</strong></div><div><small>Livres lus</small><strong>{books.filter(b=>b.read).length}</strong></div><div><small>Genres représentés</small><strong>{genres.length}</strong></div></div></section>}
  </main>
  {edit&&<div className="modalback"><form className="modal" onSubmit={saveBook}><div className="modalhead"><h2>{edit.id?'Modifier le livre':'Ajouter un livre'}</h2><button type="button" onClick={()=>setEdit(null)}><X/></button></div><div className="formgrid">
   <label>ISBN<input value={edit.isbn} onChange={e=>setEdit({...edit,isbn:e.target.value})}/></label><label>Titre *<input required value={edit.title} onChange={e=>setEdit({...edit,title:e.target.value})}/></label><label>Auteur<input value={edit.author} onChange={e=>setEdit({...edit,author:e.target.value})}/></label><label>Nombre de pages<input type="number" min="0" value={edit.pages||''} onChange={e=>setEdit({...edit,pages:Number(e.target.value)})}/></label><label>Genre<input value={edit.genre} onChange={e=>setEdit({...edit,genre:e.target.value})}/></label><label>Année de parution<input value={edit.year} onChange={e=>setEdit({...edit,year:e.target.value})}/></label><label>Emplacement<input placeholder="Ex. Étagère A1" value={edit.location} onChange={e=>setEdit({...edit,location:e.target.value})}/></label><label>URL de la jaquette<input value={edit.cover} onChange={e=>setEdit({...edit,cover:e.target.value})}/></label><label className="wide">Résumé<textarea rows={4} value={edit.summary} onChange={e=>setEdit({...edit,summary:e.target.value})}/></label></div><div className="modalactions"><button type="button" onClick={()=>setEdit(null)}>Annuler</button><button className="primary" type="submit">Enregistrer le livre</button></div></form></div>}
  {loanOpen&&<div className="modalback"><form className="modal compact" onSubmit={addLoan}><div className="modalhead"><h2>Nouveau prêt</h2><button type="button" onClick={()=>setLoanOpen(false)}><X/></button></div><p>Livre : <b>{current?.title}</b></p><label>Emprunteur<select required value={borrowerId} onChange={e=>setBorrowerId(e.target.value)}><option value="">Choisir une personne…</option>{borrowers.map(person=><option key={person.id} value={person.id}>{person.name}</option>)}</select></label><label>Date de retour prévue<input required type="date" min={today()} value={dueDate} onChange={e=>setDueDate(e.target.value)}/></label><label>Note (facultatif)<textarea rows={3} value={loanNotes} onChange={e=>setLoanNotes(e.target.value)} placeholder="Ex. Livre prêté avec sa jaquette…"/></label><div className="modalactions"><button type="button" onClick={()=>setLoanOpen(false)}>Annuler</button><button className="primary">Enregistrer le prêt</button></div></form></div>}
  {editingBorrower&&<div className="modalback"><form className="modal compact" onSubmit={saveBorrower}><div className="modalhead"><h2>{editingBorrower.id?'Modifier l’emprunteur':'Nouvel emprunteur'}</h2><button type="button" onClick={()=>setEditingBorrower(null)}><X/></button></div><label>Nom *<input required autoFocus value={editingBorrower.name} onChange={e=>setEditingBorrower({...editingBorrower,name:e.target.value})} placeholder="Prénom et nom"/></label><label>Adresse e-mail<input type="email" value={editingBorrower.email} onChange={e=>setEditingBorrower({...editingBorrower,email:e.target.value})} placeholder="nom@exemple.fr"/></label><label>Téléphone<input value={editingBorrower.phone} onChange={e=>setEditingBorrower({...editingBorrower,phone:e.target.value})} placeholder="06…"/></label><label>Notes<textarea rows={3} value={editingBorrower.notes} onChange={e=>setEditingBorrower({...editingBorrower,notes:e.target.value})} placeholder="Informations utiles…"/></label><div className="modalactions"><button type="button" onClick={()=>setEditingBorrower(null)}>Annuler</button><button className="primary">Enregistrer</button></div></form></div>}
 </div>
}
