export type Data = Record<string, any>;
export class APIError extends Error {
  constructor(
    public code: string,
    message: string,
    public details: Data = {},
  ) {
    super(message);
  }
}
export async function api<T = Data>(
  path: string,
  body?: unknown,
  method = body === undefined ? "GET" : "POST",
  key?: string,
): Promise<T> {
  const r = await fetch("/api/v1" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(method !== "GET"
        ? { "Idempotency-Key": key || crypto.randomUUID() }
        : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const data = await r.json();
  if (!r.ok)
    throw new APIError(
      data.code || "NETWORK_ERROR",
      data.message || "暫時無法完成操作",
      data.details,
    );
  return data;
}
export const money = (cents: number = 0) =>
  new Intl.NumberFormat("zh-HK", {
    style: "currency",
    currency: "HKD",
    maximumFractionDigits: 2,
  }).format(cents / 100);
export const minutes = (n: number = 0) =>
  n >= 60
    ? `${Math.floor(n / 60)} 小時${n % 60 ? ` ${n % 60} 分鐘` : ""}`
    : `${n} 分鐘`;
export const date = (v: string) =>
  new Date(v).toLocaleString("zh-HK", {
    timeZone: "Asia/Hong_Kong",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
export const labels: Record<string, string> = {
  spreadsheet: "表格處理",
  tutoring: "表格輔導",
  english: "英語交流",
  MONEY: "付費",
  BARTER: "時間互換",
  HYBRID: "互換補差",
  AWAITING_CONFIRMATION: "等待雙方確認",
  ACTIVE: "進行中",
  CLOSING: "結清中",
  DISPUTED: "爭議復核中",
  UNRESOLVED: "仍有未解決承諾",
  COMPLETED: "已完成",
  CANCELLED: "已結清取消",
  LOCKED: "待開放",
  READY: "等待交付",
  SUBMITTED: "等待驗收",
  ACCEPTED: "已驗收",
  WAIVED: "雙方已豁免",
  CONTESTED: "有異議",
  NEW: "尚未預留",
  RESERVED: "已模擬預留",
  RELEASED: "已模擬釋放",
  REFUNDED: "已模擬退回",
  APPROVED: "已復核",
  PENDING: "待復核",
  REJECTED: "未通過",
  HISTORY: "履約紀錄",
  WORK: "作品",
  ASSESSMENT: "能力測評",
};
