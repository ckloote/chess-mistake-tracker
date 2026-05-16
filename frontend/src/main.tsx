import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'

import App from './App.tsx'
import { Dashboard } from './pages/Dashboard.tsx'
import { Games } from './pages/Games.tsx'
import { GameDetail } from './pages/GameDetail.tsx'
import { Mistakes } from './pages/Mistakes.tsx'
import { MistakeDetail } from './pages/MistakeDetail.tsx'
import { Stats } from './pages/Stats.tsx'
import { Settings } from './pages/Settings.tsx'
import 'chessground/assets/chessground.base.css'
import 'chessground/assets/chessground.brown.css'
import 'chessground/assets/chessground.cburnett.css'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Single-user local-first app — server data is essentially private to
      // this browser. Keep results around long enough to make filter changes
      // feel snappy without holding stale data forever.
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
})

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <Dashboard /> },
      { path: 'games', element: <Games /> },
      { path: 'games/:id', element: <GameDetail /> },
      { path: 'mistakes', element: <Mistakes /> },
      { path: 'mistakes/:id', element: <MistakeDetail /> },
      { path: 'stats', element: <Stats /> },
      { path: 'settings', element: <Settings /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
)
