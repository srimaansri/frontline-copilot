# Interface design: three directions and the choice

The first version of the web interface worked and looked like a default: one accent on grey, a common typeface, a stock icon library, the same rounded card everywhere. Nothing in it came from the product. So the look was redone as a design exercise: three directions, each mocked on the same screens with the same real content, then judged.

The mock-ups are static HTML in [mockups](mockups). Open one in a browser; each has a light and dark switch.

| Direction | Starting idea | File |
|---|---|---|
| A. Signal and Script | The agent's call script marked with a highlighter, signal bars, the SIM card's cut corner | [a-signal-script.html](mockups/a-signal-script.html) |
| B. Switchboard | The telephone exchange: a hand-off is a call patched to a person, so the steps are a routed line | [b-switchboard.html](mockups/b-switchboard.html) |
| C. Northline Atlas | The coverage map: a legend for status symbols, the steps as a route with waypoints | [c-northline-atlas.html](mockups/c-northline-atlas.html) |

Every direction had the same rules: ground each choice in the subject, no icon library, no default typefaces, status colours separate from the brand colour, both themes designed, one bold element with the rest quiet, and every device must mean something true.

## What the interface has to do

A support agent types a customer's question and reads the answer aloud, often to an older customer. So the job of the screen, in order:

1. Make the facts to read out impossible to miss.
2. Show that personal details were removed.
3. Show when a request went to a person, and who has it.
4. Let the agent check the copilot's work: its sources and its steps.

## Critique

### A. Signal and Script

- **First impression.** The eye goes to the highlighter marks on the price and the phone numbers. That is the right place: they are what the agent says out loud.
- **Usability.** The strongest of the three. Answers and transcripts read easily at 18px; the calls list shows counts per outcome.
- **Rules.** Each device means one thing. Highlighter: say this out loud. Black bar: a personal detail was here and was removed. Cut corner: the copilot wrote this. Ink fill: you are here. Cobalt: you can press this. Each status has its own shape as well as its own colour and word.
- **Weak points.** The empty screen is plain. The steps are a conventional checklist. The icons are tidy but not memorable, and the mark is not the robot the project owner asked for.

### B. Switchboard

- **First impression.** The red-orange line. On a hand-off that is a strength: the route visibly branches to a tag naming the team and the ticket.
- **Best idea of the three.** The branching route. It answers "where did this request go?" without a word.
- **Icons.** The most original set: any line that ends on something you can connect to ends in a ring.
- **Weak points.** The brand colour sits close to its own "blocked" red, so a hand-off can read as an error. Many small capital labels slow reading. The answer text gets less emphasis than the wiring around it. The transcript drawn as a ladder gives each message a narrow column. The dark theme is close to the "black with one bright colour" look.

### C. Northline Atlas

- **First impression.** Calm and bookish: pale paper, italic serif titles, a magenta route.
- **Good ideas.** A solid leg for work the copilot did and a dashed leg for what passed to a person. A legend that keys the status shapes and stays on screen.
- **Weak points.** Italic serif titles on pale paper lean toward an editorial look this tool does not need. Magenta on a wireless carrier brings a real brand to mind. The conversation side is plain, and the labels "Q 01" and "A 01" add chrome without helping the agent. It reads more like a document than a tool.

## Decision

**Signal and Script is the base.** It serves the first two jobs of the screen better than the others: the facts to read out are highlighted, and removed details are unmistakable. Its rules are the clearest, and its brand colour does not collide with any status.

Two ideas from the others are grafted in, because they serve jobs three and four better than A's checklist does:

- **From Switchboard:** the steps are drawn as a route, and a hand-off branches to a tag that names the ticket. Drawn in A's ink and line colours, not red, so it cannot read as an error.
- **From Northline Atlas:** a solid leg for what the copilot did, a dashed leg for what passed to a person, and a small legend for the status shapes.

Two fixes to A itself:

- The mark becomes a robot whose head is the SIM shape with a signal antenna.
- The empty screen gains one true element: the four signal bars labelled with the four stages every request passes.

The highlighter stays the single bold element. The route is structure, not decoration.

The resulting system is documented in [web/DESIGN.md](../web/DESIGN.md).
