# Interview Copilot — Desktop App (Electron)

The desktop app wraps the companion web UI with OS-level privacy features that a browser cannot provide.

## Privacy Features

| Feature | How it works |
|---|---|
| **Invisible on Screen Share** | `win.setContentProtection(true)` — window appears black/blank in all screen capture APIs (Zoom/Teams/Meet share, OBS, etc.) |
| **Hidden from Taskbar / Dock** | `skipTaskbar: true` + `app.dock.hide()` (macOS) — no entry in Windows taskbar, no icon in macOS Dock |
| **Hidden from Alt+Tab / Cmd+Tab** | `type: 'panel'` (macOS) removes from Mission Control/Exposé. `type: 'toolbar'` (Windows) sets WS_EX_TOOLWINDOW to remove from Alt+Tab |
| **Always on Top** | `setAlwaysOnTop(true, 'screen-saver')` — stays above fullscreen video calls |
| **Panic Hide** | Global `Ctrl+Shift+H` hides the window at the OS level instantly — even from another app |
| **Cursor Undetectability** | CSS `cursor: none` over the companion window so cursor movement isn't visible on screen share (complementary to content protection) |

> **Note:** "Invisible in Task Manager / Activity Monitor" is NOT implemented — that requires process-hiding techniques used by malware and is outside scope.

## Setup

```bash
cd electron
npm install
```

## Run

```bash
# Make sure the backend is running first:
cd ../backend && uvicorn app.main:app --reload &

# Then launch the desktop app:
cd ../electron && npm start
```

The app opens at the top-right corner of your primary screen. It connects to `http://localhost:8000/companion` by default.

## Build distributable

```bash
npm run dist:mac    # .dmg for macOS
npm run dist:win    # .exe installer for Windows
npm run dist:linux  # .AppImage for Linux
```

## Configuration

Edit `main.js` to change:
- `BACKEND_URL` — default `http://localhost:8000/companion`
- `WIN_WIDTH` / `WIN_HEIGHT` — window size (default 460×700)
- `CORNER_GAP` — gap from screen edge in pixels
- `HIDE_HOTKEY` — global shortcut (default `Ctrl+Shift+H`)

## Usage during an interview

1. Start backend: `docker-compose up`
2. Launch desktop app: `npm start` (from `electron/` dir)
3. The window appears top-right — **it will not show up in your screen share**
4. Select Meeting Audio source → Start Session
5. When prompted to share screen, select your Teams/Meet/Zoom window with audio
6. Position window on your secondary monitor or in a corner of your primary

### Emergency hide
- **`Ctrl+Shift+H`** — global shortcut, works from any app, instantly hides/shows the window
- Click the 🛡 button in the header — same effect
- The window is already invisible on screen share, but this hides it visually from anyone looking at your physical screen

## macOS notes

`LSUIElement: true` in the app plist prevents the app from appearing in `Cmd+Tab` application switcher. This is set via `electron-builder`'s `mac.extendInfo` config in `package.json`.

## Windows notes

`type: 'toolbar'` sets the `WS_EX_TOOLWINDOW` extended window style, which removes the window from the Alt+Tab switcher. Combined with `skipTaskbar: true`, there is no visible OS presence except the system tray icon.
