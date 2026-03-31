"use client";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <html lang="en" className="dark">
      <body style={{ background: "#0f1117", color: "#e2e8f0", fontFamily: "system-ui", padding: "2rem" }}>
        <h1 style={{ color: "#f87171" }}>Something went wrong</h1>
        <pre style={{ background: "#161923", padding: "1rem", borderRadius: "0.5rem", overflow: "auto", fontSize: "0.85rem" }}>
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
      </body>
    </html>
  );
}
