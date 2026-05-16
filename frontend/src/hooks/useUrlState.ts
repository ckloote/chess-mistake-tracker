import { useCallback, useMemo } from 'react'
import { useSearchParams } from 'react-router-dom'

// Generic helper: read named string params from the URL with defaults,
// and produce a setter that updates the URL (writes the new params,
// drops the ones set to '' or undefined). Components stay declarative —
// state is the URL.

export function useUrlState<K extends string>(
  defaults: Record<K, string>,
): [Record<K, string>, (patch: Partial<Record<K, string | undefined>>) => void] {
  const [params, setParams] = useSearchParams()

  const state = useMemo(() => {
    const out = { ...defaults }
    for (const key of Object.keys(defaults) as K[]) {
      const v = params.get(key)
      if (v !== null) (out as Record<K, string>)[key] = v
    }
    return out
  }, [params, defaults])

  const update = useCallback(
    (patch: Partial<Record<K, string | undefined>>) => {
      const next = new URLSearchParams(params)
      for (const [k, v] of Object.entries(patch)) {
        if (v === undefined || v === '' || v === defaults[k as K]) {
          next.delete(k)
        } else {
          next.set(k, String(v))
        }
      }
      setParams(next, { replace: false })
    },
    [params, setParams, defaults],
  )

  return [state, update]
}
