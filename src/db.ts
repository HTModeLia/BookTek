import Dexie, { type Table } from 'dexie'

export type Book = {
  id?: number; isbn: string; title: string; author: string; pages: number;
  summary: string; cover: string; genre: string; year: string; location: string;
  read: boolean; createdAt: string
}

export type Borrower = {
  id?: number
  name: string
  email: string
  phone: string
  notes: string
  createdAt: string
}

export type Loan = {
  id?: number
  bookId: number
  borrower: string
  borrowerId?: number
  bookTitle?: string
  loanDate: string
  dueDate: string
  returnedAt?: string
  notes?: string
}

class LibraryDB extends Dexie {
  books!: Table<Book, number>
  loans!: Table<Loan, number>
  borrowers!: Table<Borrower, number>

  constructor() {
    super('ma-bibliotheque')
    this.version(1).stores({
      books: '++id, isbn, title, author, genre, location',
      loans: '++id, bookId, borrower, dueDate, returnedAt'
    })
    this.version(2).stores({
      books: '++id, isbn, title, author, genre, location',
      loans: '++id, bookId, borrower, borrowerId, dueDate, returnedAt',
      borrowers: '++id, name, email, phone'
    })
  }
}

export const db = new LibraryDB()
