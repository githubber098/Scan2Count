# Food Scan App — Architecture & Execution Report

*Prepared for: Father-son building team*
*Stack focus: Python-first, web-responsive, AI-native, Indian food market*
*Document version: 1.0*

---

## A. Executive Summary

### Project Overview
You're building a mobile-responsive web app where users photograph meals and an LLM-powered pipeline estimates macros and micronutrients, tracking against personal goals. India-first market, with strong coverage of Indian foods. V1 is a web app accessible by URL; native iOS/Android apps are V2 (6+ months out).

The product's defensible value comes from three things: (1) accurate Indian food recognition and nutrient estimation, (2) a fast, low-friction logging experience on a phone browser, and (3) AI-driven personalized insights. Everything in this document optimizes for those three.

### Recommended Phased Timeline

| Phase | Duration | Goal | Definition of Done |
|---|---|---|---|
| **Phase 0: Setup** | Week 1 | Tools installed, "hello world" deployed, accounts created | A FastAPI app on Render at a public URL, both builders can push code |
| **Phase 1: MVP** | Weeks 2–5 | Core loop works end-to-end | A real user can sign up, photograph a meal, get macros logged, see today's totals on their phone |
| **Phase 2: V1** | Weeks 6–13 | Full feature set per spec | Micronutrients, conversational AI, history views, manual search, correction loop all working |
| **Phase 3: Polish** | Weeks 14–17 | Production-ready | First 5–10 real users using it daily without you holding their hand |

This is intentionally generous. At ~28 hrs/week combined, but realistically less, and with learning happening alongside building, plan for things to take 1.5x what they "should."

### Top 3 Risks

1. **Indian food estimation accuracy.** A photo of "rajma chawal with raita" is meaningless to nutrition without portion estimation and a regional food database. Pure LLM inference won't be accurate enough. **Mitigation:** hybrid pipeline — Claude identifies the dish and portion size, then we look up macros deterministically in the IFCT (Indian Food Composition Tables) database.
2. **LLM cost spiral.** Vision API calls run $0.01–0.03 each. At 3 meals/day × 100 users = ~$30–90/day. **Mitigation:** image compression before upload (70% cost cut), caching of repeat dishes, Haiku for non-vision tasks like the chat assistant.
3. **Learning curve compounding.** Two beginners learning web dev + databases + cloud + LLMs simultaneously will hit a wall around week 3–4. **Mitigation:** "buy the boring stuff, build the interesting stuff" — Supabase for auth/db/storage, Render for hosting, Tailwind for CSS. Reserve learning energy for the AI pipeline, not for bootstrapping infra.

### Top 3 Learning Milestones

1. **End of Week 1:** Both builders can deploy a code change. They've pushed to GitHub, watched it auto-deploy to Render, and seen it live on the web. This is the single highest-leverage skill in the whole project.
2. **End of Week 3:** A user can upload a photo and the Claude API returns a structured JSON estimate of nutrients. The bridge between "Python script" and "real product" is crossed.
3. **End of Week 8:** The team is comfortable enough with the codebase to add a feature without help — they can read a Stack Overflow answer, apply it, debug what breaks. This is when the project shifts from "building" to "iterating."

---

## B. Product Specification

### Core User Flows

**Flow 1: First-time signup and goal setup**
1. User lands on the URL on their phone, sees a clean landing screen with "Sign up" / "Log in"
2. Signs up with email + password (or Google, optional)
3. Onboarding: enters age, sex, weight, height, activity level, primary goal (lose weight / maintain / gain muscle)
4. App calculates suggested daily calorie + macro targets, user can adjust
5. Lands on home screen with empty "Today" view

**Flow 2: Logging a meal by photo (the hero flow)**
1. User taps "Log meal" on home screen
2. Camera opens (browser native), user takes photo or uploads from gallery
3. Loading state: "Analyzing your meal..." (typically 3–8 seconds)
4. AI returns structured guess: e.g., "Rajma chawal — about 1.5 cups, with 1 tbsp raita on the side. ~520 kcal, 18g protein, 78g carbs, 14g fat."
5. User sees breakdown with confidence indicator. Can edit portions, swap dish, or accept.
6. Logged. Today's totals update. Returns to home screen with updated rings/bars.

**Flow 3: Manual food search and log (fallback)**
1. User taps "Search food"
2. Types "idli" or scans barcode (V1.5 maybe — defer for now)
3. Sees list of matches from IFCT/USDA database
4. Selects, enters portion size
5. Logs. Same totals update.

**Flow 4: Daily review**
1. User opens the app any time during the day
2. Home screen shows: today's date, calorie ring (consumed / goal), macro bars (P/C/F/fiber)
3. Tap a meal entry → see the photo, AI's analysis, ability to delete or edit
4. Tap "History" → see week view with daily totals

