import { useRef, useState } from "react";

import { type IndexJob, fetchJob, uploadDocument } from "../api";

const POLL_INTERVAL_MS = 800;

type Props = {
  collection: string;
  onUploaded: () => void;
};

export function UploadControl({ collection, onUploaded }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [job, setJob] = useState<IndexJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  function poll(jobId: string) {
    const timer = setInterval(async () => {
      try {
        const latest = await fetchJob(jobId);
        setJob(latest);
        if (latest.state === "ready" || latest.state === "failed") {
          clearInterval(timer);
          onUploaded();
        }
      } catch {
        clearInterval(timer);
      }
    }, POLL_INTERVAL_MS);
  }

  async function handleFileChosen(file: File) {
    setError(null);
    try {
      const created = await uploadDocument(collection, file);
      setJob(created);
      poll(created.job_id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  const inputId = `upload-${collection}`;

  return (
    <div className="upload-control">
      <input
        ref={inputRef}
        type="file"
        id={inputId}
        className="upload-input"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) handleFileChosen(file);
        }}
      />
      <label htmlFor={inputId} className="upload-label">
        Upload document
      </label>
      {job && job.state !== "ready" && (
        <div className="upload-progress">
          {job.doc}: {job.state}
          {job.state === "failed" && job.error && <span className="upload-error"> — {job.error}</span>}
        </div>
      )}
      {error && <div className="upload-error">{error}</div>}
    </div>
  );
}
