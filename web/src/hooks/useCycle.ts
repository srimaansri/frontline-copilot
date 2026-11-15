import { useEffect, useState } from "react";

/** Count 0, 1, ... length - 1 and round again, one step every `milliseconds`. */
export function useCycle(length: number, milliseconds: number): number {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const timer = window.setInterval(() => {
      setIndex((current) => (current + 1) % length);
    }, milliseconds);
    return () => {
      window.clearInterval(timer);
    };
  }, [length, milliseconds]);

  return index;
}