**Flow 5: Ask the AI assistant**
1. User taps chat icon
2. Asks "How much protein do I have left today?" or "Suggest a high-protein dinner under 400 calories"
3. AI responds, pulling from user's logged data + goals

### MVP Feature List (Phase 1)

| Feature | Why it's in MVP |
|---|---|
| Email + password auth (Supabase) | Can't have personalized data without identity |
| Photo upload + Claude vision analysis | This is the core differentiator — must work end-to-end |
| Display estimated macros (cal, protein, carbs, fat, fiber) | Minimum viable nutrient tracking |
| Save meal log entries with photo + macros | Otherwise nothing persists |
| Daily totals view on home screen | The user's "did I hit my goals today" answer |
| Profile + daily goal targets | Personalization basis |
| Mobile-responsive layout | Most usage will be on phones |

### V1 Feature List (Phase 2)

| Feature | Notes |
|---|---|
| Manual food search with Indian food database | Backed by IFCT, fallback to USDA |
| Micronutrient tracking (Vit A, C, D, B12, iron, calcium, sodium — start with these 7) | Pulled from IFCT lookups |
| Conversational AI assistant | Claude Haiku endpoint, has access to user's recent logs |
| Weekly history + simple trends | Last 7 days at a glance |
| User correction loop | "That's not rajma, it's chole" — system stores correction, uses it to improve next analysis |
| Edit/delete meal entries | Standard CRUD |
| Better confidence scoring | Shows "high / medium / low confidence" badge per food |

### Deferred to V2

- Native iOS/Android apps
- Barcode scanning of packaged foods
- Social features (friends, sharing, leaderboards)
- Recipe builder
- Restaurant/menu integration
- Offline mode
- Health app integrations (Apple Health, Google Fit)
- Advanced analytics (correlations, ML-driven suggestions)
- Multi-language UI (Hindi, regional)
- Subscription/paywall

---

## C. Technical Architecture

### System Architecture (Text Diagram)

```
                         ┌──────────────────────────────┐
                         │   User's Phone Browser       │
                         │   (mobile-responsive web app)│
                         └──────────────┬───────────────┘
                                        │ HTTPS
                                        ▼
                         ┌──────────────────────────────┐
                         │   FastAPI App on Render      │
                         │  ┌────────────────────────┐  │
                         │  │  Routes (HTML + JSON)  │  │
                         │  ├────────────────────────┤  │
                         │  │  Service Layer         │  │
                         │  │  - food_analyzer       │  │
                         │  │  - nutrient_lookup     │  │
                         │  │  - logging_service     │  │
                         │  │  - chat_service        │  │
                         │  └─┬──────────┬───────┬───┘  │
                         └────┼──────────┼───────┼──────┘
                              │          │       │
                ┌─────────────┘          │       └──────────────┐
                ▼                        ▼                      ▼
       ┌────────────────┐     ┌────────────────────┐   ┌─────────────────┐
       │  Supabase      │     │  Claude API        │   │  IFCT + USDA    │
       │  - Postgres    │     │  - Vision (Sonnet) │   │  Food Database  │
       │  - Auth (JWT)  │     │  - Chat (Haiku)    │   │  (loaded into   │
       │  - Storage     │     └────────────────────┘   │   our Postgres) │
       │    (photos)    │                              └─────────────────┘
       └────────────────┘
```

**Request flow for "log a meal" (the hero path):**

1. Phone uploads compressed JPEG to FastAPI endpoint `/meals/analyze`
2. FastAPI compresses further if needed, uploads to Supabase Storage, gets a URL
3. FastAPI calls Claude Sonnet vision API with the photo + structured prompt
4. Claude returns JSON: `{ foods: [{ name, portion_grams, confidence }] }`
5. For each identified food, FastAPI looks up the actual nutrient values in our IFCT-loaded Postgres table
6. FastAPI returns the structured estimate to the phone, renders the confirmation screen
7. User confirms → FastAPI writes a `meal_log` row in Postgres with the photo URL, items, and final macros

### Recommended Technology Stack

