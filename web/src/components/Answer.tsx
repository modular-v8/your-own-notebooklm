import { Component, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { AnswerRecord } from "../api";

type Props = {
  answer: AnswerRecord;
  onCiteClick: (chunkId: string) => void;
  // While a turn is still streaming, no citations event has arrived yet --
  // showing "No sources cited" would be premature, not a real finding.
  pending?: boolean;
};

type BoundaryProps = { fallback: string; children: ReactNode };
type BoundaryState = { failed: boolean };

// react-markdown/remark-gfm don't throw on malformed input in practice, but
// the spec requires the chat to survive even if that ever changes -- falls
// back to the raw text rather than losing the answer.
class MarkdownErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
  }
}

export function Answer({ answer, onCiteClick, pending = false }: Props) {
  return (
    <div className="answer-card">
      <div className="pipeline-label">{answer.pipeline}</div>
      <div className="answer-text">
        <MarkdownErrorBoundary fallback={answer.text}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer.text}</ReactMarkdown>
        </MarkdownErrorBoundary>
      </div>

      {!pending &&
        (answer.cited && answer.cited.length > 0 ? (
          <div className="citation-strip">
            {answer.cited.map((chunkId) => (
              <button key={chunkId} className="citation-chip" onClick={() => onCiteClick(chunkId)}>
                {chunkId}
              </button>
            ))}
          </div>
        ) : (
          <div className="no-sources">No sources cited.</div>
        ))}

      {answer.error && <div className="answer-error">Provider error: {answer.error}</div>}
    </div>
  );
}
