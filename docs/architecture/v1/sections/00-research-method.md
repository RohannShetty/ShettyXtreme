# Section 0: RESEARCH METHOD

**How we evaluated the repos:**
- Deep-dived 7 reference repos via 3 parallel research sub-agents (OpenAlgo architecture, ShettyBot V1 intelligence, DhanHQ-py/OpenBB/Fincept/AST)
- Read ShettyBot V1's full architecture blueprint (66K chars), intelligence audit (54K chars), Markov investigation, and transition charter
- Cloned and studied both UI/UX skill repos (taste-skill, ui-ux-pro-max-skill)

**How we separated product ideas from implementation details:**
- For each repo, identified *what* it does well vs *how* it implements it
- Ideas/patterns/concepts = candidate for absorption; implementation specifics = evaluated case by case
- ShettyBot V1's monolithic code = extract concepts, not code

**How we distinguished reusable architecture from repo-specific noise:**
- Asked: "Does this pattern transfer to a standalone Python platform for Indian options?" If no = noise
- Fincept's C++20/Qt6 code = noise; their analytics breadth signal = signal
- OpenAlgo's Flask/React stack = noise; their broker adapter pattern = signal

**How we checked for blind spots:**
- Used Awesome Systematic Trading as a category checklist
- Compared our planned features against the catalog's categories
- Identified gaps: cost modeling, streaming TA, execution profiling, pre-trade risk gate

**How we avoided bias toward the current direction:**
- Started from first principles: "What does an Indian prosumer options trader actually need?"
- Questioned every prior decision: OpenAlgo dependency (wrong), Textual TUI (wrong), Markov voter (misleading), risk-neutral EV (noise)
- User directive to challenge everything was taken literally

---

