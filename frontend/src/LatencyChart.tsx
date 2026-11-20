import { useMemo } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Point } from './api'
import { Empty, ms, timeLabel } from './ui'

interface Datum {
  timestamp: number
  response: number | null
  noResponse: number | null
  point: Point | null
}

interface DotProps {
  cx?: number
  cy?: number
  payload?: Datum
}

function ResponseDot({ cx, cy, payload, showSuccess }: DotProps & { showSuccess: boolean }) {
  if (cx == null || cy == null || !payload?.point || payload.response == null) return null
  if (payload.point.success && !showSuccess) return null
  return <circle cx={cx} cy={cy} r={payload.point.success ? 3.2 : 4}
    fill={payload.point.success ? '#3159e8' : '#cf3d54'} stroke="white" strokeWidth={1.2} />
}

function NoResponseDot({ cx, cy, payload }: DotProps) {
  if (cx == null || cy == null || payload?.noResponse !== 0) return null
  return <rect x={cx - 3} y={cy - 3} width={6} height={6} rx={1}
    transform={`rotate(45 ${cx} ${cy})`} fill="#cf3d54" />
}

export default function LatencyChart({ points }: { points: Point[] }) {
  const data = useMemo(() => {
    const result: Datum[] = []
    let previous: number | undefined
    for (const point of points) {
      const timestamp = Date.parse(point.started_at)
      if (point.gap_before && previous !== undefined) {
        result.push({ timestamp: (timestamp + previous) / 2, response: null, noResponse: null, point: null })
      }
      result.push({
        timestamp, point, response: point.response_ms,
        noResponse: !point.success && point.response_ms === null ? 0 : null,
      })
      previous = timestamp
    }
    return result
  }, [points])
  if (points.length === 0) return <Empty>No checks in this period.</Empty>

  const start = data[0].timestamp
  const end = data[data.length - 1].timestamp
  const padding = Math.max((end - start) * 0.03, 1000)
  const formatTick = new Intl.DateTimeFormat(undefined, end - start > 36 * 3600000
    ? { month: 'short', day: 'numeric' }
    : { hour: 'numeric', minute: '2-digit', ...(end - start < 300000 ? { second: '2-digit' } : {}) })

  return (
    <>
      <div className="chart-legend" aria-hidden="true">
        <span><i className="legend-line" />Response time</span>
        <span><i className="legend-failed" />Failed check</span>
        <span><i className="legend-missing" />No response</span>
      </div>
      <div className="chart-wrap">
        <ResponsiveContainer width="100%" height={252} minWidth={0}>
          <LineChart data={data} margin={{ top: 10, right: 18, bottom: 0, left: 2 }} accessibilityLayer>
            <CartesianGrid vertical={false} stroke="#e8edf5" strokeDasharray="4 4" />
            <XAxis dataKey="timestamp" type="number" scale="time" domain={[start - padding, end + padding]}
              tickFormatter={value => formatTick.format(+value)} minTickGap={28}
              tick={{ fill: '#5b6883', fontSize: 12 }} tickMargin={9} axisLine={false} tickLine={false} />
            <YAxis width={61} domain={[0, upper => Math.max(upper, 4)]} allowDecimals={false}
              tickFormatter={value => `${value} ms`} tick={{ fill: '#5b6883', fontSize: 12 }}
              tickMargin={8} tickLine={false} axisLine={false} />
            <Tooltip cursor={{ stroke: '#a4b4e9', strokeDasharray: '3 4' }} content={({ active, payload }) => {
              const point: Point | null | undefined = payload?.[0]?.payload?.point
              return active && point ? <div className="chart-tooltip">
                <span>{timeLabel(point.started_at)}</span>
                <strong>{point.response_ms === null ? 'Failed · No response' :
                  `${point.success ? 'Passed' : 'Failed'} · ${ms(point.response_ms)}`}</strong>
              </div> : null
            }} />
            <Line dataKey="response" name="Response time" type="linear" stroke="#3159e8" strokeWidth={2.5}
              isAnimationActive={false} connectNulls={false}
              dot={<ResponseDot showSuccess={points.length < 160} />} activeDot={{ r: 5 }} />
            <Line dataKey="noResponse" name="No response" stroke="none" isAnimationActive={false}
              dot={<NoResponseDot />} activeDot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  )
}
