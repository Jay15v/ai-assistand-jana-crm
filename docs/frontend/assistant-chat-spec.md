# CRM Assistant chat: front-end spec

## What this is

Ability CRM has an AI assistant that tells an employee how to use the CRM screens ("How do I add a ticket?"). It answers only from the user manual and only about screens the employee's role can open. It is a separate service (FastAPI). This spec describes the chat widget that puts it inside the CRM front end.

## Decisions already made (do not change without asking)

- The widget is a floating button on every signed-in CRM page that opens a chat panel.
- The browser never calls the assistant service. It calls a server route in this Next.js app, and the route calls the assistant.
- The assistant service has no login check of its own. It trusts the `user_id` and `menu` it receives. So the server route must take both from the signed-in user's session and must ignore anything the browser sends for them.
- Users have no chat history. There is no list of old chats and a closed chat cannot be reopened.
- After a page refresh the current chat must look the same. The chat lives in the browser's `sessionStorage`, not on a server.
- Text answers only. No images, no links, no source list, no suggested questions.
- Nothing streams. One request, one reply, usually after several seconds.

## How one message travels

1. Browser → this app's server route: `{ session_id, message, ui_lang }`, with the user's login token as on any other call.
2. Server route → NestJS `get-role-privileges`, with that token → the user's menu JSON.
3. Server route → assistant service `POST /chat`: the browser's three fields plus `user_id`, `user_name` and that menu JSON, unchanged, as `menu`.
4. The assistant compares the menu item names (`result[].menuitems[].name`) with the CRM screens it knows. That is how it decides what this employee may ask about.
5. The reply goes back the same way.

The menu never comes from the browser and is fetched again for every message.

## The assistant service (upstream)

`POST {CRM_ASSISTANT_URL}/chat`, JSON in, JSON out.

Request:

```json
{
  "user_id": "1042",
  "session_id": "6f1c2c1e-8f0b-4f7e-9a53-2f6a3f0f5d11",
  "user_name": "Sara Ahmed",
  "message": "How do I add a ticket?",
  "ui_lang": "en",
  "menu": {
    "result": [
      {
        "menuName": "Tickets",
        "id": 7,
        "menuitems": [
          {
            "id": 31,
            "name": "Add Ticket",
            "href": "/tickets/add",
            "privileges": [{ "id": 34, "name": "Read", "status": 1 }]
          }
        ]
      }
    ],
    "success": true,
    "is_maintenance": false
  }
}
```

| Field | Rule |
|---|---|
| `user_id` | Required string. The signed-in employee's id, the same id the NestJS backend uses. |
| `session_id` | Required string. Made by the browser (a UUID), one per chat. |
| `user_name` | Optional. Display name, used only in admin tracing. |
| `message` | Required, 1 to 2000 characters after trimming. |
| `ui_lang` | Required, `"en"` or `"ar"`: the CRM language at the moment of sending. It sets the reply language. |
| `menu` | Required. The whole JSON the NestJS menu endpoint (get-role-privileges) returns for this user, unchanged. It decides what the user may ask about. Sent with every message. |

Reply (HTTP 200):

```json
{
  "session_id": "6f1c2c1e-8f0b-4f7e-9a53-2f6a3f0f5d11",
  "answer": "1. Open Tickets > Add Ticket.\n2. ...",
  "scope": "allowed"
}
```

`scope` is one of `allowed`, `partial`, `not_allowed`, `off_topic`, `error`.

How to treat the reply:

- Always show `answer`. For refusals, off-topic questions and most failures the service already returns a finished message in the right language with HTTP 200.
- `answer` is plain text with line breaks, usually numbered steps. It can contain `**bold**`. It never contains HTML that should be rendered.
- Use `scope` only to offer "Try again" when it is `error`. Do not use it to mark an answer as successful: in one failure case the service returns `allowed` together with its error text.
- Other statuses: `422` means the request was invalid. `5xx`, a timeout or a network error means the service is down.
- The service remembers earlier turns for the same `user_id` + `session_id`, so follow-up questions work. A new `session_id` is a new chat with no memory.

## The server route in this app

