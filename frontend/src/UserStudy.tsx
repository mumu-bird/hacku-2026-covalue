import { useState } from "react";
import { Link } from "react-router-dom";

export function UserStudy() {
  const [form, setForm] = useState({
    role: "STUDENT",
    recent_event: "",
    current_method: "",
    difficulty: "",
    helpful: "",
    friction: "",
    would_use: "UNSURE",
    consent_public: false,
    personally_tested: false,
  });
  const [saved, setSaved] = useState(false);
  const labels = {
    recent_event: "最近一次需要別人幫忙／用技能交換的具體事情",
    current_method: "當時怎樣選人、談時間或價格",
    difficulty: "原來流程最困難的地方",
    helpful: "試用後，哪一步有幫助，為什麼",
    friction: "哪一步讓你不願意繼續，為什麼",
  };
  function download(e: React.FormEvent) {
    e.preventDefault();
    const response = {
      ...form,
      source: "self-reported local participant feedback",
      recorded_at: new Date().toISOString(),
      demo_identity_is_not_participant_identity: true,
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(response, null, 2)], {
        type: "application/json",
      }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = "hourlink-anonymous-feedback.json";
    a.click();
    URL.revokeObjectURL(url);
    setSaved(true);
  }
  return (
    <div className="page-width narrow-page content-page">
      <div className="page-title">
        <div className="eyebrow muted">REAL PEOPLE, HONEST EVIDENCE</div>
        <h1>用一次，再告訴我們是否值得</h1>
        <p>
          請用真實經歷作答。演示中的角色、交易與歷史不是用戶研究；目前尚未取得可核驗的試用回饋。
        </p>
      </div>
      <section className="panel">
        <h2>約10分鐘的試用流程</h2>
        <ol className="study-steps">
          <li>回想一次真實求助，記錄你如何選人與談條件。</li>
          <li>在市場中選一份需求，比較三名候選及其能力、工時、總價。</li>
          <li>
            載入時間互換案例，檢查60↔90；分別用两个角色表達收到服務的價值，嘗試不同意平台比例。
          </li>
          <li>提交並驗收第一項服務，再申請退出；檢查原回報是否仍保留。</li>
          <li>在機制實驗中運行證據不足和無交集案例，再填以下回饋。</li>
        </ol>
        <p>
          <Link to="/demo" className="text-button">
            進入演示案例 →
          </Link>
          　
          <Link to="/mechanism" className="text-button">
            進入機制實驗 →
          </Link>
        </p>
      </section>
      <form className="panel" onSubmit={download}>
        <h2>匿名回饋，只下載到你的裝置</h2>
        <p>
          不填姓名、聯絡方式或第三人資料。本頁不向伺服器傳送回饋；由你決定是否交給團隊。試用身份切換不代表有兩位真實參與者。
        </p>
        <label>
          你與項目的關係
          <select
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value })}
          >
            <option value="STUDENT">學生／目標使用者</option>
            <option value="TEAM">項目發起人／團隊成員</option>
            <option value="OTHER">其他實際試用者</option>
          </select>
        </label>
        {Object.entries(labels).map(([key, label]) => (
          <label key={key}>
            {label}
            <textarea
              minLength={5}
              maxLength={1000}
              required
              value={form[key as keyof typeof form] as string}
              onChange={(e) => setForm({ ...form, [key]: e.target.value })}
            />
          </label>
        ))}
        <label>
          下次遇到相同需求，是否願意使用
          <select
            value={form.would_use}
            onChange={(e) => setForm({ ...form, would_use: e.target.value })}
          >
            <option value="UNSURE">不確定，需改善</option>
            <option value="YES">願意</option>
            <option value="NO">不願意</option>
          </select>
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            required
            checked={form.personally_tested}
            onChange={(e) =>
              setForm({ ...form, personally_tested: e.target.checked })
            }
          />
          我本人實際操作過以上試用流程
        </label>
        <label className="checkbox-row">
          <input
            type="checkbox"
            checked={form.consent_public}
            onChange={(e) =>
              setForm({ ...form, consent_public: e.target.checked })
            }
          />
          同意將匿名回饋用於公開比賽材料；不勾選則不得公開
        </label>
        <button className="button primary">下載匿名回饋</button>
        {saved && (
          <p role="status">已下載。未傳送到平台，也未計入任何用戶驗證人數。</p>
        )}
      </form>
    </div>
  );
}