| Layer | Recommendation | Why | Simpler Alternative Considered |
|---|---|---|---|
| **Frontend** | Jinja2 templates + HTMX + Alpine.js + Tailwind CSS | Stays in Python ecosystem; HTMX gives modern interactivity (partial page updates, no full reloads) without learning a JS framework; Tailwind makes responsive design tractable without a designer; Flowbite component library (free) for cards/modals/inputs | **Streamlit:** rejected — terrible mobile UX, hard to do real auth, doesn't teach transferable web skills. **Pure HTML + sprinkles of JS:** workable but you'd reinvent HTMX poorly. **Next.js/React:** too steep a learning curve to take on while also learning everything else; defer to V2 if needed. |
| **Backend** | FastAPI (Python 3.11+) | Modern Python, async-ready, automatic OpenAPI docs, great error messages, huge community, easy to learn for Python folks. JSON API design from day 1 means V2 native apps reuse the backend. | **Django:** more "batteries included" but heavier and the ORM has a steeper learning curve. **Flask:** fine but FastAPI is strictly more capable in 2026 with similar simplicity. |
| **Database** | Supabase Postgres | Real Postgres (transferable knowledge), generous free tier (500MB DB, 1GB storage), great UI for browsing data, built-in auth + storage | **Self-hosted Postgres on Render:** more learning but more ops burden. **SQLite:** fine for dev, awkward for production multi-user. **Firebase Firestore:** NoSQL, vendor lock-in, less SQL learning value. |
| **Authentication** | Supabase Auth (email/password + optional Google OAuth) | Production-grade out of the box, JWT tokens that work for web AND future mobile apps, password reset / email verification handled, free | **Roll your own with `passlib`:** bad idea for beginners; auth is full of subtle security pitfalls. **Auth0:** more expensive, overkill. **Clerk:** great but vendor lock-in and pricier. |
| **File storage (photos)** | Supabase Storage | Same auth context as DB, simple Python client, signed URLs for privacy, free tier covers MVP | **AWS S3:** more powerful but more complex IAM/policies to learn. **Local disk on Render:** ephemeral, won't survive deploys. |
| **Hosting** | Render (web service for FastAPI) | Free tier for development, $7/mo Starter for production (no cold starts), GitHub auto-deploy, easy environment variables, simple Python support | **Vercel:** best for Next.js, awkward for Python long-running APIs. **Railway:** comparable to Render, slightly more expensive. **AWS:** way too much to learn for V1. **Fly.io:** good but more ops-y. |
| **LLM API** | Anthropic Claude API — Sonnet for vision, Haiku for chat | Already familiar, best-in-class vision quality for food, structured JSON output via tool use, good Indian food cultural awareness | **OpenAI GPT-4o vision:** comparable, fine fallback. **Open-source vision models (LLaVA, etc.):** worse accuracy, ops burden of self-hosting, not worth it. |
| **Version control** | GitHub (free private repos) + GitHub Actions for CI | Industry standard, both will use this their whole career | None considered; this is a non-negotiable foundation |
| **Error tracking** | Sentry (free tier) | Catches production errors with full stack traces, beginner-friendly | **Just logs:** insufficient for a real app once users exist. Add Sentry in Phase 3. |

### API Design (Key Endpoints)

A clean JSON-first design — same backend serves the web app today and the native app in V2.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/auth/signup` | (Proxied to Supabase) |
| `POST` | `/api/auth/login` | (Proxied to Supabase) |
| `GET` | `/api/profile/me` | Get current user's profile + goals |
| `PUT` | `/api/profile/me` | Update profile / goals |
| `POST` | `/api/meals/analyze` | Upload photo, return AI estimate (does NOT save yet) |
| `POST` | `/api/meals` | Save a meal log entry (after user confirms) |
| `GET` | `/api/meals?date=YYYY-MM-DD` | List meals for a day |
| `GET` | `/api/meals/today/totals` | Aggregate totals for today |
| `PATCH` | `/api/meals/{id}` | Edit a meal entry |
| `DELETE` | `/api/meals/{id}` | Delete a meal |
| `GET` | `/api/foods/search?q=...` | Search food database |
| `POST` | `/api/chat/message` | Send a chat message, get AI response with context |

For the web app, parallel HTML routes (`/`, `/log`, `/history`, `/chat`) render Jinja templates that call into the same service layer.

### Data Models (Key Entities)

```
users (managed by Supabase Auth)
  - id (uuid)
  - email
  - created_at

profiles
  - user_id (uuid, FK → users.id)
  - name
  - dob
  - sex (M/F/other)
  - height_cm
  - weight_kg
  - activity_level (sedentary | light | moderate | active)
  - goal (lose | maintain | gain)
  - daily_calorie_target (int)
  - daily_protein_g, daily_carbs_g, daily_fat_g, daily_fiber_g (int)
  - micronutrient_targets (jsonb)
  - updated_at

foods (the food database — populated from IFCT + USDA)
  - id (serial)
  - name
  - aliases (text[])  -- for "rajma" / "kidney beans" / "राजमा"
  - source ('IFCT' | 'USDA' | 'user_submitted')
  - per_100g_calories (numeric)
  - per_100g_protein_g, _carbs_g, _fat_g, _fiber_g (numeric)
  - per_100g_micronutrients (jsonb)  -- {vit_a_iu: 120, iron_mg: 2.1, ...}
  - cuisine ('indian' | 'global')

