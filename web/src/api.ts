// fetch + EventSource wrappers over the FastAPI backend. No business logic
// here -- one function per endpoint, plus SSE parsing for the streaming
// turn endpoint (EventSource itself can't POST, so this reads the raw
// text/event-stream body by hand).

export type Collection = { name: string; document_count: number };

export type DocumentState = "ready" | "reindexing" | "indexing" | "failed";

export type DocumentEntry = {
  name: string;
  collections: string[];
  state: DocumentState;
  chunk_count: number | null;
  empty: boolean;
  error: string | null;
};

export type JobState = "queued" | "parsing" | "embedding" | "ready" | "failed";

export type IndexJob = {
  job_id: string;
  doc: string;
  collection: string;
  state: JobState;
  error: string | null;
  chunk_count: number | null;
};

export type DeleteWarning = { message: string; collections: string[] };

export type AnswerRecord = {
  text: string;
  cited: string[] | null;
  pipeline: string;
  error?: string | null;
};

export type Turn = {
  question: string;
  baseline: AnswerRecord;
  agentic: AnswerRecord | null;
};

export type Conversation = {
  id: string;
  collection: string;
  created_at: string;
  turns: Turn[];
};

export type ChunkDetail = {
  chunk_id: string;
  doc: string;
  text: string;
  line_start: number;
  line_end: number;
};

export type StreamEvent =
  | { type: "token"; text: string }
  | { type: "citations"; cited: string[] | null }
  | { type: "error"; message: string }
  | { type: "done" };

async function asJson<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${response.status}: ${body}`);
  }
  return response.json() as Promise<T>;
}

export async function fetchCollections(): Promise<Collection[]> {
  return asJson<Collection[]>(await fetch("/api/collections"));
}

export async function createCollection(name: string): Promise<void> {
  const response = await fetch("/api/collections", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
}

export async function renameCollection(name: string, newName: string): Promise<void> {
  const response = await fetch(`/api/collections/${encodeURIComponent(name)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: newName }),
  });
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
}

export async function deleteCollection(name: string): Promise<void> {
  const response = await fetch(`/api/collections/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (!response.ok && response.status !== 204) throw new Error(`${response.status}: ${await response.text()}`);
}

export async function fetchDocuments(): Promise<DocumentEntry[]> {
  return asJson<DocumentEntry[]>(await fetch("/api/documents"));
}

export async function uploadDocument(collection: string, file: File): Promise<IndexJob> {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`/api/collections/${encodeURIComponent(collection)}/documents`, {
    method: "POST",
    body: formData,
  });
  return asJson<IndexJob>(response);
}

export async function fetchJob(jobId: string): Promise<IndexJob> {
  return asJson<IndexJob>(await fetch(`/api/jobs/${encodeURIComponent(jobId)}`));
}

export async function removeDocumentFromCollection(collection: string, doc: string): Promise<void> {
  const response = await fetch(
    `/api/collections/${encodeURIComponent(collection)}/documents/${encodeURIComponent(doc)}`,
    { method: "DELETE" }
  );
  if (!response.ok && response.status !== 204) throw new Error(`${response.status}: ${await response.text()}`);
}

// Returns the warning body when the server refuses without confirm=true;
// resolves to null on success so a caller can tell "done" from "needs confirmation".
export async function deleteDocument(doc: string, confirm: boolean): Promise<DeleteWarning | null> {
  const response = await fetch(`/api/documents/${encodeURIComponent(doc)}${confirm ? "?confirm=true" : ""}`, {
    method: "DELETE",
  });
  if (response.status === 409) {
    const body = await response.json();
    return body.detail as DeleteWarning;
  }
  if (!response.ok) throw new Error(`${response.status}: ${await response.text()}`);
  return null;
}

export async function createConversation(collection: string): Promise<Conversation> {
  const response = await fetch("/api/conversations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ collection }),
  });
  return asJson<Conversation>(response);
}

export async function getConversation(id: string): Promise<Conversation> {
  return asJson<Conversation>(await fetch(`/api/conversations/${id}`));
}

export async function escalateTurn(conversationId: string, turnIndex: number): Promise<AnswerRecord> {
  const response = await fetch(`/api/conversations/${conversationId}/turns/${turnIndex}/escalate`, {
    method: "POST",
  });
  return asJson<AnswerRecord>(response);
}

export async function fetchChunk(chunkId: string): Promise<ChunkDetail | null> {
  const response = await fetch(`/api/chunks/${encodeURIComponent(chunkId)}`);
  if (response.status === 404) return null;
  return asJson<ChunkDetail>(response);
}

function parseSseBlock(raw: string): StreamEvent | null {
  let eventName = "message";
  let data = "";
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) data += line.slice(5).trim();
  }

  if (eventName === "done") return { type: "done" };
  if (!data) return null;

  const parsed = JSON.parse(data);
  if (eventName === "token") return { type: "token", text: parsed.text };
  if (eventName === "citations") return { type: "citations", cited: parsed.cited };
  if (eventName === "error") return { type: "error", message: parsed.message };
  return null;
}

export async function* streamTurn(conversationId: string, question: string): AsyncGenerator<StreamEvent> {
  const response = await fetch(`/api/conversations/${conversationId}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  if (!response.ok || !response.body) {
    const body = response.body ? await response.text() : "";
    throw new Error(`${response.status}: ${body}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let separator: number;
    while ((separator = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      const event = parseSseBlock(block);
      if (event) yield event;
    }
  }
}
