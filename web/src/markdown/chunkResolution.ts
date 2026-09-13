// Whether an inline `[chunk-id]` reference actually resolves in the current
// index. A chip that looks clickable and does nothing is worse than the
// literal brackets it replaces (spec), so resolution is checked before a
// chip ever renders -- never optimistically, never downgraded after the
// fact. One fetch per chunk id no matter how many times it appears in an
// answer or how many times the surrounding text re-renders while streaming.
import { type ChunkDetail, fetchChunk } from "../api";

const cache = new Map<string, Promise<ChunkDetail | null>>();

export function resolveChunk(chunkId: string): Promise<ChunkDetail | null> {
  let pending = cache.get(chunkId);
  if (!pending) {
    pending = fetchChunk(chunkId);
    cache.set(chunkId, pending);
  }
  return pending;
}