meal_logs
  - id (uuid)
  - user_id (uuid, FK)
  - logged_at (timestamptz)
  - photo_url (text, nullable)
  - input_method ('photo' | 'manual' | 'chat')
  - raw_ai_response (jsonb, nullable)  -- store for debugging + future model improvement
  - total_calories, total_protein_g, total_carbs_g, total_fat_g, total_fiber_g (numeric)
  - total_micronutrients (jsonb)
  - notes (text, nullable)

meal_log_items (denormalized for quick queries; one row per food in a meal)
  - id (uuid)
  - meal_log_id (uuid, FK)
  - food_id (int, FK → foods.id, nullable if AI-only freeform)
  - food_name (text)  -- snapshot in case food row changes
  - portion_grams (numeric)
  - calories, protein_g, carbs_g, fat_g, fiber_g (numeric)
  - confidence ('high' | 'medium' | 'low')

corrections (user feedback loop)
  - id (uuid)
  - user_id (uuid)
  - meal_log_id (uuid)
  - original_ai_guess (jsonb)
  - user_correction (jsonb)
  - created_at
```

### Why this stack is good for beginners + scalable for V2

For beginners: Python everywhere except the HTML/Tailwind layer. Supabase eliminates the most error-prone parts (auth, database setup, file storage). FastAPI's automatic Swagger UI at `/docs` lets them test endpoints visually without Postman. Render auto-deploys from GitHub, so they see their changes live within 2 minutes of pushing.

For V2: The JSON API is the contract. When you build the iOS/Android apps in React Native or Swift/Kotlin, they call the exact same endpoints. Supabase Auth issues JWT tokens that mobile SDKs consume natively. Photos in Supabase Storage are accessible via signed URLs from any client. The web frontend (Jinja templates) becomes one of three clients, not the only one. Nothing structural needs to change — you'd add new routes if needed, never rewrite the foundation.

---

## D. AI/ML Pipeline

### Food Image Recognition Approach

The pipeline is **hybrid, not pure LLM**. This is critical for accuracy.

```
[Photo] → [Compress + Resize] → [Claude Sonnet Vision]
                                       │
                                       ▼
                               [Structured JSON output:
                                identified dishes + portion estimates
                                + confidence per item]
                                       │
                                       ▼
                          [For each dish, look up in foods table
                           (IFCT-first, USDA-fallback)]
                                       │
                                       ▼
                          [Calculate macros from per_100g × portion_g]
                                       │
                                       ▼
                          [Show user with confidence badges + edit affordances]
```

Why hybrid? Claude is excellent at "this is a plate of rajma chawal with cucumber raita" and reasonable at "the rice portion looks like ~150g cooked." Claude is *not* reliable at "the protein in this rajma is 12g" — that requires looking up actual food composition data, which databases do deterministically.

### Prompt Design Strategy

Use Claude's tool-use feature to force structured output. Example prompt structure:

```
System: You are a nutrition analysis assistant specializing in Indian cuisine.
You identify foods in photos and estimate portion sizes. You respond ONLY by
calling the `analyze_meal` tool with structured data.

For Indian dishes, use canonical names (rajma, dal makhani, idli, dosa, etc.)
and identify regional variations when visible.

For portion estimation, use visual cues: standard plate ~25cm, standard bowl
~300ml, hand size of typical adult, etc. Provide portions in grams.

