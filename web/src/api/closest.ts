/**
 * Finds the recorded question closest to one the demo has no recording for.
 *
 * The public demo is a static page: it cannot run the copilot, so it can only
 * replay. A visitor rarely types a recorded question word for word, and "no
 * recording" for an ordinary question reads as a broken product. This matcher
 * lets the demo show the recorded answer to the closest question instead, and
 * the page says plainly that it did so and which question the answer belongs to.
 *
 * It is plain word overlap, weighted so that rare words count for more. It is
 * not the copilot's search and makes no claim to be: nothing here runs in the
 * live app.
 */

export interface RecordedText {
  question: string;
  /** The recorded answer and the titles of its sources: weaker evidence than the question. */
  context: string;
}

export interface ClosestMatch {
  question: string;
  /** From 0 to 1: the share of the typed question's weight found in the recording. */
  score: number;
}

/** Words that say nothing about the topic of a support question. */
const STOP_WORDS = new Set(
  (
    "a an the is are was were be been am if of to in on for and or but not do does did can could " +
    "would will should may might i you my me we our us they them their her his she he its it this " +
    "that these those there here what which who whom how when where why with at by as from into " +
    "about have has had get gets got customer customers caller agent asking ask asks asked wants " +
    "want wanted know tell show please need needs says say said northline cue some any so just " +
    "also than then very really out up down over again still"
  ).split(" "),
);

/**
 * Words a visitor uses for one topic, mapped to one word the recordings use. Kept
 * short on purpose: it covers how people name a topic, not how they phrase a request.
 */
const SAME_TOPIC: Readonly<Record<string, string>> = {
  abroad: "travel",
  overseas: "travel",
  trip: "travel",
  vacation: "travel",
  holiday: "travel",
  roam: "travel",
  roaming: "travel",
  international: "travel",
  country: "travel",
  countries: "travel",
  asia: "travel",
  europe: "travel",
  japan: "travel",
  india: "travel",
  invoice: "bill",
  statement: "bill",
  billing: "bill",
  cost: "price",
  costs: "price",
  cheap: "price",
  cheaper: "price",
  cheapest: "price",
  expensive: "price",
  much: "price",
  fee: "price",
  fees: "price",
  charge: "price",
  charged: "price",
  charges: "price",
  mobile: "phone",
  cell: "phone",
  cellphone: "phone",
  handset: "phone",
  device: "phone",
  iphone: "phone",
  android: "phone",
  internet: "data",
  stolen: "lost",
  missing: "lost",
  quit: "cancel",
  leave: "cancel",
  leaving: "cancel",
  terminate: "cancel",
  port: "transfer",
  porting: "transfer",
  switch: "transfer",
  switching: "transfer",
  password: "pin",
  passcode: "pin",
};

function stem(word: string): string {
  let out = word;
  if (out.length > 4 && out.endsWith("ies")) {
    out = `${out.slice(0, -3)}y`;
  } else if (out.length > 5 && out.endsWith("ing")) {
    out = out.slice(0, -3);
  } else if (out.length > 4 && out.endsWith("ed")) {
    out = out.slice(0, -2);
  } else if (out.length > 3 && out.endsWith("s") && !out.endsWith("ss")) {
    out = out.slice(0, -1);
  }
  // "travelling" and "traveling" both become "travel".
  if (out.length > 4 && out.at(-1) === out.at(-2)) {
    out = out.slice(0, -1);
  }
  return out;
}

/** The topic words of a text: lower case, without filler, plurals or endings. */
export function topicWords(text: string): Set<string> {
  const words = new Set<string>();
  for (const raw of text.toLowerCase().match(/[a-z0-9]+/g) ?? []) {
    if (STOP_WORDS.has(raw) || raw.length < 2) {
      continue;
    }
    const word = SAME_TOPIC[raw] ?? stem(raw);
    words.add(SAME_TOPIC[word] ?? word);
  }
  return words;
}

/** How much a word found only in the answer counts, against one found in the question. */
const CONTEXT_WEIGHT = 0.5;

interface Indexed {
  question: string;
  inQuestion: Set<string>;
  inContext: Set<string>;
}

/** Builds a matcher over the recordings. The returned function ranks them for a typed question. */
export function buildMatcher(recordings: readonly RecordedText[]) {
  const indexed: Indexed[] = recordings.map((item) => ({
    question: item.question,
    inQuestion: topicWords(item.question),
    inContext: topicWords(item.context),
  }));
  const seenIn = new Map<string, number>();
  for (const item of indexed) {
    for (const word of new Set([...item.inQuestion, ...item.inContext])) {
      seenIn.set(word, (seenIn.get(word) ?? 0) + 1);
    }
  }
  // A word in every recording tells the recordings apart least. One in none of
  // them counts as the rarest: a question about something nobody recorded should
  // score low, however many common words it shares.
  const weight = (word: string) => Math.log(1 + indexed.length / (seenIn.get(word) ?? 0.5));

  return function rank(typed: string): ClosestMatch[] {
    const words = [...topicWords(typed)];
    const total = words.reduce((sum, word) => sum + weight(word), 0);
    if (total === 0) {
      return [];
    }
    return indexed
      .map((item) => {
        let found = 0;
        for (const word of words) {
          if (item.inQuestion.has(word)) {
            found += weight(word);
          } else if (item.inContext.has(word)) {
            found += weight(word) * CONTEXT_WEIGHT;
          }
        }
        return { question: item.question, score: found / total };
      })
      .filter((match) => match.score > 0)
      .sort((first, second) => second.score - first.score);
  };
}
