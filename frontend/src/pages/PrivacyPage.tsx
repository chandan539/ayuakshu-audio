export function PrivacyPage() {
  return (
    <div>
      <h1 className="page-title">Privacy</h1>
      <p className="page-sub">Built for local-first speech generation.</p>
      <div className="panel">
        <ul style={{ lineHeight: 1.8, margin: 0, paddingLeft: 18 }}>
          <li>Your text stays on this Mac.</li>
          <li>Your voice recordings stay on this Mac.</li>
          <li>Speech generation happens on this Mac.</li>
          <li>No cloud API is required for speech generation.</li>
          <li>No audio is uploaded.</li>
          <li>No text is uploaded.</li>
          <li>No analytics / telemetry services are included.</li>
        </ul>
        <p className="muted">
          Only use voice recordings you own or have permission to use.
        </p>
        <p className="muted">
          Third-party libraries (TTS model, PyTorch, lameenc, Tauri, etc.) should be license-audited before commercial redistribution.
          See THIRD_PARTY_LICENSES.md before shipping.
        </p>
      </div>
    </div>
  )
}
