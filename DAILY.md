# Daily Reels run — instructions for Claude

You are making today's 3 Reels for **Groupe Caltech**, a Montréal agency that builds AI agents and automations for Quebec SMEs.
n8n posts them to Facebook + Instagram at 08:00, 12:30 and 18:00 (Montréal) from `queue.json`. Each video ends with "Commente AUDIT"; a separate n8n workflow DMs everyone who comments AUDIT. The goal is warm leads, not views.

## Steps
1. `DATE=$(TZ=America/Toronto date +%F)`. If `specs/$DATE/` already exists, stop: today is done.
2. Read `engine/state.json` (rotation + recent hooks) and `engine/example_spec.json` (a complete, approved Reel).
3. Write 3 specs: `specs/$DATE/1.json`, `2.json`, `3.json`, one per format below, following the rotation.
4. Check the look: `python3 engine/reel.py specs/$DATE/1.json --stills /tmp/st1` (same for 2 and 3) and look at every still with the Read tool. Fix any text that overflows the frame, overlaps, or is cut off (shorten the text; never shrink fonts below the defaults).
5. Update `engine/state.json` (advance `idx` by 3, append the 3 hooks to `recent_hooks`, keep the last 30).
6. `python3 engine/make_day.py $DATE` — renders, prunes old videos, updates `queue.json`, commits and pushes.
7. Report in 3 lines: the 3 hooks, their formats/industries, and that they were pushed.

## Audience and voice
- Owners of 5–50-person businesses anywhere in Quebec. Quebec French, tutoiement, short sentences, zero tech jargon.
- Show the automation working (lead captured, follow-up sent, invoice entered, booking made) — not abstract "AI is the future" talk.

## Honesty rules (non-negotiable)
- Never invent real clients, testimonials, results or statistics presented as real. Businesses in the videos are fictional and named plausibly (e.g. "Rénovations Boréal", "Clinique Saint-Laurent", "Transport Lavoie"). Numbers are examples ("par exemple", "jusqu'à"), never claims.
- No real brands, competitors, people or logos.
- Every caption ends with `🤖 Vidéo générée par IA — Groupe Caltech` (the video frame already shows "Contenu généré par IA").

## Formats (rotate; use `state.idx % 5` for the first, then the next two)
0. **regarde-comment** — hook → notif → chat → card → statement (follow-up) → cta. Like the example.
1. **sauve-du-temps** — hook ("Combien d'heures par semaine sur …?") → statement (the manual way, painful) → card (what the agent does: rows) → statement (time saved, as an example) → cta.
2. **cout-cache** — hook (a question about lost money) → statement (simple example math) → chat or card (how the agent fixes it) → cta.
3. **avant-apres** — hook → list (dark=false, "Avant", 3 items) → list (dark=true, "Après", 3 items) → cta.
4. **3-taches** — hook → list ("3 tâches à confier à un agent IA cette semaine", industry-specific) → statement → cta.

Industries (use `state.idx + n` mod 12): rénovation/construction, plomberie/CVC, électriciens, paysagement/déneigement, cabinets comptables, courtiers immobiliers, cliniques, restaurants/traiteurs, transport/logistique, manufacturiers, commerce de détail, gestion immobilière.
Regions (mod 17): Montréal, Laval, Montérégie, Capitale-Nationale, Laurentides, Lanaudière, Estrie, Mauricie, Outaouais, Chaudière-Appalaches, Centre-du-Québec, Saguenay–Lac-Saint-Jean, Bas-Saint-Laurent, Abitibi-Témiscamingue, Côte-Nord, Gaspésie–Îles-de-la-Madeleine, Nord-du-Québec. Mention the region once (hook kicker or caption).

## Spec reference (see `engine/example_spec.json`)
Top level: `{"id", "music": 0|1|2, "meta": {"hook","format","industry","region"}, "scenes": [...], "caption"}`.
Scene types:
- `hook`: `kicker`, `lines` (2–3 lines, ≤ 18 chars each), `accent_line` (index, italic cobalt), `sub`, `pill`, `dark` (default true)
- `notif`: `time`, `date`, `label`, `title`, `lines` (≤ 2), `caption`
- `chat`: `business`, `initials`, `badge`, `messages`: `{"side":"ai"|"client","text"}` or `{"side":"client","photos":3}` (4–6 messages)
- `card`: `kicker`, `intro`, `title`, `tag`, `rows` ([label, value], 4–6 rows, values ≤ 24 chars), `confirm` ([title, subtitle])
- `statement`: `kicker`, `lines` (≤ 3, ≤ 20 chars each), `accent_line`, `bubble` ({`label`,`text`}), `after`, `dark`
- `list`: `title`, `items` ([[title, detail]] × 3, titles ≤ 28 chars), `dark` (default false)
- `cta`: `lines` (2), `keyword` ("AUDIT"), `sub`, `free`
Keep each Reel 25–45 s. Use `music` 0/1/2 so the 3 videos sound different.

Caption: 2–3 short lines in Quebec French, then
`👉 Commente « AUDIT » et on t'envoie 3 tâches que ton entreprise peut automatiser. Gratuit.`, a blank line, the AI line, then 3–5 hashtags (e.g. #PMEQuébec #AgentIA #Automatisation + industry + region).
