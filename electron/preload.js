'use strict';
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  isElectron: true,

  // Window controls
  hide:     () => ipcRenderer.send('win:hide'),
  show:     () => ipcRenderer.send('win:show'),
  minimize: () => ipcRenderer.send('win:minimize'),
  close:    () => ipcRenderer.send('win:close'),

  // Position helpers
  moveToCorner: (corner) => ipcRenderer.send('win:move', corner),  // 'tr'|'tl'|'br'|'bl'

  // Privacy status — read back from main
  onPrivacyStatus: (cb) => ipcRenderer.on('privacy:status', (_e, status) => cb(status)),
});
