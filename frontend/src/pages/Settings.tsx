export function Settings() {
  return (
    <div>
      <div className="page-header">
        <div className="page-header-title">
          <span className="eyebrow">Configuration</span>
          <h1>Settings</h1>
        </div>
      </div>
      <div className="placeholder">
        <span className="placeholder-tag">Forthcoming · Phase 12</span>
        <p>
          Detection thresholds, suppression bounds, Lichess username, study
          IDs — wired to <code>GET</code> &amp; <code>PATCH /settings</code>.
          Re-analysis is a click away when the thresholds change.
        </p>
      </div>
    </div>
  )
}
