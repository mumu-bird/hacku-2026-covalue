import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, money, type Data } from "./api";

const defaults = {
  received_minutes: 90,
  target_minutes: 60,
  quality: 74,
  swing_fit: 40,
  swing_quality: 40,
  swing_quantity: 20,
};
export function ValueModelLab() {
  const { data, error } = useQuery({
    queryKey: ["value-model"],
    queryFn: () => api<Data>("/value-model"),
  });
  const [inputs, setInputs] = useState(defaults);
  const [result, setResult] = useState<Data | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  async function run(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setFailure("");
    try {
      setResult(await api("/value-model/simulate", inputs));
    } catch (e) {
      setFailure(e instanceof Error ? e.message : "無法計算");
    } finally {
      setBusy(false);
    }
  }
  const labels: Record<string, string> = {
    received_minutes: "英語服務分鐘",
    target_minutes: "本次目標分鐘",
    quality: "相關歷史品質",
    swing_fit: "技能覆蓋改善的重要程度",
    swing_quality: "品質改善的重要程度",
    swing_quantity: "目標時長改善的重要程度",
  };
  return (
    <div className="page-width content-page value-model-page">
      <div className="page-title">
        <div className="eyebrow muted">TIME → OUTCOME → VALUE</div>
        <h1>把難量化的幫助，拆成可說明的價值</h1>
        <p>
          同樣90分鐘，對只需要30分鐘練習的人，和需要120分鐘練習的人，幫助可以不同。
        </p>
      </div>
      <section className="panel">
        <h2>三層模型</h2>
        <ol>
          <li>
            <b>投入參考：</b>小時基準 × 能力係數 × 認可投入／60 ＋
            現金費用；能力與效率分開計。
          </li>
          <li>
            <b>本單幫助：</b>
            技能覆蓋、相關驗收品質、目標練習量的加權指標；超過目標後，時長項停止增加。
          </li>
          <li>
            <b>可接受方案：</b>
            先檢查技能、時段、分輪與雙方條件，再用線性偏好近似選擇共同候選。目標方案可減少多餘時長並重新建議補差。
          </li>
        </ol>
        <p>
          幫助分數用於本單比較。它不是成功機率，不換成金錢，也不跨人衡量幸福或公平。
        </p>
      </section>
      <section className="panel">
        <h2>改變需求，平台重新分析</h2>
        <p>
          使用隔離的演示證據與正式估值函式；不改任何真實提案。偏好評分衡量各項從0到100的改善，實際使用需本人確認尺度與權重。
        </p>
        <form onSubmit={run}>
          <div className="form-grid">
            {Object.entries(labels).map(([k, label]) => (
              <label key={k}>
                {label}
                <input
                  type="number"
                  required
                  min={k.includes("minutes") ? 15 : 0}
                  max={k.includes("minutes") ? 240 : 100}
                  value={inputs[k as keyof typeof defaults]}
                  onChange={(e) =>
                    setInputs({ ...inputs, [k]: +e.target.value })
                  }
                />
              </label>
            ))}
          </div>
          <button className="button primary" disabled={busy}>
            分析時間與受益
          </button>
        </form>
        {failure && <p role="alert">{failure}</p>}
        {result && (
          <div className="value-model-result" role="status">
            <h3>
              投入參考 {money(result.reference.reference_amount)} · 幫助指標{" "}
              {result.benefit.score ?? "待驗證"}
            </h3>
            <p>
              目標時長覆蓋 {result.benefit.components.quantity}%；超出目標{" "}
              {result.benefit.extra_minutes_after_target} 分鐘。
            </p>
            <p>品質不滿足門檻或沒有證據時，平台暫停綜合建議。</p>
          </div>
        )}
      </section>
      <section className="panel">
        <h2>相同品質，增加分鐘何時停止增加幫助？</h2>
        {error && <p role="alert">無法載入模型實驗</p>}
        <div className="table-scroll">
          <table className="mechanism-table">
            <thead>
              <tr>
                <th>服務分鐘</th>
                <th>目標分鐘</th>
                <th>投入參考</th>
                <th>時長覆蓋</th>
                <th>幫助指標</th>
              </tr>
            </thead>
            <tbody>
              {data?.experiments.map((x: Data) => (
                <tr key={x.inputs.received_minutes}>
                  <td>{x.inputs.received_minutes}</td>
                  <td>{x.inputs.target_minutes}</td>
                  <td>{money(x.reference.reference_amount)}</td>
                  <td>{x.benefit.components.quantity}%</td>
                  <td>{x.benefit.score}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>{data?.method}</p>
        <p>
          60、90、120分鐘在假設目標60分鐘時，時長受益相同，投入參考仍增加。這能提醒平台：提供更多時間，未必增加本次需要的幫助。
        </p>
      </section>
      <section className="panel">
        <h2>理論來源與採用假設</h2>
        {data?.sources.map((x: Data) => (
          <p key={x.url}>
            <a href={x.url} target="_blank" rel="noreferrer">
              {x.title}
            </a>
            <br />
            {x.application}
          </p>
        ))}
        <p>
          Q、技能覆蓋、目標量是演示代理指標。學習增益、流利度和實際節省時間需要服務前後測量；目前沒有這些實測資料。加法指標假設各項偏好可以獨立權衡；預設40／40／20並非文獻給出的係數。Nash近似也不證明線下公平。
        </p>
        <Link className="text-button" to="/mechanism">
          查看交易保护与规则实验
        </Link>
      </section>
    </div>
  );
}