`POST /api/assistant/chat` (use this repo's own naming if it differs).

Browser sends:

```json
{ "session_id": "…", "message": "…", "ui_lang": "en" }
```

The route:

1. Rejects the call if nobody is signed in (401, the same way other protected routes in this app do).
2. Checks the body: `session_id` non-empty string, `message` 1 to 2000 characters after trimming, `ui_lang` is `en` or `ar`. Otherwise 400.
3. Gets `user_id`, `user_name` and `menu` for the signed-in user from the session / the NestJS backend, using the user's own token. Fetches the menu on every message so a permission change applies at once. Ignores any `user_id`, `user_name` or `menu` in the browser's body.
4. Sends the full request to `{CRM_ASSISTANT_URL}/chat`. `CRM_ASSISTANT_URL` is a server-only setting (never `NEXT_PUBLIC_`).
5. Gives up after 60 seconds.
6. Returns to the browser:
   - upstream 200 → 200 with `{ session_id, answer, scope }` unchanged;
   - upstream 422 → 400 `{ "error": "invalid_request" }`;
   - upstream 5xx, timeout, network error, or the menu could not be fetched → 502 `{ "error": "assistant_unavailable" }`.
   Never send the upstream URL, stack traces or upstream error text to the browser.

## The widget

- A round button fixed to the bottom corner on the inline-end side (right in English, left in Arabic), on every signed-in page. Not on the login page.
- It opens a panel anchored to the same corner: header (title, "New chat", close), message list, input. On small screens the panel fills the screen.
- The panel does not block the page. The employee can keep using the CRM screen behind it.
- The page layout follows the CRM language (RTL in Arabic). Each message bubble uses `dir="auto"`, because an employee can type English while the CRM is in Arabic.
- Render `answer` as text with line breaks kept, plus `**bold**` shown as bold. Never inject it as HTML.
- While waiting: show the user's message at once, a "writing" indicator, and keep the send button disabled. One request at a time.
- Input: multi-line, Enter sends, Shift+Enter makes a new line, 2000 character limit with a counter that appears near the limit.
- Failure (502, network error, or `scope: "error"`): show the message as an error bubble with "Try again", which resends the same text with the same `session_id`.
- 401: handle it the way the app handles an expired session everywhere else.
- "New chat": if the chat has messages, ask for confirmation, then make a new `session_id` and clear the messages. The old chat is gone for the user.
- Keyboard and screen readers: the button and the icon buttons have labels, focus moves to the input when the panel opens, Escape closes it and returns focus to the button, new answers are announced politely.

## Chat state in the browser

- `session_id`: `crypto.randomUUID()`, made when the first message of a chat is sent.
- Stored in `sessionStorage`: `session_id`, the messages, and whether the panel is open. Store it under a key that includes the user id, and clear it on logout, so a different employee signing in on the same tab never sees the previous chat.
- Read `sessionStorage` after the component mounts, not during server rendering.
- `ui_lang` is read at the moment of sending, from the CRM's current language.

## Texts

Add these to the app's translation files, in the way the app already does translations.

| Key | English | Arabic |
|---|---|---|
| title | CRM Assistant | مساعد النظام |
| open | Open CRM assistant | افتح مساعد النظام |
| close | Close | إغلاق |
| newChat | New chat | محادثة جديدة |
| newChatConfirm | Start a new chat? The current one can't be reopened. | تبدأ محادثة جديدة؟ المحادثة الحالية مش هتتفتح تاني. |
| welcome | I can help you with how to use the CRM screens. What would you like to do? | أقدر أساعدك في طريقة استخدام شاشات النظام. تحب تعمل إيه؟ |
| placeholder | Ask how to do something in the CRM… | اسأل عن طريقة عمل أي حاجة في النظام… |
| send | Send | إرسال |
| writing | Writing the answer… | جاري كتابة الرد… |
| unavailable | The CRM assistant is temporarily unavailable. Please try again in a few minutes. | المساعد غير متاح حاليًا. برجاء المحاولة مرة أخرى بعد قليل. |
| retry | Try again | حاول مرة أخرى |
| tooLong | Your message is too long (2000 characters maximum). | رسالتك طويلة جدًا (الحد الأقصى 2000 حرف). |

## Not part of this work

Chat history screens, streaming, file or image upload, voice, feedback buttons, showing sources, suggested questions, and any change to the assistant service.
