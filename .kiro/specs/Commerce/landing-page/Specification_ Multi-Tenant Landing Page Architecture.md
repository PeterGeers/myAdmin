# Specification: Multi-Tenant Landing Page Architecture

## 1. Purpose

This specification describes the architecture for providing tenant-specific public landing pages within a multi-tenant SaaS platform.

The solution must support:

- Multiple tenants using the same SaaS platform.
- Each tenant having its own public landing page.
- Public visitors without authentication.
- Secure tenant isolation.
- Dynamic content management.
- Fast delivery through CDN caching.
- Future support for custom domains and branding.

---

# 2. Functional Requirements

## 2.1 Public Landing Page

A visitor must be able to access a tenant landing page through:

Option A: Tenant subdomain

```
https://tenant-name.platform.com
```

Option B: Custom domain

```
https://www.tenant-domain.com
```

The system must automatically determine the tenant from the requested domain.

The visitor must not provide a tenant ID manually.

---

## 2.2 Tenant Resolution

Tenant identification is based on the HTTP host header.

Example:

```
Request:
https://hockeyclub-a.platform.com

Host:
hockeyclub-a.platform.com
```

The system resolves:

```
hockeyclub-a
        |
        ▼
TENANT#hockeyclub-a
```

The tenant identifier is controlled by the platform and cannot be manipulated by the visitor.

---

# 3. High Level Architecture

```
                 Visitor
                    |
                    |
             Tenant Domain
                    |
                    ▼
              CloudFront
                    |
                    ▼
              React SPA
                    |
                    ▼
           Tenant Resolver API
                    |
                    ▼
                Lambda
                    |
        +-----------+-----------+
        |                       |
        ▼                       ▼
   DynamoDB                S3 Published
   CMS Data                Landing JSON
```

---

# 4. Data Storage Strategy

## 4.1 DynamoDB

DynamoDB is the source of truth for:

- Landing page content
- Draft versions
- Publishing status
- Tenant configuration
- Branding
- Page structure

Example item:

```json
{
  "PK": "TENANT#hockeyclub-a",
  "SK": "LANDING#HOME",

  "status": "PUBLISHED",
  "version": 5,

  "sections": [
    {
      "type": "hero",
      "properties": {
        "title": "Welcome to Hockeyclub A",
        "subtitle": "Join our club"
      }
    },
    {
      "type": "cta",
      "properties": {
        "buttonText": "Become a member",
        "url": "/register"
      }
    }
  ]
}
```

---

# 5. Published Content Model

Published pages are exported to S3.

Example:

```
s3://platform-public-pages/

    tenant-a/
        home.json

    tenant-b/
        home.json
```

The public website reads only published content.

Example:

```
GET
https://cdn.platform.com/tenant-a/home.json
```

Advantages:

- Fast response time.
- Low AWS cost.
- CloudFront caching.
- DynamoDB remains protected.

---

# 6. Content Component Model

Landing pages are built from reusable components.

Supported component types:

```
hero
text
image
video
features
faq
cta
contact-form
reviews
map
```

Example:

```json
{
  "type": "hero",
  "properties": {
    "title": "Welcome",
    "image": "hero.jpg"
  }
}
```

React maps component types:

```
hero
 |
 ▼
HeroComponent

cta
 |
 ▼
CTAComponent
```

---

# 7. Responsive Design

Responsive behaviour is handled by React components.

The database stores content and limited layout information.

Example:

```json
{
  "type": "hero",
  "layout": "image-right"
}
```

The component handles:

Desktop:

```
+--------------+--------------+
| Text         | Image        |
+--------------+--------------+
```

Mobile:

```
+--------------+
| Image        |
+--------------+
| Text         |
+--------------+
```

No separate mobile content is required.

---

# 8. Security Model

## 8.1 Public Access

Public visitors:

Allowed:

```
Read published landing page
```

Not allowed:

```
Read DynamoDB
Modify content
Access other tenants
```

---

## 8.2 Tenant Isolation

Tenant identity must come from:

- Domain name
- Cognito identity
- Backend mapping

Never from:

```
?tenantId=12345
```

Example:

```
Request:
tenant-a.platform.com

Backend resolves:

TENANT#tenant-a
```

---

# 9. Publishing Workflow

```
Tenant Admin
      |
      ▼
CMS Editor
      |
      ▼
DynamoDB Draft
      |
      ▼
Publish Action
      |
      ▼
Generate JSON
      |
      ▼
S3 Published Content
      |
      ▼
CloudFront Cache
      |
      ▼
Public Website
```

---

# 10. Recommended AWS Services

| Function | AWS Service |
|---|---|
| Authentication | Cognito |
| API | API Gateway |
| Business logic | Lambda |
| CMS database | DynamoDB |
| Published files | S3 |
| CDN | CloudFront |
| Images | S3 |
| Hosting React SPA | S3 + CloudFront |

---

# 11. Design Principles

1. DynamoDB is the management database.
2. S3 is the public delivery layer.
3. Public users never access DynamoDB directly.
4. Tenant identification is server-controlled.
5. React components control responsive behaviour.
6. Content is configuration-driven.
7. Components are reusable across tenants.

---

# 12. Future Extensions

The architecture supports:

- Custom domains.
- Tenant branding.
- Multiple languages.
- A/B testing.
- SEO metadata.
- Analytics per tenant.
- Version history.
- Approval workflows.
- Tenant-specific themes.