import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useReducer,
  useRef,
} from 'react'
import { Chess, type PieceSymbol } from 'chess.js'
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
  // Fired on every position change (move / navigation / reset) and once on mount.
  onChange: (state: ExploreState) => void
}

// Imperative surface so the engine panel can play a suggested move on the board.
export interface ExploreHandle {
  playUci: (uci: string) => void
}

interface LineMove {
  san: string
  uci: string // 4 chars, or 5 with a promotion piece
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

function lastMoveOf(uci: string): [Key, Key] {
  return [uci.slice(0, 2) as Key, uci.slice(2, 4) as Key]
}

// "N." / "N…" / "" prefix for the move at ply index i, given the starting
// position's side-to-move and full-move number. Black continuations of a pair
// get no prefix so the list reads like a score sheet.
function moveNumberPrefix(i: number, startWhite: boolean, startFull: number): string {
  if (startWhite) {
    const no = startFull + Math.floor(i / 2)
    return i % 2 === 0 ? `${no}.` : ''
  }
  if (i === 0) return `${startFull}…`
  const j = i - 1 // first white move is j=0
  const no = startFull + 1 + Math.floor(j / 2)
  return j % 2 === 0 ? `${no}.` : ''
}

// Interactive analysis board: drag pieces (or click engine lines) to play out a
// variation from a starting position, then step back and forward through it
// non-destructively. chess.js is the rule authority (legality, SAN, FEN);
// chessground is the view. Pawn promotions auto-queen.
export const ExploreBoard = forwardRef<ExploreHandle, ExploreBoardProps>(
  function ExploreBoard(
    { startingFen, orientation, arrows, onChange }: ExploreBoardProps,
    ref,
  ) {
    const elRef = useRef<HTMLDivElement>(null)
    const apiRef = useRef<Api | null>(null)

    // Source of truth: the full explored line + a cursor (plies applied).
    // chessRef holds the position AT the cursor. Refs (not state) so the
    // chessground event handler captured at mount always sees current values;
    // `bump` forces re-render for the controls + move list.
    const lineRef = useRef<LineMove[]>([])
    const cursorRef = useRef(0)
    const chessRef = useRef<Chess>(new Chess(startingFen))
    const [, bump] = useReducer((x: number) => x + 1, 0)

    // Latest props/handlers without re-mounting the board.
    const onChangeRef = useRef(onChange)
    onChangeRef.current = onChange
    const startingFenRef = useRef(startingFen)
    startingFenRef.current = startingFen

    // Build the position after `n` plies of the current line.
    function chessAt(n: number): Chess {
      const c = new Chess(startingFenRef.current)
      for (const move of lineRef.current.slice(0, n)) {
        const u = move.uci
        c.move({
          from: u.slice(0, 2),
          to: u.slice(2, 4),
          promotion: (u.length > 4 ? u[4] : 'q') as PieceSymbol,
        })
      }
      return c
    }

    // Push the cursor position to the board + notify the parent.
    function sync(lastMove?: [Key, Key]) {
      const chess = chessRef.current
      apiRef.current?.set({
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
      onChangeRef.current({
        fen: chess.fen(),
        sanHistory: lineRef.current.slice(0, cursorRef.current).map((m) => m.san),
      })
    }

    // Jump to ply `n` (0 = starting position). Non-destructive.
    function goTo(n: number) {
      const clamped = Math.max(0, Math.min(n, lineRef.current.length))
      cursorRef.current = clamped
      chessRef.current = chessAt(clamped)
      const prev = clamped > 0 ? lineRef.current[clamped - 1] : undefined
      sync(prev ? lastMoveOf(prev.uci) : undefined)
      bump()
    }
    const goToRef = useRef(goTo)
    goToRef.current = goTo

    function handleUserMove(orig: Key, dest: Key) {
      const chess = chessRef.current
      let mv
      try {
        // promotion is ignored by chess.js when the move isn't a promotion.
        mv = chess.move({ from: orig, to: dest, promotion: 'q' })
      } catch {
        // Shouldn't happen — dests only offers legal moves — but reconcile.
        sync()
        return
      }
      const uci = `${mv.from}${mv.to}${mv.promotion ?? ''}`
      // Playing a move when not at the tip replaces the rest of the line.
      lineRef.current = lineRef.current
        .slice(0, cursorRef.current)
        .concat({ san: mv.san, uci })
      cursorRef.current += 1
      // chess is already advanced and is the cursor position.
      sync([orig, dest])
      bump()
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
      onChangeRef.current({ fen: chess.fen(), sanHistory: [] })
      return () => {
        apiRef.current?.destroy()
        apiRef.current = null
      }
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    // Starting position changed (navigated to a different mistake): clear line.
    useEffect(() => {
      lineRef.current = []
      cursorRef.current = 0
      chessRef.current = new Chess(startingFen)
      sync()
      bump()
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

    // Left/Right arrows step through the line. Ignored while typing so the
    // classification form's notes field isn't disrupted.
    useEffect(() => {
      function onKey(e: KeyboardEvent) {
        const tag = (e.target as HTMLElement | null)?.tagName
        if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
        if (e.key === 'ArrowLeft') {
          e.preventDefault()
          goToRef.current(cursorRef.current - 1)
        } else if (e.key === 'ArrowRight') {
          e.preventDefault()
          goToRef.current(cursorRef.current + 1)
        }
      }
      window.addEventListener('keydown', onKey)
      return () => window.removeEventListener('keydown', onKey)
    }, [])

    const line = lineRef.current
    const cursor = cursorRef.current
    const startWhite = (startingFen.split(' ')[1] ?? 'w') === 'w'
    const startFull = Number.parseInt(startingFen.split(' ')[5] ?? '1', 10) || 1
    const canBack = cursor > 0
    const canForward = cursor < line.length

    return (
      <div className="explore-board">
        <div ref={elRef} className="cg-wrap" />

        <div className="explore-controls">
          <button type="button" onClick={() => goTo(0)} disabled={!canBack} title="To start">
            ⏮
          </button>
          <button type="button" onClick={() => goTo(cursor - 1)} disabled={!canBack} title="Back (←)">
            ◀
          </button>
          <button
            type="button"
            onClick={() => goTo(cursor + 1)}
            disabled={!canForward}
            title="Forward (→)"
          >
            ▶
          </button>
          <button
            type="button"
            onClick={() => goTo(line.length)}
            disabled={!canForward}
            title="To end"
          >
            ⏭
          </button>
          <button
            type="button"
            className="explore-reset"
            onClick={() => {
              lineRef.current = []
              goTo(0)
            }}
            disabled={line.length === 0}
          >
            Reset
          </button>
        </div>

        {line.length > 0 && (
          <div className="explore-moves">
            <button
              type="button"
              className={`move-token move-start ${cursor === 0 ? 'current' : ''}`}
              onClick={() => goTo(0)}
              title="Starting position"
            >
              ⟲
            </button>
            {line.map((m, i) => {
              const prefix = moveNumberPrefix(i, startWhite, startFull)
              return (
                <button
                  type="button"
                  key={i}
                  className={`move-token ${cursor === i + 1 ? 'current' : ''}`}
                  onClick={() => goTo(i + 1)}
                >
                  {prefix && <span className="move-no">{prefix}</span>}
                  {m.san}
                </button>
              )
            })}
          </div>
        )}
      </div>
    )
  },
)
