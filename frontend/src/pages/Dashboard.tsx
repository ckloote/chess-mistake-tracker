export function Dashboard() {
  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Index</span>
          <h1>Dashboard</h1>
        </div>
      </div>
      <div className="placeholder">
        <span className="placeholder-tag">Forthcoming · Phase 11</span>
        <p>
          A summary view will appear here — recent games, the patterns that
          dominate your mistake distribution, and the training prescription
          that follows from them.
        </p>
        <p className="footnote">
          Until then, jump to <a href="/games">Games</a> to browse the archive
          and review individual positions.
        </p>
      </div>
    </div>
  )
}
