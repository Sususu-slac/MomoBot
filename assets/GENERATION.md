# MomoBot kitten assets

Generated on 2026-10-29 with the built-in image_gen tool. Both images have transparent backgrounds. The sticker used the generated icon as its character reference. No API key or external QR service was used for these images.

## Project files

- assets/momobot-kitten.png — original generated icon artwork.
- assets/momobot-kitten.ico — Windows icon containing 16, 20, 24, 32, 40, 48, 64, 96, 128 and 256 px frames.
- assets/momobot-hi.png — original generated Hi! artwork.
- assets/momobot-hi-chat.png — 384 px desktop chat copy; displayed at 208 px and cached.
- assets/momobot-hi.webp — transparent 512 px Telegram sticker (204,634 bytes).

The original generated PNGs are copied without alteration. ICO export and resized delivery copies preserve alpha. Previous BL62_Assistant.ico is retained; application and shortcut references now use the kitten icon.

## Icon prompt (verbatim)

Use case: logo-brand. Asset type: a single square desktop application icon and mascot for a local assistant project. Primary request: a very cute tiny baby kitten (a milk kitten), rendered as an exceptionally polished friendly app icon. Subject: one small milk-white kitten with a huge round head, tiny triangular ears, round cheeks, large expressive glossy eyes, a tiny pink nose, a sweet gentle smile, and two tiny front paws tucked just below its cheeks. Style: simple soft rounded 3D illustration, restrained plush fur detail, clean bold silhouette, charming and calm. Composition: straight-on centered close-up face and little paws, one unified compact silhouette occupying about 82 percent of a square canvas, ample safe margin around the ears and paws, strong readability when reduced to 32x32 pixels. Backdrop: true transparent alpha background. No text or lettering, no watermark, no accessories, no extra objects, no enclosing badge, no scene or background, no cast shadow outside the kitten silhouette. Deliver one finished icon, not a grid or presentation sheet.

## Hi sticker prompt (verbatim)

Use case: identity-preserve. Asset type: one transparent chat greeting sticker. Use the supplied kitten image as the character identity reference: keep exactly this same adorable milk-white baby kitten, round face, blue glossy eyes, pink nose, pink inner ears, soft plush 3D illustration, rounded proportions and sweet expression. Create a new compact pose where this kitten is smiling and raising one tiny front paw in a friendly hello wave, pink paw pads visible, with the other paw tucked below the face. Add the exact text "Hi!" in big cheerful rounded lettering beside the raised paw, with a clear outline so the greeting reads on light or dark chat backgrounds. Keep the kitten and lettering as a single balanced compact sticker composition, centered on a square transparent alpha canvas with safe margins. No scene, no badge, no other characters or objects, no watermark. It must be crisp and readable at 180-220 pixels wide.

## Behavior and checks

Standalone greetings (Hi, Hello, Hey, Chinese greetings and punctuation variants) get an immediate local reply with the kitten Hi! sticker. Task requests containing greetings still go through the task controller. Stickers persist in conversation history. Telegram mirrors each new greeting sticker once and reuses its uploaded file_id for later greetings. Only the project sticker allowlist can select local sticker files.

Native Windows tests: 63 checks passed in 15.144 seconds, including icon resolutions/transparency, local greeting rendering and persistence, Telegram upload field, duplicate suppression and cached sticker reuse. Telegram transport checks use simulated API responses; no real message was sent by the tests.