Tool: analyze_meal(items: list[{
    name: string,
    cuisine: 'indian' | 'global',
    portion_grams: number,
    portion_description: string,  // e.g. "1 medium katori"
    confidence: 'high' | 'medium' | 'low',
    notes: string  // any caveats
}])
```

Iterate on this prompt with a test set of ~20 photos representing your real expected use (mixed Indian thali, single-dish, packaged snack, restaurant plate, etc.). Measure: does it identify the right foods? Are portions within ±30% of truth? Track this — it's your only real quality signal.

### Confidence Scoring + User Correction Loop

Surface confidence visibly:
- **High confidence:** small green dot, no friction
- **Medium:** yellow dot, "Looks like rajma chawal — tap to confirm or edit"
- **Low:** orange dot, "We're not sure — please tell us what this is"

Every correction the user makes is gold. Store in the `corrections` table. In V1.5+, periodically review corrections to:
1. Find systematic prompt failures (e.g., model keeps confusing chole and rajma)
2. Refine prompts
3. Eventually fine-tune or build few-shot examples from corrections

**Don't** auto-train a model on corrections in V1 — far too complex. Just collect data well, use it manually for prompt iteration.

### Indian Food Coverage Strategy

| Source | Coverage | License | Use |
|---|---|---|---|
| **IFCT 2017 (Indian Food Composition Tables)** | ~500 Indian foods with full nutrient profiles | Government of India publication, free for use | **Primary database for Indian foods.** Load into our `foods` table at deploy time. |
| **USDA FoodData Central** | ~400,000 global foods | Public domain | **Secondary** — for global/packaged items, restaurant chains |
| **Open Food Facts (India dataset)** | Crowdsourced packaged foods | ODbL license | Future: barcode scanning |
| **Claude inference** | Anything not in DBs | Pay-per-call | Fallback for unknown items; mark as low confidence and use generic per-100g values |

**Practical loading plan:**
1. IFCT is published as a PDF and Excel. Get the Excel version, write a one-time Python script to load it into Postgres (~2 hours of work).
2. USDA has a downloadable CSV/JSON dump. Load a curated subset (~5000 most-common foods) — full DB is too big and noisy.
3. Build a search endpoint that prefers IFCT matches when both DBs match a query.

For dishes IFCT doesn't cover (regional specialties, mixed restaurant dishes), Claude estimates from constituent ingredients. Mark these clearly in the UI as estimates.

### Cost Considerations

Per-user-per-day rough estimate for active V1 user:

| Activity | Cost |
|---|---|
| 3 photo analyses (Sonnet vision) @ ~$0.015 each | $0.045 |
| 5 chat messages (Haiku) @ ~$0.001 each | $0.005 |
| **Total per active user per day** | **~$0.05** |
| **100 active users for 30 days** | **~$150/month** |

Cost controls to implement from day 1:
- Compress images to ~800px wide JPEG before sending to API (cuts cost ~70%)
- Cache: hash the image after compression, if seen recently, return cached result
- Rate limit: max N photo analyses per user per day (e.g., 10) — prevents accidents and abuse
- Use Haiku, not Sonnet, for the chat assistant
- Set a hard monthly budget alert in Anthropic console

---

## E. Security & Data Handling

### Authentication Strategy

Use Supabase Auth. Specifically:
- Email + password with email verification turned on
- Optional: Google OAuth in V1 (one-click signup, lower friction)
- Password reset flow (provided out of the box)
- JWT tokens with reasonable expiry (1 hour access, 7 day refresh)
- Tokens validated on every API call via FastAPI dependency

Do not roll your own auth. Hashing passwords correctly, handling timing attacks, session management, password reset tokens — all of these have been gotten wrong in the wild repeatedly.

### Health Data Handling

This is health data. Treat it accordingly even though you're early-stage.

- **Encryption in transit:** HTTPS everywhere. Render and Supabase enforce this.
- **Encryption at rest:** Supabase handles this for the database and storage.
- **Row-level security (RLS):** Enable RLS on every Supabase table. A user can only `SELECT`/`UPDATE`/`DELETE` rows where `user_id = auth.uid()`. This is non-negotiable — it's the single most important security control.
- **No PII in logs:** Don't log full request bodies. Don't log photo URLs. Don't log emails in plaintext beyond what's necessary for debugging.
- **Photo retention policy:** Decide upfront. Suggested: keep photos for 90 days, then delete (compliance-friendly, cost-friendly). Can offer "save permanently" later as a feature.
- **Privacy policy + terms of service:** Even for 10 users, write basic ones. Templates exist (e.g., Termly free generator). Mention what data you collect, how it's used, that you use Claude API, retention policy.

### API Security

- All `/api/*` endpoints require valid JWT (FastAPI dependency)
- CORS restricted to your domain in production
- Rate limiting on expensive endpoints (`/meals/analyze` especially) — use `slowapi` library, ~30 calls/hour per user
- Input validation via Pydantic models on every endpoint
- File upload limits: 10MB max, image MIME types only

### Image Storage and Privacy

- Photos stored in Supabase Storage in a private bucket (`meal-photos/`)
- Object key includes user ID: `{user_id}/{meal_log_id}.jpg`
- Access via signed URLs with short expiry (15 min)
- Never log signed URLs

### Environment Variables and Secrets

Use a `.env` file locally (gitignored) and Render's environment variable UI in production. Required secrets:

```
SUPABASE_URL=...
SUPABASE_ANON_KEY=...           # public, safe to expose
SUPABASE_SERVICE_ROLE_KEY=...   # secret, server-only
ANTHROPIC_API_KEY=...
APP_SECRET_KEY=...              # for session signing
SENTRY_DSN=...                  # Phase 3
```

Use `python-dotenv` and `pydantic-settings` for clean config loading. Never commit `.env`. Add it to `.gitignore` on day 1.

---

## F. Realistic Execution Plan

### Phase 0 (Week 1): Foundation

**Both builders together. This is the highest-leverage week of the entire project.**

| Day | Task | Why |
|---|---|---|
| 1 | Install: Python 3.11, VS Code, Git, GitHub Desktop. Create GitHub repo. Both builders clone. | Tooling foundation |
| 2 | Create Supabase project (free), Anthropic API account, Render account. Save all keys in a password manager. | Service accounts |
| 3 | Write a "hello world" FastAPI app (~30 lines) that returns `{"status": "ok"}` at `/`. Run locally. | Smallest possible win |
| 4 | Push to GitHub, set up Render to auto-deploy from `main` branch. Verify the URL works on phone. | Deployment muscle memory |
| 5 | Add a `/health` endpoint that connects to Supabase and returns DB version. Push, verify on Render. | Prove end-to-end connectivity |
| 6–7 | Add Tailwind + Jinja2, render an HTML page that says "Hello, future food app." Make it responsive. | Frontend foothold |

**Definition of done for Phase 0:** Both builders have pushed code that ended up on the public URL. They can debug a deploy failure independently.

### Phase 1 (Weeks 2–5): MVP

**Week 2 — Auth + Profile**
- Wire Supabase Auth: signup, login, logout pages
- Create `profiles` table with RLS policies
- Onboarding flow: collect age/sex/weight/height/goal, calculate targets (use Mifflin-St Jeor formula)
- Profile page shows current targets

**Week 3 — Photo upload + Claude analysis (the core breakthrough week)**
- HTML form with `<input type="file" capture="camera">` for native camera access
- Upload photo to Supabase Storage, get URL
- Build `food_analyzer` service: takes photo URL, calls Claude vision with structured prompt, returns JSON
- Test extensively with real meals — this is where you'll iterate on the prompt

**Week 4 — Logging + Today's totals**
- Build IFCT loader script, populate `foods` table (one-time)
- Build `nutrient_lookup` service: given AI's identified foods, return real macros
- Confirmation screen: show estimate, let user edit/accept
- On accept: insert `meal_log` + `meal_log_items` rows
- Home screen: today's totals (calories ring, macro bars), list of today's meals with photos

**Week 5 — Mobile UX polish + first real test**
- Polish responsive layout, fix issues on iOS Safari and Android Chrome
- Loading states, error states, empty states
- Add Sentry for error tracking
- **Test with 1–2 real users (yourselves first, then a friend or family member)**
- Fix the biggest issues found

**Definition of done for Phase 1:** Either of you can use the app for an entire day on your phone, log every meal by photo, and see accurate-ish totals. The rough edges are known and tracked.

### Phase 2 (Weeks 6–13): V1 Features

| Weeks | Theme | Build |
|---|---|---|
| 6–7 | Manual food search | Search endpoint over `foods` table, search UI, log-by-search flow |
| 8 | Edit/delete meals | Standard CRUD UI for meal entries |
| 9–10 | Micronutrients | Extend prompt + lookups to return micronutrient data; UI to display them; targets in profile |
| 11–12 | Conversational AI | New `/chat` endpoint using Haiku; build context (user's profile + last 7 days of meals) per message; chat UI |
| 13 | History views + correction loop | Weekly view, simple charts (use Chart.js via CDN); UI flow for "this is wrong, here's what it actually was" |

### Phase 3 (Weeks 14–17): Polish

- Comprehensive error handling and user-friendly error messages
- Image compression pipeline (reduce upload size before send)
- Cost dashboards: track Claude API spend per user
- Onboarding refinement (it's almost certainly bad on first pass)
- Performance: page load times, lazy-load images, etc.
- Accessibility pass: alt text, keyboard nav, color contrast
- Real user beta: 5–10 friends/family using it for 2 weeks, weekly feedback calls
- Privacy policy, terms of service, contact email
- A simple landing page for non-logged-in users

### Critical Learning Curve Milestones

| Milestone | When | What it signals |
|---|---|---|
| First successful deploy | Week 1 | You can ship code |
| First DB query you wrote yourself | Week 2 | You understand data persistence |
| First Claude API call returning structured JSON | Week 3 | You can build AI features |
| First feature added without help | Week 6–8 | You're past the cliff |
| First real user logging meals daily | Week 5–6 | You have a product |
| First production bug report and fix | Anywhere from Week 5 onward | You're operating, not just building |

---

## G. Learning Roadmap

### What Both Builders Need to Learn (in order)

The principle: learn just-in-time, not just-in-case. Don't read a 600-page book on web development. Pick up each concept when the project demands it.

**Block 1: Web fundamentals (Week 1)**
- HTTP basics: requests, responses, methods, status codes
- HTML basics: tags, forms, attributes
- What "the cloud" actually is in concrete terms
- Resources:
  - [MDN Web Docs HTTP overview](https://developer.mozilla.org/en-US/docs/Web/HTTP/Overview) — 30 min read
  - [The Odin Project — HTML Foundations](https://www.theodinproject.com/paths/foundations/courses/foundations) — first chapter only

**Block 2: FastAPI (Weeks 1–3)**
- Routes, request/response, Pydantic models, dependencies
- Resources:
  - [FastAPI official tutorial](https://fastapi.tiangolo.com/tutorial/) — work through "First Steps" through "Body" sections
  - Skip async until Week 4+

**Block 3: Databases & SQL (Week 2)**
- Tables, columns, primary/foreign keys, basic SELECT/INSERT/UPDATE
- Resources:
  - [SQLBolt](https://sqlbolt.com/) — 1 evening
  - Supabase docs on RLS — read carefully, this is security-critical

**Block 4: HTML/CSS for the UI (Weeks 2–3)**
- Tailwind utility classes (don't write custom CSS)
- Forms, buttons, cards, mobile-responsive layouts
- Resources:
  - [Tailwind docs](https://tailwindcss.com/docs/installation) — skim, then reference as needed
  - [Flowbite component library](https://flowbite.com/) — copy-paste components

**Block 5: Claude API + prompt engineering (Week 3)**
- API basics, vision input, tool use for structured output
- Resources:
  - [Anthropic docs — Quickstart](https://docs.claude.com/en/docs/quickstart)
  - [Anthropic docs — Vision](https://docs.claude.com/en/docs/build-with-claude/vision)
  - [Anthropic docs — Tool use](https://docs.claude.com/en/docs/build-with-claude/tool-use/overview)

**Block 6: Authentication concepts (Week 2)**
- JWTs, what they contain, how Supabase issues them
- RLS policies in Postgres
- Resources:
  - [Supabase Auth docs](https://supabase.com/docs/guides/auth) — read the conceptual overview, then the FastAPI integration guide

**Block 7: Git & GitHub (Week 1, ongoing)**
- Commits, branches, pull requests, resolving conflicts
- Resources:
  - [GitHub's "Hello World" guide](https://docs.github.com/en/get-started/quickstart/hello-world)
  - GitHub Desktop for the visual learner; CLI for the deeper learner

**Block 8: HTMX (Week 3+)**
- Hypermedia-driven interactivity without JavaScript framework
- Resources:
  - [htmx.org docs](https://htmx.org/docs/) — short, well-written
  - [Hypermedia Systems book](https://hypermedia.systems/) — free online, deeper learning if interested

**Block 9: Async Python, deployment ops, testing (Phase 2+)**
- pytest basics, async/await when needed, Render's deployment model

### Where to Spend Time Learning vs Where to Use Libraries/Services

| Spend learning time on | Why |
|---|---|
| Python application architecture (services, routes, models) | This is the core skill |
| Prompt engineering with Claude | Unique value of your app |
| SQL and database modeling | Transferable forever |
| Mobile-responsive design (Tailwind) | Visible quality matters |
| Debugging production issues | The most important real-world skill |

| Use a service/library, don't reinvent | Why |
|---|---|
| Authentication (use Supabase) | Easy to get subtly wrong |
| Database hosting (use Supabase) | Operational burden |
| File storage (use Supabase) | Same |
| CSS framework (use Tailwind) | 10x productivity gain |
| UI components (use Flowbite) | Don't reinvent buttons |
| Deployment (use Render) | DevOps is its own field |
| Error tracking (use Sentry) | Building this is a distraction |

---

## H. Post-Launch Considerations

### Deployment and Updates

Once Render auto-deploy is set up (Week 1), the cycle is:
1. Make a change locally
2. Test it locally with `uvicorn main:app --reload`
3. Commit and push to GitHub
4. Render auto-deploys (~2 minutes)
5. Verify on the live URL

For more discipline as the app matures (Phase 2+):
- Use `main` branch for production, work on `feature/*` branches
- Open pull requests, even if you're solo (forces a moment of review)
- Add basic GitHub Actions: run linting (`ruff`) and tests (`pytest`) on every PR
- Promote tagged releases to production manually once tests are reliable

### Basic Monitoring and Analytics

| Tool | Purpose | When to add |
|---|---|---|
| Render dashboard | CPU, memory, response times | Built in, use from day 1 |
| Sentry (free) | Production error tracking | End of Phase 1 |
| Plausible or PostHog (free tier) | Privacy-friendly product analytics | Phase 3 |
| Simple `/admin/stats` endpoint | Daily active users, meals logged, API spend | Build a basic version in Phase 2 |

Track a few key metrics from the start:
- Daily active users
- Meals logged per user per day
- Photo analysis success rate (i.e., did the API call return parseable JSON?)
- Average AI confidence per meal
- Anthropic API spend

### User Feedback Loop (Since You'll Be the First Users)

The best feedback loop is using your own product daily. Beyond that:
- Keep a shared Notion or Google Doc called "App issues + ideas" — every time you hit friction, jot it down
- Once you have 3–5 real users, do weekly 15-minute calls with each
- Add a simple "Send feedback" link in the app footer that opens an email to you
- Post weekly progress updates somewhere (Twitter/X, Substack, Discord) — accountability + early audience

### Path to V2 (Native Apps)

When you decide to go native (6+ months from now), here's what carries over and what changes.

**Carries over (~80% of backend work):**
- Entire FastAPI backend
- All API endpoints
- Authentication (Supabase JWT works natively in iOS/Android SDKs)
- Database schema
- AI pipeline
- Food database
- Photo storage

**Rebuilt:**
- Frontend layer (Jinja templates → SwiftUI / Jetpack Compose, or React Native if you want one codebase)
- Camera integration (better with native APIs)
- Push notifications (new capability)
- Possibly: offline-first architecture for logging without internet

**Recommendation when V2 time comes:** Start with React Native if you want one codebase. The teenager will probably be very strong at JS/TS by then anyway, and it shares mental models with React. If quality matters more than dev speed, native Swift + Kotlin separately, but this is 2x the work.

The web app doesn't go away when native ships — it remains the desktop and "no-install" entry point. Many users will never install a native app.

---

## I. Questions for the Team

These are the decisions where I shouldn't assume — your input changes the recommendation.

1. **Domain name and branding.** Do you have a name for the app yet? Affects landing page, deploy URLs, branding. If not, decide before Week 1 (e.g., something like `nutriscan.in`, `thaalo.app`, etc.) so you can register it and configure DNS during Phase 0.

2. **Budget tolerance for V1.** I've assumed ~$10–25/month total infrastructure cost (Render Starter $7, Supabase free tier, Anthropic API ~$10–50/mo depending on usage). Is this acceptable, or should we stay on free tiers as long as possible (with the trade-off of Render cold starts hurting UX)?

3. **Indian food database licensing.** IFCT 2017 is the obvious choice but I want to flag: confirm the license terms allow your use case (commercial-friendly, attribution requirements). Worth a 30-minute read of the IFCT publication's preface and any redistribution clauses. If concerns arise, fallback is to license a curated commercial DB or use Open Food Facts entirely.

4. **Authentication scope: email-only or also Google OAuth?** Email-only is simpler for V1. Google OAuth lowers friction (one tap signup) but adds ~half a day of setup. Recommend email-only for MVP, add Google in Phase 3.

5. **Photo retention.** Default suggestion: 90 days then auto-delete. Do you want users to be able to opt into permanent retention? This affects DB design and storage costs.

6. **Languages.** Initially English-only? Or do you want Hindi or other language support from V1? Affects prompt design (Claude can return Hindi food names but UI translation is its own project).

7. **Manual portion entry units.** Indian users often think in units like "katori," "chapati," "spoon." Do we provide preset portion options ("1 katori dal," "1 medium chapati") with their gram equivalents, or just grams? Recommend: preset common Indian units → grams mapping in V1.

8. **Privacy and legal.** Are either of you comfortable writing a basic privacy policy and terms of service, or would you like a recommendation for a free generator/template? Need this before any real user signs up.

9. **Beta user pool.** Who are your first 5–10 real users? This shapes when Phase 3 ends. Family? Friends? An online community? Lining this up in Week 6–8 so they're ready to start using it after Phase 1.

10. **Adult co-builder's specific learning interests.** "Learning AI" is broad. Is the goal to understand how to use LLMs in products (this project does that), or to go deeper into ML/training/fine-tuning (this project doesn't)? If the latter, we should plan a separate side track — fine-tuning a small model on food data later in V1, for example.

---

## Appendix: Decisions Flagged for Tradeoffs

To reinforce the "no magical thinking" principle, here are decisions where I'm explicitly trading something off:

- **HTMX over React.** I'm trading off "modern frontend skills as resume material" for "much faster shipping with a beginner team." If the teenager has strong interest in becoming a JS/React developer specifically, this trade-off shifts. Talk about it.
- **Supabase over self-hosted Postgres.** Trading off "deep ops learning" for "ship in 3 weeks not 6." You can self-host later if interest arises.
- **Render over AWS.** Trading off "AWS skills (huge job-market value)" for "simplicity now." Move to AWS in V2 if there's reason to; until then, AWS is overkill.
- **Hybrid AI + database lookup over pure LLM.** Trading off "elegance / pure AI demo" for "actually-correct numbers." Non-negotiable for accuracy.
- **English-only V1.** Trading off "cultural authenticity / market fit" for "scope discipline." Add Hindi in Phase 3 or V1.5 if user feedback demands it.

---

*End of report.*
