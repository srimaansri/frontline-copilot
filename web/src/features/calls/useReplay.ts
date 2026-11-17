import { useEffect, useReducer } from "react";

import type { TranscriptTurn } from "@/api/types";

/** Where a replay is: the last turn on show, counted from 0, and whether it is running. */
export interface ReplayPosition {
  turn: number;
  playing: boolean;
}

type Action = { type: "play" } | { type: "pause" } | { type: "next" } | { type: "restart" } | { type: "tick" };

function reducer(last: number) {
  return (position: ReplayPosition, action: Action): ReplayPosition => {
    switch (action.type) {
      case "play":
        // Play at the end of the call starts it again.
        return position.turn >= last ? { turn: 0, playing: last > 0 } : { ...position, playing: true };
      case "pause":
        return { ...position, playing: false };
      case "next":
        return { turn: Math.min(position.turn + 1, last), playing: false };
      case "restart":
        return { turn: 0, playing: false };
      case "tick": {
        const turn = Math.min(position.turn + 1, last);
        return { turn, playing: position.playing && turn < last };
      }
    }
  };
}

/*
 * How long a turn stays on screen before the next one arrives: long enough to
 * read it. A base, plus time for each character, within a least and a most.
 */
const BASE_MS = 900;
const MS_PER_CHARACTER = 40;
const SHORTEST_MS = 1500;
const LONGEST_MS = 5500;

/** The time to read one turn, in milliseconds. */
export function readingTime(text: string): number {
  return Math.min(Math.max(BASE_MS + MS_PER_CHARACTER * text.length, SHORTEST_MS), LONGEST_MS);
}

export interface Replay extends ReplayPosition {
  /** True when the last turn is on show. */
  atEnd: boolean;
  play: () => void;
  pause: () => void;
  /** Show one more turn and stop there. */
  next: () => void;
  /** Go back to the first turn and stop there. */
  restart: () => void;
}

/**
 * A call shown one turn at a time. It starts stopped: nothing moves until Play
 * is pressed, and Pause stops it at once. While it runs, each turn stays on
 * screen for as long as it takes to read, then the next one arrives.
 *
 * `startAtEnd` opens with the whole call on show. A page opened on a demo
 * state uses it, so that a screenshot is the same every time.
 */
export function useReplay(turns: readonly TranscriptTurn[], startAtEnd = false): Replay {
  const last = Math.max(turns.length - 1, 0);
  const [position, dispatch] = useReducer(reducer(last), {
    turn: startAtEnd ? last : 0,
    playing: false,
  });
  const { turn, playing } = position;
  const shownFor = readingTime(turns[turn]?.text ?? "");

  useEffect(() => {
    if (!playing) {
      return undefined;
    }
    const timer = window.setTimeout(() => {
      dispatch({ type: "tick" });
    }, shownFor);
    return () => {
      window.clearTimeout(timer);
    };
  }, [playing, turn, shownFor]);

  return {
    turn,
    playing,
    atEnd: turn >= last,
    play: () => {
      dispatch({ type: "play" });
    },
    pause: () => {
      dispatch({ type: "pause" });
    },
    next: () => {
      dispatch({ type: "next" });
    },
    restart: () => {
      dispatch({ type: "restart" });
    },
  };
}
