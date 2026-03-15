export type Candle = {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
};

export type Trade = {
  id: string;
  opened_at: number;
  action: string;
  entry_price: number;
  status: string;
  closed_at?: number;
  exit_price?: number;
  pnl_pct?: number;
  pnl_usdt?: number;
  reasoning?: string;
};

export type Decision = {
  ts: number;
  action: string;
  confidence: number;
  reasoning: string;
};

export type Indicators = {
  price: number;
  rsi: number;
  macd: number;
  macd_signal: number;
  bb_upper: number;
  bb_lower: number;
  ema9: number;
  ema21: number;
  volume_ratio: number;
  ts?: number;
};

export type Snapshot = {
  ts: number;
  total_value: number;
  cash: number;
  btc: number;
  daily_pnl: number;
};
