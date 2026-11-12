const { app, BrowserWindow, ipcMain } = require('electron')
const path = require('node:path')
const fs = require('node:fs/promises')

const backupDir = () => path.join(app.getPath('userData'), 'backups')
const safeName = name => typeof name === 'string' && /^booktek-\d{8}-\d{6}-(auto|manual|before-restore)\.json$/.test(name)

async function listBackups() {
  await fs.mkdir(backupDir(), { recursive: true })
  const files = await fs.readdir(backupDir())
  const rows = await Promise.all(files.filter(safeName).map(async name => {
    const stat = await fs.stat(path.join(backupDir(), name))
    return { name, date: stat.mtime.toISOString(), size: stat.size }
  }))
  return rows.sort((a, b) => b.date.localeCompare(a.date))
}

async function createBackup(data, type = 'manual') {
  if (!data || !Array.isArray(data.books) || !Array.isArray(data.loans) || !Array.isArray(data.borrowers)) {
    throw new Error('Invalid backup data')
  }
  await fs.mkdir(backupDir(), { recursive: true })
  const existing = await listBackups()
  if (type === 'auto') {
    const today = new Date().toISOString().slice(0, 10).replaceAll('-', '')
    const todayAuto = existing.find(item =>
      item.name.startsWith(`booktek-${today}-`) && item.name.endsWith('-auto.json')
    )
    if (todayAuto) return todayAuto
  }
  const stamp = new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15)
  const name = `booktek-${stamp}-${type}.json`
  const target = path.join(backupDir(), name)
  const temp = `${target}.tmp`
  await fs.writeFile(temp, JSON.stringify({ ...data, backupCreatedAt: new Date().toISOString() }, null, 2), 'utf8')
  await fs.rename(temp, target)
  const all = await listBackups()
  for (const old of all.slice(10)) await fs.unlink(path.join(backupDir(), old.name)).catch(() => {})
  return { name, date: new Date().toISOString(), size: (await fs.stat(target)).size }
}

ipcMain.handle('booktek:backup-list', () => listBackups())
ipcMain.handle('booktek:backup-create', (_event, data, type) => createBackup(data, type === 'auto' ? 'auto' : 'manual'))
ipcMain.handle('booktek:backup-read', async (_event, name) => {
  if (!safeName(name)) throw new Error('Invalid backup name')
  const content = await fs.readFile(path.join(backupDir(), name), 'utf8')
  const data = JSON.parse(content)
  if (!Array.isArray(data.books) || !Array.isArray(data.loans) || !Array.isArray(data.borrowers)) throw new Error('Invalid backup file')
  return data
})
ipcMain.handle('booktek:backup-before-restore', (_event, data) => createBackup(data, 'before-restore'))

function createWindow() {
  const win = new BrowserWindow({
    width: 1440, height: 920, minWidth: 1050, minHeight: 700,
    title: 'Ma Bibliothèque',
    backgroundColor: '#f3f6fc',
    webPreferences: { preload: path.join(__dirname, 'preload.cjs'), contextIsolation: true, nodeIntegration: false }
  })
  if (!app.isPackaged) win.loadURL('http://127.0.0.1:5173')
  else win.loadFile(path.join(__dirname, '../dist/index.html'))
}
app.whenReady().then(() => {
  createWindow()
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow() })
})
app.on('window-all-closed', () => { if (process.platform !== 'darwin') app.quit() })
