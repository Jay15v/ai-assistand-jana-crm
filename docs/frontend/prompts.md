# CRM Assistant chat: prompts for the front-end repo

These prompts are for an AI coding agent (Claude Code or similar) working inside the CRM's Next.js front-end repo.

How to use them:

1. Copy `assistant-chat-spec.md` (next to this file) into the front-end repo as `docs/assistant-chat-spec.md`. Every prompt reads it.
2. Run the prompts in order, one at a time. Read the report at the end of each before starting the next.
3. Prompt 0 changes no code. If its report says server routes cannot run in that app, stop: the forwarding then has to be a NestJS endpoint.
4. Run Prompt 5 in a new session, so the reviewer is not the author.

## Prompt 0: study the repo (no code changes)

````text
I'm going to add a chat widget for our CRM's AI assistant to this Next.js app. Before any code is written I need you to learn how this app is built, because everything we add must look and work like the rest of it.

Read docs/assistant-chat-spec.md first. It describes what we are building and the decisions that are already made.

Then explore this repo and report back. Do not change any file in this step.

What I need to know:

1. Basics: Next.js version, App Router or Pages Router, TypeScript or JavaScript, package manager, and the commands for dev, build, lint, type check and tests.
2. Does the app run a Node server in production, or is it a static export (check next.config and the deploy setup)? The plan needs a server route, so if server routes can't run here, say so clearly at the top of your report.
3. Sign-in: where the user's token is kept (httpOnly cookie, readable cookie, localStorage, an auth library), how existing code attaches it to calls to the NestJS backend, and what the app does when a session expires.
4. The current user: where the signed-in employee's id and display name come from.
5. The menu: where the app calls the NestJS endpoint that returns the user's menu and privileges (it may be called get-role-privileges), what the response looks like, and where it is kept.
6. Existing server-side code: any route handlers, API routes, server actions or middleware. Show me one typical example I should copy the style from.
7. UI: the component library and styling approach, where shared components live, how dialogs, drawers and icon buttons are done, the z-index layers used by the sidebar, header, modals and toasts.
8. Language: how English and Arabic are switched, where the current language can be read on the client, where translation texts live, and how right-to-left layout is applied.
9. Layout: the layout component that wraps every signed-in page (where a widget shown on every page would be mounted), and how the login page is kept apart from it.
10. Conventions: folder structure for a feature, data fetching (fetch, axios, React Query, SWR…), how environment variables are defined and documented, and what tests exist and with which tools.

Then give me:
- a short plan for where each piece would go in this repo (server route, API helper, state hook, components, texts), using this repo's own naming;
- how the server route can get the user's id, name and menu without trusting the browser, given what you found in points 3 to 5;
- anything in the spec that does not fit this app, and any question I have to take to the backend team.

Mark anything you could not confirm from the code as unconfirmed instead of guessing.
````

## Prompt 1: the server route

````text
We are adding the CRM assistant chat to this app. Read docs/assistant-chat-spec.md, mainly the sections "The assistant service" and "The server route in this app". Build only the server route in this step. No UI yet.

Why this route exists: the assistant service has no login check and believes whatever user_id and menu it receives. The menu decides which CRM screens a person may ask about. If the browser could send those two values, any employee could pretend to be another one or claim a bigger menu. So this route is the place where identity is decided, on the server.

What to build:
- The route described in the spec, written the way existing server-side code in this repo is written (same folder convention, same helpers, same error style).
- It takes user_id, user_name and menu from the signed-in user's session. The menu is the response of the NestJS get-role-privileges endpoint: call it from the server with the user's own token on every message, reusing the app's existing code for that call if there is any, and pass the whole JSON on unchanged (do not filter, rename or translate it; the assistant matches on the menu item names). If the token is not in a cookie the server can read, let the browser send it in the same header it already uses for the NestJS backend, and have the route use that token for its NestJS calls. A user id taken from a token counts only after NestJS has accepted that same token.
- Whatever the browser's body contains for user_id, user_name or menu is ignored.
- The assistant's address comes from a server-only setting, CRM_ASSISTANT_URL. Add it wherever this repo documents its settings (for example the example env file) with a local default of http://127.0.0.1:8000. It must never reach browser code.
- A 60 second limit on the upstream call, and the status mapping from the spec. If this app's hosting limits how long a server route may run, set that limit for this route too.

