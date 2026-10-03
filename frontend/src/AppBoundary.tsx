import React from "react";
export class AppBoundary extends React.Component<
  { children: React.ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    if (this.state.failed)
      return (
        <main className="boot">
          <h1>頁面暫時無法顯示</h1>
          <p>已儲存的協議和交易記錄會保留，請重新載入頁面。</p>
          <button
            className="button primary"
            onClick={() => window.location.reload()}
          >
            重新載入
          </button>
          <a className="button outline" href="/">
            返回市場
          </a>
        </main>
      );
    return this.props.children;
  }
}
