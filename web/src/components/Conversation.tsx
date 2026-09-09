import { useState } from "react";
import type { AnswerRecord, Conversation as ConversationData } from "../api";
import { Answer } from "./Answer";

type Props = {
  conversation: ConversationData;
  pendingQuestion: string | null;
  pendingText: string;
  streaming: boolean;
  streamError: string | null;
  escalatingIndex: number | null;
  onAsk: (question: string) => void;
  onEscalate: (turnIndex: number) => void;
  onCiteClick: (chunkId: string) => void;
};

export function Conversation({
  conversation,
  pendingQuestion,
  pendingText,
  streaming,
  streamError,
  escalatingIndex,
  onAsk,
  onEscalate,
  onCiteClick,
}: Props) {
  const [question, setQuestion] = useState("");

  function submit() {
    const trimmed = question.trim();
    if (!trimmed || streaming) return;
    onAsk(trimmed);
    setQuestion("");
  }

  const pendingAnswer: AnswerRecord | null = pendingQuestion
    ? { text: pendingText, cited: null, pipeline: "baseline" }
    : null;

  return (
    <div className="chat-screen">
      <div className="chat-header">
        <span className="label">Collection</span>
        <span>{conversation.collection}</span>
      </div>

      <div className="chat-body">
        <div className="turn-list">
          {conversation.turns.map((turn, index) => (
            <div className="turn" key={index}>
              <div className="question">{turn.question}</div>
              <Answer answer={turn.baseline} onCiteClick={onCiteClick} />

              {turn.agentic ? (
                <Answer answer={turn.agentic} onCiteClick={onCiteClick} />
              ) : (
                <div className="escalate-row">
                  {escalatingIndex === index ? (
                    <span className="escalating-state">
                      Escalating to agentic retrieval&hellip; this runs as one opaque step and its
                      duration is unmeasured -- it will appear when it finishes.
                    </span>
                  ) : (
                    <button
                      className="escalate-button"
                      onClick={() => onEscalate(index)}
                      disabled={escalatingIndex !== null}
                    >
                      Escalate to agentic retrieval
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}

          {pendingAnswer && (
            <div className="turn">
              <div className="question">{pendingQuestion}</div>
              <Answer answer={pendingAnswer} onCiteClick={onCiteClick} pending />
            </div>
          )}
        </div>
      </div>

      {streamError && <div className="stream-error">Error: {streamError}</div>}

      <div className="ask-row">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") submit();
          }}
          placeholder="Ask a question about this collection..."
          disabled={streaming}
        />
        <button className="ask-button" onClick={submit} disabled={streaming || !question.trim()}>
          {streaming ? "Asking..." : "Ask"}
        </button>
      </div>
    </div>
  );
}
