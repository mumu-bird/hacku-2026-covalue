import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, type Data } from "./api";

const defaults = {
  quality: 90,
  main_minutes: 60,
  preparation: 0,
  window_minutes: 240,
  lower: 60,
  upper: 120,
  evidence_mode: "VERIFIED",
};
export function MechanismLab() {
  const { data: report, error } = useQuery({
    queryKey: ["mechanism"],
    queryFn: () => api<Data>("/mechanism"),
  });
  const [inputs, setInputs] = useState(defaults);
  const [result, setResult] = useState<Data | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  async function run(values = inputs) {
    setBusy(true);
    setFailure("");
    try {
      setResult(await api<Data>("/mechanism/simulate", values));
      setInputs(values);
    } catch (e) {
      setFailure(e instanceof Error ? e.message : "實驗失敗");
    } finally {
      setBusy(false);
    }
  }
  const names: Record<string, string> = {
    quality: "輔導能力品質",
    main_minutes: "主服務執行分鐘",
    preparation: "納入協議的準備分鐘",
    window_minutes: "雙方可用總時段（分鐘）",
    lower: "提供者最低接受的反向分鐘",
    upper: "對方最多提供的反向分鐘",
  };
  return (
    <div className="page-width content-page mechanism-page">
      <div className="page-title">
        <div className="eyebrow muted">MECHANISM, COST & LIMITS</div>
        <h1>一小時的價值，如何改變？</h1>
        <p>
          每次實驗運行正式評估與協商規則，使用隔離的模擬資料；不建立交易、不修改你的案例。
        </p>
      </div>
      <section className="panel">
        <h2>改變條件，看規則如何回應</h2>
        <p>
          固定英語參考
          HK$100／小時；主服務為表格輔導。參數是演示假設，並非真實市場估值。
        </p>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            run();
          }}
        >
          <div className="form-grid">
            {Object.entries(names).map(([key, name]) => (
              <label key={key}>
                {name}
                <input
                  type="number"
                  min={
                    key === "quality" ||
                    key === "preparation" ||
                    key === "lower" ||
                    key === "upper"
                      ? 0
                      : key === "window_minutes"
                        ? 30
                        : 15
                  }
                  max={
                    key === "quality"
                      ? 100
                      : key === "preparation"
                        ? 60
                        : key === "main_minutes"
                          ? 240
                          : 1440
                  }
                  required
                  value={inputs[key as keyof typeof inputs]}
                  onChange={(e) =>
                    setInputs({ ...inputs, [key]: +e.target.value })
                  }
                />
              </label>
            ))}
            <label>
              主服務能力證據
              <select
                value={inputs.evidence_mode}
                onChange={(e) =>
                  setInputs({ ...inputs, evidence_mode: e.target.value })
                }
              >
                <option value="VERIFIED">已有復核能力證據</option>
                <option value="MISSING">無證據的一般任務</option>
              </select>
            </label>
          </div>
          <button className="button primary" disabled={busy}>
            運行本次實驗
          </button>
        </form>
        <div className="failure-presets">
          <span>直接運行失效案例：</span>
          <button
            className="button outline small"
            disabled={busy}
            onClick={() => run({ ...defaults, evidence_mode: "MISSING" })}
          >
            證據不足
          </button>
          <button
            className="button outline small"
            disabled={busy}
            onClick={() => run({ ...defaults, lower: 90, upper: 60 })}
          >
            雙方價值無交集
          </button>
          <button
            className="button outline small"
            disabled={busy}
            onClick={() => run({ ...defaults, preparation: 31 })}
          >
            不可合法分輪
          </button>
        </div>
        {failure && <p role="alert">{failure}</p>}
        {error && <p role="alert">{error.message}</p>}
        {result && (
          <div className="mechanism-result" aria-live="polite">
            <h3>
              {result.status === "ACCEPTABLE_CANDIDATE"
                ? "有可協商候選，仍需雙方確認"
                : result.status === "NO_DEAL"
                  ? "本輪不能成單"
                  : "暫停平台確定建議，需要補充依據"}
            </h3>
            <p>
              同分鐘交換的參考差額：HK$
              {(result.equal_time_gap / 100).toFixed(0)}。
              {result.recommendation &&
                `平台建議 ${inputs.main_minutes} 分鐘執行${inputs.preparation ? `＋${inputs.preparation} 分鐘準備` : ""} ↔ ${result.recommendation.reverse_minutes} 分鐘英語，${result.recommendation.rounds} 輪；調整後參考差額 HK$${(result.reference_gap / 100).toFixed(0)}。`}
            </p>
            {result.negotiation && (
              <p>
                共同接受範圍中的候選：{result.negotiation.candidates.join("、")}{" "}
                分鐘。參考價接近不等於雙方願意成交。
              </p>
            )}
            {result.failure && (
              <>
                <p>
                  <b>{result.failure.code}</b>：{result.failure.message}
                </p>
                <p>
                  {result.failure.code === "INSUFFICIENT_EVIDENCE"
                    ? "仍可查看模板範圍，但平台不生成確定交換比例。先復核作品或測評；不把未知能力視為能力低。"
                    : result.failure.code === "NO_FEASIBLE_PLAN"
                      ? "可重新協商時長、擴大可用時段或取消。本次沒有訂單、信用扣減和資金流水。"
                      : "先核對技能和能力要求；不能用高估價格繞過能力門檻。"}
                </p>
              </>
            )}
          </div>
        )}
      </section>
      <section className="panel">
        <h2>公平規則保護誰，讓誰多做了什麼？</h2>
        <p>
          已確認的付出保留；退出後，原回報義務完成或雙方明確豁免才關閉。先行投入越小，需驗收的輪次越多。
        </p>
        <div className="table-scroll">
          <table className="mechanism-table">
            <thead>
              <tr>
                <th>先行投入限制</th>
                <th>120↔180的輪數</th>
                <th>首輪尚未獲回報的付出</th>
                <th>雙方服務驗收次數</th>
                <th>簽署／提交／驗收命令</th>
              </tr>
            </thead>
            <tbody>
              {report?.tradeoffs.map((x: Data) => (
                <tr key={x.first_investment_limit}>
                  <td>{x.first_investment_limit}分鐘</td>
                  <td>{x.rounds}</td>
                  <td>{x.first_unreturned_minutes}分鐘</td>
                  <td>{x.service_acceptances}</td>
                  <td>{x.workflow_commands}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted-text">
          命令數按「2次簽署＋每輪2項服務各提交、驗收一次」計算，不包含協商、排期或爭議，不代表實測耗時。
        </p>
        <div className="perspective-grid">
          <article>
            <h3>受到保護</h3>
            <p>
              先履約的人承擔較小的未回報投入。低證據時停止確定建議，減少錯誤承諾；未確認成果不計為能力歷史。
            </p>
          </article>
          <article>
            <h3>承擔成本</h3>
            <p>
              雙方增加提交與驗收操作；新用戶需補充證據；不可拆分工作或準備投入過大的服務可能不能使用本規則。平台不能保證追回線下損失。
            </p>
          </article>
        </div>
      </section>
      <section className="panel">
        <h2>{report?.experiments.length || 18}組控制實驗</h2>
        <p>
          這些是機制敏感性證據，不是真實用戶成交率。79→80的品質邊界會令能力係數由1變為1.25；公開這個跳幅，後續需要用真實資料校準。
        </p>
        <div className="table-scroll">
          <table className="mechanism-table">
            <thead>
              <tr>
                <th>改變的條件</th>
                <th>主服務時薪</th>
                <th>建議英語分鐘</th>
                <th>協商結果／失效原因</th>
              </tr>
            </thead>
            <tbody>
              {report?.experiments.map((x: Data) => (
                <tr key={x.label}>
                  <td>{x.label}</td>
                  <td>
                    HK${x.main.hourly_rate / 100}
                    {x.main.quality === null ? "（模板）" : ""}
                  </td>
                  <td>{x.recommendation?.reverse_minutes ?? "暫停"}</td>
                  <td>
                    {x.failure?.code ||
                      x.negotiation?.candidates.join("／") + "分鐘"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel">
        <h2>試用與替代方案</h2>
        <p>
          我們保留具體服務回報，支持雙方對同一服務給出不同價值判斷。流程與價格基準仍需真實試用者驗證。
        </p>
        <p>
          <Link className="text-button" to="/study">
            進入匿名試用與回饋 →
          </Link>
        </p>
        <p>
          時間銀行重視每小時等值及跨成員互助；
          <a
            href="https://timebanking.org/overview/"
            target="_blank"
            rel="noreferrer"
          >
            Timebanking UK 說明
          </a>
          。付費工作平台已有時薪與里程碑機制；
          <a
            href="https://support.upwork.com/hc/en-us/articles/17931377993107--Decide-between-hourly-and-fixed-price-contract"
            target="_blank"
            rel="noreferrer"
          >
            Upwork 官方說明
          </a>
          。我們的差異在具體服務比例、雙方自願接受及退出後原服務義務，尚未證明優於這些替代方案。
        </p>
      </section>
    </div>
  );
}
