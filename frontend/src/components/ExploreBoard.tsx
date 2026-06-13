import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react'
import { Chess } from 'chess.js'
import { Chessground as initChessground } from 'chessground'
import type { Api } from 'chessground/api'
import type { Config } from 'chessground/config'
import type { Key } from 'chessground/types'
import type { DrawShape } from 'chessground/draw'
import type { BoardArrow } from './Chessground'

export interface ExploreState {
  fen: string
  sanHistory: string[]
}

export interface ExploreBoardProps {
  startingFen: string
  orientation: 'white' | 'black'
  // Engine best-move overlay (drawn as auto-shapes, separate from the position).
  arrows?: BoardArrow[]
  // Fired on every position change (move / undo / reset) and once on mount.
  onChange: (state: ExploreState) => void
}

// Imperative surface so the engine panel can play a suggested move on the board.
export interface ExploreHandle {
  playUci: (uci: string) => void
}

// Legal destination squares per origin, in the shape chessground wants.
function computeDests(chess: Chess): Map<Key, Key[]> {
  const dests = new Map<Key, Key[]>()
  for (const m of chess.moves({ verbose: true })) {
    const arr = dests.get(m.from as Key)
    if (arr) arr.push(m.to as Key)
    else dests.set(m.from as Key, [m.to as Key])
  }
  return dests
}

function turnColor(chess: Chess): 'white' | 'black' {
  return chess.turn() === 'w' ? 'white' : 'black'
}

// Interactive analysis board: drag pieces to play out lines from a starting
// position. chess.js is the rule authority (legality, SAN, FEN); chessground
// is the view. Pawn promotions auto-queen — sufficient for exploring "what if".
export const ExploreBoard = forwardRef<ExploreHandle, ExploreBoardProps>(
  function ExploreBoard(
    { startingFen, orientation, arrows, onChange }: ExploreBoardProps,
    ref,
  ) {
  const elRef = useRef<HTMLDivElement>(null)
  const apiRef = useRef<Api | null>(null)
  const chessRef = useRef<Chess>(new Chess(startingFen))
  // Keep the latest onChange without re-mounting the board.
  const onChangeRef = useRef(onChange)
  onChangeRef.current = onChange

  // Push current chess state to the board + notify the parent.
  function syncFromChess(lastMove?: [Key, Key]) {
    const chess = chessRef.current
    const api = apiRef.current
    if (api) {
      api.set({
        fen: chess.fen(),
        turnColor: turnColor(chess),
        lastMove,
        check: chess.inCheck() ? turnColor(chess) : undefined,
        movable: {
          free: false,
          color: turnColor(chess),
          dests: computeDests(chess),
        },
      })
    }
    onChangeRef.current({
      fen: chess.fen(),
      sanHistory: chess.history(),
    })
  }

  function handleUserMove(orig: Key, dest: Key) {
    const chess = chessRef.current
    try {
      // promotion is ignored by chess.js when the move isn't a promotion.
      chess.move({ from: orig, to: dest, promotion: 'q' })
    } catch {
      // Shouldn't happen — dests only offers legal moves — but reconcile the
      // board back to truth if it does.
      syncFromChess()
      return
    }
    syncFromChess([orig, dest])
  }

  useImperativeHandle(ref, () => ({
    playUci(uci: string) {
      if (uci.length < 4) return
      handleUserMove(uci.slice(0, 2) as Key, uci.slice(2, 4) as Key)
    },
  }))

  // Mount once. We reconfigure via api.set(); we never re-mount.
  useEffect(() => {
    if (!elRef.current) return
    const chess = chessRef.current
    const config: Config = {
      fen: chess.fen(),
      orientation,
      turnColor: turnColor(chess),
      coordinates: true,
      animation: { enabled: true, duration: 150 },
      highlight: { lastMove: true, check: true },
      drawable: { enabled: false, visible: true },
      movable: {
        free: false,
        color: turnColor(chess),
        dests: computeDests(chess),
        showDests: true,
        events: { after: (orig, dest) => handleUserMove(orig as Key, dest as Key) },
      },
      premovable: { enabled: false },
      draggable: { enabled: true },
      selectable: { enabled: true },
    }
    apiRef.current = initChessground(elRef.current, config)
    onChangeRef.current({ fen: chess.fen(), sanHistory: chess.history() })
    return () => {
      apiRef.current?.destroy()
      apiRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // When the starting position changes (navigated to a different mistake),
  // reset the line to it.
  useEffect(() => {
    chessRef.current = new Chess(startingFen)
    syncFromChess()
  }, [startingFen])

  // Keep orientation in sync if the parent flips it.
  useEffect(() => {
    apiRef.current?.set({ orientation })
  }, [orientation])

  // Engine best-move arrows, as an overlay independent of the position.
  useEffect(() => {
    const api = apiRef.current
    if (!api) return
    const shapes: DrawShape[] = (arrows ?? []).map((a) => ({
      orig: a.orig,
      dest: a.dest,
      brush: a.brush,
    }))
    api.setAutoShapes(shapes)
  }, [arrows])

  function reset() {
    chessRef.current = new Chess(startingFen)
    syncFromChess()
  }

  function undo() {
    const chess = chessRef.current
    if (chess.history().length === 0) return
    chess.undo()
    syncFromChess()
  }

  const canUndo = chessRef.current.history().length > 0

  return (
    <div className="explore-board">
      <div ref={elRef} className="cg-wrap" />
      <div className="explore-controls">
        <button type="button" onClick={undo} disabled={!canUndo}>
          ← Undo
        </button>
        <button type="button" onClick={reset} disabled={!canUndo}>
          Reset to position
        </button>
      </div>
    </div>
  )
  },
)
