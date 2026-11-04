"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

function stemOf(name: string): string {
  return name.replace(/^.*[/\\]/, "").replace(/\.[^.]+$/, "");
}

export default function Upload() {
  const r = useRouter();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [autoName, setAutoName] = useState("");

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const res = await fetch("/api/upload", { method: "POST", body: new FormData(e.currentTarget) });
      const j = await res.json();
      if (!res.ok) throw new Error(j.error ?? `HTTP ${res.status}`);
      r.push(`/runs/${j.run_id}`);
    } catch (x) {
      setErr((x as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card upload-card">
      <h1>Check a video</h1>
      <p className="upload-lead">
        Upload an MP4 to start a check right away — no setup required. Notes and approved contracts are optional.
      </p>

      <label>
        Video (MP4) <span className="req">required</span>
        <input
          type="file"
          name="file"
          accept="video/mp4,.mp4"
          required
          onChange={(e) => setAutoName(stemOf(e.currentTarget.files?.[0]?.name ?? ""))}
        />
      </label>

      <label>
        Script, brief or notes <span className="opt">(optional)</span>
        <span className="field-hint">
          Used as context by the checker — e.g. what the video should show, spoken dialogue, character details, or brand rules.
        </span>
        <textarea
          name="brief_text"
          className="brief-input"
          rows={4}
          maxLength={20000}
          placeholder="Describe what the video is supposed to show, paste the script, or add notes..."
        />
      </label>

      <label>
        Name <span className="opt">(optional)</span>
        <input
          type="text"
          name="asset_id"
          placeholder={autoName ? `Auto-fills from file: ${autoName}` : "Auto-fills from the file name"}
        />
      </label>

      <details className="upload-advanced">
        <summary>Advanced: use an approved contract JSON</summary>
        <div className="upload-advanced-body">
          <p className="field-hint">
            Only needed when checking against a locked JSON contract. Make sure Name above matches your contract&apos;s target asset ID.
          </p>
          <label>
            Contract JSON (upload)
            <input type="file" name="contract_file" accept="application/json,.json" />
          </label>
          <label>
            ...or paste contract JSON
            <textarea name="contract_text" />
          </label>
        </div>
      </details>

      <button className="primary btn-primary" disabled={busy}>
        {busy ? "Submitting..." : "Upload and verify"}
      </button>
      {err && (
        <div className="err" data-testid="upload-error" style={{ marginTop: 8 }}>
          {err}
        </div>
      )}
    </form>
  );
}
