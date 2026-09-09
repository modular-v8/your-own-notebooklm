import type { AnswerRecord } from "../api";

type Props = {
  answer: AnswerRecord;
  onCiteClick: (chunkId: string) => void;
  // While a turn is still streaming, no citations event has arrived yet --
  // showing "No sources cited" would be premature, not a real finding.
  pending?: boolean;
};

export function Answer({ answer, onCiteClick, pending = false }: Props) {
  return (
    <div className="answer-card">
      <div className="pipeline-label">{answer.pipeline}</div>
      <div className="answer-text">{answer.text}</div>

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
