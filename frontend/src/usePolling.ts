import { useEffect, useState } from 'react'

interface PollState<T> {
  key: string
  data?: T
  error?: string
  updated?: Date
}

export function usePolling<T>(
  key: string, load: (signal: AbortSignal) => Promise<T>, revision = 0,
): PollState<T> {
  const [state, setState] = useState<PollState<T>>({ key })

  useEffect(() => {
    const controller = new AbortController()
    let running = false

    async function poll() {
      if (running) return
      running = true
      try {
        const data = await load(controller.signal)
        if (!controller.signal.aborted) setState({ key, data, updated: new Date() })
      } catch (error) {
        if (!controller.signal.aborted) {
          const message = error instanceof Error ? error.message : 'Could not load data.'
          setState(previous => ({ ...(previous.key === key ? previous : { key }), error: message }))
        }
      } finally {
        running = false
      }
    }

    void poll()
    const timer = window.setInterval(poll, 5000)
    return () => {
      controller.abort()
      window.clearInterval(timer)
    }
  }, [key, load, revision])

  return state.key === key ? state : { key }
}
