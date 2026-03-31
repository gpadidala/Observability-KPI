"use client";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div style={{ padding: "2rem", maxWidth: "800px" }}>
      <h2 style={{ color: "#f87171", marginBottom: "1rem" }}>Page Error</h2>
      <pre style={{ background: "#161923", padding: "1rem", borderRadius: "0.5rem", overflow: "auto", fontSize: "0.85rem", color: "#e2e8f0" }}>
        {error.message}
        {"\n\n"}
        {error.stack}
      </pre>
      <button
        onClick={reset}
        style={{ marginTop: "1rem", padding: "0.5rem 1rem", background: "#6366f1", color: "white", border: "none", borderRadius: "0.5rem", cursor: "pointer" }}
      >
        Try again
      </button>
    </div>
  );
}
