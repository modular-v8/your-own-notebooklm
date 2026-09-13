import type { DocumentEntry, DocumentState } from "../api";

const STATE_LABEL: Record<DocumentState, string> = {
  ready: "Ready",
  reindexing: "Reindexing…",
  indexing: "Indexing…",
  failed: "Failed",
};

type Props = {
  documents: DocumentEntry[];
  onRemove: (doc: string) => void;
  onDelete: (doc: string) => void;
};

export function DocumentList({ documents, onRemove, onDelete }: Props) {
  if (documents.length === 0) {
    return <div className="document-list-empty">No documents yet.</div>;
  }

  return (
    <div className="document-list">
      {documents.map((doc) => (
        <div key={doc.name} className="document-row">
          <div className="document-name">{doc.name}</div>
          <div className={`document-state state-${doc.state}`}>
            {doc.empty ? "Indexed, no text found" : STATE_LABEL[doc.state]}
          </div>
          {doc.error && <div className="document-error">{doc.error}</div>}
          {!doc.locked && (
            <div className="document-actions">
              <button className="icon-button" title="Remove from this collection" onClick={() => onRemove(doc.name)}>
                −
              </button>
              <button className="icon-button" title="Delete from disk" onClick={() => onDelete(doc.name)}>
                ×
              </button>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
