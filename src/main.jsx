import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
// Ensure this path is 100% correct relative to main.jsx
import './assets/css/style.css'

// PWA auto-update: sw.js already does skipWaiting()+clients.claim(), so a new
// deploy's SW takes control moments after the app opens. Reloading on that
// controller swap is what makes the update VISIBLE without the user manually
// refreshing / reinstalling. The `hadController` guard skips the very first
// SW install (fresh visit), which would otherwise reload a brand-new session.
if ('serviceWorker' in navigator) {
  let hadController = !!navigator.serviceWorker.controller
  let reloaded = false                      // belt-and-braces against reload loops
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (!hadController) { hadController = true; return }
    if (reloaded) return
    reloaded = true
    window.location.reload()
  })
}

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)