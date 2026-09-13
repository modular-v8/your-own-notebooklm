import { useCallback, useEffect, useState } from "react";

import {
  type Collection,
  type DocumentEntry,
  createCollection,
  deleteCollection,
  deleteDocument,
  fetchCollections,
  fetchDocuments,
  removeDocumentFromCollection,
  renameCollection,
} from "../api";
import { CollectionList } from "./CollectionList";
import { DocumentList } from "./DocumentList";
import { UploadControl } from "./UploadControl";

type Props = {
  selectedCollection: string | null;
  onSelectCollection: (name: string) => void;
};

export function Sidebar({ selectedCollection, onSelectCollection }: Props) {
  const [collapsed, setCollapsed] = useState(false);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [documents, setDocuments] = useState<DocumentEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const [nextCollections, nextDocuments] = await Promise.all([fetchCollections(), fetchDocuments()]);
    setCollections(nextCollections);
    setDocuments(nextDocuments);
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function guarded(action: () => Promise<void>) {
    try {
      setError(null);
      await action();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function handleCreate(name: string) {
    await guarded(async () => {
      await createCollection(name);
      await refresh();
      onSelectCollection(name);
    });
  }

  async function handleRename(name: string, newName: string) {
    await guarded(async () => {
      await renameCollection(name, newName);
      await refresh();
    });
  }

  async function handleDeleteCollection(name: string) {
    await guarded(async () => {
      await deleteCollection(name);
      await refresh();
    });
  }

  async function handleRemoveDocument(doc: string) {
    if (!selectedCollection) return;
    await guarded(async () => {
      await removeDocumentFromCollection(selectedCollection, doc);
      await refresh();
    });
  }

  async function handleDeleteDocument(doc: string) {
    await guarded(async () => {
      const warning = await deleteDocument(doc, false);
      if (warning) {
        const names = warning.collections.join(", ");
        if (!confirm(`${warning.message}\n\nStill referenced by: ${names}. Delete anyway?`)) return;
        await deleteDocument(doc, true);
      }
      await refresh();
    });
  }

  if (collapsed) {
    return (
      <div className="sidebar collapsed">
        <button className="sidebar-toggle" onClick={() => setCollapsed(false)} title="Expand sidebar">
          »
        </button>
      </div>
    );
  }

  const documentsInSelected = selectedCollection
    ? documents.filter((d) => d.collections.includes(selectedCollection))
    : [];

  return (
    <div className="sidebar">
      <div className="sidebar-header">
        <span className="sidebar-title">Collections</span>
        <button className="sidebar-toggle" onClick={() => setCollapsed(true)} title="Collapse sidebar">
          «
        </button>
      </div>

      {collections.length === 0 && (
        <div className="sidebar-empty">No collections yet -- create one to get started.</div>
      )}
      <CollectionList
        collections={collections}
        selected={selectedCollection}
        onSelect={onSelectCollection}
        onCreate={handleCreate}
        onRename={handleRename}
        onDelete={handleDeleteCollection}
      />

      {selectedCollection && (
        <div className="sidebar-documents">
          <div className="sidebar-subheader">{selectedCollection}</div>
          <DocumentList
            documents={documentsInSelected}
            onRemove={handleRemoveDocument}
            onDelete={handleDeleteDocument}
          />
          <UploadControl collection={selectedCollection} onUploaded={refresh} />
        </div>
      )}

      {error && <div className="sidebar-error">{error}</div>}
    </div>
  );
}
