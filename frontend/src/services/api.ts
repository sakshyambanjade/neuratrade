import axios from "axios";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const API_KEY = import.meta.env.VITE_API_KEY ?? "dev-key";

const client = axios.create({
  baseURL: API_BASE,
  headers: { "x-api-key": API_KEY },
});

export async function getHealth() {
  const { data } = await axios.get(`${API_BASE}/health`);
  return data;
}

export async function getStatus() {
  const { data } = await client.get("/status");
  return data;
}

export async function getCandles(limit = 200) {
  const { data } = await client.get("/candles", { params: { limit } });
  return data;
}

export async function getTrades(limit = 100) {
  const { data } = await client.get("/trades", { params: { limit } });
  return data;
}
