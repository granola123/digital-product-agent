# International Food Recipe — Master Taxonomy

## Why this exists

We're building one master-tagged recipe library instead of writing each product from scratch. Every future product (flagship or spin-off) is a **filtered slice** of this library plus its own packaging (cover design, intro copy, layout). This is what lets the pipeline scale to "5000+ recipes" in volume while each individual product still reads as curated, not dumped.

Every recipe entry gets tagged across five independent axes. A product = one or more filters combined across these axes.

## The five tag axes

### 1. Cuisine / Region (where it's from)
- East Asia: Korean, Japanese, Chinese, Taiwanese
- Southeast Asia: Thai, Vietnamese, Indonesian, Filipino, Malaysian
- South Asia: Indian, Pakistani, Sri Lankan
- Middle East: Lebanese, Turkish, Persian, Israeli
- Mediterranean/Europe: Italian, Greek, Spanish, French
- Northern/Eastern Europe: German, Polish, Scandinavian
- Americas: Mexican, Peruvian, Brazilian, Caribbean, American (Southern/Tex-Mex/Cajun)
- Africa: Moroccan, Ethiopian, West African

### 2. Meal Type (when/how it's eaten)
Breakfast, Appetizer/Starter, Soup, Salad, Main/Dinner, Side Dish, Dessert, Snack, Beverage/Drink, Sauce/Condiment

### 3. Occasion / Theme (why you'd make it)
Everyday, Christmas, Thanksgiving, Easter, Lunar New Year, Diwali, Ramadan/Eid, Halloween, Summer BBQ/Cookout, Potluck/Party, Date Night, Meal Prep

### 4. Dietary / Style (who it's for)
Vegan, Vegetarian, Gluten-Free, Dairy-Free, Keto/Low-Carb, Kid-Friendly, High-Protein

### 5. Difficulty / Time (how much effort)
Quick (<30 min), Beginner, Intermediate, Advanced / Weekend Project

## How products are derived from the library

| Product | Filter combination |
|---|---|
| **Flagship: International Food Recipe Collection** | All cuisines × all meal types (the full library, organized by region — this is the "5000+" positioning, framed as a comprehensive world atlas of food, not a bulk-count gimmick) |
| Single-cuisine pilot (e.g. Taste of Thailand) | Cuisine = Thai, Meal Type = Dinner, Occasion = Everyday |
| **World Dessert Recipe Book** | Meal Type = Dessert, across all cuisines |
| **International Holiday Recipe Book** | Occasion = {Christmas, Thanksgiving, Lunar New Year, Diwali, ...}, across all cuisines |
| 30-Minute World Dinners | Meal Type = Main/Dinner, Difficulty = Quick |
| Vegan World Kitchen | Dietary = Vegan, across all cuisines |
| World Breakfast Book | Meal Type = Breakfast, across all cuisines |
| Kids' World Recipes | Dietary = Kid-Friendly, Difficulty = Beginner |

New spin-offs are just new filter combinations — no new content pipeline needed, only new cover design + intro/packaging copy.

## Recipe entry schema (for the pipeline / database)

Each recipe record should carry at minimum:
```
title, cuisine, meal_type[], occasion[], dietary[], difficulty, prep_time, cook_time,
serves, ingredients[], steps[], nutrition{calories, protein, carb, fat}, photo_ref
```
Tags are arrays (not single values) since a recipe can belong to multiple meal types/occasions/diets at once (e.g. a Thai curry can be Dinner + Everyday + Gluten-Free).

## Roadmap decision (2026-07-22, revised same day)

Original plan below (Phase 1: ship Thai alone first, then add cuisines one at a time) was superseded same day: user judged a single-country product too thin to be competitively attractive at launch, and chose to launch with a **7-country bundle** instead of a sequential single-country rollout.

