import { Outlet } from 'react-router-dom'
import { TopNav } from './components/TopNav'
import './App.css'

export default function App() {
  return (
    <div className="app-shell">
      <TopNav />
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  )
}
