import { useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { Key } from 'chessground/types'
import { Chessground, type BoardArrow } from '../components/Chessground'
import { MoveList } from '../components/MoveList'
import { MistakeDetailPanel } from '../components/MistakeDetailPanel'
import { useGame, type Mistake } from '../api/games'

const STARTING_FEN =
  'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1'

function parseUci(uci: string): { from: Key; to: Key } | null {
  if (uci.length < 4) return null
  // promotion adds a trailing role char (e.g. 'e7e8q'); slicing is still safe.
  return { from: uci.slice(0, 2) as Key, to: uci.slice(2, 4) as Key }
}

function extractBestUci(mistake: Mistake): string | null {
  if (mistake.best_move_uci) return mistake.best_move_uci
  const debug = mistake.suggestion_debug
  if (debug && typeof debug === 'object' && 'm_best_uci' in debug) {
    const m = (debug as { m_best_uci?: unknown }).m_best_uci
    if (typeof m === 'string') return m
  }
  return null
}

export function GameDetail() {
  const { id } = useParams<{ id: string }>()
  const gameId = id ? Number.parseInt(id, 10) : undefined
  const { data: game, isPending, isError, error } = useGame(gameId)

  const [activePly, setActivePly] = useState(0)
  const lastPly = (game?.positions.length ?? 1) - 1

  // Reset ply when the game changes.
  useEffect(() => {
    setActivePly(0)
  }, [gameId])

  const mistakesByPly = useMemo(() => {
    const map = new Map<number, Mistake>()
    game?.mistakes.forEach((m) => map.set(m.ply, m))
    return map
  }, [game?.mistakes])

  const mistakesSorted = useMemo(
    () => [...(game?.mistakes ?? [])].sort((a, b) => a.ply - b.ply),
    [game?.mistakes],
  )

  // Keyboard navigation: arrows step ply, Shift+arrows jump mistake, Home/End.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      // Ignore when typing in inputs.
      const tag = (e.target as HTMLElement | null)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if (e.key === 'ArrowLeft') {
        e.preventDefault()
        if (e.shiftKey) {
          const prev = [...mistakesSorted].reverse().find((m) => m.ply < activePly)
          if (prev) setActivePly(prev.ply)
        } else {
          setActivePly((p) => Math.max(0, p - 1))
        }
      } else if (e.key === 'ArrowRight') {
        e.preventDefault()
        if (e.shiftKey) {
          const next = mistakesSorted.find((m) => m.ply > activePly)
          if (next) setActivePly(next.ply)
        } else {
          setActivePly((p) => Math.min(lastPly, p + 1))
        }
      } else if (e.key === 'Home') {
        e.preventDefault()
        setActivePly(0)
      } else if (e.key === 'End') {
        e.preventDefault()
        setActivePly(lastPly)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activePly, lastPly, mistakesSorted])

  if (isPending) {
    return (
      <div>
        <div className="page-header">
          <div className="page-header-title">
            <span className="eyebrow">Game</span>
            <h1>#{id}</h1>
          </div>
        </div>
        <p className="muted">Loading…</p>
      </div>
    )
  }
  if (isError || !game) {
    return (
      <div>
        <div className="page-header">
          <div className="page-header-title">
            <span className="eyebrow">Game</span>
            <h1>#{id}</h1>
          </div>
        </div>
        <div className="error">Failed to load game: {String(error)}</div>
      </div>
    )
  }

  const position = game.positions[activePly]
  const fen = position?.fen ?? STARTING_FEN
  const move = position?.uci ? parseUci(position.uci) : null
  const lastMove: [Key, Key] | undefined = move ? [move.from, move.to] : undefined

  const activeMistake = mistakesByPly.get(activePly) ?? null
  const arrows: BoardArrow[] = []
  if (activeMistake) {
    // User's actual move — red.
    if (position?.uci) {
      const userMove = parseUci(position.uci)
      if (userMove) arrows.push({ orig: userMove.from, dest: userMove.to, brush: 'red' })
    }
    // Engine's best — green, when available.
    const bestUci = extractBestUci(activeMistake)
    if (bestUci) {
      // best move is played from the position BEFORE the user moved, so its
      // squares are based on positions[ply - 1]'s board. The UCI is still in
      // standard notation though, so the squares parse the same way.
      const best = parseUci(bestUci)
      if (best) arrows.push({ orig: best.from, dest: best.to, brush: 'green' })
    }
  }

  const activeMistakeIndex = activeMistake
    ? mistakesSorted.findIndex((m) => m.id === activeMistake.id)
    : -1

  function goPrevMistake() {
    if (mistakesSorted.length === 0) return
    if (activeMistakeIndex <= 0) {
      const last = mistakesSorted[mistakesSorted.length - 1]
      if (last) setActivePly(last.ply)
    } else {
      const prev = mistakesSorted[activeMistakeIndex - 1]
      if (prev) setActivePly(prev.ply)
    }
  }
  function goNextMistake() {
    if (mistakesSorted.length === 0) return
    const next =
      activeMistakeIndex === -1
        ? mistakesSorted.find((m) => m.ply > activePly) ?? mistakesSorted[0]
        : mistakesSorted[(activeMistakeIndex + 1) % mistakesSorted.length]
    if (next) setActivePly(next.ply)
  }

  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Game review</span>
          <h1 className="review-title">
            <span>{game.white}</span>
            <span className="vs">versus</span>
            <span>{game.black}</span>
            <span className="result">{game.result.replace(/-/g, '–')}</span>
          </h1>
        </div>
        <Link to="/games" className="review-back">
          ← All games
        </Link>
      </div>

      <div className="review-layout">
        <div className="review-board">
          <Chessground
            fen={fen}
            orientation={game.user_color}
            lastMove={lastMove}
            arrows={arrows}
          />
          <div className="board-meta">
            <span>
              <span className="ply-marker">{activePly}</span>
              <span className="faint"> / {lastPly}</span>
              {position?.san ? (
                <>
                  {' · '}
                  <span className="ply-san">{position.san}</span>
                </>
              ) : null}
            </span>
            <span className="board-keys">
              <kbd>←</kbd>
              <kbd>→</kbd>
              step
              {'  '}·{'  '}
              <kbd>⇧</kbd>+ mistake
            </span>
          </div>
        </div>

        <aside className="review-side">
          <MoveList
            positions={game.positions}
            mistakesByPly={mistakesByPly}
            activePly={activePly}
            onSelect={setActivePly}
          />
          {activeMistake && (
            <MistakeDetailPanel
              mistake={activeMistake}
              total={mistakesSorted.length}
              index={Math.max(0, activeMistakeIndex)}
              onPrev={goPrevMistake}
              onNext={goNextMistake}
            />
          )}
          {!activeMistake && mistakesSorted.length > 0 && (
            <button
              type="button"
              className="jump-mistake"
              onClick={goNextMistake}
            >
              Jump to first mistake ({mistakesSorted.length} total)
            </button>
          )}
        </aside>
      </div>
    </div>
  )
}
