import { useState } from "react";

import type { Collection } from "../api";

type Props = {
  collections: Collection[];
  selected: string | null;
  onSelect: (name: string) => void;
  onCreate: (name: string) => void;
  onRename: (name: string, newName: string) => void;
  onDelete: (name: string) => void;
};

export function CollectionList({ collections, selected, onSelect, onCreate, onRename, onDelete }: Props) {
  const [creating, setCreating] = useState(false);
  const [draftName, setDraftName] = useState("");
  const [renamingName, setRenamingName] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");

  function submitCreate() {
    const name = draftName.trim();
    if (name) onCreate(name);
    setDraftName("");
    setCreating(false);
  }

  function submitRename(name: string) {
    const next = renameDraft.trim();
    if (next && next !== name) onRename(name, next);
    setRenamingName(null);
  }

  return (
    <div className="collection-list">
      {collections.map((c) => (
        <div key={c.name} className={`collection-row${c.name === selected ? " selected" : ""}`}>
          {renamingName === c.name ? (
            <input
              autoFocus
              className="collection-rename-input"
              value={renameDraft}
              onChange={(e) => setRenameDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") submitRename(c.name);
                if (e.key === "Escape") setRenamingName(null);
              }}
              onBlur={() => submitRename(c.name)}
            />
          ) : (
            <button className="collection-name" onClick={() => onSelect(c.name)}>
              <span>{c.name}</span>
              {c.locked && <span className="locked-badge">Locked</span>}
            </button>
          )}
          <span className="collection-count">{c.document_count}</span>
          {!c.locked && renamingName !== c.name && (
            <div className="collection-actions">
              <button
                className="icon-button"
                title="Rename"
                onClick={() => {
                  setRenamingName(c.name);
                  setRenameDraft(c.name);
                }}
              >
                ✎
              </button>
              <button
                className="icon-button"
                title="Delete collection"
                onClick={() => {
                  if (confirm(`Delete collection "${c.name}"? Documents stay on disk.`)) onDelete(c.name);
                }}
              >
                ×
              </button>
            </div>
          )}
        </div>
      ))}

      {creating ? (
        <input
          autoFocus
          className="collection-rename-input"
          placeholder="Collection name"
          value={draftName}
          onChange={(e) => setDraftName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submitCreate();
            if (e.key === "Escape") setCreating(false);
          }}
          onBlur={submitCreate}
        />
      ) : (
        <button className="new-collection-button" onClick={() => setCreating(true)}>
          + New collection
        </button>
      )}
    </div>
  );
}
