import {
  Check,
  ArrowRight,
  Clock,
  CheckCircle2,
  ShieldCheck,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Data, money } from "./api";

export function Journey({ current }: { current: number }) {
  const steps = [
    "說明需求",
    "比較與協商",
    "雙方確認",
    "分階段履約",
    "完成與記錄",
  ];
  return (
    <ol className="journey" aria-label="交換進度">
      {steps.map((name, i) => (
        <li
          key={name}
          className={i < current ? "done" : i === current ? "current" : ""}
          aria-current={i === current ? "step" : undefined}
        >
          <span>
            {i < current ? <Check size={13} /> : String(i + 1).padStart(2, "0")}
          </span>
          <b>{name}</b>
        </li>
      ))}
    </ol>
  );
}

export function nextAction(
  a: Data,
  user: string,
): { title: string; detail: string; target: string; mine: boolean } {
  const base = { target: "#fulfillment", mine: false };
  if (a.status === "AWAITING_CONFIRMATION")
    return {
      ...base,
      target: "#agreement-confirmation",
      mine: !(a.confirmed_by || []).includes(user),
      title: (a.confirmed_by || []).includes(user)
        ? "等待另一方確認協議"
        : "確認完整協議",
      detail: "雙方確認同一版本後，才會開放服務與模擬資金。",
    };
  if (a.status === "COMPLETED")
    return {
      ...base,
      target: "#completion",
      title: "交換已完成",
      detail: "雙方已驗收的時間與能力記錄，已保存到個人頁。",
    };
  if (a.status === "CANCELLED")
    return {
      ...base,
      title: "本份協議已取消",
      detail: "已確認的貢獻仍保留；可回到市場建立新的需求。",
    };
  if (a.status === "DISPUTED")
    return {
      ...base,
      target: "#disputes",
      title: "等待爭議復核",
      detail: "本單新增履約已暫停。復核員會依交付標準和證據記錄結果。",
    };
  const waiting = (a.closeouts || []).find(
    (c: Data) => c.status === "AWAITING_CONFIRMATION",
  );
  if (waiting)
    return {
      ...base,
      target: "#closeouts",
      mine: !(waiting.confirmed_by || []).includes(user),
      title: (waiting.confirmed_by || []).includes(user)
        ? "等待另一方確認結清"
        : "確認逐項結清安排",
      detail: "核對剩餘服務、豁免項目與每筆預留資金的去向。",
    };
  if (
    ["CLOSING", "UNRESOLVED"].includes(a.status) &&
    !(a.closeouts || []).some((c: Data) => c.status === "EXECUTING")
  )
    return {
      ...base,
      mine: true,
      target: "#order-tools",
      title: "建立結清方案",
      detail: "逐項保留或明確豁免原義務，已驗收的付出不會被抹掉。",
    };
  for (const stage of a.stages || []) {
    const continues = (o: Data) =>
      a.status === "ACTIVE" ||
      (a.closeouts || []).some(
        (c: Data) =>
          c.status === "EXECUTING" &&
          c.data.obligations.some(
            (x: Data) => x.obligation_id === o.id && x.action === "CONTINUE",
          ),
      );
    if (
      stage.status === "ACTIVE" &&
      a.status === "ACTIVE" &&
      stage.payment?.state === "NEW"
    )
      return {
        ...base,
        target: "#stage-" + stage.id,
        mine: stage.payment.payer_id === user,
        title:
          stage.payment.payer_id === user
            ? "預留本階段模擬款項"
            : "等待付款方預留款項",
        detail: `第 ${stage.round_no} 階段 ${money(stage.payment.amount)}；預留後才開放交付。`,
      };
    const submitted = stage.obligations.find(
      (o: Data) => o.status === "SUBMITTED" && continues(o),
    );
    if (submitted)
      return {
        ...base,
        target: "#stage-" + stage.id,
        mine: submitted.recipient_id === user,
        title:
          submitted.recipient_id === user ? "驗收本階段交付" : "等待對方驗收",
        detail: "核對交付說明與實際投入時間，確認後才推進下一項服務。",
      };
    const ready = stage.obligations.find(
      (o: Data) => o.status === "READY" && continues(o),
    );
    if (ready)
      return {
        ...base,
        target: "#stage-" + stage.id,
        mine: ready.provider_id === user,
        title: ready.provider_id === user ? "提交本階段服務" : "等待對方交付",
        detail: ready.data.stage_deliverable,
      };
  }
  return {
    ...base,
    title: "核對剩餘承諾",
    detail: "依原服務順序繼續處理；不會因超時而自動驗收或豁免。",
  };
}

export function NextStep({
  agreement,
  user,
}: {
  agreement: Data;
  user: string;
}) {
  const step = nextAction(agreement, user);
  return (
    <section
      className={`next-step ${step.mine ? "actionable" : ""}`}
      aria-label="目前下一步"
    >
      <span className="next-step-icon">
        {agreement.status === "COMPLETED" ? (
          <CheckCircle2 size={23} />
        ) : step.mine ? (
          <ArrowRight size={23} />
        ) : (
          <Clock size={23} />
        )}
      </span>
      <div>
        <small>{step.mine ? "輪到你了" : "目前狀態"}</small>
        <h3>{step.title}</h3>
        <p>{step.detail}</p>
      </div>
      <a className="button outline small" href={step.target}>
        查看位置 <ArrowRight size={15} />
      </a>
    </section>
  );
}

export function ValuePreview() {
  return (
    <div className="value-preview">
      <div className="preview-top">
        <span className="live-dot" /> 本單時間價值分析 <span>演示案例</span>
      </div>
      <h3>
        同一小時，
        <br />
        不同的能力與需要。
      </h3>
      <div className="preview-service">
        <span>表格輔導</span>
        <b>
          60 <small>分鐘</small>
        </b>
        <span>能力品質 90 · HK$150／小時</span>
      </div>
      <div className="preview-exchange">
        <span />
        <span>⇅ 平台建議</span>
        <span />
      </div>
      <div className="preview-service secondary">
        <span>英語交流</span>
        <b>
          90 <small>分鐘</small>
        </b>
        <span>能力品質 74 · HK$100／小時</span>
      </div>
      <div className="preview-note">
        <ShieldCheck size={16} />
        <span>
          來自相關能力與本單條件，
          <br />
          每次需求重新計算。
        </span>
      </div>
      <Link to="/value-model" className="text-button">
        改變目標，看看建議如何改變 <ArrowRight size={16} />
      </Link>
    </div>
  );
}
