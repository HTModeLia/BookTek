const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('booktekBackup', {
  list: () => ipcRenderer.invoke('booktek:backup-list'),
  create: data => ipcRenderer.invoke('booktek:backup-create', data, 'manual'),
  createAutomatic: data => ipcRenderer.invoke('booktek:backup-create', data, 'auto'),
  read: name => ipcRenderer.invoke('booktek:backup-read', name),
  beforeRestore: data => ipcRenderer.invoke('booktek:backup-before-restore', data)
})
