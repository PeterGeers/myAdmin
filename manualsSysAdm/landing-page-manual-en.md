# Landing Page — User Manual

## Overview

The Landing Page feature allows you to create a public-facing website for your business directly from the myAdmin platform. Visitors can view your services, properties, company information, and contact you — all without needing a separate website or CMS.

Your landing page is accessible at: `https://[your-domain]/p/[your-slug]`

---

## Getting Started

### Step 1: Set Your Page Slug

The slug is the URL-friendly name for your landing page (e.g., `acme-rentals` becomes `/p/acme-rentals`).

1. Navigate to **Tenant Admin** → **Landing Page** in the sidebar
2. In the **Page Slug** field, enter your desired slug
3. Rules: lowercase letters, numbers, and hyphens only (min 3, max 60 characters)
4. Click **Save Slug** — the system confirms availability

> 📷 _[Screenshot: Slug configuration field with "Save Slug" button]_

---

### Step 2: Configure Branding

Set up your business identity so it appears on the landing page footer and social sharing cards.

1. Go to the **Branding** tab
2. Fill in:
   - **Company name** and **Tagline**
   - **Logo URL** (upload via Image Upload, or use an external URL)
   - **Primary color** and **Accent color** (hex codes, e.g., `#2D6A4F`)
   - **Contact details**: address, phone, email, KVK, BTW
3. Under **Social Media Links**, add your profile URLs (Instagram, Facebook, LinkedIn, etc.)
4. Toggle **Show share buttons** if you want visitors to easily share your page
5. Click **Save Branding**

> 📷 _[Screenshot: Branding settings panel with color pickers and social links]_

---

### Step 3: Add Content Blocks

Build your page by adding blocks — modular content sections you can arrange in any order.

1. Click **+ Add Block** in the editor toolbar
2. Choose a block type from the modal:

| Block Type     | Description                                 |
| -------------- | ------------------------------------------- |
| Hero           | Large banner with image, headline, and CTA  |
| About          | Text section with optional image (Markdown) |
| Gallery        | Image grid (upload multiple photos)         |
| Testimonials   | Customer reviews and quotes                 |
| FAQ            | Frequently asked questions (accordion)      |
| Pricing        | Rate table or pricing cards                 |
| Call to Action | Prominent CTA banner with button            |
| Embed          | External content via iframe (HTTPS only)    |
| Contact        | Contact form for visitor inquiries          |
| Properties     | Your STR property listings (live data)      |
| Services       | Your ZZP service listings (live data)       |

3. After adding, click the block in the list to open its **configurator panel**
4. Fill in the fields (title, content, images, URLs)
5. Choose a **layout variant** if available (e.g., "Image Right", "Centered")

> 📷 _[Screenshot: Block list with drag handles and Add Block button]_

---

### Step 4: Arrange Your Blocks

Reorder blocks using the **↑ / ↓** buttons on each block item, or drag and drop them into your preferred order.

- The order in the editor is the order on the published page
- Changes are auto-saved (you'll see "Saved ✓" in the toolbar)

---

### Step 5: Preview

Before publishing, check how your page will look:

1. Click the **Preview** button in the toolbar
2. The preview renders your current draft exactly as visitors will see it
3. Switch back to **Edit** mode to make changes

---

### Step 6: Configure SEO

Optimize how your page appears in search engines and social media shares.

1. Go to the **SEO** tab
2. Set your **SEO Title** (appears in browser tab and search results)
3. Write a **SEO Description** (shown under the title in Google results)
4. Upload a **Social Share Image** (recommended 1200×630px) — this shows when your link is shared on Facebook, LinkedIn, WhatsApp
5. Preview how your link will appear in the **Share Preview** card
6. Click **Save SEO Settings**

---

### Step 7: Publish

When you're happy with your page:

1. Click the green **Publish** button
2. Your page goes live at the public URL immediately
3. A version snapshot is saved (for future rollback if needed)

To take your page offline:

- Click **Unpublish** — the page returns a 404 for visitors

---

## Tips & Best Practices

- **Start with Hero + About** — these two blocks give visitors a strong first impression
- **Add a Contact block** at the bottom so visitors can reach you
- **Use high-quality images** — they're cached for 1 year for fast loading
- **Embed block requires HTTPS** — only `https://` URLs are accepted for security
- **Auto-save**: changes are saved automatically 2 seconds after you stop editing
- **Module data blocks** (Properties, Services): mark items as "public" in their respective admin pages first, then they appear on your landing page when you publish
- **Contact form submissions** are stored and a notification is sent to your configured email address

---

## Troubleshooting

| Issue                     | Solution                                            |
| ------------------------- | --------------------------------------------------- |
| Page shows 404            | Check if slug is set and page is published          |
| Embed block shows error   | Ensure URL starts with `https://`                   |
| No contact notifications  | Set an email in Branding → Contact Information      |
| Properties/Services empty | Mark items as "public" in their admin section first |
| Images not appearing      | Check upload succeeded (max 5MB, jpg/png/webp/svg)  |

---

_Last updated: 2025-01_
