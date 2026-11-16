import { NextTurnIcon, PauseIcon, PlayIcon, StartAgainIcon } from "@/components/icons/glyphs";
import { Button } from "@/components/ui/button";
import { IconButton } from "@/components/ui/icon-button";

export interface ReplayControlsProps {
  /** The last turn on show, counted from 0, and how many turns the call has. */
  turn: number;
  total: number;
  playing: boolean;
  onPlay: () => void;
  onPause: () => void;
  onNext: () => void;
  onRestart: () => void;
}

/**
 * The controls of a replayed call: play or pause, one turn on, back to the
 * start, and where the replay is. Play is the one cobalt fill of the region.
 * Nothing here moves: the place in the call is a readout, not a bar.
 */
export function ReplayControls({
  turn,
  total,
  playing,
  onPlay,
  onPause,
  onNext,
  onRestart,
}: ReplayControlsProps) {
  const atEnd = turn >= total - 1;
  let playLabel = "Play";
  if (atEnd) {
    playLabel = "Play again";
  } else if (turn > 0) {
    playLabel = "Carry on";
  }
  return (
    <div
      role="group"
      aria-label="Replay"
      className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-2 border-b border-line bg-surface px-4 py-3 sm:px-8"
    >
      {playing ? (
        <Button variant="primary" onClick={onPause}>
          <PauseIcon />
          Pause
        </Button>
      ) : (
        <Button variant="primary" onClick={onPlay} disabled={total < 2}>
          <PlayIcon />
          {playLabel}
        </Button>
      )}
      <IconButton label="Next turn" onClick={onNext} disabled={atEnd}>
        <NextTurnIcon />
      </IconButton>
      <IconButton label="Back to the first turn" onClick={onRestart} disabled={turn === 0 && !playing}>
        <StartAgainIcon />
      </IconButton>
      <p className="ml-auto text-meta text-ink-2">
        Turn <span className="font-mono font-semibold text-ink">{Math.min(turn + 1, total)}</span> of{" "}
        <span className="font-mono">{total}</span>
      </p>
    </div>
  );
}
