import { useEffect, useRef } from 'react'
import { Chessground as initChessground } from 'chessground'
import type { Api } from 'chessground/api'
import type { Config } from 'chessground/config'
import type { Key } from 'chessground/types'
import type { DrawShape } from 'chessground/draw'

export interface BoardArrow {
  orig: Key
  dest: Key
  brush: 'red' | 'green' | 'blue' | 'yellow'
}

export interface ChessgroundProps {
  fen: string
  orientation: 'white' | 'black'
  lastMove?: [Key, Key]
  arrows?: BoardArrow[]
}

// React wrapper around Lichess's chessground widget. Mounts once via a ref,
// syncs props on update via api.set(), tears down on unmount. View-only —
// piece dragging / move selection is disabled because the review UI doesn't
// need them (and Phase 10's classification UI uses keys, not the board).
export function Chessground({ fen, orientation, lastMove, arrows }: ChessgroundProps) {
  const ref = useRef<HTMLDivElement>(null)
  const apiRef = useRef<Api | null>(null)

  // Mount + destroy. Empty deps: we never re-mount; we re-configure via set().
  useEffect(() => {
    if (!ref.current) return
    const config: Config = {
      fen,
      orientation,
      viewOnly: true,
      coordinates: true,
      animation: { enabled: true, duration: 150 },
      highlight: { lastMove: true, check: true },
      drawable: { enabled: false, visible: true },
      movable: { free: false, color: undefined },
      premovable: { enabled: false },
      draggable: { enabled: false },
      selectable: { enabled: false },
    }
    if (lastMove) config.lastMove = lastMove
    apiRef.current = initChessground(ref.current, config)
    return () => {
      apiRef.current?.destroy()
      apiRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Sync FEN / orientation / lastMove.
  useEffect(() => {
    const api = apiRef.current
    if (!api) return
    api.set({
      fen,
      orientation,
      lastMove: lastMove ?? undefined,
    })
  }, [fen, orientation, lastMove])

  // Sync arrows separately — they're an overlay, not part of the position.
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

  return <div ref={ref} className="cg-wrap" />
}
