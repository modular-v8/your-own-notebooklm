import type { ChunkDetail } from "../api";

type Props = {
  chunk: ChunkDetail | "unresolvable" | null;
  onClose: () => void;
};

export function SourcePanel({ chunk, onClose }: Props) {
  if (chunk === null) return null;

  return (
    <div className="source-panel">
      <div className="source-panel-header">
        {chunk === "unresolvable" ? (
          <span className="doc">Unresolvable citation</span>
        ) : (
          <>
            <span className="doc">{chunk.doc}</span>
            <span className="lines">
              lines {chunk.line_start}-{chunk.line_end}
            </span>
          </>
        )}
        <button className="close" onClick={onClose} aria-label="Close">
          ×
        </button>
      </div>

      {chunk === "unresolvable" ? (
        <p className="unresolvable">This chunk id is not present in the current index.</p>
      ) : (
        <div className="chunk-text">{chunk.text}</div>
      )}
    </div>
  );
}
