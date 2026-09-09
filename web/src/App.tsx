import { useEffect, useState } from "react";
import {
  type ChunkDetail,
  type Collection,
  type Conversation as ConversationData,
  createConversation,
  escalateTurn,
  fetchChunk,
  fetchCollections,
  getConversation,
  streamTurn,
} from "./api";
import { CollectionPicker } from "./components/CollectionPicker";
import { Conversation } from "./components/Conversation";
import { SourcePanel } from "./components/SourcePanel";

export default function App() {
  const [collections, setCollections] = useState<Collection[]>([]);
  const [conversation, setConversation] = useState<ConversationData | null>(null);

  const [pendingQuestion, setPendingQuestion] = useState<string | null>(null);
  const [pendingText, setPendingText] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [streamError, setStreamError] = useState<string | null>(null);

  const [escalatingIndex, setEscalatingIndex] = useState<number | null>(null);
  const [activeChunk, setActiveChunk] = useState<ChunkDetail | "unresolvable" | null>(null);

  useEffect(() => {
    fetchCollections().then(setCollections);
  }, []);

  async function handleSelectCollection(name: string) {
    const created = await createConversation(name);
    setConversation(created);
  }

  async function handleAsk(question: string) {
    if (!conversation) return;

    setStreaming(true);
    setStreamError(null);
    setPendingQuestion(question);
    setPendingText("");

    try {
      for await (const event of streamTurn(conversation.id, question)) {
        if (event.type === "token") {
          setPendingText((text) => text + event.text);
        } else if (event.type === "error") {
          setStreamError(event.message);
        } else if (event.type === "done") {
          break;
        }
      }
    } catch (err) {
      setStreamError(err instanceof Error ? err.message : String(err));
    }

    // The server already persisted the turn (including a mid-stream
    // failure's partial answer) -- reload the canonical record rather than
    // reconstructing it client-side.
    const fresh = await getConversation(conversation.id);
    setConversation(fresh);
    setPendingQuestion(null);
    setPendingText("");
    setStreaming(false);
  }

  async function handleEscalate(turnIndex: number) {
    if (!conversation) return;
    setEscalatingIndex(turnIndex);
    try {
      await escalateTurn(conversation.id, turnIndex);
      const fresh = await getConversation(conversation.id);
      setConversation(fresh);
    } catch (err) {
      setStreamError(err instanceof Error ? err.message : String(err));
    } finally {
      setEscalatingIndex(null);
    }
  }

  async function handleCiteClick(chunkId: string) {
    const chunk = await fetchChunk(chunkId);
    setActiveChunk(chunk ?? "unresolvable");
  }

  if (!conversation) {
    return <CollectionPicker collections={collections} onSelect={handleSelectCollection} />;
  }

  return (
    <div style={{ display: "flex", height: "100%" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <Conversation
          conversation={conversation}
          pendingQuestion={pendingQuestion}
          pendingText={pendingText}
          streaming={streaming}
          streamError={streamError}
          escalatingIndex={escalatingIndex}
          onAsk={handleAsk}
          onEscalate={handleEscalate}
          onCiteClick={handleCiteClick}
        />
      </div>
      <SourcePanel chunk={activeChunk} onClose={() => setActiveChunk(null)} />
    </div>
  );
}
