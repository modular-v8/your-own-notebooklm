import type { Collection } from "../api";

type Props = {
  collections: Collection[];
  onSelect: (name: string) => void;
};

export function CollectionPicker({ collections, onSelect }: Props) {
  return (
    <div className="picker-screen">
      <h1>Pick a collection</h1>
      <div className="picker-grid">
        {collections.map((c) => (
          <button key={c.name} className="collection-card" onClick={() => onSelect(c.name)}>
            <div className="name">{c.name}</div>
            <div className="meta">
              {c.documents.length} document{c.documents.length === 1 ? "" : "s"}
            </div>
          </button>
        ))}
      </div>
      {collections.length === 0 && <p>No collections configured.</p>}
    </div>
  );
}
