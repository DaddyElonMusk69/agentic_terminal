# Whitepaper

## Agent Terminal In One Sentence

Agent Terminal is an agentic AI trader built around a simple claim:

> AI agents do not become reliable by being asked to do more.
> They become reliable when they are surrounded by structure, operating discipline, and the right context at the right time.

The analogy is the difference between a smart graduate and an industry veteran. Raw intelligence matters, but judgment under pressure comes from structure, pattern recognition, and experience encoded into the operating environment.

This repository is the implementation of that claim in a high-stakes domain where hallucination is expensive and execution gaps are immediately visible in live PnL.

## Performance Signal

This is not a demo benchmark project.

In live operation, the system has demonstrated a 30% to 50% monthly growth profile through intraday trading, with positions opened, managed, and closed by the agent itself inside a strict same-day operating window.

The specific production prompts and operating mappings are not fully published here, but the system design and tuning methodology are.

That result matters because it was not achieved by simply swapping in better models. It came from shaping when the model is allowed to think, what context it receives, and how its outputs are constrained before capital is deployed.

## The Problem

Raw models are impressive at local reasoning but cannot reliabily perform sustained, multi-step execution under noisy real-world conditions.

In trading, that weakness shows up as:

- action bias during ambiguous regimes
- inconsistent use of context across sessions
- poor memory of what opened a position and why
- brittle behavior when their framing stops matching the market
- silent failure modes between analysis, validation, and execution

A stronger base model helps, but it does not solve the coordination problem.

## The Core Thesis

Reliable autonomy is a systems problem, not just a model problem.

The useful unit is not:

`model -> answer`

It is:

`structured context -> controlled decision -> guarded execution -> observable telemetry -> agentic flywheel`

That loop is what this project implements in order to achieve consistent trading performance.

## The Tuning Process

The benchmark performance did not come from writing one prompt and getting lucky.

It came from meticulous iteration across three dimensions:

- event design: determining which market conditions deserve a model cycle and which are just noise
- context design: controlling exactly what charts, portfolio data, and quant features are shown for each event type
- instruction design: shaping the model's decision posture so it remains selective, adaptive, and coherent across changing market regimes

Those three layers interact. Changing event thresholds changes the quality of context. Changing context changes how much instruction is needed. Changing instruction quality changes whether the model overtrades, underreacts, or manages positions coherently.

This is why the project treats tuning as an engineering discipline rather than prompt tinkering.

## The Intelligence-Execution Gap

There is a large gap between:

- generating a plausible answer
- producing a safe, auditable, repeatable action in production

Crossing that gap requires proper scaffolding and deep domain-specific know-how:

- deterministic context assembly
- structured response formats
- parser validation
- trade guard rules
- circuit breakers
- session history
- prompt versioning
- rollback tooling
- live observability

Without that scaffolding, smarter models simply fail in more sophisticated ways.

## Why This Is Not A Generic MCP Or Skills Demo

The strategy behind this system is a custom trading approach that can work well in human hands, but is extremely difficult to reduce into:

- hard-coded scripts
- traditional rule bots
- plain chat-style LLM prompting

The failure mode is always the same: once the market regime shifts, rigid automation keeps behaving as if the prior regime still exists.

That is why this repository does not center itself around generic scheduled tasks or heartbeat-based agent loops.

Instead, it uses a custom state manager that emits semantic market events and only then allows the model cycle to run.

This design has three important consequences:

- the model is invoked when market structure changes, not just because time passed
- token spend stays lower because noise does not trigger full reasoning cycles
- decision quality is more stable because prompts are tied to specific event types rather than undifferentiated polling snapshots

Just as importantly, those events can be tuned. The event layer is not static infrastructure. It is part of the edge. The same is true for context selection and instruction design. Together, they form the control surface that the agentic flywheel keeps optimizing in the background.

Although this project predates the popularity of modern agent terms like `skills` and MCP, it independently arrived at adjacent architecture:

- instruction packs (Skill): prompt templates, field selections, skill workflows
- orchestration client (MCP Client): prompt builder, queue workers, LLM pipeline, runtime coordination
- execution servers/tools (MCP Server): exchanges, chart rendering, uploads, quant feeds, prompt-ops tooling


## System Shape

The live loop is:

1. Agent observe market structure, liquidity, and quant context
2. Let the state manager emit custom events only when state meaningfully changes
3. Build structured prompts with charts, portfolio context, and risk state
4. Call the sub-agent and parse a constrained execution idea
5. Validate through trade guard and circuit breaker
6. Execute via exchange connectors
7. Agent observe outcomes, analyze sessions, and update instruction maps safely through the agentic flywheel

This loop is intentionally modular because each stage fails differently.

## Why Prompt Ops Matters

One of the strongest lessons from the project is that prompt engineering and context tuning is curcial to how the agent as a whole performs.

That is why the system includes:

- versioned instruction prompt set
- event-specific prompt mapping
- session analysis scripts
- snapshot/apply/rollback tooling

Prompt changes are treated as production changes with blast radius, not as casual edits.

In practice, the flywheel continuously works on the same three levers that produced benchmark performance in the first place:

- refining the events that wake the model up
- refining the context that the model sees at each wake-up point
- refining the instructions that shape how the model interprets that context

## Why This Matters Beyond Trading

Trading is the proving ground.

The larger takeaway is applicable to any domain where a task requires an agent to:

- reason from messy context
- choose among competing actions
- call external tools
- maintain state across steps
- remain observable and recoverable when wrong

The lesson is consistent:

> agentic execution autonomy emerges from architecture, tuning, and model capability working together.

## Thoughts on the future of software

With the advancement of AI coding agents, softwares in the future won't be static and deterministic in nature, but dynamically evolving, self-healing and self-adaptable to the ever changing world, just like the agentic flywheel demonstrated in this project. Bugs are not bugs, they are the product of the nature of the world. Previously, human are in the loop to help software adapt. In the future, agents will be in the loop to help software adapt.