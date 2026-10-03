import { useState } from "react";
import { Link } from "react-router-dom";
import { api, money, type Data } from "./api";

export function ValueBenefit({
  data,
  proposal,
  userId,
  names,
  act,
}: {
  data: Data;
  proposal: Data;
  userId: string;
  names: Data[];
  act: (fn: () => Promise<Data>, message?: string) => Promise<unknown>;
}) {
  const estimate = data.estimates.find((x: Data) => x.user_id === userId);
  const b = estimate?.benefit;
  const initial = data.own_context || {
    target_minutes: b?.target_minutes || 60,
    swings: { fit: 40, quality: 40, quantity: 20 },
  };
  const [target, setTarget] = useState(initial.target_minutes);
  const [swings, setSwings] = useState<Data>(initial.swings);
  const [saving, setSaving] = useState(false);
  if (!b) return null;
  const labels: Record<string, string> = {
    fit: "需求技能覆蓋",
    quality: "相關驗收品質",
    quantity: "目標時長／成果量覆蓋",
  };
  const anchors: Record<string, string> = {
    fit: "從不覆蓋到覆蓋全部目標技能",
    quality: "從品質0分到品質100分",
    quantity: "從未達目標練習量到達到目標；成果型以完整交付作假設",
  };
  const body = (t = target, s = swings) => ({
    expected_version: proposal.version,
    scope_version: proposal.scope_version,
    target_minutes: t,
    swing_fit: s.fit,
    swing_quality: s.quality,
    swing_quantity: s.quantity,
  });
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    try {
      await act(
        () => api(`/proposals/${proposal.id}/value-context`, body(), "PUT"),
        "目標與偏好已確認；價格及私人接受條件未改變",
      );
    } finally {
      setSaving(false);
    }
  }
  async function apply() {
    setSaving(true);
    try {
      await act(
        () =>
          api(
            `/proposals/${proposal.id}/apply-value-plan`,
            body(initial.target_minutes, initial.swings),
          ),
        "目標方案已帶入提案，仍需雙方確認；舊接受條件已清除",
      );
    } finally {
      setSaving(false);
    }
  }
  const plan = data.goal_plan;
  return (
    <div className="benefit-panel">
      <h3>這次能幫我達到什麼？</h3>
      <p>
        平台拆開估計技能覆蓋、相關品質和目標練習量，讓學習與交流的幫助可以比較。金額參考與受益指標分列。
      </p>
      <div className="benefit-score">
        <strong>{b.score == null ? "待驗證" : `${b.score} / 100`}</strong>
        <span>
          本單幫助指標 ·{" "}
          {b.preference_source === "USER_CONFIRMED_SWINGS"
            ? "使用本人確認的目標與偏好"
            : "使用待確認的演示模板假設"}
        </span>
      </div>
      <div className="benefit-components">
        {Object.keys(labels).map((k) => (
          <div key={k}>
            <small>{labels[k]}</small>
            <b>{b.components[k] ?? "待驗證"}</b>
            <small>權重 {Math.round(b.weights[k] * 100)}%</small>
          </div>
        ))}
      </div>
      {b.extra_minutes_after_target > 0 && (
        <p className="notice">
          目前服務比目標多 {b.extra_minutes_after_target}{" "}
          分鐘。模型假設達標後，更多分鐘不再增加時長受益；你可以確認不同目標。
        </p>
      )}
      <details>
        <summary>確認我的目標與偏好（僅本人可見）</summary>
        <p>
          以下只需衡量三種「從最差到最好」的改善哪種對你較有幫助，平台會正規化為權重。預設40／40／20是演示假設，不是研究所得。
        </p>
        <form className="value-context-form" onSubmit={save}>
          {b.target_minutes != null && (
            <label>
              目標練習時長（分鐘）
              <input
                type="number"
                min="15"
                max="1440"
                required
                value={target}
                onChange={(e) => setTarget(+e.target.value)}
              />
            </label>
          )}
          {Object.keys(labels).map((k) => (
            <label key={k}>
              {anchors[k]}：改善的重要程度（0—100）
              <input
                type="number"
                min="0"
                max="100"
                required
                value={swings[k]}
                onChange={(e) => setSwings({ ...swings, [k]: +e.target.value })}
              />
            </label>
          ))}
          <button
            className="button outline"
            disabled={
              saving ||
              Object.values(swings).reduce(
                (a: number, x: any) => a + Number(x),
                0,
              ) <= 0
            }
          >
            確認目標與偏好
          </button>
        </form>
      </details>
      {plan && (
        <div className="notice goal-plan">
          <b>目標方案：主服務不變，反向服務改為 {plan.reverse_minutes} 分鐘</b>
          <p>
            {names.find((x) => x.id === plan.payer_id)?.name} 向{" "}
            {names.find((x) => x.id === plan.payee_id)?.name} 補差{" "}
            {money(plan.amount)}，共 {plan.rounds} 輪。{plan.explanation}
          </p>
          <button
            type="button"
            className="button outline"
            disabled={saving}
            onClick={apply}
          >
            確認目標並帶入方案
          </button>
        </div>
      )}
      <details>
        <summary>受益指標的依據與邊界</summary>
        <p>{b.quantity_basis}</p>
        {b.sensitivity_range && (
          <p>
            偏好逐項±10時：{b.sensitivity_range[0]}—{b.sensitivity_range[1]}分。
            {b.sensitivity_basis}。
          </p>
        )}
        <p>
          成果目標：{b.outcome_plan.goal}；可觀察：
          {b.outcome_plan.observable_checks.join("；")}。
        </p>
        <p>{b.outcome_plan.unmeasured}。這些是待量測成果，不作為已達成效果。</p>
        <p>{b.limitations}</p>
      </details>
      <Link className="text-button" to="/value-model">
        查看理論、數學模型與實驗
      </Link>
    </div>
  );
}
