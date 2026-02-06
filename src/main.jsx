import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
// Ensure this path is 100% correct relative to main.jsx
import './assets/css/style.css' 

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)