**Revised launch scope: 7 cuisines in the v1 bundle.**
Thai (already built) + **Mexican, Italian, Indian, Japanese, Korean, Greek/Mediterranean**. Same unit shape as Thai for each: 7-day dinner plan (8 dishes incl. one bonus dessert) + categorized grocery list + recipe cards with 1/2/3/4-serving scaling + design spec + Etsy listing copy. Country picks reasoning: Mexican/Italian/Indian/Japanese for Etsy/US name recognition + ordinary-grocery-store ingredient access; Korean added for the current global K-food demand wave; Greek/Mediterranean added to ride the "healthy Mediterranean diet" trend and give the bundle a European/health-positioned entry.

Content drafts for the 6 new cuisines were generated in parallel via subagents on 2026-07-22, mirroring the Thai draft's exact structure and tone (including its beginner/safety-conscious step-by-step style). Files land at `products/<cuisine>-meal-planner/draft-en.md`.

**First-pass technical review completed 2026-07-22 (by Claude, not a human):** Read all 6 drafts in full. Found and fixed 2 ingredient-table omissions in the Italian draft (bay leaf missing from the Bolognese table, bay leaf + dried thyme missing from the Osso Buco table — both were referenced in the steps but absent from the scaled ingredient table). Also normalized the stale "Phase 2 cuisine pack #N" / sequential-rollout language in each file's description line (leftover from the superseded single-country-first plan) to reflect the current 7-country simultaneous launch. No other structural or obvious accuracy issues found on this pass, but **this was not a substitute for human review** — quantities, spice levels, and cook times should still be sanity-checked by someone who actually cooks before anything ships, same scrutiny the Thai draft needs.

**What still has to happen before anything goes live (applies to all 7, not just Thai):**
1. Human review pass on all 7 drafts for recipe accuracy/authenticity (an agent wrote the 6 new ones — verify before trusting them the way the hand-refined Thai draft was) — **still outstanding, cannot be done by an agent.**
2. Original photography/illustration for all 7 — **done differently than planned:** the fal.ai AI-image plan discussed 2026-07-24 was never implemented; all 7 countries instead use real CC0/CC-BY/CC-BY-SA photos individually sourced (and visually verified) from Wikimedia Commons, with attribution in each `manifest.json`. This satisfies the original goal (real, licensed photos rather than generic stock/clipart) via a different, zero-cost method.
3. Visual mockups + Notion templates for the 6 new cuisines — **mockups done for all 7** (`preview.html` + `manifest.json` + `recipes.json` + `etsy-price-research.html` in every `products/<cuisine>-meal-planner/` folder, all published as Claude artifacts). **Notion templates done as of 2026-07-27** for all 6 non-Thai cuisines, mirroring Thai's structure (main page + 8 recipe sub-pages with 1/2/3/4-serving tables) via the `claude.ai Notion` MCP connector.
4. Etsy comparable-pricing research for the bundle as a whole — **worksheet built** (`products/bundle-etsy-price-research.html`, published artifact), but same as every per-cuisine log: it's an empty manual-entry sheet, because Etsy blocks scraping. **A human still has to log 5–10 real bundle comparables** before any bundle price is real rather than a hypothesis.
5. Decide bundle packaging: one Etsy listing with all 7, or 7 individual listings plus a bundle upsell. **Recommendation (2026-07-27, not yet a final decision):** ship both — 7 individual per-cuisine listings (preserves per-cuisine SEO surface like "korean meal planner printable", each already has its own listing copy/price log) **plus** one bundle listing that discounts against the sum, using this file's bundle worksheet. This is the standard Etsy multi-product-line pattern (individual entry points for search, bundle for higher-AOV buyers) and doesn't cost extra content work since all 7 units already exist standalone — it only adds one more listing wrapping them. Final call is the user's; this only unblocks it with real options instead of an open question.

**Phase 2 (next after launch): assemble/expand toward the full "International Food Recipe Collection" flagship** once the 7-country bundle has real market signal — this is still the point where broader volume framing becomes honest rather than a mill tactic, because the initial 7 will have been validated together.

**Phase 3: spin-offs (dessert book, holiday book, etc.) pull filtered subsets from the same tagged library**, per the table above. No new content pipeline needed at that point, only new packaging.

Taxonomy itself is still a draft — not yet wired into `world-cuisine-meal-planner-pipeline`'s scripts/templates. That wiring should happen once the 7-cuisine drafts are reviewed and stable.
