'use strict';
/**
 * AI Interview Copilot — Electron main process
 *
 * Privacy features implemented:
 *  • setContentProtection(true)   → window appears black in all screen recording/share tools
 *                                   (uses WDA_EXCLUDEFROMCAPTURE on Windows, setSharingType(.none) on macOS)
 *  • skipTaskbar: true            → no entry in Windows taskbar / removed from macOS Dock
 *  • app.dock.hide()              → macOS Dock icon completely removed
 *  • LSUIElement: true (plist)    → macOS: app never appears in Cmd+Tab app switcher
 *  • type: 'panel' (macOS)        → window excluded from Mission Control / Exposé
 *  • type: 'toolbar' (Windows)    → WS_EX_TOOLWINDOW set → removed from Alt+Tab
 *  • setAlwaysOnTop('screen-saver') → stays above fullscreen video calls
 *  • globalShortcut Ctrl+Shift+H  → instant hide/show from anywhere on the OS
 */

const { app, BrowserWindow, globalShortcut, ipcMain, screen, Menu, Tray } = require('electron');
const path = require('path');

// ── Config ─────────────────────────────────────────────────────────────────────
const BACKEND_URL  = 'http://localhost:8000/companion';
const WIN_WIDTH    = 460;
const WIN_HEIGHT   = 700;
const HIDE_HOTKEY  = 'CommandOrControl+Shift+H';
const CORNER_GAP   = 20;  // px from screen edge

// ── macOS: remove from Dock before any window is created ──────────────────────
if (process.platform === 'darwin') {
  app.dock.hide();
}

// ── State ─────────────────────────────────────────────────────────────────────
let win   = null;
let tray  = null;   // system-tray icon (the only visible OS presence)

// ─────────────────────────────────────────────────────────────────────────────
// Window factory
// ─────────────────────────────────────────────────────────────────────────────
function createWindow() {
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;

  win = new BrowserWindow({
    width:  WIN_WIDTH,
    height: WIN_HEIGHT,

    // ── Position: top-right corner by default ────────────────────────────────
    x: sw - WIN_WIDTH  - CORNER_GAP,
    y: CORNER_GAP,

    // ── Privacy window flags ─────────────────────────────────────────────────
    skipTaskbar: true,        // hide from Windows taskbar / macOS Dock

    // macOS:   'panel' → excluded from Mission Control, Exposé, Spaces
    // Windows: 'toolbar' → sets WS_EX_TOOLWINDOW, removed from Alt+Tab
    type: process.platform === 'darwin' ? 'panel' : 'toolbar',

    alwaysOnTop: true,        // stays above the video call window
    frame: false,             // no OS title bar — companion draws its own
    transparent: false,
    backgroundColor: '#0f1117',
    hasShadow: true,

    // Prevent accidental close
    closable: true,

    show: false,  // show after ready-to-show to avoid flash

    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  // ── Screen-share invisibility ─────────────────────────────────────────────
  // macOS: window content rendered as black in all screen capture APIs
  // Windows: SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE) via Electron
  win.setContentProtection(true);

  // Stay above fullscreen apps (Teams / Meet in presentation mode)
  // 'screen-saver' is the highest always-on-top level Electron exposes
  win.setAlwaysOnTop(true, 'screen-saver', 1);

  win.loadURL(BACKEND_URL);

  win.once('ready-to-show', () => {
    win.show();
    // Send privacy status to the renderer so it can update the UI badge
    sendPrivacyStatus();
  });

  // Prevent the window from being closed accidentally — hide instead
  win.on('close', (e) => {
    e.preventDefault();
    win.hide();
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// System tray (the only visible OS presence besides the window itself)
// ─────────────────────────────────────────────────────────────────────────────
function createTray() {
  // Use a blank 1×1 transparent icon to keep tray footprint minimal.
  // Replace with a real icon path if desired.
  const iconPath = path.join(__dirname, 'tray-icon.png');
  try {
    tray = new Tray(iconPath);
  } catch (_) {
    // If no icon file found, skip tray (app still works)
    return;
  }

  const menu = Menu.buildFromTemplate([
    { label: 'Show / Hide (Ctrl+Shift+H)', click: toggleVisibility },
    { type: 'separator' },
    { label: 'Quit', click: () => { app.exit(0); } },
  ]);

  tray.setToolTip('Interview Copilot');
  tray.setContextMenu(menu);
  tray.on('click', toggleVisibility);
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function toggleVisibility() {
  if (!win) return;
  if (win.isVisible()) {
    win.hide();
  } else {
    win.show();
    win.focus();
  }
}

function sendPrivacyStatus() {
  if (!win || !win.webContents) return;
  win.webContents.send('privacy:status', {
    screenShareProtected: true,                         // setContentProtection(true)
    taskbarHidden:        true,                         // skipTaskbar
    altTabHidden:         true,                         // panel/toolbar type
    dockHidden:           process.platform === 'darwin',
    platform:             process.platform,
    hotkey:               'Ctrl+Shift+H',
  });
}

function moveToCorner(corner) {
  if (!win) return;
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize;
  const positions = {
    tr: { x: sw - WIN_WIDTH  - CORNER_GAP, y: CORNER_GAP },
    tl: { x: CORNER_GAP,                   y: CORNER_GAP },
    br: { x: sw - WIN_WIDTH  - CORNER_GAP, y: sh - WIN_HEIGHT - CORNER_GAP },
    bl: { x: CORNER_GAP,                   y: sh - WIN_HEIGHT - CORNER_GAP },
  };
  const pos = positions[corner] || positions.tr;
  win.setPosition(pos.x, pos.y);
}

// ─────────────────────────────────────────────────────────────────────────────
// IPC handlers (called from renderer via preload.js)
// ─────────────────────────────────────────────────────────────────────────────
ipcMain.on('win:hide',     () => win && win.hide());
ipcMain.on('win:show',     () => win && (win.show(), win.focus()));
ipcMain.on('win:minimize', () => win && win.minimize());
ipcMain.on('win:close',    () => { if (win) { win.removeAllListeners('close'); win.close(); } });
ipcMain.on('win:move',     (_e, corner) => moveToCorner(corner));

// ─────────────────────────────────────────────────────────────────────────────
// App lifecycle
// ─────────────────────────────────────────────────────────────────────────────
app.whenReady().then(() => {
  createWindow();
  createTray();

  // Global OS-level shortcut — fires even when window is hidden or unfocused
  const ok = globalShortcut.register(HIDE_HOTKEY, toggleVisibility);
  if (!ok) console.warn('[copilot] Could not register global hotkey', HIDE_HOTKEY);
});

app.on('will-quit', () => {
  globalShortcut.unregisterAll();
});

// On macOS re-click on dock icon (won't appear since dock is hidden, but just in case)
app.on('activate', () => {
  if (win) { win.show(); win.focus(); }
});

// Prevent second instances
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (win) { win.show(); win.focus(); }
  });
}
