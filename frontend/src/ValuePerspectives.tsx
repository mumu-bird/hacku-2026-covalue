import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Data } from "./api";

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
  const { data } = useQuery({
    queryKey: ["perspectives", proposal.id, proposal.scope_version, userId],
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
  return (
    <section className="panel perspective-panel">
      <div className="eyebrow muted">SAME SERVICE, DIFFERENT VALUE</div>
      <h2>這份服務，對你值多少？</h2>
      <p>
        平台衡量能力與投入，你判斷收到的服務是否有用。兩種價值可以不同，雙方同意才成單。
      </p>
      <div className="perspective-grid">
        {[proposal.provider_id, proposal.requester_id].map((id: string) => {
          const view = data?.views.find((x: Data) => x.user_id === id);
          return (
            <article key={id}>
              <h3>
                {names.find((x) => x.id === id)?.name}
                {id === userId ? "（我）" : ""}
              </h3>
              {view ? (
                <>
                  <p>
                    收到：{view.received_title} · {view.platform_minutes} 分鐘
                  </p>
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
                  尚未分享本單價值判斷。未分享不代表接受，也不代表價值低。
                </p>
              )}
            </article>
          );
        })}
      </div>
      <form onSubmit={save} className="perspective-form">
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