If you cannot get the user's id or menu on the server without trusting the browser, stop and tell me what is missing. Do not fall back to reading them from the request body.

Add tests in the style this repo already uses, with the assistant and NestJS calls replaced by fakes: a normal reply passes through unchanged, not signed in, invalid body, upstream 422, upstream 500, upstream timeout, and a body that carries a fake user_id and menu (the upstream request must contain the real ones). If the repo has no tests at all, do not add a test framework; give me the exact commands to try each case by hand instead.

Do not add new packages without asking me first. Do not commit.

When you finish, tell me which files you added or changed, how you checked each case and what the result was, and anything you were unsure about.
````

## Prompt 2: chat state and the call to the route

````text
Next step of the CRM assistant chat. Read docs/assistant-chat-spec.md, mainly "Chat state in the browser" and "The widget". The server route from the previous step exists; look at it so you call it correctly. In this step build the logic only, no visible UI.

What to build, following this repo's conventions for data fetching, hooks and state:

1. A small client function that calls the route with { session_id, message, ui_lang } and returns either the reply or one of two failures: "signed out" (401) or "unavailable" (anything else that is not a 200, plus network errors).

2. A hook (or the equivalent in this repo's state approach) that the widget will use. It holds the list of messages, whether a reply is pending, and whether the panel is open, and it offers: send a message, retry a failed message, start a new chat, open and close the panel.

Behaviour that matters:
- The user's message appears in the list immediately, before the reply arrives.
- Only one request at a time. Sending is refused while a reply is pending.
- A reply with scope "error", or an "unavailable" failure, becomes an error message that can be retried. Retrying sends the same text again with the same session_id. This is safe: the assistant only remembers turns it actually answered.
- "Signed out" is handled the way this app already handles an expired session.
- ui_lang is read from the app's current language at the moment of sending, not when the chat was opened.
- session_id is created with crypto.randomUUID() when the first message of a chat is sent. Starting a new chat throws away the id and the messages.
- The chat survives a page refresh through sessionStorage, exactly as the spec says: keyed by user id, cleared on logout, read only after mount so server rendering and hydration are not affected. If storage is unavailable or its content is broken, start with an empty chat instead of failing.
- If the page was refreshed while a reply was pending, that message is restored as a failed message that can be retried.

Why sessionStorage and not a server: the product decision is that employees have no chat history. A chat lives as long as the browser tab, and a new tab is a new chat.

Add tests in this repo's style for: send and receive, the pending lock, error then retry, new chat, restore after refresh, a different user on the same tab not seeing the earlier chat. If the repo has no tests, describe how you checked each one.

No new packages without asking. Do not commit. Finish with the files changed, how you verified, and open questions.
````

## Prompt 3: the widget

````text
Now the visible part of the CRM assistant chat. Read docs/assistant-chat-spec.md, mainly "The widget" and "Texts". The server route and the chat state hook already exist; read them first and build on them.

Build the floating button and the chat panel, and show them on every signed-in page.

It has to feel like a part of this CRM, not like something added from outside. Use this repo's component library, colors, spacing, fonts, icons and its existing patterns for icon buttons, dialogs and confirmation prompts. Do not bring in a chat UI package or new styling tools.

The people using it are operations employees in the middle of a task on a CRM screen. They open the chat, read numbered steps, and follow them on the page behind it. So:
- the panel must not block or dim the page, and must stay out of the way of the sidebar and header;
- the steps must be easy to read: comfortable line height, line breaks kept, **bold** shown as bold;
- the newest message is scrolled into view when it arrives, but do not pull the view down if the employee has scrolled up to reread something;
- while waiting for a reply, which takes several seconds, it is obvious that something is happening.

Details that are easy to get wrong:
- Arabic: the button and panel sit on the opposite side, and every bubble uses dir="auto" so mixed English and Arabic reads correctly. Use logical CSS (inline-start / inline-end) or this repo's RTL approach instead of left and right.
- The answer is text from a server. Render it as text. Do not use dangerouslySetInnerHTML or any HTML injection, even for the bold parts.
- Layering: above page content, the sidebar and the header; below the app's modals and toasts. Use the layers this app already defines.
- Small screens: the panel fills the screen and the input stays visible above the on-screen keyboard.
- Keyboard and screen readers, as listed in the spec.
- The login page and any other signed-out page must not show the button.
- Add all the texts from the spec's table to the translation files, English and Arabic, using this app's translation approach. No hard-coded strings in components.

Mount the widget once, in the layout that wraps signed-in pages, so it keeps its state when the employee moves between pages.

Then run the app and check it in a browser yourself, in English and in Arabic, wide and narrow: open and close, send a question, the waiting state, an error with retry (stop the assistant service or point CRM_ASSISTANT_URL at a dead address), new chat with its confirmation, refresh keeps the chat, moving between pages keeps the chat. If you cannot run a browser here, say so and give me a checklist to run by hand; do not report it as checked.

No new packages without asking. Do not commit. Finish with the files changed, what you checked and what you saw, and anything that still looks rough.
````

## Prompt 4: tests and project checks

````text
The CRM assistant chat is built: a server route, a chat state hook, and the widget. docs/assistant-chat-spec.md describes the intended behaviour. This step is to make sure it holds up.

1. Run this repo's lint, type check, tests and production build. Fix anything our new code causes. If something unrelated was already failing before our changes, leave it and list it for me.

2. Fill gaps in the tests, in this repo's existing style and tools, where they exist:
   - widget: opens and closes; sending shows the message and the waiting state; an answer renders with line breaks and bold; an answer containing HTML tags is shown as text and not rendered; error bubble and retry; new chat confirmation; Arabic layout direction; not shown when signed out.
   - make sure the route and hook cases from the earlier steps are still covered.
   If the repo has no test setup, do not add one. Write the manual checklist instead.

3. Check these by reading the built output or the code, and tell me the result of each:
   - CRM_ASSISTANT_URL does not appear in any browser bundle.
   - No request from the browser contains user_id or menu.
   - The widget's code is not loaded on the login page.
   - How much the widget adds to the shared bundle. If it is large, load the panel only when it is first opened.

Tests are there to prove the behaviour in the spec. If a test fails because the code is wrong, fix the code, not the test.

Do not commit. Finish with the commands you ran and their results, what you fixed, and what remains.
````

## Prompt 5: independent review (run in a new session)

````text
Please review a feature that was just added to this Next.js app: a chat widget for the CRM's AI assistant. The intended behaviour is in docs/assistant-chat-spec.md. Look at the uncommitted changes (and recent commits, if it was committed) to find the code.

Review it; do not change anything yet. I want problems that would matter in production, most serious first, each with the file and line and a concrete way it goes wrong.

Look hardest at:
- Identity. The assistant service believes the user_id and menu it receives, so the server route is the only guard. Can a signed-in user make the route send someone else's id or a menu they don't have? Can a signed-out caller reach the assistant? Is a token ever trusted before the backend has accepted it?
- Leaks. Does the assistant's address, an upstream error message, or a stack trace reach the browser? Is the chat of one employee visible to the next person who signs in on the same browser tab?
- Rendering. Is the answer text ever injected as HTML?
- Behaviour against the spec: one request at a time, retry keeps the same session_id, new chat makes a new one, refresh keeps the chat, the language is read at send time.
- Arabic and right-to-left layout, keyboard use and screen reader labels.
- Fit with the repo: does it follow the conventions of the code around it, and did it add packages or patterns the repo did not have?

Also tell me what you checked and found fine, so I know what was covered. If something in the spec itself looks wrong, say that too.
````
