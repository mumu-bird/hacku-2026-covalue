import React, { useState, useEffect, createContext, useContext } from "react";
import { ValuePerspectives } from "./ValuePerspectives";
import { MechanismLab } from "./MechanismLab";
import { UserStudy } from "./UserStudy";
import { createRoot } from "react-dom/client";
import {
  BrowserRouter,
  Routes,
  Route,
  Link,
  useNavigate,
  useParams,
  useLocation,
} from "react-router-dom";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
} from "@tanstack/react-query";
import {
  ArrowUpRight,
  ArrowRight,
  Clock,
  Plus,
  Search,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  SlidersHorizontal,
  ShieldCheck,
  Users,
  FileSpreadsheet,
  MessageCircle,
  GraduationCap,
  Repeat2,
  Wallet,
  Activity,
  X,
  Info,
  ExternalLink,
  Download,
  RotateCcw,
  Leaf,
  Star,
  Calendar,
  AlertCircle,
  PanelTop,
  ChevronLeft,
} from "lucide-react";
import { api, Data, APIError, money, minutes, date, labels } from "./api";
import "./styles.css";
const qc = new QueryClient({
  defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
});
type Context = {
  me: Data;
  users: Data[];
  notify: (message: string, error?: boolean) => void;
  act: <T = Data>(
    fn: () => Promise<T>,
    message?: string,
  ) => Promise<T | undefined>;
  login: (username: string, caseId?: string) => Promise<void>;
  busy: boolean;
};
const AppContext = createContext<Context>(null!);
const useApp = () => useContext(AppContext);
function useData(path: string) {
  return useQuery({ queryKey: [path], queryFn: () => api(path) });
}
function Avatar({
  name,
  initials,
  size = "normal",
}: {
  name?: string;
  initials?: string;
  size?: string;
}) {
  return (
    <span className={`avatar ${size}`} title={name}>
      {initials || name?.slice(0, 1) || "時"}
    </span>
  );
}
function Badge({
  children,
  tone = "neutral",
}: {
  children: React.ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
function Empty({
  title = "暫時沒有資料",
  text = "下一次值得的交換，從一個需求開始。",
}: {
  title?: string;
  text?: string;
}) {
  return (
    <div className="empty">
      <Leaf size={28} />
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  );
}
function Loading() {
  return (
    <div className="loading">
      <span />
      正在讀取…
    </div>
  );
}
function ErrorBox({ error }: { error: unknown }) {
  return (
    <div className="notice danger">
      <AlertCircle size={17} />
      {error instanceof Error ? error.message : "無法讀取資料"}
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-heading">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="關閉">
            <X />
          </button>
        </div>
        {children}
      </section>
    </div>
  );
}
function CategoryIcon({
  category,
  size = 22,
}: {
  category: string;
  size?: number;
}) {
  return category === "spreadsheet" ? (
    <FileSpreadsheet size={size} />
  ) : category === "tutoring" ? (
    <GraduationCap size={size} />
  ) : (
    <MessageCircle size={size} />
  );
}
function App() {
  const navigate = useNavigate();
  const [me, setMe] = useState<Data | null>(null);
  const [users, setUsers] = useState<Data[]>([]);
  const [toast, setToast] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const [busy, setBusy] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const location = useLocation();
  const notify = (message: string, error = false) => {
    setToast({ message, error });
    setTimeout(() => setToast(null), 5000);
  };
  async function login(username: string, caseId?: string) {
    await api("/auth/demo-login", {
      username,
      case: caseId || me?.case || "cash",
    });
    const current = await api("/me");
    qc.clear();
    setMe(current);
    localStorage.setItem(
      "hourlink-demo",
      JSON.stringify({ username, case: current.case }),
    );
    setAccountOpen(false);
    if (caseId) navigate("/");
  }
  useEffect(() => {
    Promise.all([
      api<Data[]>("/demo/users"),
      api("/me").catch(async () => {
        const saved = JSON.parse(localStorage.getItem("hourlink-demo") || "{}");
        await api("/auth/demo-login", {
          username: saved.username || "zao",
          case: saved.case || "cash",
        });
        return api("/me");
      }),
    ])
      .then(([u, m]) => {
        setUsers(u);
        setMe(m);
      })
      .catch((e) => notify(e.message, true));
  }, []);
  useEffect(() => {
    setAccountOpen(false);
    window.scrollTo(0, 0);
  }, [location.pathname]);
  async function act<T>(
    fn: () => Promise<T>,
    message?: string,
  ): Promise<T | undefined> {
    setBusy(true);
    try {
      const result = await fn();
      await qc.invalidateQueries();
      setMe(await api("/me"));
      if (message) notify(message);
      return result;
    } catch (e) {
      notify(e instanceof Error ? e.message : "操作失敗", true);
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  if (!me)
    return (
      <main className="boot">
        <div className="brand">
          hourlink<span>時間有價</span>
        </div>
        <Loading />
        {toast && <ErrorBox error={new Error(toast.message)} />}
      </main>
    );
  return (
    <AppContext.Provider value={{ me, users, notify, act, login, busy }}>
      <header className="site-header">
        <div className="header-inner">
          <Link to="/" className="brand">
            <span className="logo-mark">
              <Clock size={21} />
            </span>
            hourlink<span className="brand-sub">時間有價</span>
          </Link>
          <nav>
            <Link className={location.pathname === "/" ? "active" : ""} to="/">
              探索市場
            </Link>
            <Link
              className={
                location.pathname.startsWith("/orders") ? "active" : ""
              }
              to="/orders"
            >
              我的交換
            </Link>
            <Link
              className={location.pathname === "/me" ? "active" : ""}
              to="/me"
            >
              能力與時間
            </Link>
          </nav>
          <div className="header-actions">
            <Link className="demo-pill" to="/demo">
              <span />
              演示模式
            </Link>
            <button
              className="account-button"
              onClick={() => setAccountOpen(!accountOpen)}
              aria-label="切換演示身份"
            >
              <Avatar initials={me.user.initials} />
              <span>{me.user.name}</span>
              <ChevronDown size={14} />
            </button>
            {accountOpen && (
              <div className="account-menu">
                <small>切換演示身份 · 非實名登入</small>
                {users.map((u) => (
                  <button key={u.id} onClick={() => act(() => login(u.id))}>
                    <Avatar initials={u.initials} />
                    <span>{u.name}</span>
                    {me.user.id === u.id && <Check size={16} />}
                  </button>
                ))}
                <Link to="/demo">
                  案例與復核面板 <ArrowRight size={15} />
                </Link>
              </div>
            )}
          </div>
        </div>
      </header>
      <div className="demo-strip">
        <ShieldCheck size={13} />
        <span>所有歷史、估值與資金均為演示資料 · 不涉及真實支付</span>
        <span className="strip-right">HacKU 2026</span>
      </div>
      <main>
        <Routes>
          <Route path="/" element={<Market />} />
          <Route path="/publish" element={<Publish />} />
          <Route path="/listing/:id" element={<Listing />} />
          <Route path="/proposal/:id" element={<Proposal />} />
          <Route path="/orders" element={<Orders />} />
          <Route path="/orders/:id" element={<Order />} />
          <Route path="/me" element={<Profile />} />
          <Route path="/demo" element={<Demo />} />
          <Route path="/mechanism" element={<MechanismLab />} />
          <Route path="/study" element={<UserStudy />} />
          <Route path="*" element={<Empty title="找不到這個頁面" />} />
        </Routes>
      </main>
      <footer>
        <Link className="brand" to="/">
          hourlink<span>時間有價</span>
        </Link>
        <p>讓能力被看見，讓付出的時間有清楚的約定。</p>
        <span>時間互換 · 明確承諾 · 可解釋的建議</span>
      </footer>
      {toast && (
        <div className={`toast ${toast.error ? "error" : ""}`} role="status">
          {toast.error ? <AlertCircle size={18} /> : <CheckCircle2 size={18} />}{" "}
          {toast.message}
          <button onClick={() => setToast(null)} aria-label="關閉通知">
            <X size={16} />
          </button>
        </div>
      )}
      {busy && <div className="busy-line" />}
    </AppContext.Provider>
  );
}
function TimeIllustration() {
  return (
    <div className="time-illustration" aria-label="不同能力，讓時間連結">
      <div className="orbit orbit-one" />
      <div className="orbit orbit-two" />
      <div className="orbit orbit-three" />
      <div className="orbit-core">
        <Clock size={52} strokeWidth={1.25} />
        <span>時間，連起彼此</span>
      </div>
      <div className="float-card float-one">
        <span className="float-icon">
          <FileSpreadsheet size={20} />
        </span>
        <div>
          <b>表格輔導</b>
          <small>60 分鐘的專注</small>
        </div>
        <span className="float-avatar">知</span>
      </div>
      <div className="float-card float-two">
        <span className="float-icon sand">
          <MessageCircle size={20} />
        </span>
        <div>
          <b>英語交流</b>
          <small>90 分鐘的陪伴</small>
        </div>
        <span className="float-avatar coral">予</span>
      </div>
      <div className="float-note">
        <Repeat2 size={15} />
        <span>不同能力，同樣值得</span>
      </div>
      <span className="orbit-dot dot-one" />
      <span className="orbit-dot dot-two" />
      <span className="orbit-star">✳</span>
    </div>
  );
}
function Market() {
  const [kind, setKind] = useState("REQUEST");
  const [q, setQ] = useState("");
  const [category, setCategory] = useState("");
  const [serviceMode, setServiceMode] = useState("");
  const [place, setPlace] = useState("");
  const [availableStart, setAvailableStart] = useState("");
  const [availableEnd, setAvailableEnd] = useState("");
  const [filters, setFilters] = useState(false);
  const { data, isLoading, error } = useData(
    `/listings?kind=${kind}&category=${category}&q=${encodeURIComponent(q)}&service_mode=${serviceMode}&location=${encodeURIComponent(place)}${availableStart ? `&time_start=${encodeURIComponent(new Date(availableStart).toISOString())}` : ""}${availableEnd ? `&time_end=${encodeURIComponent(new Date(availableEnd).toISOString())}` : ""}`,
  );
  const listings = (data || []) as Data[];
  return (
    <>
      <section className="hero page-width">
        <div className="hero-copy">
          <div className="eyebrow">
            <span />
            從一個小需求，開始一段值得的交換
          </div>
          <h1>
            你的能力，
            <br />
            值得被看見。<span className="hero-spark">✳</span>
          </h1>
          <p>
            找到適合的人，把彼此的時間用在值得的地方。
            <br />
            讓平臺幫你比較能力、估計投入，再一起確認約定。
          </p>
          <div className="hero-buttons">
            <Link className="button primary" to="/publish">
              <Plus size={17} />
              發佈我的需求
              <ArrowUpRight size={18} />
            </Link>
            <button
              className="button text"
              onClick={() => {
                setKind("OFFER");
                document
                  .getElementById("market")
                  ?.scrollIntoView({ behavior: "smooth" });
              }}
            >
              探索社羣能力 <ArrowRight size={17} />
            </button>
          </div>
          <div className="hero-proof">
            <div className="stacked-avatars">
              <Avatar initials="知" />
              <Avatar initials="維" />
              <Avatar initials="予" />
            </div>
            <span>讓每一次付出，都有清楚的回應。</span>
          </div>
        </div>
        <TimeIllustration />
      </section>
      <section className="principles page-width">
        <div>
          <span className="principle-icon">
            <Users size={19} />
          </span>
          <p>
            <b>先找到適合的人</b>
            <small>相關能力與過往，讓選擇有依據</small>
          </p>
        </div>
        <div>
          <span className="principle-icon">
            <Clock size={19} />
          </span>
          <p>
            <b>時間價值，有跡可循</b>
            <small>看單價，也看本次任務的總投入</small>
          </p>
        </div>
        <div>
          <span className="principle-icon">
            <ShieldCheck size={19} />
          </span>
          <p>
            <b>付出的時間，不會消失</b>
            <small>分階段確認，保留每一份承諾</small>
          </p>
        </div>
      </section>
      <section className="market-section page-width" id="market">
        <div className="section-heading">
          <div>
            <div className="eyebrow muted">THE COMMUNITY BOARD</div>
            <h2>看看社羣正在需要什麼</h2>
            <p>一份小小的能力，可能剛好是另一個人的答案。</p>
          </div>
          <Link className="button outline small" to="/publish">
            <Plus size={16} />
            發佈需求或能力
          </Link>
        </div>
        <div className="market-toolbar">
          <div className="tabs">
            <button
              className={kind === "REQUEST" ? "selected" : ""}
              onClick={() => setKind("REQUEST")}
            >
              看需求 <span>REQUESTS</span>
            </button>
            <button
              className={kind === "OFFER" ? "selected" : ""}
              onClick={() => setKind("OFFER")}
            >
              找服務 <span>SKILLS</span>
            </button>
          </div>
          <div className="search-tools">
            <label className="search-field">
              <Search size={17} />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="搜尋需求、能力或關鍵字"
              />
            </label>
            <button
              className={`filter-button ${filters ? "selected" : ""}`}
              onClick={() => setFilters(!filters)}
              aria-label="篩選"
            >
              <SlidersHorizontal size={17} />
              <span>篩選</span>
            </button>
          </div>
        </div>
        {filters && (
          <div className="filter-panel">
            <label>
              服務方式
              <select
                value={serviceMode}
                onChange={(e) => setServiceMode(e.target.value)}
              >
                <option value="">全部方式</option>
                <option value="ONLINE">線上</option>
                <option value="OFFLINE">線下</option>
              </select>
            </label>
            <label>
              地點
              <input
                value={place}
                onChange={(e) => setPlace(e.target.value)}
                placeholder="例如：線上"
              />
            </label>
            <label>
              可用開始
              <input
                type="datetime-local"
                value={availableStart}
                onChange={(e) => setAvailableStart(e.target.value)}
              />
            </label>
            <label>
              可用結束
              <input
                type="datetime-local"
                value={availableEnd}
                onChange={(e) => setAvailableEnd(e.target.value)}
              />
            </label>
          </div>
        )}
        <div className="category-pills">
          {[
            ["", "全部"],
            ["spreadsheet", "表格處理"],
            ["tutoring", "表格輔導"],
            ["english", "英語交流"],
          ].map(([id, name]) => (
            <button
              key={id}
              className={category === id ? "selected" : ""}
              onClick={() => setCategory(id)}
            >
              {id && <CategoryIcon category={id} size={15} />} {name}
            </button>
          ))}
          <span>
            {listings.length} 個{kind === "REQUEST" ? "需求" : "服務"}
          </span>
        </div>
        {isLoading ? (
          <Loading />
        ) : error ? (
          <ErrorBox error={error} />
        ) : listings.length ? (
          <div className="listing-grid">
            {listings.map((l) => (
              <ListingCard key={l.id} listing={l} />
            ))}
          </div>
        ) : (
          <Empty title="還沒有符合的刊登" text="試試其他類別或關鍵字。" />
        )}
        <div className="market-bottom">
          <Leaf size={17} />
          <span>不必擁有完美的技能，從你願意分享的能力開始。</span>
          <Link to="/publish?kind=OFFER">
            分享我的能力 <ArrowUpRight size={15} />
          </Link>
        </div>
      </section>
    </>
  );
}
function ListingCard({ listing: l }: { listing: Data }) {
  const category = l.category;
  return (
    <Link to={`/listing/${l.id}`} className={`listing-card card-${category}`}>
      <div className="card-top">
        <div className="category-symbol">
          <CategoryIcon category={category} />
        </div>
        <Badge>{l.kind === "REQUEST" ? "社羣需求" : "可提供服務"}</Badge>
      </div>
      <div className="card-category">
        {labels[category]}
        <span>·</span>
        {l.data.service_mode === "ONLINE" ? "線上" : "線下"}
      </div>
      <h3>{l.title}</h3>
      <p>{l.data.delivery_standard}</p>
      <div className="card-time">
        <Clock size={15} />
        <span>
          {category === "spreadsheet"
            ? "工時由平臺分析"
            : `${minutes(l.data.duration)} · 可協商`}
        </span>
        {l.status !== "OPEN" && <Badge tone="green">已承接</Badge>}
      </div>
      <div className="card-tags">
        {l.data.accepted_modes.map((m: string) => (
          <span key={m}>{labels[m]}</span>
        ))}
      </div>
      <div className="card-bottom">
        <div>
          <Avatar initials={l.owner_initials} />
          <span>{l.owner_name}</span>
        </div>
        <span className="card-arrow">
          <ArrowUpRight size={18} />
        </span>
      </div>
    </Link>
  );
}
function localDateTime(d: Date) {
  return new Date(d.getTime() - d.getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16);
}
function Publish() {
  const { me, act, busy } = useApp();
  const navigate = useNavigate();
  const { data: templates } = useData("/templates");
  const initialKind =
    new URLSearchParams(useLocation().search).get("kind") || "REQUEST";
  const tomorrow = new Date(Date.now() + 24 * 3600 * 1000);
  const [form, setForm] = useState<Data>({
    kind: initialKind,
    title: "",
    category: "spreadsheet",
    scenario: "",
    difficulty: "basic",
    workload: "medium",
    required_skills: ["資料清理", "公式"],
    preferred_skills: [],
    duration: 60,
    preparation: 0,
    travel: 0,
    include_preparation: false,
    include_travel: false,
    material_amount: 0,
    transport_amount: 0,
    delivery_standard: "整理後的工作表與修改說明",
    service_mode: "ONLINE",
    location: "線上",
    start: localDateTime(new Date(tomorrow.setMinutes(0))),
    end: localDateTime(new Date(tomorrow.getTime() + 8 * 3600000)),
    accepted_modes: ["MONEY", "BARTER", "HYBRID"],
  });
  const update = (key: string, v: any) => setForm((f) => ({ ...f, [key]: v }));
  const template = templates?.templates[form.category];
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const b = {
      ...form,
      start: new Date(form.start).toISOString(),
      end: new Date(form.end).toISOString(),
    };
    const r = await act(
      () => api("/listings", b),
      "已發佈，接下來看看適合的人",
    );
    if (r) navigate(`/listing/${r.id}`);
  }
  return (
    <div className="page-width narrow-page">
      <Link className="back-link" to="/">
        <ChevronLeft size={16} />
        返回市場
      </Link>
      <div className="page-title">
        <div className="eyebrow muted">MAKE A CONNECTION</div>
        <h1>從一個清楚的約定開始</h1>
        <p>你說明需要什麼，平臺幫你分析合適的人與時間投入。</p>
      </div>
      <form onSubmit={submit} className="panel publish-form">
        <div className="segmented">
          <button
            type="button"
            className={form.kind === "REQUEST" ? "selected" : ""}
            onClick={() => update("kind", "REQUEST")}
          >
            我需要幫助
          </button>
          <button
            type="button"
            className={form.kind === "OFFER" ? "selected" : ""}
            onClick={() => update("kind", "OFFER")}
          >
            我能提供能力
          </button>
        </div>
        <div className="form-grid">
          <label className="full">
            用一句話說明
            <input
              required
              minLength={2}
              maxLength={120}
              placeholder="例如：幫我整理讀書會的報名錶格"
              value={form.title}
              onChange={(e) => update("title", e.target.value)}
            />
          </label>
          <label>
            服務類別
            <select
              value={form.category}
              disabled={!templates}
              onChange={(e) =>
                setForm((f) => ({
                  ...f,
                  category: e.target.value,
                  required_skills:
                    templates?.templates[e.target.value].skills.slice(0, 2) ||
                    [],
                  preferred_skills: [],
                  delivery_standard:
                    templates?.templates[e.target.value].deliverable || "",
                }))
              }
            >
              {Object.keys(labels)
                .filter((k) =>
                  ["spreadsheet", "tutoring", "english"].includes(k),
                )
                .map((k) => (
                  <option key={k} value={k}>
                    {labels[k]}
                  </option>
                ))}
            </select>
          </label>
          <label>
            任務難度
            <select
              value={form.difficulty}
              onChange={(e) => update("difficulty", e.target.value)}
            >
              <option value="basic">基礎 · 能力門檻 60</option>
              <option value="medium">中等 · 能力門檻 80</option>
              <option value="advanced">較高 · 能力門檻 90</option>
            </select>
          </label>
          <label className="full">
            需求情境
            <textarea
              required
              value={form.scenario}
              onChange={(e) => update("scenario", e.target.value)}
              placeholder="目前遇到了什麼問題？希望完成後能達到什麼？"
            />
          </label>
          <label className="full">
            交付與驗收標準
            <textarea
              required
              value={form.delivery_standard}
              onChange={(e) => update("delivery_standard", e.target.value)}
            />
          </label>
          <fieldset className="full">
            <legend>必需技能</legend>
            <div className="check-options">
              {template?.skills.map((skill: string) => (
                <label key={skill}>
                  <input
                    type="checkbox"
                    checked={form.required_skills.includes(skill)}
                    onChange={(e) =>
                      update(
                        "required_skills",
                        e.target.checked
                          ? [...form.required_skills, skill]
                          : form.required_skills.filter(
                              (s: string) => s !== skill,
                            ),
                      )
                    }
                  />
                  {skill}
                </label>
              ))}
            </div>
          </fieldset>
          <label>
            工作量
            <select
              value={form.workload}
              onChange={(e) => update("workload", e.target.value)}
            >
              <option value="small">小型</option>
              <option value="medium">中型</option>
              <option value="large">大型</option>
            </select>
          </label>
          <label>
            約定服務時長（分鐘）
            <input
              type="number"
              min="15"
              max="1440"
              step="15"
              value={form.duration}
              onChange={(e) => update("duration", +e.target.value)}
            />
            <small>成果型任務另由平臺估計工時。</small>
          </label>
          <label>
            預計準備時間（分鐘）
            <input
              type="number"
              min="0"
              value={form.preparation}
              onChange={(e) => update("preparation", +e.target.value)}
            />
            <span className="inline-check">
              <input
                type="checkbox"
                checked={form.include_preparation}
                onChange={(e) =>
                  update("include_preparation", e.target.checked)
                }
              />
              納入本單認可投入
            </span>
          </label>
          <label>
            預計差旅時間（分鐘）
            <input
              type="number"
              min="0"
              value={form.travel}
              onChange={(e) => update("travel", +e.target.value)}
            />
            <span className="inline-check">
              <input
                type="checkbox"
                checked={form.include_travel}
                onChange={(e) => update("include_travel", e.target.checked)}
              />
              納入本單認可投入
            </span>
          </label>
          <label>
            可用時段開始（本地時間）
            <input
              type="datetime-local"
              required
              value={form.start}
              onChange={(e) => update("start", e.target.value)}
            />
          </label>
          <label>
            材料費（HK$）
            <input
              type="number"
              min="0"
              step="1"
              value={form.material_amount / 100}
              onChange={(e) =>
                update("material_amount", Math.round(+e.target.value * 100))
              }
            />
            <small>現金費用另列，不作時間投入。</small>
          </label>
          <label>
            交通現金費用（HK$）
            <input
              type="number"
              min="0"
              step="1"
              value={form.transport_amount / 100}
              onChange={(e) =>
                update("transport_amount", Math.round(+e.target.value * 100))
              }
            />
          </label>
          <label>
            可用時段結束（本地時間）
            <input
              type="datetime-local"
              required
              value={form.end}
              onChange={(e) => update("end", e.target.value)}
            />
          </label>
          <label>
            服務方式
            <select
              value={form.service_mode}
              onChange={(e) => {
                update("service_mode", e.target.value);
                update(
                  "location",
                  e.target.value === "ONLINE" ? "線上" : "香港大學",
                );
              }}
            >
              <option value="ONLINE">線上</option>
              <option value="OFFLINE">線下</option>
            </select>
          </label>
          <label>
            地點
            <input
              required
              value={form.location}
              onChange={(e) => update("location", e.target.value)}
            />
          </label>
          <fieldset className="full">
            <legend>接受的交易方式</legend>
            <div className="check-options">
              {["MONEY", "BARTER", "HYBRID"].map((m) => (
                <label key={m}>
                  <input
                    type="checkbox"
                    checked={form.accepted_modes.includes(m)}
                    onChange={(e) =>
                      update(
                        "accepted_modes",
                        e.target.checked
                          ? [...form.accepted_modes, m]
                          : form.accepted_modes.filter((x: string) => x !== m),
                      )
                    }
                  />
                  {labels[m]}
                </label>
              ))}
            </div>
          </fieldset>
        </div>
        <div className="form-footer">
          <span>
            <Avatar initials={me.user.initials} />以 {me.user.name} 發佈
          </span>
          <button
            className="button primary"
            disabled={busy || !templates || !form.accepted_modes.length}
          >
            發佈並分析 <ArrowRight size={17} />
          </button>
        </div>
      </form>
    </div>
  );
}
function Listing() {
  const { id } = useParams();
  const { me, act, busy, users } = useApp();
  const navigate = useNavigate();
  const { data: l, isLoading, error } = useData(`/listings/${id}`);
  const { data: matching } = useData(`/listings/${id}/matches`);
  const { data: own } = useData(`/listings?kind=OFFER&owner_id=${me.user.id}`);
  const [sort, setSort] = useState("fit");
  const [mode, setMode] = useState("MONEY");
  const [reverse, setReverse] = useState("");
  const [detail, setDetail] = useState<Data | null>(null);
  const [analysis, setAnalysis] = useState<Data | null>(null);
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!l) return null;
  const isOwner = l.owner_id === me.user.id;
  const candidates = [...(matching?.candidates || [])].sort(
    (a: Data, b: Data) =>
      sort === "budget"
        ? a.total_amount - b.total_amount
        : sort === "fast"
          ? a.estimated_minutes - b.estimated_minutes
          : (b.recommendation_score ?? -1) - (a.recommendation_score ?? -1),
  );
  async function choose(provider: string) {
    const p = await act(async () => {
      const proposal = await api("/proposals", {
        listing_id: id,
        provider_id: provider,
        mode,
        reverse_listing_id: mode === "MONEY" ? null : reverse || own?.[0]?.id,
      });
      return api(`/proposals/${proposal.id}/recommend`, {
        expected_version: proposal.version,
      });
    });
    if (p) navigate(`/proposal/${p.id}`);
  }
  return (
    <div className="page-width detail-page">
      <Link className="back-link" to="/">
        <ChevronLeft size={16} />
        返回市場
      </Link>
      <div className="detail-layout">
        <div>
          <section className="panel request-detail">
            <div className="card-category">
              <CategoryIcon category={l.category} />
              {labels[l.category]}
              <Badge tone="green">
                {l.kind === "REQUEST" ? "需求" : "服務"}
              </Badge>
            </div>
            <h1>{l.title}</h1>
            <p className="large-muted">{l.data.scenario}</p>
            <div className="request-facts">
              <span>
                <Clock size={16} />
                {l.category === "spreadsheet"
                  ? "成果驗收 · 平臺估計投入"
                  : minutes(l.data.duration)}
              </span>
              <span>
                <Calendar size={16} />
                {date(l.data.start)}—{date(l.data.end)}
              </span>
              <span>
                <PanelTop size={16} />
                {l.data.service_mode === "ONLINE"
                  ? "線上服務"
                  : l.data.location}
              </span>
            </div>
            <h4>完成後，我希望得到</h4>
            <p>{l.data.delivery_standard}</p>
            {(l.data.material_amount > 0 || l.data.transport_amount > 0) && (
              <p className="muted-text">
                另列現金費用：材料 {money(l.data.material_amount)}；交通{" "}
                {money(l.data.transport_amount)}。純互換請改用補差。
              </p>
            )}
            <div className="card-tags">
              {l.data.required_skills.map((s: string) => (
                <span key={s}>{s}</span>
              ))}
            </div>
            {isOwner && (
              <button
                className="button outline small"
                onClick={async () => {
                  const r = await act(() =>
                    api(`/listings/${id}/analyze`, {
                      expected_version: l.version,
                    }),
                  );
                  if (r) setAnalysis(r);
                }}
              >
                分析需求 <Activity size={15} />
              </button>
            )}
            {analysis && (
              <div className="notice">
                <CheckCircle2 size={17} />
                {analysis.missing_fields.length
                  ? "需要補充：" + analysis.missing_fields.join("、")
                  : "需求已完整，平臺依技能、難度、交付與時段配對。"}
              </div>
            )}
            {!isOwner && (
              <button
                className="button primary"
                disabled={busy}
                onClick={() =>
                  choose(l.kind === "OFFER" ? l.owner_id : me.user.id)
                }
              >
                {l.kind === "OFFER" ? "向這位服務者發起提案" : "回應這個需求"}
                <ArrowRight size={16} />
              </button>
            )}
          </section>
          <div className="section-heading compact">
            <div>
              <div className="eyebrow muted">MATCHED FOR THIS TASK</div>
              <h2>誰適合這次需求？</h2>
              <p>能力決定參考單價，效率影響總投入。</p>
            </div>
          </div>
          <div className="sort-tabs">
            {[
              ["fit", "最適合"],
              ["budget", "更省預算"],
              ["fast", "更快完成"],
            ].map(([v, t]) => (
              <button
                key={v}
                className={sort === v ? "selected" : ""}
                onClick={() => setSort(v)}
              >
                {t}
              </button>
            ))}
          </div>
          <div className="candidate-list">
            {candidates.map((c: Data, i: number) => (
              <div className="candidate-card panel" key={c.user_id}>
                <div className="candidate-header">
                  <Avatar name={c.name} initials={c.initials} size="large" />
                  <div>
                    <h3>
                      {c.name}{" "}
                      {matching?.recommended_id === c.user_id && (
                        <Badge tone="green">最適合本需求</Badge>
                      )}
                    </h3>
                    <p>{c.headline}</p>
                  </div>
                  <span className="candidate-rank">0{i + 1}</span>
                </div>
                <div className="candidate-metrics">
                  <div>
                    <small>相關能力</small>
                    <b>
                      {c.quality === null ? "待驗證" : `${c.quality} / 100`}
                    </b>
                  </div>
                  <div>
                    <small>預計總投入</small>
                    <b>{minutes(c.estimated_minutes)}</b>
                    <small>
                      估計範圍 {c.minutes_range[0]}—{c.minutes_range[1]} 分鐘
                    </small>
                  </div>
                  <div>
                    <small>本單參考總價</small>
                    <b className="teal-text">{money(c.total_amount)}</b>
                  </div>
                </div>
                <div className="candidate-meta">
                  <span>
                    {money(c.hourly_rate)}／小時（{money(c.hourly_range[0])}—
                    {money(c.hourly_range[1])}） · {c.independent_peers}{" "}
                    位獨立交易對手
                  </span>
                  <Badge>{c.confidence}證據</Badge>
                </div>
                <div className="candidate-footer">
                  <button className="text-button" onClick={() => setDetail(c)}>
                    查看評估依據 <ChevronRight size={15} />
                  </button>
                  <button
                    className="button primary small"
                    disabled={
                      !isOwner ||
                      busy ||
                      l.status !== "OPEN" ||
                      (mode !== "MONEY" && !(own || []).length)
                    }
                    onClick={() => choose(c.user_id)}
                  >
                    選擇並生成方案 <ArrowRight size={15} />
                  </button>
                </div>
              </div>
            ))}
          </div>
          {!candidates.length && (
            <Empty
              title="暫時沒有符合條件的人"
              text="平臺不會把技能或時段不符的人列為合格候選。"
            />
          )}
          {matching?.excluded?.length > 0 && (
            <details className="excluded">
              <summary>
                未推薦的候選與原因（{matching?.excluded.length}）
              </summary>
              {matching?.excluded.map((r: Data) => (
                <p key={r.user_id}>
                  {users.find((u) => u.id === r.user_id)?.name || r.user_id}：
                  {r.reason}
                </p>
              ))}
            </details>
          )}
        </div>
        <aside>
          <div className="panel sticky-panel">
            <div className="eyebrow muted">YOUR EXCHANGE</div>
            <h3>這次怎麼交換？</h3>
            <p>平臺先給建議，再由雙方確認完整條件。</p>
            <div className="mode-options">
              {l.data.accepted_modes.map((m: string) => (
                <button
                  key={m}
                  className={mode === m ? "selected" : ""}
                  onClick={() => setMode(m)}
                >
                  {m === "MONEY" ? <Wallet size={18} /> : <Repeat2 size={18} />}
                  <span>{labels[m]}</span>
                  {mode === m && <Check size={16} />}
                </button>
              ))}
            </div>
            {mode !== "MONEY" && (
              <label>
                我提供的反向服務
                <select
                  value={reverse || own?.[0]?.id || ""}
                  onChange={(e) => setReverse(e.target.value)}
                >
                  {(own || []).map((o: Data) => (
                    <option key={o.id} value={o.id}>
                      {o.title}
                    </option>
                  ))}
                </select>
                {!own?.length && (
                  <small>
                    先<Link to="/publish?kind=OFFER">發佈一項能力</Link>
                    ，再建立互換。
                  </small>
                )}
              </label>
            )}
            <div className="notice subtle">
              <Info size={17} />
              <span>
                參考價是演示規則的計算結果，不是市場行情或個人的固定身價。
              </span>
            </div>
            <div className="side-rule">
              <ShieldCheck size={18} />
              <span>分輪履約，已確認的付出保留。</span>
            </div>
          </div>
        </aside>
      </div>
      {detail && (
        <Modal title="本單評估依據" onClose={() => setDetail(null)}>
          <div className="metrics-row">
            <div>
              <small>技能適配 M</small>
              <b>{detail.fit}</b>
            </div>
            <div>
              <small>能力品質 Q</small>
              <b>{detail.quality ?? "未評估"}</b>
            </div>
            <div>
              <small>證據充足 E</small>
              <b>{detail.evidence_score}</b>
            </div>
          </div>
          <p className="formula">
            推薦分 = 0.6 × 適配 + 0.3 × 品質 + 0.1 × 證據
          </p>
          <p>{detail.estimate_source}</p>
          <p>
            投入範圍 {detail.minutes_range[0]}—{detail.minutes_range[1]}{" "}
            分鐘；公開演示區間規則，不是精確預測。
          </p>
          <p>
            時薪 = 類目基準 × 能力係數 {detail.coefficient}；本單預計{" "}
            {detail.estimated_minutes} 分鐘。
          </p>
          <p>
            參考時薪區間：{money(detail.hourly_range[0])}—
            {money(detail.hourly_range[1])}
          </p>
          <div className="evidence-list">
            {detail.evidence_summary.map((r: Data) => (
              <div key={r.id}>
                <ShieldCheck size={17} />
                <span>
                  {r.title}
                  <small>
                    {labels[r.kind]} · 品質 {r.quality} · {r.skills.join("、")}
                  </small>
                </span>
              </div>
            ))}
          </div>
          <div className="notice subtle">
            <Info size={16} />
            品質採正確性 50%、完整性 30%、自主完成 20%；演示權重可配置。
          </div>
        </Modal>
      )}
    </div>
  );
}
function Proposal() {
  const { id } = useParams();
  const { data: p, isLoading, error } = useData(`/proposals/${id}`);
  const { me, act, busy, users } = useApp();
  const navigate = useNavigate();
  const [amount, setAmount] = useState("");
  const [reverse, setReverse] = useState("");
  const [payer, setPayer] = useState("");
  const [bound, setBound] = useState("");
  const [chosenRounds, setChosenRounds] = useState("");
  const [calculated, setCalculated] = useState<Data | null>(null);
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!p) return null;
  const d = p.data;
  const r = d.recommendation;
  const provider = users.find((u) => u.id === p.provider_id);
  const requester = users.find((u) => u.id === p.requester_id);
  async function draft() {
    const a = await act(
      () =>
        api("/agreements", {
          proposal_id: p!.id,
          expected_version: p!.version,
          rounds: +(chosenRounds || d.selected_rounds || r?.rounds || 2),
          first_provider_id: p!.provider_id,
          ...(p!.mode === "MONEY"
            ? {
                stage_amounts:
                  +(chosenRounds || d.selected_rounds || r?.rounds || 2) === 1
                    ? [d.amount]
                    : +(chosenRounds || d.selected_rounds || r?.rounds || 2) ===
                        2
                      ? [
                          Math.floor(d.amount * 0.4),
                          d.amount - Math.floor(d.amount * 0.4),
                        ]
                      : undefined,
              }
            : {}),
        }),
      "協議已建立，等待雙方確認",
    );
    if (a) navigate(`/orders/${a.id}`);
  }
  return (
    <div className="page-width narrow-page">
      <Link className="back-link" to={`/listing/${p.listing_id}`}>
        <ChevronLeft size={16} />
        返回需求與配對
      </Link>
      <div className="page-title">
        <div className="eyebrow muted">A CLEAR AGREEMENT</div>
        <h1>把時間，變成清楚的約定</h1>
        <p>平臺已準備預設方案。你們可以直接確認，也可以調整。</p>
      </div>
      <div className="panel proposal-panel">
        <div className="panel-top">
          <Badge tone="green">{labels[p.mode]}</Badge>
          <span>提案版本 {p.scope_version}</span>
        </div>
        <div className="exchange-columns">
          <div>
            <Avatar initials={provider?.initials} />
            <small>{provider?.name} 提供</small>
            <h3>{d.scope.title}</h3>
            <b>{minutes(r?.main.execution_minutes || d.scope.duration)}</b>
            <p>{d.scope.delivery_standard}</p>
            {r && (
              <span className="muted-text">
                {money(r.main.hourly_rate)}／小時 · 能力{" "}
                {r.main.quality ?? "待驗證"}
              </span>
            )}
          </div>
          <div className="exchange-symbol">
            {p.mode === "MONEY" ? <Wallet size={24} /> : <Repeat2 size={26} />}
          </div>
          <div>
            <Avatar initials={requester?.initials} />
            <small>
              {requester?.name} {p.mode === "MONEY" ? "支付" : "提供"}
            </small>
            <h3>{p.mode === "MONEY" ? "分階段模擬支付" : d.reverse?.title}</h3>
            <b>
              {p.mode === "MONEY"
                ? money(d.amount)
                : minutes(d.reverse_minutes)}
            </b>
            <p>
              {p.mode === "MONEY"
                ? "每階段先預留，驗收後才釋放。"
                : d.reverse?.delivery_standard}
            </p>
            {r?.reverse && (
              <span className="muted-text">
                {money(r.reverse.hourly_rate)}／小時 · 能力{" "}
                {r.reverse.quality ?? "待驗證"}
              </span>
            )}
          </div>
        </div>
        {p.mode === "HYBRID" && (
          <div className="hybrid-line">
            <Wallet size={19} />
            <span>
              另由 {users.find((u) => u.id === d.payer_id)?.name} 向{" "}
              {users.find((u) => u.id === d.payee_id)?.name} 補差{" "}
              <b>{money(d.amount)}</b>（模擬）
            </span>
          </div>
        )}
        {r ? (
          <div className="recommendation-box">
            <ShieldCheck size={20} />
            <div>
              <b>平臺建議有依據</b>
              <p>
                主服務參考 {money(r.main.total_amount)}
                {r.reverse
                  ? `，反向服務參考時薪 ${money(r.reverse.hourly_rate)}`
                  : ""}
                。
                {p.mode === "BARTER"
                  ? "枚舉合法時長，選擇雙方參考價最接近的組合。"
                  : "能力影響時薪，預計投入影響本單總額。"}
              </p>
              {(r.main.material_amount > 0 || r.main.transport_amount > 0) && (
                <p>
                  時間投入 {money(r.main.time_amount)}；材料{" "}
                  {money(r.main.material_amount)}；交通{" "}
                  {money(r.main.transport_amount)}。
                </p>
              )}
              {r.reverse &&
                (r.reverse.material_amount > 0 ||
                  r.reverse.transport_amount > 0) && (
                  <p>
                    反向時間投入 {money(r.reverse.time_amount)}；材料{" "}
                    {money(r.reverse.material_amount)}；交通{" "}
                    {money(r.reverse.transport_amount)}。
                  </p>
                )}
              <small>本單建議 · {r.rule_version} · 演示估值</small>
            </div>
          </div>
        ) : (
          <div className="notice">
            <Info size={17} />
            範圍或方向已修改，請重新計算平臺建議。
          </div>
        )}
        <div className="agreement-rules">
          <h4>分階段保護彼此的時間</h4>
          <p>
            <Check size={16} />
            平台建議 {d.selected_rounds || r?.rounds || 2}{" "}
            個可獨立驗收的階段；互換按雙方順序履約。
          </p>
          <p>
            <Check size={16} />
            退出不會抹掉已確認的貢獻和原回報義務。
          </p>
          <p>
            <Check size={16} />
            參考價、實際成交條件與實際耗時分開記錄。
          </p>
        </div>
        <label>
          可獨立驗收的階段數
          <input
            type="number"
            min="1"
            max="20"
            value={chosenRounds || d.selected_rounds || r?.rounds || 2}
            onChange={(e) => setChosenRounds(e.target.value)}
          />
          <small>每輪必須有真實交付；先行投入仍由平台檢查。</small>
        </label>
        {d.warnings?.map((w: string) => (
          <div key={w} className="notice amber">
            <Info size={16} />
            {w}
          </div>
        ))}
        <div className="proposal-actions">
          <button
            className="button outline"
            disabled={busy}
            onClick={() =>
              act(
                () =>
                  api(`/proposals/${id}/recommend`, {
                    expected_version: p.version,
                  }),
                "已重新生成參考方案",
              )
            }
          >
            重新計算建議
          </button>
          <button className="button primary" disabled={busy} onClick={draft}>
            建立雙方協議 <ArrowRight size={17} />
          </button>
        </div>
      </div>
      {p.mode !== "MONEY" && (
        <ValuePerspectives
          key={`${p.id}-${p.scope_version}-${me.user.id}`}
          proposal={p}
          userId={me.user.id}
          names={users}
          act={act}
        />
      )}
      <details className="panel negotiation-panel">
        <summary>
          想調整條件？直接協商或填寫私人接受條件 <ChevronDown size={17} />
        </summary>
        <div className="form-grid">
          {p.mode !== "BARTER" && (
            <label>
              協商金額（HKD）
              <input
                type="number"
                min="0"
                step="1"
                placeholder={String(d.amount / 100)}
                value={amount}
                onChange={(e) => setAmount(e.target.value)}
              />
            </label>
          )}
          {p.mode !== "MONEY" && (
            <label>
              反向服務分鐘數
              <input
                type="number"
                min="15"
                step="15"
                placeholder={String(d.reverse_minutes)}
                value={reverse}
                onChange={(e) => setReverse(e.target.value)}
              />
            </label>
          )}
          {p.mode === "HYBRID" && (
            <label>
              補差付款方
              <select
                value={payer || d.payer_id}
                onChange={(e) => setPayer(e.target.value)}
              >
                {[p.requester_id, p.provider_id].map((u) => (
                  <option key={u} value={u}>
                    {users.find((x) => x.id === u)?.name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
        <button
          className="button outline small"
          onClick={() =>
            act(
              () =>
                api(`/proposals/${id}/revise`, {
                  expected_version: p.version,
                  ...(amount !== ""
                    ? { amount: Math.round(+amount * 100) }
                    : {}),
                  ...(reverse !== "" ? { reverse_minutes: +reverse } : {}),
                  ...(payer ? { cash_payer_id: payer } : {}),
                }),
              "條件已更新，過期接受條件已清除",
            )
          }
        >
          保存協商條件
        </button>
        <hr />
        <h4>我的私人接受條件</h4>
        <p className="muted-text">
          只供本人和計算後端讀取。
          {p.mode === "BARTER"
            ? me.user.id === p.provider_id
              ? "你最低接受多少分鐘反向服務？"
              : "你最多願意提供多少分鐘反向服務？"
            : me.user.id === d.payee_id
              ? "你最低接受多少 HKD？"
              : "你最高願意支付多少 HKD？"}
        </p>
        <div className="inline-form">
          <input
            type="number"
            min="0"
            value={bound}
            onChange={(e) => setBound(e.target.value)}
            placeholder={p.mode === "BARTER" ? "分鐘" : "HKD"}
          />
          <button
            className="button outline small"
            disabled={bound === ""}
            onClick={() =>
              act(
                () =>
                  api(
                    `/proposals/${id}/preference`,
                    {
                      expected_version: p.version,
                      scope_version: p.scope_version,
                      value:
                        p.mode === "BARTER" ? +bound : Math.round(+bound * 100),
                    },
                    "PUT",
                  ),
                "私人接受條件已保存",
              )
            }
          >
            保存
          </button>
          <button
            className="button primary small"
            onClick={async () => {
              const result = await act(() =>
                api(`/proposals/${id}/calculate`, {
                  expected_version: p.version,
                }),
              );
              if (result) setCalculated(result);
            }}
          >
            計算交集
          </button>
        </div>
        {calculated && (
          <div className="notice">
            <CheckCircle2 size={17} />
            <span>
              候選：
              {calculated.candidates
                .map((x: number) =>
                  calculated.unit === "港仙" ? money(x) : minutes(x),
                )
                .join("、")}{" "}
              <button
                className="text-button"
                onClick={() =>
                  act(
                    () =>
                      api(`/proposals/${id}/select`, {
                        expected_version: p.version,
                        value: calculated.candidates[0],
                      }),
                    "已選用協商候選",
                  )
                }
              >
                選用首個候選
              </button>
            </span>
          </div>
        )}
      </details>
    </div>
  );
}
function Orders() {
  const { data: orders, isLoading, error } = useData("/me/orders");
  const { data: proposals } = useData("/me/proposals");
  return (
    <div className="page-width content-page">
      <div className="page-title">
        <div className="eyebrow muted">YOUR CONNECTIONS</div>
        <h1>每一份交換，都有下文</h1>
        <p>查看協商中的方案，以及仍在履行的承諾。</p>
      </div>
      <h2 className="subheading">我的訂單</h2>
      {isLoading ? (
        <Loading />
      ) : error ? (
        <ErrorBox error={error} />
      ) : orders?.length ? (
        <div className="order-list">
          {orders.map((a: Data) => (
            <Link key={a.id} className="panel order-row" to={`/orders/${a.id}`}>
              <div className="category-symbol">
                <CategoryIcon category={a.data.scope.category} />
              </div>
              <div>
                <h3>{a.data.scope.title}</h3>
                <span>
                  {labels[a.mode]} · {a.data.rounds} 個階段
                </span>
              </div>
              <Badge tone={a.status === "COMPLETED" ? "green" : "neutral"}>
                {labels[a.status]}
              </Badge>
              <ArrowUpRight size={19} />
            </Link>
          ))}
        </div>
      ) : (
        <Empty
          title="還沒有訂單"
          text="選擇一個適合的人，先建立一份清楚的協議。"
        />
      )}
      <h2 className="subheading">協商中的提案</h2>
      <div className="order-list">
        {proposals?.map((p: Data) => (
          <Link key={p.id} className="panel order-row" to={`/proposal/${p.id}`}>
            <div className="category-symbol">
              <Repeat2 size={21} />
            </div>
            <div>
              <h3>{p.data.scope.title}</h3>
              <span>
                {labels[p.mode]} ·{" "}
                {p.path === "ASSISTED" ? "輔助協商" : "平臺預設方案／直接協商"}
              </span>
            </div>
            <span>
              {p.mode === "BARTER"
                ? minutes(p.data.reverse_minutes)
                : money(p.data.amount)}
            </span>
            <ArrowUpRight size={19} />
          </Link>
        ))}
      </div>
    </div>
  );
}
function ScoreFields({
  scores,
  setScores,
}: {
  scores: Data;
  setScores: (v: Data) => void;
}) {
  return (
    <div className="scores-grid">
      {[
        ["correctness", "正確性"],
        ["completeness", "完整性"],
        ["independence", "自主完成"],
      ].map(([key, label]) => (
        <label key={key}>
          {label}
          <input
            type="number"
            min="0"
            max="100"
            value={scores[key]}
            onChange={(e) => setScores({ ...scores, [key]: +e.target.value })}
          />
        </label>
      ))}
    </div>
  );
}
function Order() {
  const { id } = useParams();
  const { data: a, isLoading, error } = useData(`/agreements/${id}`);
  const { me, users, act, busy } = useApp();
  const [modal, setModal] = useState<{ kind: string; ob?: Data } | null>(null);
  const [text, setText] = useState("");
  const [execution, setExecution] = useState(30);
  const [prep, setPrep] = useState(0);
  const [travel, setTravel] = useState(0);
  const [scores, setScores] = useState<Data>({
    correctness: 90,
    completeness: 90,
    independence: 90,
  });
  const [actions, setActions] = useState<Data[]>([]);
  const [fundActions, setFundActions] = useState<Data[]>([]);
  if (isLoading) return <Loading />;
  if (error) return <ErrorBox error={error} />;
  if (!a) return null;
  const all = a.stages.flatMap((s: Data) => s.obligations);
  const pending = all.filter(
    (o: Data) => !["ACCEPTED", "WAIVED"].includes(o.status),
  );
  const canFulfill = (o: Data) =>
    a.status === "ACTIVE" ||
    (a.status === "CLOSING" &&
      a.closeouts?.some(
        (c: Data) =>
          c.status === "EXECUTING" &&
          c.data.obligations.some(
            (x: Data) => x.obligation_id === o.id && x.action === "CONTINUE",
          ),
      ));
  const person = (u: string) => users.find((x) => x.id === u)?.name || u;
  function open(kind: string, ob?: Data) {
    setModal({ kind, ob });
    setText(
      kind === "submit"
        ? ""
        : kind === "accept"
          ? "符合約定的交付與驗收標準"
          : "",
    );
    setExecution(ob?.data.minutes || 30);
    setPrep(ob?.data.preparation || 0);
    setTravel(ob?.data.travel || 0);
    if (kind === "closeout") {
      setActions(
        pending.map((o: Data) => ({
          obligation_id: o.id,
          action: a!.stages
            .find((s: Data) => s.id === o.stage_id)
            .obligations.some((x: Data) => x.status === "ACCEPTED")
            ? "CONTINUE"
            : "WAIVE",
        })),
      );
      setFundActions(
        a!.stages
          .filter(
            (s: Data) =>
              s.payment &&
              s.payment.reserved > s.payment.released + s.payment.refunded,
          )
          .map((s: Data) => ({
            payment_id: s.payment.id,
            action: s.obligations.some((o: Data) => o.status === "ACCEPTED")
              ? "HOLD"
              : "REFUND",
          })),
      );
    }
  }
  async function executeModal(e: React.FormEvent) {
    e.preventDefault();
    if (!modal) return;
    const ob = modal.ob;
    let result;
    if (modal.kind === "submit")
      result = await act(
        () =>
          api(`/obligations/${ob!.id}/submit`, {
            expected_version: ob!.version,
            evidence: text,
            execution_minutes: execution,
            preparation_minutes: prep,
            travel_minutes: travel,
          }),
        "已提交交付，等待對方驗收",
      );
    if (modal.kind === "accept")
      result = await act(
        () =>
          api(`/obligations/${ob!.id}/accept`, {
            expected_version: ob!.version,
            scores,
            note: text,
          }),
        "已確認貢獻與本階段服務",
      );
    if (modal.kind === "withdraw")
      result = await act(
        () =>
          api(`/agreements/${id}/withdraw`, {
            expected_version: a!.version,
            reason: text,
          }),
        "已暫停新增履約，請確認結清方案",
      );
    if (modal.kind === "dispute")
      result = await act(
        () =>
          api(`/agreements/${id}/disputes`, {
            expected_version: a!.version,
            reason: text,
            obligation_id: ob?.id || null,
          }),
        "爭議已交由復核，不會自動判違約",
      );
    if (modal.kind === "closeout")
      result = await act(
        () =>
          api(`/agreements/${id}/closeouts`, {
            expected_version: a!.version,
            reason: text,
            obligations: actions,
            payments: fundActions,
          }),
        "結清方案已建立，等待雙方確認",
      );
    if (result) setModal(null);
  }
  return (
    <div className="page-width content-page">
      <Link className="back-link" to="/orders">
        <ChevronLeft size={16} />
        我的交換
      </Link>
      <div className="order-title">
        <div>
          <div className="eyebrow muted">EVERY COMMITMENT MATTERS</div>
          <h1>{a.data.scope.title}</h1>
          <p>
            {person(a.provider_id)} 與 {person(a.requester_id)} ·{" "}
            {labels[a.mode]}
          </p>
        </div>
        <Badge
          tone={
            a.status === "COMPLETED"
              ? "green"
              : a.status === "DISPUTED"
                ? "amber"
                : "neutral"
          }
        >
          {labels[a.status]}
        </Badge>
      </div>
      <div className="detail-layout">
        <div>
          <section className="panel order-overview">
            <div className="metrics-row">
              <div>
                <small>協議服務</small>
                <b>{minutes(a.data.main_estimate.execution_minutes)}</b>
              </div>
              <div>
                <small>{a.mode === "MONEY" ? "模擬總價" : "反向服務"}</small>
                <b>
                  {a.mode === "MONEY"
                    ? money(a.data.amount)
                    : minutes(a.data.reverse_minutes)}
                </b>
              </div>
              <div>
                <small>{a.mode === "HYBRID" ? "模擬補差" : "已驗收"}</small>
                <b>
                  {a.mode === "HYBRID"
                    ? money(a.data.amount)
                    : `${all.filter((o: Data) => o.status === "ACCEPTED").length} / ${all.length}`}
                </b>
              </div>
            </div>
            <div className="notice subtle">
              <ShieldCheck size={17} />
              已確認的貢獻保留；剩餘義務不因退出消失，亦不能跨服務相減。
            </div>
            {a.status === "AWAITING_CONFIRMATION" && (
              <div className="consent-area">
                <p>確認同一版本的完整服務、階段、時間安排及取消規則。</p>
                <div className="consent-people">
                  {[a.requester_id, a.provider_id].map((u) => (
                    <span
                      key={u}
                      className={a.confirmed_by.includes(u) ? "confirmed" : ""}
                    >
                      <CheckCircle2 size={16} />
                      {person(u)}{" "}
                      {a.confirmed_by.includes(u) ? "已確認" : "待確認"}
                    </span>
                  ))}
                </div>
                <button
                  className="button primary"
                  disabled={
                    busy ||
                    a.confirmed_by.includes(me.user.id) ||
                    me.user.reviewer
                  }
                  onClick={() =>
                    act(
                      () =>
                        api(`/agreements/${id}/confirm`, {
                          expected_version: a.version,
                          terms_version: a.terms_version,
                        }),
                      "已確認協議",
                    )
                  }
                >
                  我確認此版本協議 <Check size={16} />
                </button>
              </div>
            )}
          </section>
          <div className="section-heading compact">
            <h2>履約與時間承諾</h2>
            <span className="muted-text">按輪次推進，先完成這一輪</span>
          </div>
          <div className="stage-list">
            {a.stages.map((stage: Data) => (
              <section
                key={stage.id}
                className={`panel stage-card ${stage.status === "LOCKED" ? "stage-locked" : ""}`}
              >
                <div className="stage-heading">
                  <span className="round-number">
                    {String(stage.round_no).padStart(2, "0")}
                  </span>
                  <div>
                    <h3>第 {stage.round_no} 階段</h3>
                    <small>
                      {stage.status === "COMPLETED"
                        ? "本輪服務已完成"
                        : stage.status === "ACTIVE"
                          ? "目前履約階段"
                          : "待前一輪完成"}
                    </small>
                  </div>
                  {stage.status === "COMPLETED" && (
                    <CheckCircle2 size={21} className="teal-text" />
                  )}
                </div>
                {stage.payment && (
                  <div className="payment-line">
                    <Wallet size={16} />
                    <div>
                      <b>{money(stage.payment.amount)}</b>
                      <span> 模擬支付 · {labels[stage.payment.state]}</span>
                      <small>
                        已釋放 {money(stage.payment.released)} · 已退回{" "}
                        {money(stage.payment.refunded)}
                      </small>
                    </div>
                    {stage.status === "ACTIVE" &&
                      a.status === "ACTIVE" &&
                      stage.payment.state === "NEW" &&
                      stage.payment.payer_id === me.user.id && (
                        <button
                          className="button outline small"
                          disabled={busy}
                          onClick={() =>
                            act(
                              () =>
                                api(`/stages/${stage.id}/fund`, {
                                  expected_version: a.version,
                                }),
                              "本階段已模擬預留",
                            )
                          }
                        >
                          模擬預留
                        </button>
                      )}
                  </div>
                )}
                {stage.obligations.map((o: Data) => (
                  <div className="obligation" key={o.id}>
                    <div className="obligation-heading">
                      <span
                        className={`status-dot ${o.status.toLowerCase()}`}
                      />
                      <div>
                        <b>
                          {person(o.provider_id)} → {person(o.recipient_id)}
                        </b>
                        <p>{o.data.stage_deliverable}</p>
                      </div>
                      <Badge
                        tone={o.status === "ACCEPTED" ? "green" : "neutral"}
                      >
                        {labels[o.status]}
                      </Badge>
                    </div>
                    <div className="obligation-body">
                      <p>{o.data.acceptance}</p>
                      {o.data.evidence && (
                        <div className="submitted-evidence">
                          <small>交付證據</small>
                          <p>{o.data.evidence}</p>
                        </div>
                      )}
                      {o.time_entries?.length > 0 && (
                        <span className="time-entry">
                          <Clock size={14} />
                          {o.time_entries.reduce(
                            (n: number, t: Data) => n + t.minutes,
                            0,
                          )}{" "}
                          分鐘投入 ·{" "}
                          {o.status === "ACCEPTED"
                            ? "已確認貢獻"
                            : "提供者申報，待確認"}
                        </span>
                      )}
                      <div className="obligation-actions">
                        {o.status === "READY" &&
                          o.provider_id === me.user.id &&
                          canFulfill(o) && (
                            <button
                              className="button primary small"
                              disabled={busy}
                              onClick={() => open("submit", o)}
                            >
                              提交交付
                            </button>
                          )}
                        {o.status === "SUBMITTED" &&
                          o.recipient_id === me.user.id &&
                          canFulfill(o) && (
                            <>
                              <button
                                className="button primary small"
                                disabled={busy}
                                onClick={() => open("accept", o)}
                              >
                                驗收並確認時間
                              </button>
                              <button
                                className="button outline small"
                                onClick={() => open("dispute", o)}
                              >
                                提出異議
                              </button>
                            </>
                          )}
                      </div>
                    </div>
                  </div>
                ))}
              </section>
            ))}
          </div>
          {a.closeouts?.length > 0 && (
            <section className="panel closeout-list">
              <h3>結清方案</h3>
              {a.closeouts.map((c: Data) => (
                <div key={c.id}>
                  <Badge>{labels[c.status] || c.status}</Badge>
                  <p>{c.data.reason}</p>
                  {c.data.obligations.map((x: Data) => (
                    <p key={x.obligation_id}>
                      {
                        all.find((o: Data) => o.id === x.obligation_id)?.data
                          .stage_deliverable
                      }
                      ：
                      {x.action === "CONTINUE"
                        ? "保留原義務，繼續補做"
                        : "雙方明確豁免"}
                    </p>
                  ))}
                  {c.data.payments.map((x: Data) => (
                    <p key={x.payment_id}>
                      模擬資金：
                      {x.action === "HOLD"
                        ? "保留，服務結清後處理"
                        : x.action === "REFUND"
                          ? "退回原付款方"
                          : "釋放給收款方"}
                    </p>
                  ))}
                  {c.status === "AWAITING_CONFIRMATION" &&
                    !me.user.reviewer && (
                      <button
                        className="button primary small"
                        disabled={
                          busy || (c.confirmed_by || []).includes(me.user.id)
                        }
                        onClick={() =>
                          act(
                            () =>
                              api(`/closeouts/${c.id}/confirm`, {
                                expected_version: c.version,
                                agreement_version: a.version,
                              }),
                            "已確認結清方案",
                          )
                        }
                      >
                        {(c.confirmed_by || []).includes(me.user.id)
                          ? "你已確認"
                          : "確認這份結清方案"}
                      </button>
                    )}
                </div>
              ))}
            </section>
          )}
          {a.disputes?.length > 0 && (
            <section className="panel dispute-list">
              <h3>爭議與復核紀錄</h3>
              {a.disputes.map((r: Data) => (
                <div key={r.id}>
                  <p>{r.data.reason}</p>
                  <Badge>
                    {r.status === "OPEN" ? "待復核" : "已記錄復核結果"}
                  </Badge>
                  {r.data.review && (
                    <p>
                      依據：{r.data.review.basis} · 結果 {r.data.review.outcome}
                    </p>
                  )}
                </div>
              ))}
            </section>
          )}
        </div>
        <aside>
          <section className="panel sticky-panel">
            <h3>清楚知道，接下來做什麼</h3>
            <p>
              目前以 <b>{me.user.name}</b>{" "}
              操作。需要另一方確認時，可從右上角切換演示身份。
            </p>
            <div className="side-stat">
              <span>待履行義務</span>
              <b>{pending.length} 項</b>
            </div>
            <div className="side-stat">
              <span>條款版本</span>
              <b>{a.terms_version}</b>
            </div>
            <div className="side-stat">
              <span>約定時段</span>
              <b>{date(a.data.scope.start)}</b>
            </div>
            <details className="snapshot">
              <summary>查看完整協議快照</summary>
              <p>交付：{a.data.scope.delivery_standard}</p>
              <p>取消：{a.data.cancel_rule}</p>
              <p>驗收回應期限：{date(a.data.response_due)}</p>
              <p>準備／差旅只計入事前約定的投入。</p>
              <p>先行方：{person(a.data.first_provider_id)}</p>
            </details>
            {!me.user.reviewer &&
              ["ACTIVE", "DISPUTED", "UNRESOLVED"].includes(a.status) && (
                <button
                  className="button outline full-width"
                  onClick={() => open("withdraw")}
                >
                  申請退出與結清
                </button>
              )}
            {!me.user.reviewer &&
              ["ACTIVE", "CLOSING", "UNRESOLVED"].includes(a.status) && (
                <button className="text-button" onClick={() => open("dispute")}>
                  申請爭議復核
                </button>
              )}
            {!me.user.reviewer &&
              ["CLOSING", "UNRESOLVED"].includes(a.status) && (
                <button
                  className="button primary full-width"
                  onClick={() => open("closeout")}
                >
                  建立結清方案
                </button>
              )}
            <div className="notice subtle">
              <Info size={17} />
              超時不會自動驗收、判違約或抹掉義務。
            </div>
          </section>
        </aside>
      </div>
      {modal && (
        <Modal
          title={
            {
              submit: "提交服務與時間紀錄",
              accept: "確認交付與貢獻",
              withdraw: "申請退出",
              dispute: "提出異議與證據",
              closeout: "確認原義務怎樣結清",
            }[modal.kind]!
          }
          onClose={() => setModal(null)}
        >
          <form onSubmit={executeModal}>
            {modal.kind === "submit" && (
              <>
                <p>{modal.ob?.data.stage_deliverable}</p>
                <div className="form-grid">
                  <label>
                    執行分鐘數
                    <input
                      type="number"
                      min="1"
                      max="1440"
                      value={execution}
                      onChange={(e) => setExecution(+e.target.value)}
                    />
                  </label>
                  <label>
                    準備分鐘數
                    <input
                      type="number"
                      min="0"
                      value={prep}
                      onChange={(e) => setPrep(+e.target.value)}
                    />
                  </label>
                  <label>
                    差旅分鐘數
                    <input
                      type="number"
                      min="0"
                      value={travel}
                      onChange={(e) => setTravel(+e.target.value)}
                    />
                  </label>
                </div>
              </>
            )}
            {modal.kind === "accept" && (
              <>
                <ScoreFields scores={scores} setScores={setScores} />
                <p className="muted-text">
                  確認收到約定成果與申報時間；評分只適用這項服務。
                </p>
              </>
            )}
            {modal.kind === "closeout" && (
              <>
                <p>已驗收貢獻保留。請逐項決定原義務，豁免需雙方確認。</p>
                {actions.map((x, i) => (
                  <label key={x.obligation_id}>
                    {
                      all.find((o: Data) => o.id === x.obligation_id)?.data
                        .stage_deliverable
                    }
                    <select
                      value={x.action}
                      onChange={(e) =>
                        setActions(
                          actions.map((a, j) =>
                            j === i ? { ...a, action: e.target.value } : a,
                          ),
                        )
                      }
                    >
                      <option value="CONTINUE">保留原義務，補做</option>
                      <option value="WAIVE">雙方明確豁免</option>
                    </select>
                  </label>
                ))}
                {fundActions.map((x, i) => (
                  <label key={x.payment_id}>
                    本筆模擬預留
                    <select
                      value={x.action}
                      onChange={(e) =>
                        setFundActions(
                          fundActions.map((a, j) =>
                            j === i ? { ...a, action: e.target.value } : a,
                          ),
                        )
                      }
                    >
                      <option value="HOLD">保留至服務結清</option>
                      <option value="REFUND">退回原付款者</option>
                      <option value="RELEASE">釋放給原收款者</option>
                    </select>
                  </label>
                ))}
              </>
            )}
            <label>
              {modal.kind === "submit" ? "交付證據與說明" : "說明與依據"}
              <textarea
                required
                minLength={modal.kind === "submit" ? 5 : 3}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="具體說明成果、需要處理的問題或雙方同意的安排。"
              />
            </label>
            <div className="modal-actions">
              <button
                type="button"
                className="button outline"
                onClick={() => setModal(null)}
              >
                返回
              </button>
              <button className="button primary" disabled={busy}>
                提交 <ArrowRight size={16} />
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
function Profile() {
  const { me, act, busy } = useApp();
  const { data: summary } = useData("/me/time-summary");
  const { data: account } = useData("/me/mock-account");
  const { data: evidence } = useData("/me/evidence");
  const [form, setForm] = useState<Data>({
    category: "spreadsheet",
    kind: "WORK",
    title: "",
    body: "",
    skills: ["資料清理", "公式"],
    difficulty: "basic",
  });
  const { data: templates } = useData("/templates");
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const r = await act(
      () => api("/capability-evidence", form),
      "作品已提交，等待復核",
    );
    if (r) setForm({ ...form, title: "", body: "" });
  }
  return (
    <div className="page-width content-page">
      <div className="profile-title">
        <Avatar initials={me.user.initials} size="large" />
        <div>
          <div className="eyebrow muted">YOUR CAPABILITY, YOUR TIME</div>
          <h1>{me.user.name}的能力與時間</h1>
          <p>{me.user.headline}</p>
        </div>
      </div>
      <div className="profile-stats">
        <div className="panel">
          <Clock size={22} />
          <small>已確認貢獻</small>
          <b>{minutes(summary?.provided_minutes)}</b>
          <span>按類別與原訂單追蹤</span>
        </div>
        <div className="panel">
          <Repeat2 size={22} />
          <small>已獲得服務</small>
          <b>{minutes(summary?.received_service_minutes)}</b>
          <span>僅計服務，不把等待計成貢獻</span>
        </div>
        <div className="panel">
          <ShieldCheck size={22} />
          <small>待履行承諾</small>
          <b>{summary?.pending?.length || 0} 項</b>
          <span>退出後仍保留原義務</span>
        </div>
        <div className="panel">
          <Wallet size={22} />
          <small>模擬可用餘額</small>
          <b>{money(account?.available)}</b>
          <span>已預留 {money(account?.reserved)} · 不可提現</span>
        </div>
      </div>
      <div className="notice subtle">
        <Info size={17} />
        {summary?.notice || "時間記錄不是可消費積分；不同服務不能相減。"}
      </div>
      <div className="detail-layout">
        <div>
          <h2 className="subheading">我的能力證據</h2>
          <div className="evidence-list panel">
            {evidence?.map((e: Data) => (
              <div key={e.id}>
                <CategoryIcon category={e.category} size={19} />
                <span>
                  <b>{e.data.title}</b>
                  <small>
                    {labels[e.category]} · {labels[e.kind]} ·{" "}
                    {e.quality !== null ? `品質 ${e.quality}` : "等待評估"} ·{" "}
                    {labels[e.status]}
                  </small>
                  <small>{e.data.basis || e.data.source}</small>
                </span>
              </div>
            ))}
          </div>
          <h2 className="subheading">仍需完成的承諾</h2>
          {summary?.pending?.length ? (
            <div className="order-list">
              {summary.pending.map((o: Data) => (
                <Link
                  className="panel order-row"
                  key={o.id}
                  to={`/orders/${o.agreement_id}`}
                >
                  <Clock size={19} />
                  <div>
                    <h3>{o.data.service.title}</h3>
                    <span>
                      {o.provider_id === me.user.id
                        ? "我需要提供"
                        : "我等待接收"}
                      ：{o.data.stage_deliverable}
                    </span>
                  </div>
                  <Badge>{labels[o.status]}</Badge>
                </Link>
              ))}
            </div>
          ) : (
            <Empty
              title="目前沒有未完成承諾"
              text="每一份付出都有紀錄，每一項義務都有去向。"
            />
          )}
          <h2 className="subheading">模擬資金明細</h2>
          {account?.ledger?.length ? (
            <div className="panel ledger-table">
              {account.ledger.map((l: Data) => (
                <div key={l.id}>
                  <span>
                    {
                      { RESERVE: "預留", RELEASE: "釋放", REFUND: "退回" }[
                        l.action as "RESERVE"
                      ]
                    }
                  </span>
                  <b>{money(l.amount)}</b>
                  <small>{date(l.created)}</small>
                </div>
              ))}
            </div>
          ) : (
            <p className="muted-text">尚未發生模擬資金動作。</p>
          )}
        </div>
        <aside>
          <form className="panel sticky-panel" onSubmit={submit}>
            <h3>讓你的能力有依據</h3>
            <p>提供作品或測評，經結構化復核後可進入本類能力評估。</p>
            <label>
              服務類別
              <select
                value={form.category}
                disabled={!templates}
                onChange={(e) =>
                  setForm({
                    ...form,
                    category: e.target.value,
                    skills: templates?.templates[e.target.value].skills || [],
                  })
                }
              >
                {["spreadsheet", "tutoring", "english"].map((c) => (
                  <option key={c} value={c}>
                    {labels[c]}
                  </option>
                ))}
              </select>
            </label>
            <label>
              證據類型
              <select
                value={form.kind}
                onChange={(e) => setForm({ ...form, kind: e.target.value })}
              >
                <option value="WORK">作品</option>
                <option value="ASSESSMENT">能力測評</option>
              </select>
            </label>
            <label>
              作品或測評名稱
              <input
                required
                minLength={2}
                value={form.title}
                onChange={(e) => setForm({ ...form, title: e.target.value })}
              />
            </label>
            <label>
              證據對應難度
              <select
                value={form.difficulty}
                onChange={(e) =>
                  setForm({ ...form, difficulty: e.target.value })
                }
              >
                <option value="basic">基礎</option>
                <option value="medium">中等</option>
                <option value="advanced">較高</option>
              </select>
            </label>
            <label>
              材料與完成說明
              <textarea
                required
                minLength={5}
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
              />
            </label>
            <div className="check-options">
              {templates?.templates[form.category].skills.map((s: string) => (
                <label key={s}>
                  <input
                    type="checkbox"
                    checked={form.skills.includes(s)}
                    onChange={(e) =>
                      setForm({
                        ...form,
                        skills: e.target.checked
                          ? [...form.skills, s]
                          : form.skills.filter((x: string) => x !== s),
                      })
                    }
                  />
                  {s}
                </label>
              ))}
            </div>
            <button
              className="button primary full-width"
              disabled={busy || !templates}
            >
              提交能力證據 <ArrowUpRight size={16} />
            </button>
          </form>
        </aside>
      </div>
    </div>
  );
}
function Demo() {
  const { me, act, login, busy, notify } = useApp();
  const { data: cases } = useData("/demo/cases");
  const { data: queue, error } = useData("/review/queue");
  const [selected, setSelected] = useState<Data | null>(null);
  const [scores, setScores] = useState<Data>({
    correctness: 90,
    completeness: 90,
    independence: 90,
  });
  const [basis, setBasis] = useState("");
  const [outcome, setOutcome] = useState("RESUME");
  async function review(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    const r = await act(
      () =>
        api(
          selected.type === "evidence"
            ? `/capability-evidence/${selected.id}/review`
            : `/disputes/${selected.id}/review`,
          selected.type === "evidence"
            ? { approve: true, scores, basis }
            : {
                expected_version: selected.version,
                outcome,
                basis,
                ...(outcome === "ACCEPT" ? { scores } : {}),
              },
        ),
      "復核結果已記錄",
    );
    if (r) setSelected(null);
  }
  async function download() {
    const r = await act(() => api("/demo/events"));
    if (r) {
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(r, null, 2)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = `hourlink-${me.case}-events.json`;
      a.click();
      URL.revokeObjectURL(url);
    }
  }
  return (
    <div className="page-width content-page">
      <div className="page-title">
        <div className="eyebrow muted">DEMO & REVIEW STUDIO</div>
        <h1>把規則，展示得清清楚楚</h1>
        <p>每個案例使用獨立資料庫。切換身份不等於實名驗證。</p>
        <p>
          <Link className="text-button" to="/mechanism">
            運行機制實驗、取捨與失效案例 →
          </Link>
          　
          <Link className="text-button" to="/study">
            匿名真實試用回饋 →
          </Link>
        </p>
      </div>
      <div className="demo-cases">
        {cases?.cases.map((c: Data) => (
          <button
            key={c.id}
            className={`panel ${me.case === c.id ? "selected" : ""}`}
            onClick={() => act(() => login(me.user.id, c.id))}
          >
            <span className="case-number">0{cases.cases.indexOf(c) + 1}</span>
            <h3>{c.name}</h3>
            <p>
              {
                {
                  cash: "比較候選 → 雙籤 → 分階段模擬支付",
                  no_deal: "接受條件無交集，不成交不扣信用",
                  withdrawal: "已釋放 HK$60，待退回 HK$90",
                  barter: "60 分鐘輔導 ↔ 90 分鐘英語交流",
                  hybrid: "雙方服務加 HK$50 模擬補差",
                }[c.id as "cash"]
              }
            </p>
            <span>
              {me.case === c.id ? "目前案例" : "載入案例"}{" "}
              <ArrowUpRight size={15} />
            </span>
          </button>
        ))}
      </div>
      <div className="demo-tools panel">
        <div>
          <h3>案例管理</h3>
          <p>只有預置復核員可重置和匯出完整公開事件。</p>
        </div>
        {!me.user.reviewer ? (
          <button
            className="button primary"
            onClick={() => act(() => login("reviewer"))}
          >
            切換復核員
          </button>
        ) : (
          <>
            <button
              className="button outline"
              disabled={busy}
              onClick={() =>
                act(() => api("/demo/reset", {}), "當前案例已重置")
              }
            >
              <RotateCcw size={16} />
              重置本案例
            </button>
            <button className="button primary" onClick={download}>
              <Download size={16} />
              匯出脫敏事件
            </button>
          </>
        )}
      </div>
      <h2 className="subheading">能力證據與爭議復核</h2>
      {!me.user.reviewer ? (
        <div className="notice">
          <ShieldCheck size={17} />
          此區需要復核員身份。交易雙方仍可在訂單中提出異議。
        </div>
      ) : error ? (
        <ErrorBox error={error} />
      ) : (
        <div className="review-grid">
          {queue?.evidence.map((e: Data) => (
            <div className="panel" key={e.id}>
              <Badge>能力證據</Badge>
              <h3>{e.data.title}</h3>
              <p>{e.data.body}</p>
              <small>
                {labels[e.category]} · {e.data.skills.join("、")}
              </small>
              <button
                className="button outline small"
                onClick={() => {
                  setSelected({ ...e, type: "evidence" });
                  setBasis("");
                }}
              >
                查看並復核
              </button>
            </div>
          ))}
          {queue?.disputes.map((d: Data) => (
            <div className="panel" key={d.id}>
              <Badge tone="amber">訂單爭議</Badge>
              <h3>{d.data.reason}</h3>
              <Link to={`/orders/${d.agreement_id}`}>
                查看原協議與證據 <ExternalLink size={14} />
              </Link>
              <button
                className="button outline small"
                onClick={() => {
                  setSelected({ ...d, type: "dispute" });
                  setBasis("");
                }}
              >
                記錄復核結果
              </button>
            </div>
          ))}
          {!queue?.evidence.length && !queue?.disputes.length && (
            <Empty
              title="目前沒有待復核事項"
              text="所有復核結果都會留下依據；沒有證據時可以保留未解決。"
            />
          )}
        </div>
      )}
      <div className="panel demo-explanation">
        <h3>演示的公平規則</h3>
        <p>
          能力證據影響本類參考單價；效率影響工時。先行投入按輪限制，已確認的貢獻不因退出被抹掉。
        </p>
        <p>
          代價：分階段驗收增加操作，限制不可拆分服務；平臺不能證明線下真實履約或保證追回損失。
        </p>
        <small>
          所有基準、權重、價格與歷史均為演示資料。核心流程不依賴 AI 或外網。
        </small>
      </div>
      {selected && (
        <Modal
          title={selected.type === "evidence" ? "復核能力材料" : "記錄爭議復核"}
          onClose={() => setSelected(null)}
        >
          <form onSubmit={review}>
            {selected.type === "dispute" && (
              <label>
                復核處理
                <select
                  value={outcome}
                  onChange={(e) => setOutcome(e.target.value)}
                >
                  <option value="RESUME">恢復原流程</option>
                  <option value="ACCEPT">依證據確認成果</option>
                  <option value="REDO">返回原義務重做</option>
                  <option value="CLOSEOUT">轉入雙方結清</option>
                  <option value="UNRESOLVED">證據不足，保留未解決</option>
                </select>
              </label>
            )}
            {(selected.type === "evidence" || outcome === "ACCEPT") && (
              <ScoreFields scores={scores} setScores={setScores} />
            )}
            <label>
              復核依據
              <textarea
                required
                minLength={5}
                value={basis}
                onChange={(e) => setBasis(e.target.value)}
                placeholder="列出對照的驗收條款、作品內容和可核對結果。"
              />
            </label>
            <button className="button primary" disabled={busy}>
              保存復核結果
            </button>
          </form>
        </Modal>
      )}
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
