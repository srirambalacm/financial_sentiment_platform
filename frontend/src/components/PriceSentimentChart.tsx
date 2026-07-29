import { useState } from "react";
import {
  ComposedChart,
  Line,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";
import { useApi } from "../useApi";
import { getTimeseries, type TimeseriesPoint } from "../api/client";
import { formatDate, formatScore } from "../format";

const WINDOWS = [30, 90, 180, 365] as const;

const PRICE_COLOR = "#3987e5";
const POSITIVE_COLOR = "#0ca30c";
const NEGATIVE_COLOR = "#e66767";
const GRID_COLOR = "#2c2c2a";
const AXIS_COLOR = "#898781";

interface PriceSentimentChartProps {
  symbol: string;
}

interface TooltipPayloadEntry {
  payload: TimeseriesPoint;
}

function ChartTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
}) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0].payload;
  return (
    <div className="rounded border border-slate-700 bg-slate-900 p-3 text-sm shadow-lg">
      <div className="font-medium text-slate-200">
        {formatDate(point.date)}
      </div>
      <div className="mt-1 text-slate-400">
        Close: <span className="text-slate-200">${point.close.toFixed(2)}</span>
      </div>
      <div className="text-slate-400">
        Sentiment:{" "}
        <span className="text-slate-200">
          {point.sentiment === null ? "n/a" : formatScore(point.sentiment)}
        </span>
      </div>
      <div className="text-slate-400">
        Headlines:{" "}
        <span className="text-slate-200">{point.headline_count}</span>
      </div>
    </div>
  );
}

export default function PriceSentimentChart({
  symbol,
}: PriceSentimentChartProps) {
  const [days, setDays] = useState<number>(180);
  const [state, retry] = useApi(
    () => getTimeseries(symbol, days),
    [symbol, days]
  );

  return (
    <div className="rounded-lg border border-slate-800 bg-slate-900/60 p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-200">
          Price vs. sentiment — {symbol}
        </h2>
        <div className="flex gap-1" role="group" aria-label="Chart window">
          {WINDOWS.map((w) => (
            <button
              key={w}
              onClick={() => setDays(w)}
              aria-pressed={days === w}
              className={`rounded px-2.5 py-1 text-xs transition-colors ${
                days === w
                  ? "bg-teal-900/50 text-teal-200"
                  : "text-slate-400 hover:bg-slate-800 hover:text-slate-200"
              }`}
            >
              {w}d
            </button>
          ))}
        </div>
      </div>

      {state.status === "loading" && (
        <div className="flex h-72 items-center justify-center text-sm text-slate-500">
          Loading chart…
        </div>
      )}

      {state.status === "error" && (
        <div className="flex h-72 flex-col items-center justify-center gap-3 text-sm text-red-300">
          <span>Couldn't load price/sentiment data: {state.message}</span>
          <button
            onClick={retry}
            className="rounded border border-red-800 px-3 py-1 text-red-200 hover:bg-red-900/40"
          >
            Retry
          </button>
        </div>
      )}

      {state.status === "success" && state.data.points.length === 0 && (
        <div className="flex h-72 items-center justify-center text-sm text-slate-500">
          No data available for {symbol} in this window.
        </div>
      )}

      {state.status === "success" && state.data.points.length > 0 && (
        <ResponsiveContainer width="100%" height={320}>
          <ComposedChart data={state.data.points}>
            <CartesianGrid stroke={GRID_COLOR} vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={formatDate}
              stroke={AXIS_COLOR}
              tick={{ fill: AXIS_COLOR, fontSize: 11 }}
              minTickGap={30}
            />
            <YAxis
              yAxisId="price"
              orientation="left"
              stroke={AXIS_COLOR}
              tick={{ fill: AXIS_COLOR, fontSize: 11 }}
              domain={["auto", "auto"]}
              width={64}
            />
            <YAxis
              yAxisId="sentiment"
              orientation="right"
              stroke={AXIS_COLOR}
              tick={{ fill: AXIS_COLOR, fontSize: 11 }}
              domain={[-1, 1]}
              width={48}
            />
            <ReferenceLine y={0} yAxisId="sentiment" stroke={AXIS_COLOR} />
            <Tooltip content={<ChartTooltip />} />
            <Bar
              yAxisId="sentiment"
              dataKey="sentiment"
              barSize={4}
              isAnimationActive={false}
            >
              {state.data.points.map((p, i) => (
                <Cell
                  key={i}
                  fill={
                    p.sentiment === null
                      ? "transparent"
                      : p.sentiment >= 0
                      ? POSITIVE_COLOR
                      : NEGATIVE_COLOR
                  }
                />
              ))}
            </Bar>
            <Line
              yAxisId="price"
              type="monotone"
              dataKey="close"
              stroke={PRICE_COLOR}
              strokeWidth={2}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      )}

      <div className="mt-3 flex gap-4 text-xs text-slate-400">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-4"
            style={{ backgroundColor: PRICE_COLOR }}
          />
          Close price (left axis)
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: POSITIVE_COLOR }}
          />
          Positive sentiment
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm"
            style={{ backgroundColor: NEGATIVE_COLOR }}
          />
          Negative sentiment (right axis)
        </span>
      </div>
    </div>
  );
}
