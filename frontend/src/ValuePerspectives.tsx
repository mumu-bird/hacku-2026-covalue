import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, money, type Data } from "./api";
import { ValueBenefit } from "./ValueBenefit";

export function ValuePerspectives({
  proposal,
  userId,
  names,
  act,
}: {
  proposal: Data;
  userId: string;
  names: Data[];
  act: (fn: () => Promise<Data>, message?: string) => Promise<unknown>;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: [
      "perspectives",
      proposal.id,
      proposal.version,
      proposal.scope_version,
      userId,
    ],
    queryFn: () => api<Data>(`/proposals/${proposal.id}/perspectives`),
  });
  const [value, setValue] = useState("");
  const [reason, setReason] = useState("");
  const [shared, setShared] = useState(false);
  const [saving, setSaving] = useState(false);
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await act(
        () =>
          api(
            `/proposals/${proposal.id}/perspectives`,
            {
              expected_version: proposal.version,
              scope_version: proposal.scope_version,
              received_value: Math.round(Number(value) * 100),
              reason,
              shared,
            },
            "PUT",
          ),
        "本單價值判斷已保存；成交條件未改變",
      );
    } finally {
      setSaving(false);
    }
  }
  const own = data?.views.find((x: Data) => x.user_id === userId);
  const estimate = data?.estimates.find((x: Data) => x.user_id === userId);
  function adopt() {
    const v = estimate?.valuation;
    if (v?.suggested_amount == null) return;
    setValue(String(v.suggested_amount / 100));
    setReason(
      `我採用平台本單估值 ${money(v.suggested_amount)}；依據${v.duration_source}、相關能力與已納入投入。`,
    );
  }
  return (
    <section className="panel perspective-panel">
      <div className="eyebrow muted">AN ESTIMATE YOU CAN EXPLAIN</div>
      <h2>平台先估算這份時間的價值</h2>
      <p>
        根據相關能力證據、任務工作量與預計投入，自動生成本單建議。你可以一鍵採用，或按實際需要調整。
      </p>
      {isLoading && <p role="status">正在計算本單估值…</p>}
      {error && <p role="alert">估值暫時無法載入，請重新整理後再試。</p>}
      <div className="perspective-grid">
        {[proposal.provider_id, proposal.requester_id].map((id: string) => {
          const view = data?.views.find((x: Data) => x.user_id === id);
          const estimate = data?.estimates.find((x: Data) => x.user_id === id);
          const v = estimate?.valuation;
          return (
            <article key={id}>
              <h3>
                {names.find((x) => x.id === id)?.name}
                {id === userId ? "（我）" : ""}
              </h3>
              {estimate && (
                <div className="algorithm-estimate" data-recipient={id}>
                  <p>
                    收到：{estimate.received_title} ·{" "}
                    {estimate.platform_minutes} 分鐘
                  </p>
                  <span>
                    {v.suggested_amount != null ? "算法建議" : "模板參考"}
                  </span>
                  <strong>
                    {money(v.suggested_amount ?? v.reference_amount)}
                  </strong>
                  {v.amount_range && (
                    <p className="muted-text">
                      建議範圍 {money(v.amount_range[0])}—
                      {money(v.amount_range[1])}
                    </p>
                  )}
                  {v.status !== "ESTIMATED" && (
                    <p className="notice">
                      {v.status === "NOT_ELIGIBLE"
                        ? "能力或必需技能未達本單要求，暫不推薦承接。"
                        : "能力證據不足，暫不生成確定估值；請先復核作品或測評。"}
                    </p>
                  )}
                  <details>
                    <summary>查看估值依據</summary>
                    <p>{v.formula}</p>
                    {v.base_hourly_rate != null && (
                      <p>
                        基準 {money(v.base_hourly_rate)}／小時 × 能力係數{" "}
                        {v.quality_coefficient} = {money(v.hourly_rate)}／小時
                      </p>
                    )}
                    {v.execution_minutes != null && (
                      <p>
                        服務 {v.execution_minutes} ＋ 準備{" "}
                        {v.preparation_minutes} ＋ 差旅 {v.travel_minutes} ={" "}
                        {v.recognized_minutes} 分鐘認可投入
                      </p>
                    )}
                    {v.time_amount != null && (
                      <p>
                        時間 {money(v.time_amount)} ＋ 材料{" "}
                        {money(v.material_amount)} ＋ 交通{" "}
                        {money(v.transport_amount)}
                      </p>
                    )}
                    <p>工時來源：{v.duration_source}</p>
                    {v.evidence_count != null && (
                      <p>
                        能力分 {v.quality ?? "待驗證"}；{v.independent_peers}{" "}
                        位獨立交易對手、{v.reviewed_external_count}{" "}
                        項復核作品／測評。工時樣本 {v.duration_sample_count}{" "}
                        筆。
                      </p>
                    )}
                    {v.execution_range && (
                      <p>
                        執行時間範圍 {v.execution_range[0]}—
                        {v.execution_range[1]} 分鐘
                        {v.duration_mad_minutes != null
                          ? `；歷史耗時中位絕對偏差 ${v.duration_mad_minutes} 分鐘`
                          : ""}
                        。
                      </p>
                    )}
                    <small>
                      {v.range_basis}。演示基準與參數，尚未以真實市場價格校準。
                      {estimate.source === "AGREEMENT_SNAPSHOT"
                        ? "沿用建立協議時的估值快照。"
                        : "依據目前本單範圍與相關證據。"}{" "}
                      {v.algorithm_version}
                    </small>
                  </details>
                </div>
              )}
              {view ? (
                <>
                  <div className="value-comparison">
                    <span>
                      平台參考<b>HK${(view.platform_value / 100).toFixed(0)}</b>
                    </span>
                    <span>
                      本人認為值得
                      <b>HK${(view.received_value / 100).toFixed(0)}</b>
                    </span>
                  </div>
                  <p>{view.reason}</p>
                  <small>
                    {view.shared ? "本人同意向對方分享" : "僅本人可見"} ·
                    差額不自動變成補差款
                  </small>
                </>
              ) : (
                <p className="muted-text">
                  尚未分享本單價值判斷。平台建議已列在上方，未分享不代表接受。
                </p>
              )}
            </article>
          );
        })}
      </div>
      {data && (
        <ValueBenefit
          data={data}
          proposal={proposal}
          userId={userId}
          names={names}
          act={act}
        />
      )}
      <form onSubmit={save} className="perspective-form">
        <div className="estimate-adoption">
          <button
            type="button"
            className="button outline"
            onClick={adopt}
            disabled={estimate?.valuation.suggested_amount == null}
          >
            採用平台估值
          </button>
          <small>
            先帶入金額與計算理由，再由你確認保存；分享設定由你決定。
          </small>
        </div>
        <label>
          收到的整份服務，對我值得多少（HKD）
          <input
            type="number"
            min="0"
            max="100000"
            required
            value={value}
            placeholder={
              own
                ? String(own.received_value / 100)
                : estimate?.valuation.suggested_amount != null
                  ? String(estimate.valuation.suggested_amount / 100)
                  : "請填本單價值，不是你的時薪"
            }
            onChange={(e) => setValue(e.target.value)}
          />
        </label>
        <label>
          為什麼我這樣判斷
          <textarea
            required
            minLength={5}
            maxLength={1000}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="例如：我只需要口語練習，增加時長對我幫助有限。請勿填寫私人接受底線或個人資料。"
          />
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={shared}
            onChange={(e) => setShared(e.target.checked)}
          />
          我同意向本單對方分享以上價值與理由；不勾選只供自己查看
        </label>
        <button className="button outline" disabled={saving}>
          保存我的價值判斷
        </button>
      </form>
      <p className="muted-text">
        這不是成交價，不會改寫提案或已簽協議。服務範圍變更後須重新表達；私人協商上限與底線始終不公開。你可重新保存並取消分享。
      </p>
    </section>
  );
}
