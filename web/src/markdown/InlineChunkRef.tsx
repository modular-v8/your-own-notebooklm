import { useEffect, useState } from "react";

import { resolveChunk } from "./chunkResolution";

type Status = "pending" | "resolved" | "unresolved";

type Props = {
  chunkId: string;
  onCiteClick: (chunkId: string) => void;
};

// Renders plain `[chunk-id]` text until resolution confirms the id is real,
// then upgrades to a chip -- never the other way around, so a viewer never
// sees a chip that turns out to do nothing.
export function InlineChunkRef({ chunkId, onCiteClick }: Props) {
  const [status, setStatus] = useState<Status>("pending");

  useEffect(() => {
    let cancelled = false;
    resolveChunk(chunkId).then((detail) => {
      if (!cancelled) setStatus(detail ? "resolved" : "unresolved");
    });
    return () => {
      cancelled = true;
    };
  }, [chunkId]);

  if (status === "resolved") {
    return (
      <button className="citation-chip inline-citation-chip" onClick={() => onCiteClick(chunkId)}>
        {chunkId}
      </button>
    );
  }

  return <>{`[${chunkId}]`}</>;
}
