# Landing Page

## Overview

The Landing Page feature lets you create a professional public webpage for your business. The page is hosted on a fast CDN (CloudFront) and accessible via a unique URL. Visitors can view your page without logging in.

## Setting up your slug

The slug is the unique part of your page URL (e.g., `my-company` → `https://d3afn46os9e9nc.cloudfront.net/my-company`).

1. Go to **Tenant Admin** → **Landing Page** tab
2. Enter a slug (lowercase letters, numbers, and hyphens only, minimum 3 characters)
3. Click **Save**

!!! note "Changing your slug"
You can change your slug after setting it. Re-publish afterwards to update the URL.

## Adding and editing blocks

Your page is built from blocks that you can add, remove, and reorder.

### Available block types

| Type         | Description                                                         |
| ------------ | ------------------------------------------------------------------- |
| Hero         | Main section with title, subtitle, image, and call-to-action button |
| About        | Text content with optional image                                    |
| Gallery      | Photo gallery                                                       |
| Testimonials | Customer reviews/quotes                                             |
| FAQ          | Frequently asked questions (accordion)                              |
| Pricing      | Rates/packages                                                      |
| CTA          | Call-to-action banner                                               |
| Embed        | External widget (iframe, e.g., booking calendar)                    |
| Contact      | Contact form                                                        |
| Services     | ZZP service listings (only with active ZZP module)                  |

### Managing blocks

1. Click **+ Add Block** to add a new block
2. Choose the type and a layout variant
3. Click a block to edit its settings (right panel)
4. Use the arrow buttons to reorder blocks
5. Use the trash icon to remove a block

Changes are saved automatically (auto-save).

## Uploading images

Upload images via drag-and-drop or click the upload area.

- **Allowed formats:** JPG, PNG, WebP, SVG
- **Maximum size:** 5 MB
- Images are stored in the cloud and instantly available via a fast URL

## Branding & social links

Go to the **Branding** tab to configure your business details:

- **Logo** — upload your company logo
- **Company name & tagline** — appears in the page header
- **Colors** — primary color and accent color for your page
- **Contact details** — address, phone, email, chamber of commerce, VAT number
- **Social media** — links to Instagram, Facebook, LinkedIn, Airbnb, Booking.com, YouTube, TikTok, X/Twitter
- **Share buttons** — toggle whether visitors can share your page

!!! tip "Don't forget to save"
Click the **Save** button at the top after changing branding details.

## SEO settings & OG image

Go to the **SEO** tab to control how your page appears in search results and when shared on social media:

- **SEO Title** — the title shown in Google and when sharing (max 60 characters)
- **SEO Description** — short description for search results (max 155 characters)
- **OG Image** — image shown when sharing on social media (recommended: 1200×630 pixels)

The OG preview card shows how your link will look when someone shares it.

## Publishing & unpublishing

### Publishing

1. Add at least one block
2. Click the green **Publish** button
3. Your page is immediately visible at your URL

Each publish creates a version snapshot so you can roll back if needed.

### Taking offline

Click **Unpublish** to take your page offline. Visitors will see a 404 page. Your draft is preserved.

## Contact form

If you've added a Contact block, visitors can send you messages.

- Messages are stored in the database
- You receive an email notification at the address configured in Branding
- **Spam protection:** maximum 5 messages per email address per hour
- **Bot protection:** honeypot field (invisible to real visitors)

## Share buttons

When enabled (via Branding → Share buttons), visitors see buttons to share your page via:

- Facebook
- X/Twitter
- WhatsApp
- LinkedIn
- Email

No external scripts are loaded — only standard share URLs.
