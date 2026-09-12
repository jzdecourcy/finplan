# {name} — household notes for Claude

This is a finplan household directory. The generic operator manual (ground rules,
guardrails, file conventions, commands) is injected by the **finplan plugin** at session
start, so it is not repeated here. If it did not appear, install the plugin once:

```
/plugin marketplace add jzdecourcy/finplan
/plugin install finplan@finplan
```

This file holds only what is specific to this household. Keep it short. Durable facts,
assumptions, decisions, and open questions go in `knowledge/`, with dates.

## Preferences

- (fill in during or after `/finplan:interview`; examples below, delete what does not apply)
- Retirement goal and how to frame it: e.g. "always show the both-stop-in-YEAR case".
- How results should be presented: e.g. levers priced in points of success probability.
- Who decides: entries in `knowledge/decisions.md` marked DECIDED (name) are household
  choices; everything else is the model's priced recommendation.

## House and other assets outside the engine

- Home value and mortgage balance are recorded, dated, in `knowledge/facts.md`; report net
  worth both as the engine's account total and as the total including home equity.
